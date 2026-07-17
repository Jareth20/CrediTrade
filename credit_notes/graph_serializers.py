"""Serialización explícita y sanitizada para el visualizador agéntico."""

from django.urls import reverse
from django.utils import timezone

from .graph_catalog import LEGACY_NODE_ALIASES, graph_structure
from .graph_observability import sanitize_visible_value
from .models import EjecucionAgente, EventoAgente


VISUAL_STATES = {
    "pending": {"label": "Pendiente", "icon": "clock", "help": "Este nodo todavía no participó."},
    "running": {"label": "En ejecución", "icon": "activity", "help": "El nodo está procesando información."},
    "completed": {"label": "Completado", "icon": "check", "help": "El nodo terminó correctamente."},
    "waiting_human": {"label": "Revisión humana", "icon": "person", "help": "El flujo espera una decisión autorizada."},
    "failed": {"label": "Error controlado", "icon": "warning", "help": "El nodo terminó con un error controlado."},
    "skipped": {"label": "Omitido", "icon": "skip", "help": "La condición eligió otra ruta."},
    "cancelled": {"label": "Cancelado", "icon": "stop", "help": "Una decisión detuvo esta ruta."},
    "unavailable": {"label": "Servicio no disponible", "icon": "offline", "help": "Un servicio externo no respondió; los datos siguen guardados."},
}

EVENT_STATE_MAP = {
    EventoAgente.Estado.INICIADO: "running",
    EventoAgente.Estado.COMPLETADO: "completed",
    EventoAgente.Estado.ESPERANDO_HUMANO: "waiting_human",
    EventoAgente.Estado.ERROR: "failed",
    EventoAgente.Estado.REANUDADO: "completed",
    EventoAgente.Estado.CANCELADO: "cancelled",
    EventoAgente.Estado.NO_DISPONIBLE: "unavailable",
}


def _iso(value):
    return value.isoformat() if value else None


def _duration_ms(execution):
    end = execution.finalizada_en or (
        timezone.now()
        if execution.estado == EjecucionAgente.Estado.EJECUTANDO
        else execution.actualizada_en
    )
    return max(0, round((end - execution.iniciada_en).total_seconds() * 1000))


def serialize_event(event, technical=False):
    node_id = LEGACY_NODE_ALIASES.get(event.agente, event.agente)
    payload = {
        "id": event.pk,
        "order": event.orden,
        "node_id": node_id,
        "status": EVENT_STATE_MAP.get(event.estado, "unavailable"),
        "status_label": event.get_estado_display(),
        "summary": sanitize_visible_value(event.resumen),
        "started_at": _iso(event.iniciada_en or event.creado_en),
        "finished_at": _iso(event.finalizada_en),
        "duration_ms": event.duracion_ms,
        "attempt": event.intento,
        "retries": event.reintentos,
        "transition": sanitize_visible_value(event.transicion),
        "input": sanitize_visible_value(event.entrada),
        "output": sanitize_visible_value(event.salida),
        "changes": sanitize_visible_value(event.cambios),
        "sources": sanitize_visible_value(event.fuentes),
        "controlled_error": sanitize_visible_value(event.error_controlado),
    }
    if technical:
        payload["technical"] = {
            "event_state": event.estado,
            "metadata": sanitize_visible_value(event.metadatos),
        }
    return payload


def serialize_execution_summary(execution):
    return {
        "id": str(execution.pk),
        "thread_id": str(execution.pk),
        "note_id": str(execution.nota_id),
        "note_number": execution.nota.numero_titulo,
        "operator": execution.operador.get_full_name() or execution.operador.username,
        "status": execution.estado,
        "status_label": execution.get_estado_display(),
        "stage": execution.etapa,
        "pending_node": execution.nodo_pendiente,
        "started_at": _iso(execution.iniciada_en),
        "updated_at": _iso(execution.actualizada_en),
        "finished_at": _iso(execution.finalizada_en),
        "duration_ms": _duration_ms(execution),
        "detail_url": reverse("agent_flow_execution_api", args=[execution.pk]),
    }


def serialize_execution(execution, technical=False):
    structure = graph_structure()
    events = list(execution.eventos.all().order_by("orden", "creado_en"))
    serialized_events = [serialize_event(event, technical=technical) for event in events]
    latest_by_node = {}
    for event in serialized_events:
        latest_by_node[event["node_id"]] = event

    terminal = execution.estado != EjecucionAgente.Estado.EJECUTANDO
    nodes = []
    for node in structure["nodes"]:
        latest = latest_by_node.get(node["id"])
        if node["id"] == "__start__":
            status = "completed" if events else "running"
        elif node["id"] == "__end__":
            status = "completed" if execution.estado == EjecucionAgente.Estado.COMPLETADA else "pending"
        elif latest:
            status = latest["status"]
        else:
            status = "skipped" if terminal else "pending"
        nodes.append({**node, "status": status, "status_meta": VISUAL_STATES[status], "latest_event": latest})

    taken_pairs = set()
    completed_nodes = {
        event["node_id"] for event in serialized_events if event["status"] in {"completed", "waiting_human", "unavailable"}
    }
    for edge in structure["edges"]:
        if edge["source"] in completed_nodes and edge["target"] in completed_nodes:
            taken_pairs.add((edge["source"], edge["target"]))
    supervisor_event = latest_by_node.get("supervisor")
    if supervisor_event and supervisor_event.get("transition"):
        route_target = {
            "documental": "documental",
            "negociacion": "negociacion",
            "fin": "__end__",
        }.get(supervisor_event["transition"])
        if route_target:
            taken_pairs.add(("supervisor", route_target))
    edges = [
        {**edge, "taken": (edge["source"], edge["target"]) in taken_pairs}
        for edge in structure["edges"]
    ]

    return {
        "execution": serialize_execution_summary(execution),
        "states": VISUAL_STATES,
        "nodes": nodes,
        "edges": edges,
        "events": serialized_events,
        "poll": execution.estado == EjecucionAgente.Estado.EJECUTANDO,
        "technical_allowed": technical,
    }
