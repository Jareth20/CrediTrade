"""Puerta única y medible para Gemini generativo y embeddings."""

import hashlib
import json
import logging
import random
import re
import time
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone
from pydantic import ValidationError

from .models import OperacionIdempotente

logger = logging.getLogger(__name__)


class GeminiServiceError(RuntimeError):
    user_message = (
        "El servicio de análisis no está disponible en este momento. "
        "La información permanece guardada."
    )


class GeminiRateLimitError(GeminiServiceError):
    user_message = (
        "Gemini está recibiendo demasiadas solicitudes en este momento. "
        "Espera unos segundos antes de intentarlo nuevamente."
    )


class GeminiQuotaExceededError(GeminiServiceError):
    user_message = (
        "El servicio de IA alcanzó temporalmente su límite de uso. "
        "Las funciones principales de CrediTrade continúan disponibles."
    )


class GeminiTimeoutError(GeminiServiceError):
    user_message = (
        "El análisis tardó más de lo esperado. La información permanece guardada. "
        "Puedes intentarlo nuevamente."
    )


class GeminiUnavailableError(GeminiServiceError):
    user_message = (
        "El servicio de análisis no está disponible en este momento. "
        "Inténtalo nuevamente más tarde."
    )


class GeminiInvalidResponseError(GeminiServiceError):
    user_message = (
        "El servicio respondió con un formato inesperado. "
        "La información permanece guardada y puedes reintentar."
    )


class GeminiAuthorizationError(GeminiServiceError):
    user_message = (
        "El titular no ha autorizado el procesamiento de sus datos con IA. "
        "Puedes continuar usando las funciones no asistidas."
    )


@dataclass(frozen=True)
class GeminiProfile:
    name: str
    model: str
    thinking_level: str
    max_output_tokens: int


@dataclass(frozen=True)
class ClassifiedError:
    exception_type: type[GeminiServiceError]
    retryable: bool
    retry_delay: float | None = None


def get_profile(name="fast"):
    if name == "deep":
        return GeminiProfile(
            "deep",
            settings.GEMINI_DEEP_MODEL,
            settings.GEMINI_DEEP_THINKING_LEVEL,
            settings.GEMINI_MAX_OUTPUT_TOKENS,
        )
    return GeminiProfile(
        "fast",
        settings.GEMINI_FAST_MODEL,
        settings.GEMINI_FAST_THINKING_LEVEL,
        min(settings.GEMINI_MAX_OUTPUT_TOKENS, 512),
    )


def _extract_retry_delay(detail):
    patterns = (
        r"retry in\s+([0-9]+(?:\.[0-9]+)?)s",
        r"retrydelay[^0-9]*([0-9]+(?:\.[0-9]+)?)s",
        r"retry_delay[^0-9]*([0-9]+(?:\.[0-9]+)?)",
    )
    for pattern in patterns:
        match = re.search(pattern, detail, re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def classify_error(exc):
    detail = str(exc).lower()
    code = str(
        getattr(exc, "status_code", "")
        or getattr(exc, "code", "")
        or getattr(getattr(exc, "response", None), "status_code", "")
    )
    is_429 = code == "429" or "429" in detail or "resource_exhausted" in detail or "too_many_requests" in detail
    retry_delay = _extract_retry_delay(detail)
    # Google incluye frases genéricas sobre plan y free tier tanto en límites
    # transitorios como en cuotas agotadas. Sólo consideramos "dura" una cuota
    # cuando el mensaje identifica explícitamente billing, límite cero o cuota
    # diaria; un RetryInfo de segundos debe conservarse como 429 transitorio.
    hard_markers = (
        "billing not enabled",
        "quota daily",
        "requests per day",
        "requests_per_day",
        "limit: 0",
        "quota has been exhausted",
    )
    if is_429 and any(marker in detail for marker in hard_markers):
        return ClassifiedError(GeminiQuotaExceededError, False)
    if is_429:
        return ClassifiedError(GeminiRateLimitError, True, retry_delay)
    if isinstance(exc, TimeoutError) or any(marker in detail for marker in ("timeout", "timed out", "deadline_exceeded", "504")):
        return ClassifiedError(GeminiTimeoutError, True)
    if code in {"408", "500", "502", "503"} or any(
        marker in detail for marker in (" 408", " 500", " 502", " 503", "unavailable", "service unavailable")
    ):
        return ClassifiedError(GeminiUnavailableError, True)
    return ClassifiedError(GeminiUnavailableError, False)


@lru_cache(maxsize=4)
def _get_gemini_client(api_key, timeout_ms):
    from google import genai
    from google.genai import types

    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=timeout_ms,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )


def _require_configuration(model):
    if not settings.GEMINI_API_KEY:
        raise GeminiUnavailableError("GEMINI_API_KEY no configurada")
    if not model:
        raise GeminiUnavailableError("Modelo Gemini no configurado")


def _client_or_error(operation, model):
    try:
        return _get_gemini_client(settings.GEMINI_API_KEY, settings.GEMINI_TIMEOUT_MS)
    except Exception as exc:
        classified = classify_error(exc)
        if classified.exception_type is GeminiQuotaExceededError:
            _activate_cooldown(operation, model)
        logger.exception(
            "gemini_client_error operation=%s model=%s error_type=%s",
            operation,
            model,
            classified.exception_type.__name__,
        )
        raise classified.exception_type("No fue posible inicializar Gemini") from exc


def _fingerprint(operation, model, profile, payload, version):
    compact = json.dumps(
        {
            "operation": operation,
            "model": model,
            "profile": profile,
            "version": version,
            "payload": payload,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def _cooldown_key(operation, model):
    # v2 evita reutilizar cooldowns creados por el clasificador anterior, que
    # confundía algunos límites transitorios de free tier con cuota agotada.
    return f"gemini-cooldown:v2:{operation}:{model}"


def _assert_no_cooldown(operation, model):
    if OperacionIdempotente.objects.filter(
        clave=_cooldown_key(operation, model), expira_en__gt=timezone.now()
    ).exists():
        logger.info(
            "gemini_call operation=%s model=%s status=cooldown cache=blocked",
            operation,
            model,
        )
        raise GeminiQuotaExceededError("Cooldown de cuota activo")


def _activate_cooldown(operation, model):
    expiry = timezone.now() + timedelta(seconds=settings.GEMINI_QUOTA_COOLDOWN_SECONDS)
    OperacionIdempotente.objects.update_or_create(
        clave=_cooldown_key(operation, model),
        defaults={
            "tipo": "GEMINI_COOLDOWN",
            "completada_en": timezone.now(),
            "expira_en": expiry,
            "error_tipo": "CUOTA_AGOTADA",
            "resultado": {"operation": operation, "model": model},
        },
    )


def _cache_get(key, schema_model=None):
    record = OperacionIdempotente.objects.filter(
        clave=key,
        completada_en__isnull=False,
        expira_en__gt=timezone.now(),
    ).first()
    if not record or not record.resultado:
        return None
    try:
        return schema_model.model_validate(record.resultado) if schema_model else record.resultado
    except ValidationError:
        logger.warning("gemini_cache_invalid key=%s", key[-16:])
        record.delete()
        return None


def _cache_set(key, operation, result, attempts, ttl_seconds):
    payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
    OperacionIdempotente.objects.update_or_create(
        clave=key,
        defaults={
            "tipo": f"GEMINI_CACHE_{operation}"[:80],
            "completada_en": timezone.now(),
            "expira_en": timezone.now() + timedelta(seconds=ttl_seconds),
            "resultado": payload,
            "intentos": attempts,
            "error_tipo": "",
        },
    )


def _retry_delay(classified, retry_index):
    requested = classified.retry_delay
    if requested is not None:
        return requested
    base = settings.GEMINI_RETRY_BASE_SECONDS * (2**retry_index)
    return base + random.uniform(0, min(base * 0.25, 0.5))


def _execute(call, *, operation, model, profile, prompt_chars, note_id=None, fragments=0):
    _assert_no_cooldown(operation, model)
    started = time.monotonic()
    attempts = 0
    retries = 0
    status = "error"
    error_type = ""
    try:
        for retry_index in range(settings.GEMINI_MAX_RETRIES + 1):
            attempts += 1
            try:
                result = call()
                status = "success"
                return result, attempts
            except Exception as exc:
                classified = classify_error(exc)
                error_type = classified.exception_type.__name__
                if classified.exception_type is GeminiQuotaExceededError:
                    logger.exception(
                        "gemini_provider_error operation=%s model=%s error_type=%s provider_detail=%s",
                        operation,
                        model,
                        error_type,
                        str(exc)[:1200],
                    )
                    _activate_cooldown(operation, model)
                    raise GeminiQuotaExceededError("Cuota Gemini agotada") from exc
                if not classified.retryable or retry_index >= settings.GEMINI_MAX_RETRIES:
                    logger.exception(
                        "gemini_provider_error operation=%s model=%s error_type=%s provider_detail=%s",
                        operation,
                        model,
                        error_type,
                        str(exc)[:1200],
                    )
                    raise classified.exception_type("Fallo controlado de Gemini") from exc
                delay = _retry_delay(classified, retry_index)
                if delay > settings.GEMINI_MAX_RETRY_WAIT_SECONDS:
                    logger.warning(
                        "gemini_retry_skipped operation=%s model=%s delay_seconds=%.2f provider_detail=%s",
                        operation,
                        model,
                        delay,
                        str(exc)[:1200],
                    )
                    raise classified.exception_type("Espera solicitada demasiado larga") from exc
                retries += 1
                logger.warning(
                    "gemini_retry operation=%s model=%s retry=%s delay_seconds=%.2f error=%s",
                    operation,
                    model,
                    retries,
                    delay,
                    error_type,
                )
                time.sleep(delay)
    finally:
        duration_ms = round((time.monotonic() - started) * 1000)
        logger.info(
            "gemini_call operation=%s model=%s profile=%s duration_ms=%s attempts=%s retries=%s status=%s error_type=%s cache=miss prompt_chars=%s fragments=%s note_id=%s",
            operation,
            model,
            profile,
            duration_ms,
            attempts,
            retries,
            status,
            error_type,
            prompt_chars,
            fragments,
            note_id or "-",
        )


def call_structured(
    prompt,
    schema_model,
    *,
    operation="generic",
    profile="fast",
    prompt_version="v1",
    force_refresh=False,
    note_id=None,
    fragments=0,
):
    selected = get_profile(profile)
    _require_configuration(selected.model)
    fingerprint = _fingerprint(operation, selected.model, selected.name, prompt, prompt_version)
    cache_key = f"gemini-cache:{fingerprint}"
    if not force_refresh:
        cached = _cache_get(cache_key, schema_model)
        if cached is not None:
            logger.info(
                "gemini_call operation=%s model=%s profile=%s status=success cache=hit prompt_chars=%s fragments=%s note_id=%s",
                operation,
                selected.model,
                selected.name,
                len(prompt),
                fragments,
                note_id or "-",
            )
            return cached

    client = _client_or_error(operation, selected.model)
    generation_config = {"max_output_tokens": selected.max_output_tokens}
    if selected.thinking_level:
        generation_config["thinking_level"] = selected.thinking_level

    def request():
        return client.interactions.create(
            model=selected.model,
            input=prompt,
            generation_config=generation_config,
            store=False,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": schema_model.model_json_schema(),
            },
        )

    interaction, attempts = _execute(
        request,
        operation=operation,
        model=selected.model,
        profile=selected.name,
        prompt_chars=len(prompt),
        note_id=note_id,
        fragments=fragments,
    )
    usage = getattr(interaction, "usage", None)
    logger.info(
        "gemini_usage operation=%s model=%s input_tokens=%s output_tokens=%s total_tokens=%s",
        operation,
        selected.model,
        getattr(usage, "input_tokens", None)
        or getattr(usage, "prompt_token_count", None)
        or "-",
        getattr(usage, "output_tokens", None)
        or getattr(usage, "candidates_token_count", None)
        or "-",
        getattr(usage, "total_tokens", None)
        or getattr(usage, "total_token_count", None)
        or "-",
    )
    output_text = getattr(interaction, "output_text", None)
    if not output_text:
        raise GeminiInvalidResponseError("Gemini respondió sin contenido")
    cleaned = re.sub(
        r"^```(?:json)?\s*|\s*```$", "", output_text.strip(), flags=re.IGNORECASE
    ).strip()
    try:
        result = schema_model.model_validate_json(cleaned)
    except ValidationError as exc:
        logger.exception(
            "gemini_invalid_response operation=%s model=%s response=omitted",
            operation,
            selected.model,
        )
        raise GeminiInvalidResponseError("Respuesta estructurada inválida") from exc
    _cache_set(cache_key, operation, result, attempts, settings.GEMINI_CACHE_SECONDS)
    return result


def embed_texts(texts, *, task_type, operation, note_id=None):
    if not texts:
        return []
    model = settings.GEMINI_EMBEDDING_MODEL
    _require_configuration(model)
    fingerprint = _fingerprint(operation, model, task_type, texts, "embedding-v2")
    cache_key = f"gemini-cache:{fingerprint}"
    cached = _cache_get(cache_key)
    if cached and len(cached.get("vectors", [])) == len(texts):
        logger.info(
            "gemini_call operation=%s model=%s profile=embedding status=success cache=hit prompt_chars=%s fragments=%s note_id=%s",
            operation,
            model,
            sum(len(text) for text in texts),
            len(texts),
            note_id or "-",
        )
        return cached["vectors"]

    from google.genai import types

    client = _client_or_error(operation, model)

    def request():
        return client.models.embed_content(
            model=model,
            contents=texts,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=settings.RAG_EMBEDDING_DIMENSIONS,
            ),
        )

    response, attempts = _execute(
        request,
        operation=operation,
        model=model,
        profile="embedding",
        prompt_chars=sum(len(text) for text in texts),
        note_id=note_id,
        fragments=len(texts),
    )
    vectors = [list(item.values) for item in getattr(response, "embeddings", [])]
    if len(vectors) != len(texts):
        raise GeminiInvalidResponseError("Embeddings incompletos")
    _cache_set(
        cache_key,
        operation,
        {"vectors": vectors},
        attempts,
        settings.GEMINI_CACHE_SECONDS,
    )
    return vectors


def user_message(exc):
    return getattr(exc, "user_message", GeminiServiceError.user_message)
