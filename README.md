# CrediTrade

CrediTrade es un MVP web para registrar, validar, negociar y confirmar notas de crédito tributarias en Ecuador. Centraliza cada caso en un expediente único y distribuye el trabajo entre recepción, validación y negociación.

La inteligencia artificial apoya al operador con sugerencias, explicaciones y borradores. No aprueba expedientes ni ejecuta liquidaciones, transferencias o endosos.

**Aplicación:** [creditrade.vercel.app](https://creditrade.vercel.app/)

## Qué permite hacer

- Registrar clientes y notas de crédito.
- Adjuntar referencias de documentos de respaldo.
- Consultar antecedentes y detectar posibles duplicados.
- Generar y revisar sugerencias de Gemini.
- Validar existencia, saldo, estado, bloqueos, faltantes y riesgos.
- Preparar una negociación dentro de límites confirmados.
- Generar reportes y enlaces de confirmación.
- Conservar trazabilidad del operador, la fecha y la decisión.

## Flujo de trabajo

```mermaid
flowchart LR
    A[Recepción] --> B[Expediente y documentos]
    B --> C[Sugerencias de IA]
    C --> D[Revisión humana]
    D --> E[Validación por reglas]
    E --> F{Decisión del contador}
    F -->|Corrección| A
    F -->|Aprobación| G[Negociación]
    G --> H[Confirmaciones]
    H --> I[Solicitud de cierre]
```

### Operador 1: recepción

Busca o registra al cliente, crea el expediente, agrega documentos y revisa cada sugerencia de IA antes de aplicarla.

### Operador 2: validación

Ejecuta reglas deterministas, revisa inconsistencias y decide si el caso vuelve a corrección o pasa a negociación. La explicación de Gemini es informativa.

### Operador 3: negociación

Selecciona al comprador, define valores y fechas, prepara el borrador y gestiona las confirmaciones necesarias para solicitar el cierre.

## Arquitectura

| Capa | Tecnología y responsabilidad |
|---|---|
| Interfaz | Django Templates, HTML, CSS y JavaScript |
| Aplicación | Django 5 y control de acceso por roles |
| Reglas | Validaciones deterministas del expediente |
| IA | Google Gemini con respuestas validadas por Pydantic |
| Datos | PostgreSQL en Neon |
| Reportes | ReportLab |
| Despliegue | Vercel conectado a GitHub |

Componentes principales:

```text
accounts/       usuarios, autenticación y roles
credit_notes/   dominio, formularios, reglas, IA, reportes y vistas
creditrade/     configuración central de Django
templates/      interfaz renderizada en el servidor
static/         estilos, imágenes y JavaScript
```

La aplicación usa una conexión PostgreSQL agrupada (`DATABASE_URL`) para el tráfico normal y una conexión directa (`DATABASE_URL_UNPOOLED`) para migraciones.

## Instalación local

### Requisitos

- Python 3.12 o superior.
- Git.
- Una base PostgreSQL, preferiblemente Neon.
- Una API key de Gemini para probar las funciones de IA.

### 1. Preparar el proyecto

```powershell
git clone https://github.com/Jareth20/CrediTrade.git
cd CrediTrade
py -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### 2. Crear la configuración privada

Crea un archivo `.env` junto a `manage.py`. No copies credenciales al README, a archivos de ejemplo, a capturas ni a Git.

Variables mínimas:

```dotenv
DJANGO_SECRET_KEY=<clave-privada>
DJANGO_DEBUG=True
DATABASE_URL=<conexion-postgresql-pooled>
DATABASE_URL_UNPOOLED=<conexion-postgresql-directa>
DJANGO_USE_UNPOOLED=False
GEMINI_API_KEY=<clave-privada>
GEMINI_MODEL=<modelo-disponible-para-tu-proyecto>
PUBLIC_BASE_URL=http://127.0.0.1:8000
```

Variables opcionales frecuentes:

```dotenv
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
GEMINI_TIMEOUT_MS=60000
DB_CONN_MAX_AGE=60
DEMO_LOGIN_PREFILL=True
DEMO_ADMIN_PASSWORD=<clave-local>
DEMO_OPERATOR_PASSWORD=<clave-local>
```

### 3. Aplicar migraciones y cargar datos demostrativos

Usa la conexión directa únicamente durante estos comandos:

```powershell
$env:DJANGO_USE_UNPOOLED="True"
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py seed_demo
$env:DJANGO_USE_UNPOOLED="False"
```

El comando `seed_demo` crea usuarios demostrativos. Configura contraseñas propias mediante `DEMO_ADMIN_PASSWORD` y `DEMO_OPERATOR_PASSWORD`; no uses valores demostrativos en producción.

### 4. Iniciar la aplicación

```powershell
.\venv\Scripts\python.exe manage.py runserver
```

Abre [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

## Verificación y pruebas

Comprobar Django y PostgreSQL:

```powershell
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py verificar_integraciones
```

La comprobación de Gemini realiza una solicitud real y consume cuota:

```powershell
.\venv\Scripts\python.exe manage.py verificar_integraciones --gemini
```

Ejecutar las pruebas aisladas con SQLite:

```powershell
$env:DATABASE_URL="sqlite:///test.sqlite3"
$env:DJANGO_ALLOW_NON_POSTGRES_FOR_TESTS="True"
$env:DJANGO_SECRET_KEY="clave-solo-para-pruebas"
.\venv\Scripts\python.exe manage.py test
```

## Despliegue en Vercel

1. Importa el repositorio desde GitHub.
2. Usa como raíz la carpeta que contiene `manage.py`.
3. Configura las variables privadas en **Project → Settings → Environment Variables**.
4. Usa `DATABASE_URL` pooled y mantén `DJANGO_USE_UNPOOLED=False` en Vercel.
5. Ejecuta las migraciones desde una máquina controlada con `DATABASE_URL_UNPOOLED`; no las ejecutes automáticamente en cada build.
6. Despliega la rama deseada y revisa los Function Logs ante errores.

Configuración mínima de producción:

```dotenv
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=.vercel.app
CSRF_TRUSTED_ORIGINS=https://*.vercel.app
DJANGO_USE_UNPOOLED=False
PUBLIC_BASE_URL=https://<proyecto>.vercel.app
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=3600
```

También debes configurar de forma privada `DJANGO_SECRET_KEY`, `DATABASE_URL`, `DATABASE_URL_UNPOOLED`, `GEMINI_API_KEY` y `GEMINI_MODEL`.

## Seguridad

- `.env`, sus variantes y los archivos de ejemplo locales están ignorados por Git.
- También se ignoran llaves, certificados privados, credenciales JSON, volcados de base de datos y logs.
- No uses `git add -f` para publicar un archivo ignorado.
- No publiques capturas o reportes que contengan datos reales.
- Rota cualquier credencial que haya sido expuesta en un chat, log o commit.
- Cambia las contraseñas demostrativas antes de publicar el sistema.
- Las sugerencias de IA siempre requieren revisión humana.

El `.gitignore` evita nuevas inclusiones accidentales, pero no elimina secretos que ya formen parte del historial. Si una credencial fue versionada, debes rotarla y limpiar el historial por separado.

## Limitaciones del MVP

- Las fuentes SRI y DECEVALE son simuladas o cargadas manualmente.
- No se ejecutan liquidaciones, transferencias, endosos ni firmas electrónicas.
- Los archivos reales requieren almacenamiento externo como Vercel Blob, S3 o equivalente.
- Para alto volumen se necesitan colas, procesamiento en segundo plano, paginación y monitoreo de cuotas.

## Autores

- Cristina Villacís — Ingeniería en Ciencias de la Computación.
- Jareth Rojas — Ingeniería en Ciencia de Datos e IA.
- Alejandro Verdesoto — Ingeniería en Ciencia de Datos e IA.

Proyecto desarrollado para el Track 4 del Hackathon de Agentic Scale.
