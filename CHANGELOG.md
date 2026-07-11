# Cambios de esta versión

- Proyecto y marca renombrados a **CrediTrade**.
- Paquete Django renombrado de `taxai_connect` a `creditrade`.
- PostgreSQL/Neon obligatorio, sin fallback automático a SQLite.
- Selección entre URL pooled y directa mediante `DJANGO_USE_UNPOOLED`.
- Operadores con múltiples roles acumulables.
- Migración de compatibilidad para convertir el rol único anterior a los nuevos permisos.
- Usuario demo `operador_total` con los tres roles.
- Gemini obligatorio para sugerencias, explicaciones y reportes.
- Eliminadas las plantillas y sugerencias locales de respaldo.
- Salidas de Gemini estructuradas y validadas con Pydantic.
- Manejo explícito de errores de Gemini en las vistas.
- Comando `verificar_integraciones` para comprobar PostgreSQL y Gemini.
- Scripts CMD para configurar, migrar, iniciar y probar integraciones.
- Documentación actualizada para Neon y Vercel.
- Seis pruebas automatizadas para flujo, roles múltiples y ausencia de fallback.

- Archivo `.env` privado agregado por solicitud del propietario y protegido mediante `.gitignore`.
- Scripts `configurar_vercel.cmd` y `configurar_vercel.ps1` para copiar variables privadas a Vercel sin versionarlas.
- Guías de inicio y despliegue actualizadas para el flujo GitHub → Vercel.
