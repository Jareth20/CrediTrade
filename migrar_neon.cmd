@echo off
setlocal
cd /d "%~dp0"
call venv\Scripts\activate || goto :error

set DJANGO_USE_UNPOOLED=True
py manage.py check --database default || goto :error
py manage.py migrate || goto :error
py manage.py seed_demo || goto :error
set DJANGO_USE_UNPOOLED=False

echo.
echo Migraciones y datos demo completados en Neon.
echo Ejecuta iniciar_local.cmd para abrir CrediTrade.
exit /b 0

:error
set DJANGO_USE_UNPOOLED=False
echo.
echo No se pudo migrar. Revisa DATABASE_URL_UNPOOLED en .env.
exit /b 1
