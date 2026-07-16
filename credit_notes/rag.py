import hashlib
import logging
import math
import re

from django.conf import settings
from django.db import connection, transaction
from pgvector.django import CosineDistance

from .models import DocumentoRespaldo, FragmentoDocumento

logger = logging.getLogger(__name__)


class RAGServiceError(RuntimeError):
    """Fallo controlado de indexacion o recuperacion semantica."""


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


def generar_embeddings(textos):
    if not textos:
        return []
    if not settings.GEMINI_API_KEY:
        raise RAGServiceError("El servicio de evidencia semantica no esta disponible.")
    try:
        from google import genai
        from google.genai import types

        cliente = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=settings.GEMINI_TIMEOUT_MS),
        )
        respuesta = cliente.models.embed_content(
            model=settings.GEMINI_EMBEDDING_MODEL,
            contents=textos,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT" if len(textos) > 1 else "RETRIEVAL_QUERY",
                output_dimensionality=settings.RAG_EMBEDDING_DIMENSIONS,
            ),
        )
        vectores = [list(item.values) for item in respuesta.embeddings]
        if len(vectores) != len(textos):
            raise RAGServiceError("No se pudieron representar todos los fragmentos.")
        return vectores
    except RAGServiceError:
        raise
    except Exception as exc:
        logger.exception("Fallo de embeddings Gemini")
        raise RAGServiceError(
            "No fue posible preparar la evidencia semantica en este momento."
        ) from exc


@transaction.atomic
def indexar_documento(documento):
    textos = fragmentar_texto(documento.texto_extraido)
    if not textos:
        return []
    hashes = [hashlib.sha256(texto.encode("utf-8")).hexdigest() for texto in textos]
    existentes = set(
        documento.fragmentos.filter(texto_hash__in=hashes).values_list(
            "texto_hash", flat=True
        )
    )
    pendientes = [(i, texto, hashes[i]) for i, texto in enumerate(textos) if hashes[i] not in existentes]
    if not pendientes:
        return list(documento.fragmentos.all())
    vectores = generar_embeddings([item[1] for item in pendientes])
    creados = []
    for (indice, texto, texto_hash), vector in zip(pendientes, vectores):
        creados.append(
            FragmentoDocumento.objects.create(
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
    return creados


def _coseno(a, b):
    producto = sum(x * y for x, y in zip(a, b))
    norma = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return producto / norma if norma else 0.0


def buscar_fragmentos(query, nota, limite=None):
    query = limpiar_texto(query)
    if not query:
        return []
    limite = limite or settings.RAG_TOP_K
    vector = generar_embeddings([query])[0]
    base = FragmentoDocumento.objects.filter(
        cliente=nota.cliente_vendedor
    ).select_related("documento", "nota", "cliente")
    if connection.vendor == "postgresql":
        candidatos = list(
            base.annotate(distancia=CosineDistance("embedding", vector))
            .order_by("distancia")[:limite]
        )
        return [
            {
                "fragmento_id": str(item.pk),
                "documento": item.documento.nombre,
                "nota": item.nota.numero_titulo,
                "cliente": item.cliente.nombre_razon_social,
                "tipo_documento": item.tipo_documento,
                "fuente": item.fuente,
                "seccion": item.seccion,
                "fecha": item.documento.cargado_en.isoformat(),
                "texto": item.texto,
                "relevancia": round(max(0.0, 1.0 - float(item.distancia)), 4),
            }
            for item in candidatos
        ]
    # Solo para pruebas aisladas en un backend no PostgreSQL.
    candidatos = sorted(
        ((item, _coseno(vector, list(item.embedding))) for item in base),
        key=lambda par: par[1],
        reverse=True,
    )[:limite]
    return [
        {
            "fragmento_id": str(item.pk),
            "documento": item.documento.nombre,
            "nota": item.nota.numero_titulo,
            "cliente": item.cliente.nombre_razon_social,
            "tipo_documento": item.tipo_documento,
            "fuente": item.fuente,
            "seccion": item.seccion,
            "fecha": item.documento.cargado_en.isoformat(),
            "texto": item.texto,
            "relevancia": round(score, 4),
        }
        for item, score in candidatos
    ]


def preparar_evidencia(nota):
    documentos = DocumentoRespaldo.objects.filter(
        nota__cliente_vendedor=nota.cliente_vendedor
    ).select_related("nota", "nota__cliente_vendedor")
    for documento in documentos:
        if documento.texto_extraido:
            indexar_documento(documento)
    consulta = (
        f"titulo {nota.numero_titulo}; RUC {nota.cliente_vendedor.ruc_identificacion}; "
        f"tipo {nota.get_tipo_nota_display()}; origen {nota.get_origen_tributario_display()}"
    )
    resultados = buscar_fragmentos(consulta, nota)
    if not resultados:
        return {
            "conclusion": "No existe evidencia semantica suficiente para emitir una conclusion.",
            "evidencia": [],
            "fuentes": [],
            "confianza": 0.0,
            "advertencias": ["El operador debe revisar o cargar documentos con texto extraible."],
            "siguiente_accion": "Agregar evidencia y ejecutar un nuevo analisis.",
        }
    confianza = sum(item["relevancia"] for item in resultados) / len(resultados)
    return {
        "conclusion": "Se recuperaron antecedentes internos relacionados; requieren revision humana.",
        "evidencia": resultados,
        "fuentes": [
            {key: item[key] for key in ("documento", "nota", "fuente", "fecha", "seccion")}
            for item in resultados
        ],
        "confianza": round(confianza, 2),
        "advertencias": ["La similitud semantica no confirma autenticidad ni validez tributaria."],
        "siguiente_accion": "Contrastar los fragmentos con los documentos fuente.",
    }
