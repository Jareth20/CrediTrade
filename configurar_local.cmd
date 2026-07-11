@echo off
setlocal
cd /d "%~dp0"

if not exist venv (
  echo Creando entorno virtual...
  py -m venv venv || goto :error
)

call venv\Scripts\activate || goto :error
py -m pip install --upgrade pip || goto :error
pip install -r requirements.txt || goto :error

if not exist .env (
  copy .env.example .env >nul
  echo.
  echo Se creo un .env de ejemplo. Completa sus credenciales antes de continuar.
  notepad .env
) else (
  echo .env privado detectado; no fue sobrescrito.
)

echo.
echo Configuracion local terminada.
echo Siguiente paso: ejecuta migrar_neon.cmd
exit /b 0

:error
echo.
echo Ocurrio un error durante la configuracion.
exit /b 1
