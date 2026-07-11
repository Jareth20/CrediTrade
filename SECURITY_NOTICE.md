# Aviso de seguridad

Este paquete incluye un `.env` privado porque el propietario solicitó que las credenciales proporcionadas quedaran configuradas para uso local.

- `.env` está cubierto por `.gitignore` y no debe forzarse con `git add -f`.
- `.env.example` no contiene secretos y sí puede subirse a GitHub.
- Vercel debe recibir las variables desde su panel o mediante `configurar_vercel.cmd`; no desde el repositorio.
- No publiques capturas, logs ni archivos ZIP que contengan `.env`.
- Cambia las contraseñas de los usuarios demo antes de una demostración pública.
- Como las credenciales fueron compartidas previamente fuera de un gestor de secretos, se recomienda rotarlas antes de un despliegue definitivo.
