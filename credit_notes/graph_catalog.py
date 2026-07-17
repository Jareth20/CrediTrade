"""Catálogo operativo compartido por LangGraph y su visualizador."""

from functools import lru_cache


GRAPH_NODE_SPECS = {
    "__start__": {
        "label": "Inicio",
        "purpose": "Inicia una ejecución con los datos permitidos del expediente.",
        "owner": "CrediTrade",
        "question": "¿Con qué información comienza el análisis?",
        "inputs": ["Expediente", "operador", "etapa actual"],
        "outputs": ["Estado inicial de la ejecución"],
    },
    "supervisor": {
        "label": "Supervisor del flujo",
        "purpose": "Selecciona la ruta real según la etapa y la decisión humana previa.",
        "owner": "Orquestador",
        "question": "¿Qué ruta debe seguir el expediente?",
        "inputs": ["Estado del expediente", "decisiones humanas"],
        "outputs": ["Ruta documental, negociación o finalización"],
    },
    "documental": {
        "label": "Revisión documental",
        "purpose": "Inventaría respaldos y detecta datos obligatorios pendientes.",
        "owner": "Agente documental",
        "question": "¿Están disponibles los datos y documentos necesarios?",
        "inputs": ["Nota de crédito", "documentos"],
        "outputs": ["Documentos resumidos", "campos faltantes"],
    },
    "rag": {
        "label": "Buscar evidencia",
        "purpose": "Recupera fragmentos internos relacionados mediante búsqueda semántica.",
        "owner": "Agente RAG",
        "question": "¿Qué evidencia interna respalda el expediente?",
        "inputs": ["Documentos", "datos identificadores"],
        "outputs": ["Fragmentos relevantes", "fuentes", "advertencias"],
    },
    "validacion": {
        "label": "Validación y riesgos",
        "purpose": "Aplica reglas para detectar faltantes, duplicados, bloqueos y diferencias.",
        "owner": "Agente de validación",
        "question": "¿Qué hallazgos requieren revisión del operador?",
        "inputs": ["Datos de la nota", "evidencia recuperada"],
        "outputs": ["Hallazgos", "riesgos", "acciones recomendadas"],
    },
    "negociacion": {
        "label": "Escenarios de negociación",
        "purpose": "Calcula escenarios no vinculantes dentro de los límites registrados.",
        "owner": "Agente de negociación",
        "question": "¿Qué valores puede revisar el vendedor?",
        "inputs": ["Saldo disponible", "mínimo a recibir"],
        "outputs": ["Escenario conservador, equilibrado y límite"],
    },
    "explicacion": {
        "label": "Explicación operativa",
        "purpose": "Resume resultados y señala la decisión humana necesaria.",
        "owner": "Agente de explicación",
        "question": "¿Qué encontró el flujo y qué necesita del operador?",
        "inputs": ["Hallazgos", "evidencias", "escenarios"],
        "outputs": ["Resumen operativo", "decisión requerida"],
    },
    "checkpoint_humano": {
        "label": "Revisión humana",
        "purpose": "Detiene el flujo antes de avanzar y conserva responsable y criterio.",
        "owner": "Operador autorizado",
        "question": "¿El operador acepta, edita, rechaza o solicita otro análisis?",
        "inputs": ["Resumen", "evidencias", "hallazgos"],
        "outputs": ["Decisión humana trazable"],
        "human_checkpoint": True,
    },
    "__end__": {
        "label": "Fin",
        "purpose": "Finaliza la ruta actual sin ejecutar acciones financieras.",
        "owner": "CrediTrade",
        "question": "¿Terminó la ruta seleccionada?",
        "inputs": ["Estado final de la ruta"],
        "outputs": ["Ejecución detenida o completada"],
    },
}


LEGACY_NODE_ALIASES = {
    "ingreso_documental": "documental",
    "antecedentes_rag": "rag",
    "validacion_riesgos": "validacion",
}


def runtime_node_ids():
    return [
        node_id
        for node_id in GRAPH_NODE_SPECS
        if node_id not in {"__start__", "__end__"}
    ]


@lru_cache(maxsize=1)
def graph_structure():
    """Extrae nodos y aristas desde el grafo compilado real."""
    from .agents import GRAFO_CREDITRADE

    drawable = GRAFO_CREDITRADE.get_graph()
    nodes = []
    for node_id in drawable.nodes:
        spec = GRAPH_NODE_SPECS.get(node_id, {})
        nodes.append(
            {
                "id": node_id,
                "technical_name": node_id,
                "label": spec.get("label", node_id.replace("_", " ").title()),
                "purpose": spec.get("purpose", "Nodo registrado en LangGraph."),
                "owner": spec.get("owner", "CrediTrade"),
                "question": spec.get("question", "¿Qué resultado produce este paso?"),
                "inputs": spec.get("inputs", []),
                "outputs": spec.get("outputs", []),
                "human_checkpoint": bool(spec.get("human_checkpoint")),
            }
        )
    edges = [
        {
            "source": edge.source,
            "target": edge.target,
            "conditional": bool(edge.conditional),
            "condition": str(edge.data or "") if edge.conditional else "",
        }
        for edge in drawable.edges
    ]
    return {"nodes": nodes, "edges": edges, "entry": "__start__", "end": "__end__"}
