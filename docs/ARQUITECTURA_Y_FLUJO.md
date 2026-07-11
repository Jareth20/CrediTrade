# Arquitectura y flujo de CrediTrade

## Componentes

1. **Autenticación:** `accounts.Operador`, basado en `AbstractUser`.
2. **Roles múltiples:** tres booleanos permiten acumular recepción, validación y negociación.
3. **Dominio:** clientes, notas de crédito, documentos, validaciones, órdenes, reportes, aprobaciones y trazabilidad.
4. **IA:** `credit_notes/ai_services.py`, respuestas estructuradas de Gemini validadas con Pydantic y sin fallback local.
5. **Base de datos:** PostgreSQL en Neon con URL pooled para la aplicación y directa para migraciones.
6. **Presentación:** plantillas Django, Bootstrap por CDN y CSS local ligero.
7. **Despliegue:** Django WSGI en Vercel; archivos estáticos recopilados en `STATIC_ROOT`.

## Flujo

### Operador 1

Registra o busca al cliente, crea el expediente, añade documentos y solicita sugerencias a Gemini. Cada sugerencia se acepta o rechaza por separado.

### Operador 2

Ejecuta la validación contra la fuente simulada, revisa faltantes, inconsistencias, duplicados y riesgos. Gemini explica el resultado de reglas, pero no decide la aprobación.

### Operador 3

Prepara la orden, selecciona al comprador, define valores y solicita a Gemini un borrador de negociación. El sistema genera PDF y enlaces de confirmación.

## Controles

- No se modifican datos automáticamente por una sugerencia.
- La IA no ejecuta acciones reguladas.
- Los errores de Gemini son visibles y no disparan contenido inventado.
- Cada cambio relevante queda asociado a operador, fecha y expediente.
