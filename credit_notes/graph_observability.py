"""Instrumentación segura y reutilizable para los nodos de LangGraph."""

import logging
import time
from contextvars import ContextVar
from functools import wraps

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .graph_catalog import GRAPH_NODE_SPECS
from .models import EjecucionAgente, EventoAgente

logger = logging.getLogger(__name__)

_summary_context = ContextVar("agent_node_summary", default=None)
_BANNED_PARTS = (
    "key", "secret", "token", "password", "authorization", "cookie",
    "database_url", "prompt", "raw_response", "api_key", "connection",
)
_IGNORED_DIFF_FIELDS = {"fecha_inicio", "fecha_actualizacion", "nodos_ejecutados"}
_TEXT_LIMIT = 500
_LIST_LIMIT = 12


def visualizer_enabled():
    return bool(getattr(settings, "LANGGRAPH_VISUALIZER_ENABLED", False))


def _safe_text(value, limit=_TEXT_LIMIT):
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _forbidden(name):
    lowered = str(name).lower()
    return any(part in lowered for part in _BANNED_PARTS)


def _sanitize_value(value, depth=0):
    if depth > 4:
        return "[resumen omitido]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, dict):
        return {
            str(key): _sanitize_value(item, depth + 1)
            for key, item in list(value.items())[:_LIST_LIMIT]
            if not _forbidden(key)
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(item, depth + 1) for item in value[:_LIST_LIMIT]]
    return _safe_text(value)


def sanitize_visible_value(value):
    """Sanitiza nuevamente datos persistidos antes de exponerlos por API."""
    return _sanitize_value(value)


def sanitize_graph_state(state):
    """Lista blanca operativa; nunca devuelve el estado completo sin filtrar."""
    state = state or {}
    visible = {
        "nota_id": state.get("nota_id"),
        "etapa_actual": state.get("etapa_actual"),
        "ruta": state.get("ruta"),
        "nodo_pendiente": state.get("nodo_pendiente"),
        "datos_nota": state.get("datos_nota", {}),
        "cantidad_documentos": len(state.get("documentos", [])),
        "cantidad_fragmentos": len(state.get("fragmentos_recuperados", [])),
        "cantidad_antecedentes": len(state.get("antecedentes", [])),
        "documentos": state.get("documentos", []),
        "fragmentos": state.get("fragmentos_recuperados", []),
        "antecedentes": state.get("antecedentes", []),
        "sugerencias": state.get("sugerencias", []),
        "hallazgos": state.get("hallazgos", []),
        "riesgos": state.get("riesgos", []),
        "acciones_recomendadas": state.get("acciones_recomendadas", []),
        "decisiones_humanas": state.get("decisiones_humanas", []),
        "errores_controlados": state.get("errores_controlados", []),
        "resultado": state.get("resultado_final", {}),
    }
    return _sanitize_value(visible)


def state_diff(before, after):
    before = before or {}
    after = after or {}
    changes = []
    for field in sorted(set(before) | set(after)):
        if field in _IGNORED_DIFF_FIELDS or before.get(field) == after.get(field):
            continue
        previous = before.get(field)
        current = after.get(field)
        if field.startswith("cantidad_"):
            description = f"{field.replace('_', ' ').capitalize()}: {previous or 0} → {current or 0}."
        elif field == "etapa_actual":
            description = f"La etapa cambió de {previous or 'inicio'} a {current or 'sin definir'}."
        elif field == "nodo_pendiente":
            description = f"El siguiente punto de revisión es {current or 'ninguno'}."
        else:
            description = f"Se actualizó {field.replace('_', ' ')}."
        changes.append(
            {
                "field": field,
                "before": _sanitize_value(previous),
                "after": _sanitize_value(current),
                "description": description,
            }
        )
    return changes[:20]


def capture_node_summary(summary, status=EventoAgente.Estado.COMPLETADO, **metadata):
    _summary_context.set(
        {
            "summary": _safe_text(summary, 300),
            "status": status,
            "metadata": _sanitize_value(metadata),
        }
    )


def _create_event(execution_id, node_id, status, summary, **fields):
    try:
        with transaction.atomic():
            EjecucionAgente.objects.select_for_update().get(pk=execution_id)
            maximum = EventoAgente.objects.filter(
                ejecucion_id=execution_id
            ).aggregate(maximum=Max("orden"))["maximum"]
            return EventoAgente.objects.create(
                ejecucion_id=execution_id,
                agente=node_id,
                estado=status,
                resumen=_safe_text(summary, 300),
                orden=(maximum or 0) + 1,
                **fields,
            )
    except Exception:
        logger.exception(
            "agent_observability_error execution=%s node=%s status=%s",
            execution_id,
            node_id,
            status,
        )
        return None


def record_execution_event(execution_id, node_id, status, summary, **fields):
    """Punto público para decisiones humanas y compatibilidad histórica."""
    safe_fields = {
        key: value
        for key, value in fields.items()
        if key in {
            "metadatos", "entrada", "salida", "cambios", "fuentes",
            "transicion", "iniciada_en", "finalizada_en", "duracion_ms",
            "intento", "reintentos", "error_controlado",
        }
    }
    for json_field in ("metadatos", "entrada", "salida", "cambios", "fuentes"):
        if json_field in safe_fields:
            safe_fields[json_field] = _sanitize_value(safe_fields[json_field])
    return _create_event(
        execution_id,
        node_id,
        status,
        summary,
        **safe_fields,
    )


def _sources_from_state(state):
    sources = []
    for item in (state or {}).get("fragmentos_recuperados", [])[:8]:
        sources.append(
            {
                key: _sanitize_value(item.get(key))
                for key in (
                    "fragmento_id", "documento", "nota", "tipo_documento",
                    "fuente", "seccion", "fecha", "texto", "relevancia",
                )
                if item.get(key) not in (None, "")
            }
        )
    return sources


def _next_transition(node_id, result):
    explicit = (result or {}).get("ruta") or (result or {}).get("nodo_pendiente")
    if explicit:
        return _safe_text(explicit, 80)
    try:
        from .graph_catalog import graph_structure

        outgoing = [
            edge for edge in graph_structure()["edges"] if edge["source"] == node_id
        ]
        if len(outgoing) == 1:
            return outgoing[0]["target"]
    except Exception:
        logger.exception("agent_transition_metadata_error node=%s", node_id)
    return ""


def instrument_node(node_id, handler):
    """Registra entrada/salida sin cambiar el resultado funcional del nodo."""
    @wraps(handler)
    def wrapped(state):
        if not visualizer_enabled():
            return handler(state)
        execution_id = state.get("ejecucion_id")
        if not execution_id:
            return handler(state)
        spec = GRAPH_NODE_SPECS.get(node_id, {})
        before = sanitize_graph_state(state)
        started_at = timezone.now()
        _summary_context.set(None)
        _create_event(
            execution_id,
            node_id,
            EventoAgente.Estado.INICIADO,
            f"Inició {spec.get('label', node_id)}.",
            entrada=before,
            iniciada_en=started_at,
        )
        started_clock = time.monotonic()
        try:
            result = handler(state)
        except Exception as exc:
            finished_at = timezone.now()
            _create_event(
                execution_id,
                node_id,
                EventoAgente.Estado.ERROR,
                f"{spec.get('label', node_id)} terminó con un error controlado.",
                entrada=before,
                finalizada_en=finished_at,
                duracion_ms=round((time.monotonic() - started_clock) * 1000),
                error_controlado=_safe_text(type(exc).__name__, 80),
            )
            raise
        after_state = {**state, **(result or {})}
        after = sanitize_graph_state(after_state)
        captured = _summary_context.get() or {}
        status = captured.get("status", EventoAgente.Estado.COMPLETADO)
        if node_id == "rag" and len(after_state.get("errores_controlados", [])) > len(state.get("errores_controlados", [])):
            status = EventoAgente.Estado.NO_DISPONIBLE
        finished_at = timezone.now()
        _create_event(
            execution_id,
            node_id,
            status,
            captured.get("summary") or f"Completó {spec.get('label', node_id)}.",
            entrada=before,
            salida=after,
            cambios=state_diff(before, after),
            fuentes=_sources_from_state(after_state),
            transicion=_next_transition(node_id, result),
            iniciada_en=started_at,
            finalizada_en=finished_at,
            duracion_ms=round((time.monotonic() - started_clock) * 1000),
        )
        return result

    return wrapped
