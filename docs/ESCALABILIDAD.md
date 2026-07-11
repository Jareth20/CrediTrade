# Escalabilidad

- Usa `DATABASE_URL` pooled en Vercel y `DATABASE_URL_UNPOOLED` solo para migraciones.
- Los índices cubren RUC, título, estados, fechas y relaciones operativas.
- Para cargas masivas, usa `bulk_create`, `COPY`, validación por lotes y paginación.
- No ejecutes cientos de solicitudes a Gemini dentro de una sola petición HTTP; incorpora una cola en una fase posterior.
- Los documentos se representan por URL y texto extraído, evitando depender del disco efímero de Vercel.
- Para archivos reales, utiliza Vercel Blob, S3, R2 o un servicio equivalente.
