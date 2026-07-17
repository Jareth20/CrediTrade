import json
import logging

from decimal import Decimal
from typing import List, Literal

from django.conf import settings
from django.db import transaction
from pydantic import BaseModel

from .gemini_service import (
    GeminiInvalidResponseError,
    GeminiQuotaExceededError,
    GeminiRateLimitError,
    GeminiServiceError,
    GeminiTimeoutError,
    GeminiUnavailableError,
    call_structured,
    classify_error,
    get_profile,
    user_message,
)
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


def _rate_limit_delay(exc):
    """Compatibilidad con pruebas y utilidades anteriores."""
    classified = classify_error(exc)
    return classified.retry_delay if classified.retryable else None


def _call_gemini(prompt, schema_model, **kwargs):
    """API compatible que delega en el servicio centralizado."""
    return call_structured(prompt, schema_model, **kwargs)


def _require_ai_authorization(nota):
    if not nota.cliente_vendedor.autorizacion_consulta:
        raise GeminiServiceError(
            "El titular no ha autorizado el procesamiento de sus datos con IA."
        )


def _serialize_note(nota):
    data = {
        "numero_titulo": nota.numero_titulo,
        "tipo_nota": nota.tipo_nota,
        "origen_tributario": nota.origen_tributario,
        "valor_nominal": str(nota.valor_nominal),
        "saldo_disponible": str(nota.saldo_disponible),
        "minimo_recibir": str(nota.minimo_recibir),
        "fecha_emision": nota.fecha_emision.isoformat() if nota.fecha_emision else None,
        "estado_fuente": nota.estado_fuente,
    }
    return {key: value for key, value in data.items() if value not in (None, "")}


def _compact_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def generar_sugerencias_nota(nota, operador):
    """Genera propuestas revisables con Gemini; nunca cambia la nota automáticamente."""
    _require_ai_authorization(nota)

    antecedentes = list(
        NotaCredito.objects.filter(cliente_vendedor=nota.cliente_vendedor)
        .exclude(pk=nota.pk)
        .order_by("-actualizado_en")[:2]
    )
    documentos = [
        {
            "tipo": documento.tipo_documento,
            "fuente": documento.fuente,
            "hash": documento.hash_sha256,
            "texto": documento.texto_extraido[:800],
        }
        for documento in nota.documentos.all()[:2]
        if documento.texto_extraido
    ]

    from pydantic import BaseModel, Field

    class SuggestedField(BaseModel):
        campo: str = Field(
            description=(
                "Nombre exacto del campo sugerido. Valores permitidos: "
                "tipo_nota, origen_tributario, valor_nominal, "
                "saldo_disponible, minimo_recibir, fecha_emision "
                "o estado_fuente."
            )
        )
        valor_sugerido: str = Field(
            min_length=1,
            description="Valor sugerido expresado como texto.",
        )
        confianza: float = Field(
            default=0.70,
            ge=0,
            le=1,
            description="Confianza entre 0 y 1.",
        )
        fuente: str = Field(
            min_length=1,
            description="Antecedente o documento utilizado.",
        )
        evidencia: str = Field(
            min_length=1,
            description="Explicación breve de la evidencia encontrada.",
        )


    class SuggestionBundle(BaseModel):
        sugerencias: list[SuggestedField] = Field(
            default_factory=list
        )

    payload = {
        "actual": _serialize_note(nota),
        "antecedentes": [_serialize_note(item) for item in antecedentes],
        "documentos": documentos,
    }
    prompt = (
        "Genera sugerencias de precarga para CrediTrade usando solo la evidencia JSON. "
        "Campos permitidos: tipo_nota, origen_tributario, valor_nominal, "
        "saldo_disponible, minimo_recibir, fecha_emision, estado_fuente. "
        "Omite campos sin evidencia; no atribuyas validaciones a SRI/DECEVALE; "
        "fuente y evidencia deben ser breves. Datos:"
        + _compact_json(payload)
    )

    bundle = _call_gemini(
        prompt,
        SuggestionBundle,
        operation="sugerencias",
        profile="fast",
        prompt_version="sugerencias-v2",
        note_id=str(nota.pk),
    )
    campos_permitidos = {
        "tipo_nota",
        "origen_tributario",
        "valor_nominal",
        "saldo_disponible",
        "minimo_recibir",
        "fecha_emision",
        "estado_fuente",
    }

    suggestions = [
        item.model_dump()
        for item in bundle.sugerencias
        if item.campo in campos_permitidos
    ]

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
                    generada_por_modelo=get_profile("fast").model,
                )
            )

        registrar_evento(
            nota,
            operador,
            "SUGERENCIAS_GENERADAS",
            f"Gemini generó {len(created)} sugerencias para revisión humana.",
            {"modelo": get_profile("fast").model, "cantidad": len(created)},
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
    prompt = (
        "Explica brevemente en español esta validación por reglas. No cambies el resultado, "
        "no inventes hechos y devuelve evidencia a revisar y una acción humana concreta. Datos:"
        + _compact_json(context)
    )
    result = _call_gemini(
        prompt,
        ValidationExplanation,
        operation="explicacion_validacion",
        profile="fast",
        prompt_version="validacion-v2",
        note_id=str(validacion.nota_id),
    )
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
            "terminos": order.terminos[:1200],
            "observaciones": order.observaciones[:800],
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
            for documento in nota.documentos.all()[:5]
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

    prompt = (
        "Redacta un borrador conciso de negociación para revisión humana. Usa solo el JSON; "
        "separa hechos, riesgos y pendientes; no inventes validaciones ni garantías; indica que "
        "liquidación, transferencia y endoso son externos y requieren aprobación. Datos:"
        + _compact_json(base_content)
    )
    result = _call_gemini(
        prompt,
        NegotiationDraft,
        operation="reporte_negociacion",
        profile="deep",
        prompt_version="reporte-v2",
        note_id=str(nota.pk),
    )
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
            modelo_ia=get_profile("deep").model,
            generado_por=operador,
        )
        registrar_evento(
            nota,
            operador,
            "REPORTE_IA_GENERADO",
            "Gemini generó un borrador de negociación para revisión del operador 3.",
            {"reporte_id": str(report.id), "modelo": get_profile("deep").model},
        )
    return report
