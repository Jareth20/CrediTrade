import hashlib
import logging
import math
import re

from django.conf import settings
from django.db import connection, transaction
from pgvector.django import CosineDistance

from .gemini_service import GeminiServiceError, embed_texts
from .models import DocumentoRespaldo, FragmentoDocumento

logger = logging.getLogger(__name__)


class RAGServiceError(RuntimeError):
    """Fallo controlado de indexación o recuperación semántica."""


def limpiar_texto(texto):
    return re.sub(r"\s+", " ", (texto or "")).strip()


def fragmentar_texto(texto, tamano=900, solapamiento=120):
    limpio = limpiar_texto(texto)
    if not limpio:
        return []
    fragmentos = []
    inicio = 0
    while inicio < len(limpio):
        fin = min(len(limpio), inicio + tamano)
        if fin < len(limpio):
            corte = limpio.rfind(" ", inicio + tamano // 2, fin)
            fin = corte if corte > inicio else fin
        fragmentos.append(limpio[inicio:fin].strip())
        if fin >= len(limpio):
            break
        inicio = max(fin - solapamiento, inicio + 1)
    return [item for item in fragmentos if item]


def generar_embeddings(textos, task_type="RETRIEVAL_DOCUMENT", note_id=None):
    try:
        operation = (
            "embedding_consulta"
            if task_type == "RETRIEVAL_QUERY"
            else "embedding_documentos"
        )
        return embed_texts(
            textos,
            task_type=task_type,
            operation=operation,
            note_id=note_id,
        )
    except GeminiServiceError as exc:
        logger.warning(
            "rag_embedding_error operation=%s error_type=%s note_id=%s",
            task_type,
            type(exc).__name__,
            note_id or "-",
        )
        raise RAGServiceError(
            "No fue posible preparar la evidencia semántica en este momento."
        ) from exc


def _pending_chunks(documento):
    textos = fragmentar_texto(documento.texto_extraido)[
        : settings.RAG_MAX_CHUNKS_PER_DOCUMENT
    ]
    if not textos:
        return []
    hashes = [hashlib.sha256(texto.encode("utf-8")).hexdigest() for texto in textos]
    existentes = set(
        documento.fragmentos.filter(texto_hash__in=hashes).values_list(
            "texto_hash", flat=True
        )
    )
    return [
        (documento, indice, texto, hashes[indice])
        for indice, texto in enumerate(textos)
        if hashes[indice] not in existentes
    ]


def indexar_documentos(documentos):
    documentos = list(documentos)
    pendientes = [
        item for documento in documentos for item in _pending_chunks(documento)
    ][: settings.RAG_MAX_EMBEDDING_BATCH]
    if not pendientes:
        return []
    note_id = str(pendientes[0][0].nota_id)
    vectores = generar_embeddings(
        [item[2] for item in pendientes],
        task_type="RETRIEVAL_DOCUMENT",
        note_id=note_id,
    )
    objetos = []
    for (documento, indice, texto, texto_hash), vector in zip(pendientes, vectores):
        objetos.append(
            FragmentoDocumento(
                documento=documento,
                nota=documento.nota,
                cliente=documento.nota.cliente_vendedor,
                indice=indice,
                seccion=f"Fragmento {indice + 1}",
                texto=texto,
                texto_hash=texto_hash,
                fuente=documento.fuente,
                tipo_documento=documento.tipo_documento,
                embedding=vector,
                modelo_embedding=settings.GEMINI_EMBEDDING_MODEL,
            )
        )
    with transaction.atomic():
        return FragmentoDocumento.objects.bulk_create(objetos, ignore_conflicts=True)


def indexar_documento(documento):
    indexar_documentos([documento])
    return list(documento.fragmentos.all())


def _coseno(a, b):
    producto = sum(x * y for x, y in zip(a, b))
    norma = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return producto / norma if norma else 0.0


def _format_candidates(pairs, limite):
    resultados = []
    hashes = set()
    total_chars = 0
    for item, score in pairs:
        if score < settings.RAG_MIN_RELEVANCE or item.texto_hash in hashes:
            continue
        remaining = settings.RAG_MAX_CONTEXT_CHARS - total_chars
        if remaining <= 0:
            break
        texto = item.texto[:remaining]
        if not texto:
            break
        hashes.add(item.texto_hash)
        total_chars += len(texto)
        resultados.append(
            {
                "fragmento_id": str(item.pk),
                "documento": item.documento.nombre,
                "nota": item.nota.numero_titulo,
                "cliente": item.cliente.nombre_razon_social,
                "tipo_documento": item.tipo_documento,
                "fuente": item.fuente,
                "seccion": item.seccion,
                "fecha": item.documento.cargado_en.isoformat(),
                "texto": texto,
                "relevancia": round(score, 4),
            }
        )
        if len(resultados) >= limite:
            break
    return resultados


def buscar_fragmentos(query, nota, limite=None):
    query = limpiar_texto(query)
    if not query:
        return []
    limite = min(limite or settings.RAG_TOP_K, settings.RAG_TOP_K)
    vector = generar_embeddings(
        [query], task_type="RETRIEVAL_QUERY", note_id=str(nota.pk)
    )[0]
    base = FragmentoDocumento.objects.filter(
        cliente=nota.cliente_vendedor
    ).select_related("documento", "nota", "cliente")
    candidate_limit = max(limite * 2, limite)
    if connection.vendor == "postgresql":
        candidatos = list(
            base.annotate(distancia=CosineDistance("embedding", vector))
            .order_by("distancia")[:candidate_limit]
        )
        pairs = [
            (item, max(0.0, 1.0 - float(item.distancia))) for item in candidatos
        ]
    else:
        pairs = sorted(
            ((item, _coseno(vector, list(item.embedding))) for item in base),
            key=lambda par: par[1],
            reverse=True,
        )[:candidate_limit]
    return _format_candidates(pairs, limite)


def preparar_evidencia(nota):
    documentos = list(
        DocumentoRespaldo.objects.filter(
            nota__cliente_vendedor=nota.cliente_vendedor
        )
        .select_related("nota", "nota__cliente_vendedor")
        .order_by("-cargado_en")[: settings.RAG_MAX_DOCUMENTS]
    )
    indexar_documentos(
        documento for documento in documentos if documento.texto_extraido
    )
    consulta = (
        f"título {nota.numero_titulo}; RUC {nota.cliente_vendedor.ruc_identificacion}; "
        f"tipo {nota.get_tipo_nota_display()}; origen {nota.get_origen_tributario_display()}"
    )
    resultados = buscar_fragmentos(consulta, nota)
    if not resultados:
        return {
            "conclusion": "No existe evidencia semántica suficiente para emitir una conclusión.",
            "evidencia": [],
            "fuentes": [],
            "confianza": 0.0,
            "advertencias": [
                "El operador debe revisar o cargar documentos con texto extraíble."
            ],
            "siguiente_accion": "Agregar evidencia y ejecutar un nuevo análisis.",
        }
    confianza = sum(item["relevancia"] for item in resultados) / len(resultados)
    return {
        "conclusion": "Se recuperaron antecedentes internos relacionados; requieren revisión humana.",
        "evidencia": resultados,
        "fuentes": [
            {
                key: item[key]
                for key in ("documento", "nota", "fuente", "fecha", "seccion")
            }
            for item in resultados
        ],
        "confianza": round(confianza, 2),
        "advertencias": [
            "La similitud semántica no confirma autenticidad ni validez tributaria."
        ],
        "siguiente_accion": "Contrastar los fragmentos con los documentos fuente.",
    }
