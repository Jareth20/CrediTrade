from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import (
    EventoTrazabilidad,
    NotaCredito,
    RegistroSimuladoTitulo,
    ValidacionNota,
)


def registrar_evento(nota, operador, accion, descripcion, metadatos=None):
    return EventoTrazabilidad.objects.create(
        nota=nota,
        operador=operador,
        accion=accion,
        descripcion=descripcion,
        metadatos=metadatos or {},
    )


def buscar_antecedentes(query):
    query = (query or "").strip()
    if not query:
        return NotaCredito.objects.none()
    return (
        NotaCredito.objects.select_related("cliente_vendedor")
        .filter(
            Q(cliente_vendedor__ruc_identificacion__icontains=query)
            | Q(numero_titulo__icontains=query)
            | Q(cliente_vendedor__nombre_razon_social__icontains=query)
        )
        .order_by("-actualizado_en")[:25]
    )


def _campos_faltantes(nota):
    campos = []
    if not nota.cliente_vendedor.autorizacion_consulta:
        campos.append("autorizacion_consulta_cliente")
    if not nota.fecha_emision:
        campos.append("fecha_emision")
    if not nota.documentos.exists():
        campos.append("documentos_respaldo")
    if nota.cliente_vendedor.estado_cuenta_sri == "PENDIENTE":
        campos.append("estado_cuenta_sri")
    return campos


def _duplicados(nota):
    duplicates = []
    same_client = NotaCredito.objects.filter(
        cliente_vendedor=nota.cliente_vendedor,
        valor_nominal=nota.valor_nominal,
        saldo_disponible=nota.saldo_disponible,
    ).exclude(pk=nota.pk)
    for candidate in same_client[:5]:
        duplicates.append(
            {
                "numero_titulo": candidate.numero_titulo,
                "fecha": candidate.creado_en.date().isoformat(),
                "estado": candidate.get_estado_flujo_display(),
                "razon": "Coinciden titular, valor nominal y saldo.",
            }
        )
    return duplicates


def ejecutar_validacion_simulada(nota, operador):
    """Valida contra una tabla local que representa una fuente SRI/DECEVALE simulada."""
    registro = RegistroSimuladoTitulo.objects.filter(
        numero_titulo__iexact=nota.numero_titulo
    ).first()
    inconsistencias = []
    riesgos = []
    faltantes = _campos_faltantes(nota)
    duplicates = _duplicados(nota)

    if registro:
        if registro.titular_ruc != nota.cliente_vendedor.ruc_identificacion:
            inconsistencias.append(
                {
                    "campo": "titular_ruc",
                    "registrado": nota.cliente_vendedor.ruc_identificacion,
                    "fuente": registro.titular_ruc,
                    "evidencia": "Registro simulado del título.",
                }
            )
        if registro.tipo_nota != nota.tipo_nota:
            inconsistencias.append(
                {
                    "campo": "tipo_nota",
                    "registrado": nota.get_tipo_nota_display(),
                    "fuente": registro.get_tipo_nota_display(),
                    "evidencia": "Registro simulado del título.",
                }
            )
        if abs(registro.valor_nominal - nota.valor_nominal) > Decimal("0.01"):
            inconsistencias.append(
                {
                    "campo": "valor_nominal",
                    "registrado": str(nota.valor_nominal),
                    "fuente": str(registro.valor_nominal),
                    "evidencia": "Registro simulado del título.",
                }
            )
        if abs(registro.saldo - nota.saldo_disponible) > Decimal("0.01"):
            inconsistencias.append(
                {
                    "campo": "saldo_disponible",
                    "registrado": str(nota.saldo_disponible),
                    "fuente": str(registro.saldo),
                    "evidencia": "Registro simulado del título.",
                }
            )
        if registro.bloqueada:
            riesgos.append(
                {
                    "tipo": "BLOQUEO",
                    "detalle": registro.motivo_bloqueo or "Título bloqueado en fuente simulada.",
                    "severidad": "ALTA",
                }
            )
    else:
        riesgos.append(
            {
                "tipo": "NO_EXISTE",
                "detalle": "El número de título no consta en la fuente simulada.",
                "severidad": "ALTA",
            }
        )

    if duplicates:
        riesgos.append(
            {
                "tipo": "POSIBLE_DUPLICADO",
                "detalle": f"Se encontraron {len(duplicates)} casos con datos similares.",
                "severidad": "MEDIA",
            }
        )

    if not registro:
        resultado = ValidacionNota.Resultado.NO_CONFORME
        next_action = "Solicitar evidencia del título o revisar el número ingresado."
    elif registro.bloqueada or inconsistencias:
        resultado = ValidacionNota.Resultado.NO_CONFORME
        next_action = "Solicitar corrección y revisar la evidencia indicada."
    elif faltantes or duplicates:
        resultado = ValidacionNota.Resultado.OBSERVADA
        next_action = "Completar pendientes y confirmar coincidencias antes de aprobar."
    else:
        resultado = ValidacionNota.Resultado.CONFORME
        next_action = "Aprobar para preparar la orden de negociación."

    validation = ValidacionNota.objects.create(
        nota=nota,
        fuente=ValidacionNota.Fuente.SIMULADA,
        existe=bool(registro),
        saldo_fuente=registro.saldo if registro else None,
        estado_fuente=registro.estado if registro else "NO ENCONTRADO",
        bloqueada=registro.bloqueada if registro else False,
        motivo_bloqueo=registro.motivo_bloqueo if registro else "",
        campos_faltantes=faltantes,
        inconsistencias=inconsistencias,
        duplicados=duplicates,
        coincidencias_riesgo=riesgos,
        siguiente_accion=next_action,
        resultado=resultado,
        realizada_por=operador,
    )
    registrar_evento(
        nota,
        operador,
        "VALIDACION_EJECUTADA",
        f"Validación simulada completada con resultado {validation.get_resultado_display()}.",
        {
            "fuente": validation.fuente,
            "resultado": validation.resultado,
            "faltantes": len(faltantes),
            "inconsistencias": len(inconsistencias),
            "riesgos": len(riesgos),
        },
    )
    return validation


@transaction.atomic
def enviar_a_validacion(nota, operador):
    if nota.estado_flujo not in {
        NotaCredito.EstadoFlujo.BORRADOR,
        NotaCredito.EstadoFlujo.CORRECCION_REQUERIDA,
    }:
        raise ValueError("El caso no está en un estado que permita enviarlo a validación.")
    if not nota.documentos.exists():
        raise ValueError("Debe adjuntar al menos un documento de respaldo.")
    nota.estado_flujo = NotaCredito.EstadoFlujo.PENDIENTE_VALIDACION
    nota.enviado_validacion_en = timezone.now()
    nota.save(update_fields=["estado_flujo", "enviado_validacion_en", "actualizado_en"])
    registrar_evento(
        nota,
        operador,
        "ENVIADO_VALIDACION",
        "El recepcionista envió el caso al contador.",
    )
    return nota
