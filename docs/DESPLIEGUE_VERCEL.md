# Despliegue de CrediTrade en Vercel

## 1. Preparar Neon

El `.env` privado incluido contiene:

- `DATABASE_URL`: conexión pooled, con `-pooler` en el host.
- `DATABASE_URL_UNPOOLED`: conexión directa, sin `-pooler`.

Ejecuta las migraciones desde tu computadora:

```cmd
configurar_local.cmd
migrar_neon.cmd
```

No ejecutes migraciones automáticamente en cada build de Vercel.

## 2. Subir a GitHub

Desde la carpeta donde está `manage.py`:

```cmd
git init
git add .
git status
git commit -m "CrediTrade MVP"
git branch -M main
git remote add origin URL_DEL_REPOSITORIO
git push -u origin main
```

`git status` no debe mostrar `.env`. El archivo está excluido por `.gitignore`.

## 3. Configurar Vercel automáticamente

Instala Node.js LTS y ejecuta:

```cmd
configurar_vercel.cmd
```

El script:

1. Vincula la carpeta con un proyecto de Vercel.
2. Lee las credenciales desde `.env`.
3. Crea o actualiza las variables de `production` y `preview`.
4. No escribe secretos en archivos versionados ni en los argumentos del comando.

Después puedes desplegar:

```cmd
npx vercel --prod
```

## 4. Configuración manual alternativa

En `Project > Settings > Environment Variables`, agrega:

```env
DJANGO_SECRET_KEY=EL_MISMO_VALOR_PRIVADO_DEL_ENV
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=.vercel.app
CSRF_TRUSTED_ORIGINS=https://*.vercel.app
DATABASE_URL=CONEXION_POOLED_NEON
DATABASE_URL_UNPOOLED=CONEXION_DIRECTA_NEON
DJANGO_USE_UNPOOLED=False
GEMINI_API_KEY=CLAVE_GEMINI
GEMINI_MODEL=gemini-3.5-flash
GEMINI_TIMEOUT_MS=60000
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=3600
SECURE_HSTS_INCLUDE_SUBDOMAINS=False
SECURE_HSTS_PRELOAD=False
```

No habilites `DJANGO_USE_UNPOOLED=True` en Vercel.

## 5. Importar desde GitHub

Importa el repositorio en Vercel. La raíz del proyecto debe ser la carpeta donde se encuentran `manage.py`, `requirements.txt` y `creditrade/wsgi.py`. Los pushes posteriores a la rama conectada generarán nuevos despliegues.

## 6. Dominio final

Tras el primer despliegue, agrega o actualiza:

```env
PUBLIC_BASE_URL=https://nombre-real.vercel.app
```

Con dominio personalizado:

```env
DJANGO_ALLOWED_HOSTS=.vercel.app,creditrade.tudominio.com
CSRF_TRUSTED_ORIGINS=https://*.vercel.app,https://creditrade.tudominio.com
PUBLIC_BASE_URL=https://creditrade.tudominio.com
```

## 7. Diagnóstico

Localmente:

```cmd
probar_integraciones.cmd
venv\Scripts\activate
py manage.py check --deploy
```

En Vercel revisa los Function Logs si Gemini o PostgreSQL devuelven errores.
