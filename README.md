# CrediTrade — MVP Django

CrediTrade es un MVP para agilizar el ingreso, validación, negociación y cierre asistido de notas de crédito tributarias en una casa de valores de Ecuador.

## Funcionalidades principales

- Login con usuario personalizado `Operador`.
- Un mismo usuario puede tener uno, dos o los tres roles:
  - Operador 1: recepción y precarga.
  - Operador 2: validación y cumplimiento.
  - Operador 3: negociación y reportes.
- Clientes registrados como compradores, vendedores o ambos.
- Expediente único de nota de crédito, documentos, responsables, observaciones y trazabilidad.
- PostgreSQL obligatorio mediante Neon; no existe fallback automático a SQLite.
- Gemini obligatorio para sugerencias, explicación de validaciones y reportes; no existe contenido alternativo local.
- Sugerencias revisables: el operador debe aceptar o rechazar cada dato antes de aplicarlo.
- Reporte PDF de negociación.
- Flujo regulado representado como solicitud o aprobación; el MVP no ejecuta liquidación, transferencia ni endoso.
- Bootstrap por CDN y diseño de neumorfismo discreto.
- Preparado para despliegue en Vercel.

## Configuración privada incluida

El paquete incluye un archivo `.env` listo para la ejecución local con las credenciales proporcionadas por el propietario del proyecto. Ese archivo está excluido por `.gitignore`, por lo que `git add .` no lo incorpora al repositorio. `.env.example` permanece como plantilla pública sin secretos.

Vercel no recibe el `.env` ignorado desde GitHub. Usa `configurar_vercel.cmd` para vincular el proyecto y copiar las variables privadas a los entornos `production` y `preview`, o configúralas manualmente en el panel de Vercel.

## Inicio rápido en Windows

1. Ejecuta `configurar_local.cmd`.
2. Ejecuta `migrar_neon.cmd` para crear las tablas y los usuarios demo en Neon.
3. Ejecuta `probar_integraciones.cmd` para verificar PostgreSQL y Gemini.
4. Ejecuta `iniciar_local.cmd`.
5. Abre `http://127.0.0.1:8000/`.

Comandos equivalentes:

```cmd
py -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
rem El archivo .env privado ya está incluido y permanece ignorado por Git.
set "DJANGO_USE_UNPOOLED=True"
py manage.py migrate
py manage.py seed_demo
set "DJANGO_USE_UNPOOLED=False"
py manage.py runserver
```

## Variables obligatorias

```env
DJANGO_SECRET_KEY=una-clave-larga
DATABASE_URL=conexion-pooled-de-neon
DATABASE_URL_UNPOOLED=conexion-directa-de-neon
GEMINI_API_KEY=clave-de-gemini
GEMINI_MODEL=gemini-3.5-flash
```

La URL pooled contiene `-pooler` en el host y se usa para la aplicación. La URL directa se usa para migraciones con `DJANGO_USE_UNPOOLED=True`.

## Usuarios demo

Después de ejecutar `seed_demo`:

| Usuario | Contraseña inicial | Roles |
|---|---|---|
| `recepcionista` | `OperadorDemo123!` | Operador 1 |
| `contador` | `OperadorDemo123!` | Operador 2 |
| `vendedor` | `OperadorDemo123!` | Operador 3 |
| `operador_total` | `OperadorDemo123!` | Operadores 1, 2 y 3 |
| `admin` | `AdminDemo123!` | Superusuario |

Cambia estas contraseñas antes de una demostración pública.

## Gemini sin fallback

`credit_notes/ai_services.py` usa `google-genai` con respuestas JSON estructuradas y Pydantic. Si la clave, modelo, cuota o respuesta son inválidos:

- no se inventan sugerencias;
- no se crea un reporte local;
- las sugerencias anteriores no se eliminan;
- el operador recibe un error controlado;
- la validación por reglas puede quedar registrada, pero la explicación de IA permanece ausente.

Prueba ambas integraciones con:

```cmd
py manage.py verificar_integraciones --gemini
```

## Operador con varios roles

El modelo `accounts.Operador` tiene los campos:

```text
puede_recepcionar
puede_validar
puede_negociar
```

Desde `/admin/` pueden activarse simultáneamente. Los permisos de las vistas se comprueban con `user.tiene_rol(1, 2, 3)`.

## Despliegue en Vercel

1. Sube la carpeta que contiene `manage.py` a GitHub; `.env` quedará fuera del commit.
2. Importa el repositorio en Vercel o ejecuta `configurar_vercel.cmd`.
3. Ejecuta las migraciones desde tu computadora usando `migrar_neon.cmd`.
4. Despliega y luego actualiza `PUBLIC_BASE_URL` con el dominio final.

No ejecutes migraciones automáticamente en cada build.

## Pruebas

Las pruebas usan una base SQLite únicamente cuando se habilita explícitamente la variable de pruebas; la aplicación normal nunca cae automáticamente a SQLite.

```cmd
set "DATABASE_URL=sqlite:///test.sqlite3"
set "DJANGO_ALLOW_NON_POSTGRES_FOR_TESTS=True"
set "DJANGO_SECRET_KEY=test-secret-key"
py manage.py test
```

## Estructura

```text
accounts/          autenticación y roles múltiples
credit_notes/      modelos, vistas, servicios, Gemini y PDF
creditrade/        configuración Django
static/            CSS y JavaScript ligeros
templates/         interfaz Bootstrap
docs/              arquitectura y despliegue
```
