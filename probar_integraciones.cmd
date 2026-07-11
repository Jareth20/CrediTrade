@echo off
setlocal
cd /d "%~dp0"
call venv\Scripts\activate || goto :error
set DJANGO_USE_UNPOOLED=False
py manage.py verificar_integraciones --gemini
exit /b %errorlevel%

:error
echo No se pudo activar el entorno virtual.
exit /b 1
