import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, TypedDict

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from langgraph.graph import END, StateGraph

from .models import (
    EjecucionAgente,
    EventoAgente,
    MemoriaAgente,
    NotaCredito,
)
from .rag import RAGServiceError, preparar_evidencia
from .services import _campos_faltantes, _duplicados, registrar_evento

logger = logging.getLogger(__name__)


class EstadoCrediTrade(TypedDict, total=False):
    ejecucion_id: str
    nota_id: str
    operador_id: int
    roles_habilitados: list[str]
    etapa_actual: str
    ruta: str
    datos_nota: dict[str, Any]
    documentos: list[dict[str, Any]]
    fragmentos_recuperados: list[dict[str, Any]]
    antecedentes: list[dict[str, Any]]
    sugerencias: list[dict[str, Any]]
    hallazgos: list[dict[str, Any]]
    riesgos: list[dict[str, Any]]
    acciones_recomendadas: list[str]
    decisiones_humanas: list[dict[str, Any]]
    errores_controlados: list[str]
    fecha_inicio: str
    fecha_actualizacion: str
    nodos_ejecutados: list[str]
    nodo_pendiente: str
    resultado_final: dict[str, Any]


def _json(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _evento(state, agente, resumen, estado=EventoAgente.Estado.COMPLETADO, **meta):
    EventoAgente.objects.create(
        ejecucion_id=state["ejecucion_id"],
        agente=agente,
        estado=estado,
        resumen=resumen,
        metadatos=meta,
    )


def _nodo(state, nombre):
    return {
        "etapa_actual": nombre,
        "fecha_actualizacion": timezone.now().isoformat(),
        "nodos_ejecutados": [*state.get("nodos_ejecutados", []), nombre],
    }


def supervisor(state: EstadoCrediTrade):
    note = NotaCredito.objects.get(pk=state["nota_id"])
    decision = (state.get("decisiones_humanas") or [{}])[-1].get("decision")
    if decision == "CONTINUAR" and note.estado_flujo in {
        NotaCredito.EstadoFlujo.VALIDADA,
        NotaCredito.EstadoFlujo.EN_NEGOCIACION,
    }:
        ruta = "negociacion"
    elif decision in {"RECHAZAR", "EDITAR"}:
        ruta = "fin"
    else:
        ruta = "documental"
    _evento(state, "supervisor", f"Etapa detectada: {note.get_estado_flujo_display()}.", ruta=ruta)
    return {**_nodo(state, "supervisor"), "ruta": ruta}


def agente_documental(state: EstadoCrediTrade):
    note = NotaCredito.objects.select_related("cliente_vendedor").prefetch_related("documentos").get(pk=state["nota_id"])
    documentos = [
        {
            "id": str(doc.pk),
            "nombre": doc.nombre,
            "tipo": doc.get_tipo_documento_display(),
            "fuente": doc.fuente,
            "hash": doc.hash_sha256,
            "tiene_texto": bool(doc.texto_extraido),
        }
        for doc in note.documentos.all()
    ]
    faltantes = _campos_faltantes(note)
    sugerencias = [
        {"campo": campo, "conclusion": "Completar antes de continuar", "confianza": 1.0, "fuente": "Reglas del expediente"}
        for campo in faltantes
    ]
    documento_texto = "documento" if len(documentos) == 1 else "documentos"
    faltante_texto = "faltante" if len(faltantes) == 1 else "faltantes"
    _evento(state, "ingreso_documental", f"{len(documentos)} {documento_texto} y {len(faltantes)} {faltante_texto} revisados.")
    return {**_nodo(state, "ingreso_documental"), "documentos": documentos, "sugerencias": sugerencias}


def agente_rag(state: EstadoCrediTrade):
    note = NotaCredito.objects.select_related("cliente_vendedor").get(pk=state["nota_id"])
    try:
        respuesta = preparar_evidencia(note)
    except RAGServiceError:
        respuesta = None
        logger.exception(
            "RAG no disponible para ejecucion %s; el servicio central controla los reintentos",
            state["ejecucion_id"],
        )
    if respuesta is not None:
        fragmentos = respuesta["evidencia"]
        errores = state.get("errores_controlados", [])
    else:
        fragmentos = []
        errores = [*state.get("errores_controlados", []), "La evidencia semantica no estuvo disponible; los datos permanecen guardados."]
        respuesta = {"conclusion": "No fue posible recuperar evidencia semantica en este momento.", "evidencia": [], "fuentes": [], "confianza": 0, "advertencias": ["Reintente el analisis."], "siguiente_accion": "Reintentar sin modificar el expediente."}
    _evento(state, "antecedentes_rag", respuesta["conclusion"], fuentes=len(respuesta["fuentes"]))
    return {
        **_nodo(state, "antecedentes_rag"),
        "fragmentos_recuperados": fragmentos,
        "antecedentes": respuesta["fuentes"],
        "errores_controlados": errores,
        "resultado_final": {"rag": respuesta},
    }


def agente_validacion(state: EstadoCrediTrade):
    note = NotaCredito.objects.select_related("cliente_vendedor").get(pk=state["nota_id"])
    hallazgos = []
    for campo in _campos_faltantes(note):
        hallazgos.append({"severidad": "alto", "tipo": "faltante", "detalle": campo, "por_que_importa": "Impide verificar el expediente de forma completa."})
    for duplicado in _duplicados(note):
        hallazgos.append({"severidad": "medio", "tipo": "posible_duplicado", "detalle": duplicado, "por_que_importa": "Puede representar un ingreso repetido."})
    if note.bloqueada:
        hallazgos.append({"severidad": "critico", "tipo": "bloqueo", "detalle": note.motivo_bloqueo or "Titulo bloqueado", "por_que_importa": "No debe avanzar sin revision humana."})
    if note.saldo_disponible < note.valor_nominal:
        hallazgos.append({"severidad": "informativo", "tipo": "saldo", "detalle": f"Diferencia: {note.valor_nominal - note.saldo_disponible}", "por_que_importa": "Delimita el valor efectivamente negociable."})
    _evento(state, "validacion_riesgos", f"{len(hallazgos)} hallazgos clasificados.")
    return {**_nodo(state, "validacion_riesgos"), "hallazgos": hallazgos, "riesgos": [h for h in hallazgos if h["severidad"] in {"critico", "alto"}], "acciones_recomendadas": ["Revisar evidencia y decidir como operador responsable."]}


def agente_negociacion(state: EstadoCrediTrade):
    note = NotaCredito.objects.get(pk=state["nota_id"])
    saldo = note.saldo_disponible
    minimo = note.minimo_recibir
    medio = (saldo + minimo) / Decimal("2")
    escenarios = [
        {"nombre": "Conservador", "valor": str(saldo), "descuento": "0.00", "explicacion": "Prioriza el saldo disponible."},
        {"nombre": "Equilibrado", "valor": str(medio.quantize(Decimal("0.01"))), "descuento": str(((saldo - medio) / saldo * 100).quantize(Decimal("0.01"))) if saldo else "0.00", "explicacion": "Punto medio dentro de limites registrados."},
        {"nombre": "Limite", "valor": str(minimo), "descuento": str(((saldo - minimo) / saldo * 100).quantize(Decimal("0.01"))) if saldo else "0.00", "explicacion": "No baja del minimo indicado por el vendedor."},
    ]
    _evento(state, "negociacion", "Tres escenarios no vinculantes preparados.")
    return {**_nodo(state, "negociacion"), "resultado_final": {**state.get("resultado_final", {}), "escenarios_negociacion": escenarios}, "nodo_pendiente": "aprobacion_negociacion"}


def agente_explicacion(state: EstadoCrediTrade):
    resumen = {
        "conclusion": f"Se revisaron {len(state.get('documentos', []))} documentos y se identificaron {len(state.get('hallazgos', []))} hallazgos.",
        "fuentes_utilizadas": len(state.get("fragmentos_recuperados", [])),
        "decision_requerida": "Aceptar, editar, rechazar o solicitar un nuevo analisis.",
        "advertencia": "Ningun resultado cambia el estado regulado de la nota.",
    }
    _evento(state, "explicacion", "Resultado traducido a lenguaje operativo.")
    return {**_nodo(state, "explicacion"), "resultado_final": {**state.get("resultado_final", {}), "explicacion": resumen}}


def checkpoint_humano(state: EstadoCrediTrade):
    pendiente = state.get("nodo_pendiente") or "revision_operador"
    _evento(state, "supervisor", "Flujo detenido para decision humana.", pendiente=pendiente)
    return {**_nodo(state, "checkpoint_humano"), "nodo_pendiente": pendiente}


def _ruta_supervisor(state):
    return state.get("ruta", "documental")


def construir_grafo():
    grafo = StateGraph(EstadoCrediTrade)
    grafo.add_node("supervisor", supervisor)
    grafo.add_node("documental", agente_documental)
    grafo.add_node("rag", agente_rag)
    grafo.add_node("validacion", agente_validacion)
    grafo.add_node("negociacion", agente_negociacion)
    grafo.add_node("explicacion", agente_explicacion)
    grafo.add_node("checkpoint_humano", checkpoint_humano)
    grafo.set_entry_point("supervisor")
    grafo.add_conditional_edges("supervisor", _ruta_supervisor, {"documental": "documental", "negociacion": "negociacion", "fin": END})
    grafo.add_edge("documental", "rag")
    grafo.add_edge("rag", "validacion")
    grafo.add_edge("validacion", "explicacion")
    grafo.add_edge("negociacion", "explicacion")
    grafo.add_edge("explicacion", "checkpoint_humano")
    grafo.add_edge("checkpoint_humano", END)
    return grafo.compile()


GRAFO_CREDITRADE = construir_grafo()


def _roles(operador):
    return [nombre for permitido, nombre in ((operador.tiene_rol(1), "recepcion"), (operador.tiene_rol(2), "validacion"), (operador.tiene_rol(3), "negociacion")) if permitido]


def iniciar_analisis(nota, operador):
    with transaction.atomic():
        cutoff = timezone.now() - timedelta(seconds=settings.AI_OPERATION_LOCK_SECONDS)
        EjecucionAgente.objects.filter(
            nota=nota,
            operador=operador,
            estado=EjecucionAgente.Estado.EJECUTANDO,
            actualizada_en__lt=cutoff,
        ).update(
            estado=EjecucionAgente.Estado.ERROR_CONTROLADO,
            error_amigable=(
                "La ejecución anterior se interrumpió. Los datos permanecen guardados y puedes iniciar un nuevo análisis."
            ),
            finalizada_en=timezone.now(),
        )
        activa = EjecucionAgente.objects.select_for_update().filter(
            nota=nota,
            operador=operador,
            estado__in=[
                EjecucionAgente.Estado.EJECUTANDO,
                EjecucionAgente.Estado.ESPERANDO_HUMANO,
            ],
        ).first()
        if activa:
            return activa, False
        try:
            with transaction.atomic():
                ejecucion = EjecucionAgente.objects.create(
                    nota=nota, operador=operador
                )
        except IntegrityError:
            activa = EjecucionAgente.objects.filter(
                nota=nota,
                operador=operador,
                estado__in=[
                    EjecucionAgente.Estado.EJECUTANDO,
                    EjecucionAgente.Estado.ESPERANDO_HUMANO,
                ],
            ).first()
            if activa:
                return activa, False
            raise
    estado: EstadoCrediTrade = {
        "ejecucion_id": str(ejecucion.pk), "nota_id": str(nota.pk), "operador_id": operador.pk,
        "roles_habilitados": _roles(operador), "etapa_actual": "inicio",
        "datos_nota": {field: _json(getattr(nota, field)) for field in ("numero_titulo", "estado_flujo", "valor_nominal", "saldo_disponible", "minimo_recibir", "fecha_emision")},
        "documentos": [], "fragmentos_recuperados": [], "antecedentes": [], "sugerencias": [], "hallazgos": [], "riesgos": [], "acciones_recomendadas": [], "decisiones_humanas": [], "errores_controlados": [],
        "fecha_inicio": timezone.now().isoformat(), "fecha_actualizacion": timezone.now().isoformat(), "nodos_ejecutados": [], "nodo_pendiente": "", "resultado_final": {},
    }
    try:
        final = GRAFO_CREDITRADE.invoke(estado)
        ejecucion.estado = EjecucionAgente.Estado.ESPERANDO_HUMANO
        ejecucion.etapa = final.get("etapa_actual", "checkpoint_humano")
        ejecucion.nodo_pendiente = final.get("nodo_pendiente", "revision_operador")
        ejecucion.estado_compartido = final
        ejecucion.save()
        registrar_evento(nota, operador, "ANALISIS_AGENTICO_PREPARADO", "Los agentes prepararon evidencia y recomendaciones; esperan revision humana.", {"ejecucion": str(ejecucion.pk)})
    except Exception:
        logger.exception("Fallo controlado del grafo %s", ejecucion.pk)
        ejecucion.estado = EjecucionAgente.Estado.ERROR_CONTROLADO
        ejecucion.error_amigable = "No fue posible completar el analisis en este momento. La informacion registrada permanece guardada. Puedes intentar nuevamente."
        ejecucion.save()
    return ejecucion, True


@transaction.atomic
def registrar_decision(ejecucion, operador, decision, observacion=""):
    ejecucion = EjecucionAgente.objects.select_for_update().select_related("nota", "nota__cliente_vendedor").get(pk=ejecucion.pk)
    if ejecucion.operador_id != operador.pk and not operador.is_superuser:
        raise PermissionError("La ejecucion pertenece a otro operador.")
    if ejecucion.estado != EjecucionAgente.Estado.ESPERANDO_HUMANO:
        raise ValueError("La ejecucion no espera una decision.")
    registro = {"decision": decision, "observacion": observacion, "operador_id": operador.pk, "fecha": timezone.now().isoformat(), "nodo": ejecucion.nodo_pendiente}
    decisiones = [*ejecucion.decisiones_humanas, registro]
    estado = {**ejecucion.estado_compartido, "decisiones_humanas": decisiones}
    resultado = {**estado.get("resultado_final", {})}
    if resultado.get("explicacion"):
        resultado["explicacion"] = {
            **resultado["explicacion"],
            "decision_requerida": "Decision registrada; no hay una revision pendiente en esta ejecucion.",
        }
    estado["resultado_final"] = resultado
    ejecucion.estado_compartido = estado
    if decision == "NUEVO_ANALISIS":
        ejecucion.estado = EjecucionAgente.Estado.COMPLETADA
        ejecucion.finalizada_en = timezone.now()
        ejecucion.nodo_pendiente = ""
        ejecucion.etapa = "completada"
    elif decision == "CONTINUAR" and ejecucion.nota.estado_flujo in {NotaCredito.EstadoFlujo.VALIDADA, NotaCredito.EstadoFlujo.EN_NEGOCIACION}:
        final = GRAFO_CREDITRADE.invoke(estado)
        ejecucion.estado_compartido = final
        ejecucion.nodo_pendiente = final.get("nodo_pendiente", "aprobacion_negociacion")
        ejecucion.estado = EjecucionAgente.Estado.ESPERANDO_HUMANO
    else:
        ejecucion.estado = EjecucionAgente.Estado.COMPLETADA
        ejecucion.finalizada_en = timezone.now()
        ejecucion.nodo_pendiente = ""
        ejecucion.etapa = "completada"
    ejecucion.decisiones_humanas = decisiones
    ejecucion.save()
    MemoriaAgente.objects.create(operador=operador, nota=ejecucion.nota, cliente=ejecucion.nota.cliente_vendedor, ambito=MemoriaAgente.Ambito.NOTA, categoria="decision_agente", contenido=registro)
    registrar_evento(ejecucion.nota, operador, "DECISION_ANALISIS_AGENTICO", "El operador registro una decision sobre la recomendacion de agentes.", {"ejecucion": str(ejecucion.pk), "decision": decision, "observacion": observacion, "agente": "supervisor"})
    return ejecucion
