import json
import logging
from decimal import Decimal
from typing import List, Literal

from django.conf import settings
from django.db import transaction

from .models import NotaCredito, ReporteIA, SugerenciaIA
from .services import registrar_evento

logger = logging.getLogger(__name__)

ALLOWED_SUGGESTION_FIELDS = {
    "tipo_nota",
    "origen_tributario",
    "valor_nominal",
    "saldo_disponible",
    "minimo_recibir",
    "fecha_emision",
    "estado_fuente",
}


class GeminiServiceError(RuntimeError):
    """Error controlado al consultar o validar una respuesta de Gemini."""


def _call_gemini(prompt, schema_model):
    """
    Consulta Gemini mediante Interactions API y valida la salida
    estructurada con Pydantic. No utiliza fallback local.
    """
    if not settings.GEMINI_API_KEY:
        raise GeminiServiceError(
            "GEMINI_API_KEY no está configurada."
        )

    if not settings.GEMINI_MODEL:
        raise GeminiServiceError(
            "GEMINI_MODEL no está configurado."
        )

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise GeminiServiceError(
            "La dependencia google-genai no está instalada."
        ) from exc

    try:
        client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=types.HttpOptions(
                timeout=settings.GEMINI_TIMEOUT_MS
            ),
        )

        interaction = client.interactions.create(
            model=settings.GEMINI_MODEL,
            input=prompt,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": schema_model.model_json_schema(),
            },
        )

        output_text = getattr(
            interaction,
            "output_text",
            None,
        )

        if not output_text:
            raise GeminiServiceError(
                "Gemini respondió, pero no devolvió contenido."
            )

        return schema_model.model_validate_json(output_text)

    except GeminiServiceError:
        raise

    except Exception as exc:
        logger.exception(
            "Error real al consultar Gemini: %s",
            exc,
        )

        detalle = ""

        if settings.DEBUG:
            detalle = (
                f" Detalle técnico: "
                f"{type(exc).__name__}: {exc}"
            )

        raise GeminiServiceError(
            "Gemini no pudo generar una respuesta estructurada válida."
            + detalle
        ) from exc


def _require_ai_authorization(nota):
    if not nota.cliente_vendedor.autorizacion_consulta:
        raise GeminiServiceError(
            "El titular no ha autorizado el procesamiento de sus datos con IA."
        )


def _serialize_note(nota):
    return {
        "numero_titulo": nota.numero_titulo,
        "ruc_titular": nota.cliente_vendedor.ruc_identificacion,
        "tipo_nota": nota.tipo_nota,
        "origen_tributario": nota.origen_tributario,
        "valor_nominal": str(nota.valor_nominal),
        "saldo_disponible": str(nota.saldo_disponible),
        "minimo_recibir": str(nota.minimo_recibir),
        "fecha_emision": nota.fecha_emision.isoformat() if nota.fecha_emision else None,
        "estado_fuente": nota.estado_fuente,
        "estado_flujo": nota.estado_flujo,
        "creado_en": nota.creado_en.isoformat(),
    }


def generar_sugerencias_nota(nota, operador):
    """Genera propuestas revisables con Gemini; nunca cambia la nota automáticamente."""
    _require_ai_authorization(nota)

    antecedentes = list(
        NotaCredito.objects.filter(cliente_vendedor=nota.cliente_vendedor)
        .exclude(pk=nota.pk)
        .order_by("-actualizado_en")[:8]
    )
    documentos = [
        {
            "tipo": documento.tipo_documento,
            "fuente": documento.fuente,
            "texto": documento.texto_extraido[:2500],
        }
        for documento in nota.documentos.all()[:6]
        if documento.texto_extraido
    ]

    from pydantic import BaseModel, Field

    class SuggestedField(BaseModel):
        campo: Literal[
            "tipo_nota",
            "origen_tributario",
            "valor_nominal",
            "saldo_disponible",
            "minimo_recibir",
            "fecha_emision",
            "estado_fuente",
        ]
        valor_sugerido: str
        confianza: float = Field(ge=0, le=1)
        fuente: str
        evidencia: str

    class SuggestionBundle(BaseModel):
        sugerencias: List[SuggestedField]

    prompt = f"""
Eres el asistente de debida diligencia de CrediTrade, un MVP para una casa de valores en Ecuador.
Genera únicamente sugerencias de precarga sustentadas en antecedentes o documentos proporcionados.
No inventes validaciones del SRI, DECEVALE, una bolsa de valores ni terceros.
No afirmes que un título existe si la evidencia no lo demuestra.
Si no existe evidencia suficiente para un campo, omítelo.
Cada sugerencia debe identificar una fuente concreta y explicar brevemente la evidencia.
Las sugerencias serán revisadas, aceptadas o rechazadas por un operador humano.

Caso actual:
{json.dumps(_serialize_note(nota), ensure_ascii=False)}

Antecedentes del mismo RUC:
{json.dumps([_serialize_note(item) for item in antecedentes], ensure_ascii=False)}

Documentos y texto de respaldo:
{json.dumps(documentos, ensure_ascii=False)}
"""

    bundle = _call_gemini(prompt, SuggestionBundle)
    suggestions = [item.model_dump() for item in bundle.sugerencias]

    with transaction.atomic():
        # Solo se sustituyen sugerencias pendientes después de una respuesta válida de Gemini.
        SugerenciaIA.objects.filter(
            nota=nota,
            estado=SugerenciaIA.Estado.PENDIENTE,
        ).delete()

        created = []
        for suggestion in suggestions:
            campo = suggestion.get("campo")
            if campo not in ALLOWED_SUGGESTION_FIELDS:
                continue
            current = getattr(nota, campo, "")
            confidence = Decimal(str(suggestion.get("confianza", 0))).quantize(
                Decimal("0.01")
            )
            confidence = max(Decimal("0.00"), min(confidence, Decimal("1.00")))
            created.append(
                SugerenciaIA.objects.create(
                    nota=nota,
                    campo=campo,
                    valor_actual=str(current or ""),
                    valor_sugerido=str(suggestion.get("valor_sugerido", "")),
                    confianza=confidence,
                    fuente=str(suggestion.get("fuente", "Gemini"))[:160],
                    evidencia=str(suggestion.get("evidencia", "")),
                    generada_por_modelo=settings.GEMINI_MODEL,
                )
            )

        registrar_evento(
            nota,
            operador,
            "SUGERENCIAS_GENERADAS",
            f"Gemini generó {len(created)} sugerencias para revisión humana.",
            {"modelo": settings.GEMINI_MODEL, "cantidad": len(created)},
        )
    return created


def generar_explicacion_validacion(validacion):
    """Explica con Gemini el resultado de reglas; no altera el resultado calculado."""
    _require_ai_authorization(validacion.nota)

    from pydantic import BaseModel

    class ValidationExplanation(BaseModel):
        resumen: str
        evidencia_a_revisar: List[str]
        siguiente_accion: str

    context = {
        "existe": validacion.existe,
        "saldo_fuente": (
            str(validacion.saldo_fuente)
            if validacion.saldo_fuente is not None
            else None
        ),
        "estado_fuente": validacion.estado_fuente,
        "bloqueada": validacion.bloqueada,
        "faltantes": validacion.campos_faltantes,
        "inconsistencias": validacion.inconsistencias,
        "duplicados": validacion.duplicados,
        "riesgos": validacion.coincidencias_riesgo,
        "resultado_reglas": validacion.resultado,
    }
    prompt = f"""
Resume en español la validación de una nota de crédito tributaria para CrediTrade.
No modifiques el resultado calculado por reglas y no inventes hechos fuera del JSON.
Explica la evidencia que debe revisar el operador 2 y propone una siguiente acción concreta.
La decisión final siempre corresponde a una persona autorizada.

Datos:
{json.dumps(context, ensure_ascii=False)}
"""
    result = _call_gemini(prompt, ValidationExplanation)
    explanation = result.resumen.strip()
    if result.evidencia_a_revisar:
        explanation += "\n\nEvidencia a revisar:\n- " + "\n- ".join(
            result.evidencia_a_revisar
        )

    validacion.explicacion_ia = explanation
    validacion.siguiente_accion = result.siguiente_accion[:300]
    validacion.save(update_fields=["explicacion_ia", "siguiente_accion"])
    return explanation


def generar_reporte_negociacion(nota, operador):
    """Genera con Gemini el borrador del operador 3; sin plantilla alternativa."""
    _require_ai_authorization(nota)
    order = getattr(nota, "orden_negociacion", None)
    if not order:
        raise ValueError("Primero debe crear la orden de negociación.")

    base_content = {
        "expediente": {
            "numero_titulo": nota.numero_titulo,
            "estado": nota.get_estado_flujo_display(),
            "proxima_accion": nota.proxima_accion,
        },
        "vendedor": {
            "nombre": nota.cliente_vendedor.nombre_razon_social,
            "ruc": nota.cliente_vendedor.ruc_identificacion,
            "representante": nota.cliente_vendedor.representante_legal,
        },
        "comprador": {
            "nombre": order.comprador.nombre_razon_social,
            "ruc": order.comprador.ruc_identificacion,
        },
        "titulo": {
            "tipo": nota.get_tipo_nota_display(),
            "origen": nota.get_origen_tributario_display(),
            "valor_nominal": str(nota.valor_nominal),
            "saldo": str(nota.saldo_disponible),
            "minimo_recibir": str(nota.minimo_recibir),
        },
        "propuesta": {
            "valor_venta": str(order.valor_venta),
            "descuento_porcentaje": str(order.porcentaje_descuento),
            "fecha": order.fecha_propuesta.isoformat(),
            "vigencia_hasta": (
                order.vigencia_hasta.isoformat() if order.vigencia_hasta else None
            ),
            "terminos": order.terminos,
            "observaciones": order.observaciones,
        },
        "responsables": {
            "recepcionista": str(nota.recepcionista),
            "contador": str(nota.contador) if nota.contador else "Pendiente",
            "vendedor": str(nota.vendedor or operador),
        },
        "documentos": [
            {
                "nombre": documento.nombre,
                "tipo": documento.get_tipo_documento_display(),
                "fuente": documento.fuente,
            }
            for documento in nota.documentos.all()
        ],
        "aviso_regulatorio": (
            "Este documento es un borrador de negociación. La liquidación, transferencia "
            "y endoso quedan como solicitud de aprobación y no se ejecutan desde el MVP."
        ),
    }

    from pydantic import BaseModel

    class NegotiationDraft(BaseModel):
        titulo: str
        resumen_ejecutivo: str
        puntos_clave: List[str]
        riesgos_y_pendientes: List[str]
        siguiente_accion: str
        texto_carta: str

    prompt = f"""
Redacta un borrador profesional, claro y conciso de negociación para CrediTrade.
Usa exclusivamente los datos del JSON. No inventes validaciones, normas, garantías ni compradores.
Distingue hechos confirmados, riesgos y pendientes.
Indica expresamente que liquidación, transferencia y endoso requieren aprobación humana y ejecución externa.
El documento será revisado por un operador 3 antes de utilizarse.

Datos:
{json.dumps(base_content, ensure_ascii=False)}
"""
    result = _call_gemini(prompt, NegotiationDraft)
    base_content["puntos_clave"] = result.puntos_clave
    base_content["riesgos_y_pendientes"] = result.riesgos_y_pendientes
    base_content["siguiente_accion_ia"] = result.siguiente_accion
    base_content["texto_carta"] = result.texto_carta

    with transaction.atomic():
        report = ReporteIA.objects.create(
            nota=nota,
            tipo=ReporteIA.Tipo.NEGOCIACION,
            titulo=result.titulo[:200],
            resumen=result.resumen_ejecutivo,
            contenido=base_content,
            modelo_ia=settings.GEMINI_MODEL,
            generado_por=operador,
        )
        registrar_evento(
            nota,
            operador,
            "REPORTE_IA_GENERADO",
            "Gemini generó un borrador de negociación para revisión del operador 3.",
            {"reporte_id": str(report.id), "modelo": settings.GEMINI_MODEL},
        )
    return report
