# Optimización y resiliencia de Gemini

## Diagnóstico

La auditoría se realizó con `google-genai 2.11.0`. El SDK aplica por defecto hasta
cinco intentos en errores transitorios. CrediTrade añadía además un ciclo propio de
dos intentos, por lo que un clic podía producir hasta diez intentos efectivos en un
429/5xx y mantener la petición abierta durante demasiado tiempo.

También se detectó lo siguiente:

- cada operación creaba un cliente nuevo;
- sugerencias, explicaciones y reportes compartían modelo y razonamiento;
- no existía cooldown persistente para cuota dura;
- los resultados estructurados no se reutilizaban;
- RAG generaba un lote de embeddings por documento y otro para la consulta;
- el agente repetía el flujo RAG completo sobre la política del SDK;
- los prompts contenían instrucciones repetidas y más antecedentes de los necesarios.

Referencias verificadas:

- [Límites de Gemini](https://ai.google.dev/gemini-api/docs/rate-limits)
- [Solución de errores y reintentos](https://ai.google.dev/gemini-api/docs/troubleshooting)
- [Interactions API](https://ai.google.dev/api/interactions-api-v1)
- [Niveles de razonamiento](https://ai.google.dev/gemini-api/docs/thinking)

## Llamadas por acción

| Acción | Antes, respuesta normal | Antes, peor ruta transitoria | Ahora, respuesta normal | Ahora con caché | Ahora con cuota dura |
|---|---:|---:|---:|---:|---:|
| Generar sugerencias | 1 | hasta 10 intentos | 1 | 0 | 1 y cooldown |
| Validar ahora (explicación) | 1 | hasta 10 intentos | 1 | 0 | 1 y reglas conservadas |
| Reintentar explicación | 1 | hasta 10 intentos | 1 | 0 | 0 durante cooldown |
| Generar reporte | 1 | hasta 10 intentos | 1 | 0 | 1 y orden conservada |
| Análisis RAG inicial | documentos + consulta | el flujo podía repetirse | 1 lote + 1 consulta | 0 si nada cambió | se detiene sin repetir |

El número real anterior dependía de dónde fallara el SDK. La columna de peor ruta
representa el máximo teórico de la composición encontrada, no una medición de consumo
facturado.

## Política nueva

`credit_notes/gemini_service.py` es la única puerta para Interactions API y
embeddings. El cliente se reutiliza dentro del proceso caliente de Vercel y se crea
con `HttpRetryOptions(attempts=1)`, deshabilitando el backoff interno para evitar
políticas anidadas.

La aplicación realiza como máximo `GEMINI_MAX_RETRIES` reintentos propios:

- backoff exponencial con jitter;
- respeto de `retryDelay` cuando es corto;
- espera individual limitada por `GEMINI_MAX_RETRY_WAIT_SECONDS`;
- ningún reintento ante cuota dura o facturación;
- timeout, 408 y 5xx convertidos en errores de dominio.

Una cuota dura crea en PostgreSQL un registro `GEMINI_COOLDOWN` por operación y
modelo. Hasta su expiración, las solicitudes equivalentes fallan inmediatamente con
un mensaje seguro y el resto de CrediTrade continúa funcionando.

## Caché e invalidación

Se reutilizó `OperacionIdempotente`, ampliándolo con resultado JSON, expiración,
intentos y tipo de error. La huella incluye:

- operación y versión del prompt;
- perfil y modelo;
- prompt compacto o textos de embeddings;
- datos, documentos y evidencia incluidos realmente.

Un cambio de datos, documentos, prompt, modelo o perfil produce una huella distinta.
Los embeddings de documentos siguen persistidos en `FragmentoDocumento`; además se
cachea la consulta semántica para evitar llamadas idénticas.

## Perfiles y límites

- `fast`: sugerencias y explicación de validación; razonamiento `minimal`, máximo
  efectivo de 512 tokens.
- `deep`: borrador de negociación; razonamiento `low`, máximo configurable.
- `embedding`: documentos consolidados y consulta RAG.

El modelo rápido y profundo heredan `GEMINI_MODEL` si no se definen variables nuevas.
Solo se envían parámetros confirmados para Gemini 3.5 Flash e Interactions API.

## Variables nuevas

```env
GEMINI_FAST_MODEL=gemini-3.5-flash
GEMINI_DEEP_MODEL=gemini-3.5-flash
GEMINI_FAST_THINKING_LEVEL=minimal
GEMINI_DEEP_THINKING_LEVEL=low
GEMINI_MAX_OUTPUT_TOKENS=900
GEMINI_MAX_RETRIES=1
GEMINI_RETRY_BASE_SECONDS=1
GEMINI_MAX_RETRY_WAIT_SECONDS=8
GEMINI_QUOTA_COOLDOWN_SECONDS=900
GEMINI_CACHE_SECONDS=86400
AI_OPERATION_LOCK_SECONDS=300
RAG_TOP_K=4
RAG_MIN_RELEVANCE=0.20
RAG_MAX_CONTEXT_CHARS=4000
RAG_MAX_DOCUMENTS=12
RAG_MAX_CHUNKS_PER_DOCUMENT=12
RAG_MAX_EMBEDDING_BATCH=48
```

No se modificó `.env` ni se añadieron secretos.

## Observabilidad

Los logs `gemini_call`, `gemini_retry` y `gemini_usage` permiten consultar:

- operación, perfil y modelo;
- duración, intentos y reintentos;
- éxito, error y cooldown;
- cache hit/miss;
- caracteres del prompt y fragmentos RAG;
- tokens reportados por el proveedor cuando estén disponibles;
- identificador interno de nota.

Nunca se registran prompts, documentos, respuestas completas, claves o conexiones.

## Latencia esperada

- Cuota dura: pasa de reintentos/esperas acumuladas a una respuesta inmediata tras el
  primer error; durante cooldown no existe llamada externa.
- Error transitorio: máximo de dos intentos con la configuración predeterminada y
  espera máxima individual de ocho segundos.
- Cache hit: solo lectura PostgreSQL, sin latencia de Gemini.
- Éxito sin caché: depende del proveedor, pero usa prompts más cortos, salida acotada y
  razonamiento mínimo/bajo.

## Prueba manual

1. Generar sugerencias dos veces sin cambiar la nota: la segunda no debe llamar a
   Gemini ni duplicar filas.
2. Ejecutar validación: las reglas deben quedar guardadas aunque falle la explicación.
3. Reintentar explicación: no se vuelve a ejecutar la comparación por reglas.
4. Generar reporte: un error conserva la orden y permite continuar con confirmaciones.
5. Ejecutar análisis agéntico dos veces sin cambios: documentos y consulta deben usar
   los fragmentos/caché existentes.
6. Ante una cuota dura, comprobar el mensaje amigable y que las pantallas CRUD siguen
   disponibles.
