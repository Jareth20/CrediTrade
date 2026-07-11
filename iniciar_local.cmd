@echo off
setlocal
cd /d "%~dp0"
call venv\Scripts\activate || goto :error
set DJANGO_USE_UNPOOLED=False
py manage.py runserver
exit /b 0

:error
echo No se pudo iniciar. Ejecuta primero configurar_local.cmd.
exit /b 1
