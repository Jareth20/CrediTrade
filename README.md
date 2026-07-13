# CrediTrade

## Asistencia inteligente para el ingreso y negociación de notas de crédito tributarias en Ecuador

CrediTrade es un MVP web desarrollado en Django para agilizar el ingreso, revisión, validación, negociación y cierre asistido de notas de crédito tributarias dentro de una casa de valores en Ecuador.

La plataforma centraliza los expedientes, distribuye las responsabilidades entre diferentes operadores y utiliza inteligencia artificial para reutilizar antecedentes, proponer datos, explicar resultados de validación y generar borradores de negociación.

> La inteligencia artificial funciona como apoyo para el operador. Ninguna sugerencia, aprobación, liquidación, transferencia o endoso se ejecuta automáticamente.

---

## Demostración

Aplicación desplegada:

[https://creditrade.vercel.app/](https://creditrade.vercel.app/)

---

## Índice

1. [Track asignado](#1-track-asignado)
2. [Tipo de negocio](#2-tipo-de-negocio)
3. [Problema identificado](#3-problema-identificado)
4. [Solución propuesta](#4-solución-propuesta)
5. [Usuarios y roles](#5-usuarios-y-roles)
6. [Alcance funcional](#6-alcance-funcional)
7. [Arquitectura de la solución](#7-arquitectura-de-la-solución)
8. [Flujo principal](#8-flujo-principal)
9. [Uso de inteligencia artificial](#9-uso-de-inteligencia-artificial)
10. [Integraciones externas](#10-integraciones-externas)
11. [Integración con sistemas empresariales](#11-integración-con-sistemas-empresariales)
12. [Modelo de datos](#12-modelo-de-datos)
13. [Tecnologías](#13-tecnologías)
14. [Estructura del proyecto](#14-estructura-del-proyecto)
15. [Instalación local](#15-instalación-local)
16. [Variables de entorno](#16-variables-de-entorno)
17. [Test local con migraciones y datos iniciales](#17-test-local-con-migraciones-y-datos-iniciales)
18. [Usuarios de demostración](#18-usuarios-de-demostración)
19. [Pruebas manuales](#19-pruebas-manuales)
20. [Pruebas automatizadas](#20-pruebas-automatizadas)
21. [Despliegue en Vercel](#21-despliegue-en-vercel)
22. [Seguridad y control humano](#22-seguridad-y-control-humano)
23. [Limitaciones del MVP](#23-limitaciones-del-mvp)
24. [Mejoras futuras](#24-mejoras-futuras)
25. [Autores](#25-autores)

---

# 1. Track asignado

**Hackathon de Agentes Financieros IA — Track 4**

### Asistencia Inteligente para el Ingreso y Negociación de Notas de Crédito Tributarias en Ecuador

El proyecto responde al proceso de recepción, validación, negociación y cierre asistido de notas de crédito tributarias.

Los agentes financieros relacionados con el track son:

- Agente IA para Debida Diligencia y Cumplimiento.
- Analista Financiero IA para Tesorería Digital.

CrediTrade busca reducir:

- El reingreso manual de información.
- Los errores de digitación.
- La duplicación de expedientes.
- La omisión de documentos y controles.
- El tiempo de revisión entre operadores.
- El retrabajo durante la preparación de una negociación.
- La creación manual de reportes y borradores.

---

# 2. Tipo de negocio

CrediTrade está diseñado principalmente para una **casa de valores** que recibe notas de crédito tributarias de clientes interesados en negociarlas.

También puede adaptarse a:

- Intermediarios bursátiles.
- Empresas de servicios financieros.
- Áreas de tesorería.
- Equipos de cumplimiento.
- Firmas que administran títulos tributarios.
- Empresas que reciben notas de crédito como mecanismo de pago.
- Organizaciones que requieren validación documental y trazabilidad financiera.

## Aplicación dentro del negocio

La plataforma permite que una casa de valores:

1. Registre al titular de una nota de crédito.
2. Reutilice información de operaciones anteriores.
3. Revise documentos de respaldo.
4. Detecte inconsistencias y posibles duplicados.
5. Valide el expediente.
6. Prepare una negociación con un comprador.
7. Genere un borrador de orden, carta o reporte.
8. Registre confirmaciones y solicitudes de cierre.

---

# 3. Problema identificado

El procedimiento de recepción y negociación de notas de crédito puede involucrar múltiples operadores, documentos, validaciones y comunicaciones.

Cuando el proceso se realiza de forma manual pueden aparecer los siguientes problemas:

- Datos ingresados varias veces.
- Expedientes incompletos.
- Errores en el RUC, número de título, saldo o valor nominal.
- Falta de trazabilidad.
- Pérdida de información entre departamentos.
- Demoras en la revisión.
- Dificultad para reutilizar antecedentes.
- Posibles casos duplicados.
- Omisión de documentos obligatorios.
- Reportes preparados manualmente.
- Falta de claridad sobre la siguiente acción.

CrediTrade centraliza la información en un expediente único y guía a cada operador durante su etapa del proceso.

---

# 4. Solución propuesta

CrediTrade divide el proceso en tres módulos operativos:

1. **Recepción asistida**
2. **Validación y cumplimiento**
3. **Negociación y cierre asistido**

La plataforma permite:

- Buscar clientes y antecedentes.
- Crear expedientes.
- Registrar notas de crédito.
- Agregar documentos de respaldo.
- Proponer datos mediante inteligencia artificial.
- Aceptar o rechazar individualmente cada sugerencia.
- Ejecutar validaciones mediante reglas.
- Detectar posibles duplicados.
- Explicar riesgos y pendientes.
- Recomendar la siguiente acción.
- Preparar borradores de negociación.
- Generar reportes PDF.
- Mantener trazabilidad de responsables, fechas y observaciones.

---

# 5. Usuarios y roles

El sistema utiliza un modelo de usuario personalizado llamado `Operador`.

Un mismo usuario puede tener uno, dos o los tres roles simultáneamente.

## Operador 1 — Recepcionista

Responsable de:

- Registrar clientes.
- Consultar antecedentes.
- Crear expedientes.
- Ingresar notas de crédito.
- Agregar documentos de respaldo.
- Revisar sugerencias generadas por IA.
- Confirmar, modificar o rechazar datos sugeridos.
- Remitir el expediente para validación.

## Operador 2 — Contador o responsable de validación

Responsable de:

- Verificar existencia, saldo y estado.
- Revisar campos faltantes.
- Detectar inconsistencias.
- Identificar posibles duplicados.
- Revisar coincidencias de riesgo.
- Solicitar correcciones o documentos.
- Aprobar o rechazar el avance del expediente.
- Autorizar el paso a negociación.

## Operador 3 — Vendedor o negociador

Responsable de:

- Registrar o seleccionar al comprador.
- Preparar las condiciones de negociación.
- Generar borradores con inteligencia artificial.
- Crear reportes PDF.
- Registrar observaciones.
- Gestionar confirmaciones.
- Preparar la solicitud de cierre.

## Administrador

Responsable de:

- Crear y administrar usuarios.
- Asignar uno o varios roles.
- Activar o desactivar operadores.
- Consultar los registros administrativos del sistema.

---

# 6. Alcance funcional

## Gestión de usuarios

- Inicio y cierre de sesión.
- Usuario personalizado `Operador`.
- Asignación de múltiples roles.
- Restricción de vistas por permisos.
- Panel administrativo de Django.

## Gestión de clientes

- Registro de personas o empresas.
- Clasificación como comprador, vendedor o ambos.
- Identificación mediante RUC o cédula.
- Información del representante legal.
- Datos de contacto.
- Autorización para uso de información.

## Gestión de notas de crédito

- Número de título.
- Titular.
- Tipo de nota.
- Origen tributario.
- Valor nominal.
- Saldo disponible.
- Valor mínimo esperado.
- Estado del expediente.
- Responsables por etapa.
- Observaciones.

## Documentos de respaldo

- Tipo de respaldo.
- Nombre.
- Enlace al documento.
- Contenido relevante para revisión.
- Origen del respaldo.
- Comprobación automática de integridad.

El operador no necesita ingresar códigos técnicos. Cuando selecciona un documento, CrediTrade calcula internamente su comprobación.

## Validación

- Existencia del título.
- Saldo reportado.
- Estado de la fuente.
- Posibles bloqueos.
- Campos faltantes.
- Inconsistencias.
- Posibles duplicados.
- Coincidencias de riesgo.
- Próxima acción sugerida.

## Negociación

- Selección del comprador.
- Preparación de condiciones.
- Generación de borradores.
- Generación de reportes.
- Confirmación de las partes.
- Solicitud de cierre.

---

# 7. Arquitectura de la solución

```mermaid
flowchart LR
    subgraph Usuarios
        OP1[Operador 1<br>Recepcionista]
        OP2[Operador 2<br>Contador]
        OP3[Operador 3<br>Vendedor]
        ADM[Administrador]
        EXT[Comprador o vendedor<br>Enlace de confirmación]
    end

    subgraph Canales
        WEB[Aplicación web responsive]
        PUBLICO[Canal público de confirmación]
        ADMIN[Django Admin]
    end

    subgraph Aplicacion["CrediTrade — Django"]
        AUTH[Autenticación y roles]
        CORE[Gestión de expedientes]
        RULES[Motor de reglas]
        AI_SERVICE[Servicio de inteligencia artificial]
        REPORTS[Generación de reportes PDF]
        AUDIT[Trazabilidad y auditoría]
    end

    subgraph Integraciones
        GEMINI[Google Gemini]
        NEON[(PostgreSQL<br>Neon)]
        STORAGE[Almacenamiento documental<br>Blob / S3 / Supabase Storage]
        SRI[SRI<br>Real o simulado]
        DECEVALE[DECEVALE<br>Real o simulado]
        ERP[ERP / CRM / Core financiero]
    end

    subgraph Infraestructura
        VERCEL[Vercel]
        GITHUB[GitHub]
    end

    OP1 --> WEB
    OP2 --> WEB
    OP3 --> WEB
    ADM --> ADMIN
    EXT --> PUBLICO

    WEB --> AUTH
    ADMIN --> AUTH
    PUBLICO --> CORE
    AUTH --> CORE

    CORE --> RULES
    CORE --> AI_SERVICE
    CORE --> REPORTS
    CORE --> AUDIT
    CORE --> NEON
    CORE --> STORAGE

    RULES --> SRI
    RULES --> DECEVALE
    AI_SERVICE --> GEMINI

    ERP <--> CORE

    GITHUB --> VERCEL
    VERCEL --> WEB
```

## Componentes principales

### Canal web

Interfaz utilizada por los operadores para gestionar los expedientes.

Está construida con:

- Django Templates.
- Bootstrap.
- HTML.
- CSS.
- JavaScript ligero.

### Autenticación y roles

Controla:

- Inicio de sesión.
- Acceso por módulo.
- Usuarios con varios roles.
- Operadores activos o inactivos.
- Permisos administrativos.

### Núcleo de expedientes

Centraliza:

- Clientes.
- Notas de crédito.
- Documentos.
- Responsables.
- Validaciones.
- Negociaciones.
- Observaciones.
- Confirmaciones.

### Motor de reglas

Ejecuta validaciones determinísticas antes de solicitar una explicación a la inteligencia artificial.

Puede detectar:

- Campos faltantes.
- Diferencias de saldo.
- Títulos no encontrados.
- Posibles bloqueos.
- Expedientes duplicados.
- Coincidencias de riesgo.

### Servicio de inteligencia artificial

Google Gemini se utiliza para:

- Proponer información.
- Comparar antecedentes.
- Explicar validaciones.
- Recomendar la siguiente acción.
- Generar resúmenes.
- Crear borradores de negociación.

### Base de datos

PostgreSQL alojado en Neon almacena:

- Operadores.
- Clientes.
- Notas de crédito.
- Documentos.
- Validaciones.
- Sugerencias.
- Reportes.
- Eventos de trazabilidad.
- Enlaces de confirmación.

### Generador de reportes

ReportLab se utiliza para crear documentos PDF relacionados con la negociación.

---

# 8. Flujo principal

```mermaid
flowchart TD
    A[Registrar o buscar cliente]
    B[Crear expediente]
    C[Ingresar nota de crédito]
    D[Buscar antecedentes]
    E[Agregar documentos]
    F[Generar sugerencias con IA]
    G[Operador revisa cada sugerencia]
    H{¿Aceptar sugerencia?}
    I[Aplicar dato confirmado]
    J[Rechazar sugerencia]
    K[Enviar a validación]
    L[Ejecutar reglas de validación]
    M[Gemini explica resultados]
    N{¿Expediente conforme?}
    O[Solicitar corrección o documento]
    P[Autorizar negociación]
    Q[Registrar comprador]
    R[Generar borrador y reporte]
    S[Recibir confirmaciones]
    T[Preparar solicitud de cierre]
    U[Liquidación, transferencia o endoso<br>fuera del MVP]

    A --> B
    B --> C
    C --> D
    D --> E
    E --> F
    F --> G
    G --> H

    H -- Sí --> I
    H -- No --> J

    I --> K
    J --> K

    K --> L
    L --> M
    M --> N

    N -- No --> O
    O --> C

    N -- Sí --> P
    P --> Q
    Q --> R
    R --> S
    S --> T
    T --> U
```

---

# 9. Uso de inteligencia artificial

CrediTrade utiliza Google Gemini únicamente desde el backend.

La API key:

- No se envía al navegador.
- No se incluye en HTML.
- No se guarda en GitHub.
- Se configura mediante variables de entorno.

## Funciones de Gemini

### Sugerencias de ingreso

Gemini puede analizar:

- Información del expediente actual.
- Antecedentes del cliente.
- Casos anteriores.
- Texto de documentos de respaldo.

Después propone valores que el operador debe revisar.

### Explicación de validaciones

Las reglas del sistema producen un resultado técnico.

Gemini transforma ese resultado en una explicación que incluye:

- Resumen.
- Riesgos detectados.
- Evidencia que debe revisarse.
- Próxima acción recomendada.

### Preparación de negociación

Gemini genera:

- Resumen ejecutivo.
- Puntos clave.
- Riesgos y pendientes.
- Siguiente acción.
- Borrador de carta.
- Contenido para el reporte del vendedor.

## Control humano

Gemini no puede:

- Aprobar un expediente.
- Modificar datos sin confirmación.
- Ejecutar una transferencia.
- Ejecutar un endoso.
- Liquidar una operación.
- Reemplazar la decisión del operador.

## Comportamiento ante errores

Si Gemini no responde correctamente:

- No se inventan datos.
- No se genera contenido local alternativo.
- No se eliminan sugerencias anteriores.
- No se aprueba automáticamente el caso.
- Se muestra un error controlado al operador.

---

# 10. Integraciones externas

## Google Gemini

Utilizado para:

- Sugerencias.
- Comparaciones.
- Explicaciones.
- Recomendaciones.
- Borradores y reportes.

## Neon PostgreSQL

Utilizado como base de datos principal.

El proyecto emplea:

- Conexión agrupada para la aplicación.
- Conexión directa para las migraciones.

## Vercel

Utilizado para desplegar la aplicación Django.

## GitHub

Utilizado para:

- Control de versiones.
- Colaboración.
- Despliegues automáticos en Vercel.

## SRI

En el MVP se representa mediante una fuente simulada o cargada por el equipo.

Una integración futura podría consultar:

- Existencia del título.
- Estado.
- Saldo.
- Información tributaria disponible.
- Bloqueos o restricciones.

## DECEVALE

En el MVP se representa mediante una fuente simulada.

Una integración futura podría validar información relacionada con la custodia o registro del título.

## Almacenamiento documental

Los documentos pueden almacenarse en servicios externos como:

- Vercel Blob.
- Amazon S3.
- Azure Blob Storage.
- Google Cloud Storage.
- Supabase Storage.

---

# 11. Integración con sistemas empresariales

CrediTrade puede funcionar como aplicación independiente o integrarse con sistemas existentes.

## Integración mediante API REST

Se puede incorporar Django REST Framework para exponer servicios como:

```text
POST   /api/clientes/
GET    /api/clientes/{identificacion}/
POST   /api/notas-credito/
GET    /api/notas-credito/{id}/
POST   /api/notas-credito/{id}/validar/
POST   /api/notas-credito/{id}/negociar/
GET    /api/notas-credito/{id}/estado/
GET    /api/notas-credito/{id}/trazabilidad/
```

Esto permitiría conectar CrediTrade con:

- ERP.
- CRM.
- Sistema contable.
- Core financiero.
- Aplicaciones móviles.
- Portales de clientes.
- Gestores documentales.

## Integración con ERP o CRM

CrediTrade podría recibir automáticamente:

- RUC o identificación.
- Razón social.
- Representante legal.
- Información de contacto.
- Historial comercial.
- Operaciones anteriores.
- Nivel de riesgo interno.

También podría devolver:

- Estado del expediente.
- Resultado de validación.
- Valor nominal.
- Saldo disponible.
- Responsable actual.
- Próxima acción.
- Resultado de negociación.

## Inicio de sesión empresarial

El login actual puede integrarse con:

- Microsoft Entra ID.
- Active Directory.
- OAuth 2.0.
- OpenID Connect.
- SAML.
- Single Sign-On.
- Microsoft Authenticator.
- Autenticación de dos factores.

Los grupos empresariales podrían mapearse de esta manera:

```text
Grupo Recepción    → puede_recepcionar
Grupo Cumplimiento → puede_validar
Grupo Negociación  → puede_negociar
```

## Integración mediante webhooks

CrediTrade podría informar a otros sistemas cuando ocurra un evento.

Ejemplos:

- Expediente creado.
- Documento requerido.
- Riesgo detectado.
- Validación aprobada.
- Negociación preparada.
- Confirmación recibida.
- Caso listo para cierre.

Ejemplo de evento:

```json
{
  "evento": "NOTA_VALIDADA",
  "expediente": "NCT-2026-00015",
  "estado": "VALIDADA",
  "responsable": "contador01",
  "fecha": "2026-07-12T18:30:00Z"
}
```

## Integración documental

Un sistema empresarial podría enviar documentos a CrediTrade y recibir:

- Nombre del documento.
- Tipo.
- Enlace de almacenamiento.
- Fecha de carga.
- Responsable.
- Resultado de comprobación.
- Texto extraído.

## Procesamiento masivo

Para manejar grandes volúmenes se recomienda incorporar:

- Importación mediante CSV o Excel.
- Operaciones masivas de PostgreSQL.
- Procesamiento por lotes.
- Colas con Celery o RQ.
- Reintentos automáticos.
- Paginación.
- Monitoreo.
- Alertas.
- Control de cuota de Gemini.
- Particionamiento de tablas cuando sea necesario.

---

# 12. Modelo de datos

## Operador

Usuario que puede tener varios roles:

```text
puede_recepcionar
puede_validar
puede_negociar
```

## Cliente

Puede ser:

- Comprador.
- Vendedor.
- Comprador y vendedor.

Contiene información como:

- Nombres o razón social.
- RUC o identificación.
- Representante legal.
- Contacto.
- Autorización de consulta.

## Nota de crédito

Representa el expediente principal.

Contiene:

- Número de título.
- Tipo de nota.
- Origen tributario.
- Valor nominal.
- Saldo.
- Valor mínimo esperado.
- Estado.
- Responsables.
- Fechas.

## Documento de respaldo

Contiene:

- Tipo.
- Nombre.
- Enlace.
- Contenido para revisión.
- Fuente.
- Comprobación automática.
- Operador que lo registró.

## Sugerencia de IA

Contiene:

- Campo propuesto.
- Valor sugerido.
- Nivel de confianza.
- Fuente.
- Evidencia.
- Estado de revisión.

## Validación

Contiene:

- Existencia.
- Saldo de la fuente.
- Estado.
- Bloqueo.
- Faltantes.
- Inconsistencias.
- Duplicados.
- Riesgos.
- Explicación de IA.
- Siguiente acción.

## Reporte

Contiene:

- Resumen.
- Puntos clave.
- Riesgos.
- Borrador.
- Modelo de IA utilizado.
- Operador responsable.
- Fecha.

## Evento de trazabilidad

Registra:

- Acción.
- Operador.
- Fecha.
- Expediente.
- Descripción.
- Datos adicionales.

---

# 13. Tecnologías

| Componente | Tecnología |
|---|---|
| Backend | Django 5 |
| Lenguaje | Python |
| Base de datos | PostgreSQL |
| Proveedor de base | Neon |
| Inteligencia artificial | Google Gemini |
| Validación de respuestas | Pydantic |
| Generación de PDF | ReportLab |
| Frontend | Django Templates |
| Interfaz | Bootstrap |
| Despliegue | Vercel |
| Repositorio | GitHub |
| Control de versiones | Git |

---

# 14. Estructura del proyecto

```text
accounts/
├── admin.py
├── models.py
├── migrations/
└── views.py

credit_notes/
├── admin.py
├── ai_services.py
├── apps.py
├── decorators.py
├── forms.py
├── management/
├── migrations/
├── models.py
├── pdf_reports.py
├── services.py
├── tests.py
├── urls.py
└── views.py

creditrade/
├── asgi.py
├── settings.py
├── urls.py
└── wsgi.py

docs/
└── ARQUITECTURA_Y_FLUJO.md

static/
├── css/
├── img/
└── js/

templates/
├── accounts/
├── credit_notes/
└── base.html

manage.py
requirements.txt
vercel.json
README.md
```

---

# 15. Instalación local

## Requisitos

- Python 3.12 o superior.
- Git.
- Cuenta de Neon.
- API key de Gemini.

## Clonar el repositorio

```bash
git clone https://github.com/Jareth20/CrediTrade.git
cd CrediTrade
```

## Crear el entorno virtual

### Windows CMD

```cmd
py -m venv venv
venv\Scripts\activate
```

### Windows PowerShell

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
```

## Instalar dependencias

```bash
pip install -r requirements.txt
```

## Crear el archivo `.env`

Crea un archivo llamado:

```text
.env
```

en la misma carpeta donde se encuentra `manage.py`.

---

# 16. Variables de entorno

Ejemplo de configuración local:

```env
DJANGO_SECRET_KEY=una-clave-segura
DJANGO_DEBUG=True

DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,.vercel.app
CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000,https://*.vercel.app

DATABASE_URL=postgresql://USUARIO:CONTRASENA@HOST-POOLER/neondb?sslmode=require
DATABASE_URL_UNPOOLED=postgresql://USUARIO:CONTRASENA@HOST-DIRECTO/neondb?sslmode=require
DJANGO_USE_UNPOOLED=False

GEMINI_API_KEY=clave-de-gemini
GEMINI_MODEL=gemini-3.5-flash
GEMINI_TIMEOUT_MS=60000

PUBLIC_BASE_URL=http://127.0.0.1:8000

SECURE_SSL_REDIRECT=False
SECURE_HSTS_SECONDS=0
SECURE_HSTS_INCLUDE_SUBDOMAINS=False
SECURE_HSTS_PRELOAD=False
```

## Conexiones de Neon

La conexión de aplicación debe contener:

```text
-pooler
```

La conexión directa para migraciones no debe contenerlo.

Las credenciales reales nunca deben incluirse en el repositorio.

---

# 17. Test local con migraciones y datos iniciales

## Windows CMD

```cmd
set "DJANGO_USE_UNPOOLED=True"
python manage.py migrate
python manage.py seed_demo
set "DJANGO_USE_UNPOOLED=False"
```

## PowerShell

```powershell
$env:DJANGO_USE_UNPOOLED="True"
python manage.py migrate
python manage.py seed_demo
Remove-Item Env:DJANGO_USE_UNPOOLED
```

## Verificar integraciones

```bash
python manage.py verificar_integraciones --gemini
```

## Iniciar el servidor

```bash
python manage.py runserver
```

Abrir:

```text
http://127.0.0.1:8000/
```

---

# 18. Usuarios de demostración

| Usuario | Contraseña inicial | Roles |
|---|---|---|
| `recepcionista` | `OperadorDemo123!` | Operador 1 |
| `contador` | `OperadorDemo123!` | Operador 2 |
| `vendedor` | `OperadorDemo123!` | Operador 3 |
| `operador_total` | `OperadorDemo123!` | Operadores 1, 2 y 3 |
| `admin` | `AdminDemo123!` | Administrador |

> Estas contraseñas deben cambiarse antes de una demostración pública o uso en producción.

---

# 19. Pruebas manuales

Los casos probados deben documentarse con:

- Datos de entrada.
- Resultado esperado.
- Resultado obtenido.
- Validaciones aplicadas.
- Evidencia o captura.

## Matriz mínima de pruebas

| Caso | Entrada | Resultado esperado | Resultado obtenido |
|---|---|---|---|
| Inicio de sesión | Credenciales válidas | Acceso al sistema | Acceso correcto |
| Credenciales incorrectas | Contraseña inválida | Rechazar acceso | Acceso rechazado |
| Control de roles | Usuario operador 1 | Acceso a recepción | Permisos aplicados |
| Usuario multirrol | Usuario con roles 1, 2 y 3 | Acceso a los tres módulos | Acceso correcto |
| Registro de cliente | Identificación y datos válidos | Cliente almacenado | Registro correcto |
| Cliente duplicado | Identificación existente | Mostrar advertencia | Duplicado controlado |
| Registro de nota | Datos válidos | Crear expediente | Expediente creado |
| Campos obligatorios | Formulario incompleto | Mostrar errores | Validaciones mostradas |
| Consulta de antecedentes | RUC existente | Mostrar casos relacionados | Antecedentes encontrados |
| Sugerencias de IA | Expediente con información | Generar sugerencias | Sugerencias generadas |
| Aceptar sugerencia | Confirmación del operador | Aplicar dato elegido | Dato actualizado |
| Rechazar sugerencia | Rechazo del operador | Mantener dato original | Dato conservado |
| Posible duplicado | Titular, valor y saldo similares | Mostrar alerta | Riesgo detectado |
| Título no encontrado | Número inexistente | Estado no conforme | Riesgo registrado |
| Explicación de IA | Validación ejecutada | Explicar evidencia | Explicación generada |
| Documento de respaldo | Archivo seleccionado | Comprobar automáticamente | Documento comprobado |
| Autorización | Validación conforme | Habilitar negociación | Flujo habilitado |
| Reporte | Expediente aprobado | Generar borrador y PDF | Reporte creado |
| Confirmación pública | Enlace válido | Registrar respuesta | Confirmación guardada |

## Ejemplo documentado

### Caso: detección de posible duplicado

**Entrada**

- RUC: `0999999999001`
- Valor nominal: `10000`
- Saldo: `10000`
- Número de título: `SIM-NCT-0001`

**Resultado esperado**

El sistema debe buscar expedientes anteriores y detectar coincidencias relevantes.

**Resultado obtenido**

Se mostraron casos con coincidencia de titular, valor nominal y saldo.

**Validaciones aplicadas**

- Comparación por titular.
- Comparación por identificación.
- Comparación por valor nominal.
- Comparación por saldo.
- Búsqueda de expedientes anteriores.

**Evidencia**

```text
docs/capturas/posible-duplicado.png
```

## Capturas 

```text
docs/capturas/
├── 01-login.png
├── 02-dashboard.png
├── 03-registro-cliente.png
├── 04-registro-nota.png
├── 05-antecedentes.png
├── 06-sugerencias-ia.png
├── 07-validacion.png
├── 08-explicacion-gemini.png
├── 09-negociacion.png
├── 10-reporte-pdf.png
└── 11-confirmacion.png
```

---

# 20. Pruebas automatizadas

Las pruebas pueden ejecutarse con una base temporal habilitada explícitamente.

## Windows CMD

```cmd
set "DATABASE_URL=sqlite:///test.sqlite3"
set "DJANGO_ALLOW_NON_POSTGRES_FOR_TESTS=True"
set "DJANGO_SECRET_KEY=test-secret-key"
python manage.py test
```

## PowerShell

```powershell
$env:DATABASE_URL="sqlite:///test.sqlite3"
$env:DJANGO_ALLOW_NON_POSTGRES_FOR_TESTS="True"
$env:DJANGO_SECRET_KEY="test-secret-key"

python manage.py test
```

La aplicación normal no cambia automáticamente a SQLite.

---

# 21. Despliegue en Vercel

## Preparación

1. Subir el proyecto a GitHub.
2. Confirmar que `.env` esté ignorado.
3. Importar el repositorio en Vercel.
4. Seleccionar Django como preset.
5. Mantener la raíz donde se encuentra `manage.py`.
6. Agregar las variables de entorno.
7. Desplegar.

## Variables principales de producción

```env
DJANGO_SECRET_KEY=clave-segura
DJANGO_DEBUG=False

DJANGO_ALLOWED_HOSTS=.vercel.app
CSRF_TRUSTED_ORIGINS=https://*.vercel.app

DATABASE_URL=conexion-pooled-de-neon
DJANGO_USE_UNPOOLED=False

GEMINI_API_KEY=clave-de-gemini
GEMINI_MODEL=gemini-3.5-flash
GEMINI_TIMEOUT_MS=45000

PUBLIC_BASE_URL=https://creditrade.vercel.app

SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=3600
SECURE_HSTS_INCLUDE_SUBDOMAINS=False
SECURE_HSTS_PRELOAD=False
```

## Migraciones

Las migraciones deben ejecutarse desde una máquina controlada usando la conexión directa.

No se recomienda ejecutar:

```bash
python manage.py migrate
```

automáticamente durante cada build de Vercel.

## Actualizaciones

Después de realizar cambios:

```bash
git add .
git commit -m "Descripción del cambio"
git push origin main
```

Vercel detectará el cambio y generará un nuevo despliegue.

---

# 22. Seguridad y control humano

CrediTrade mantiene las siguientes reglas:

- Ninguna sugerencia reemplaza información automáticamente.
- Cada dato sugerido debe ser aceptado o rechazado.
- Gemini no aprueba expedientes.
- Los usuarios solo acceden a los módulos permitidos.
- Las acciones importantes quedan registradas.
- Las credenciales se almacenan en variables de entorno.
- `.env` no se sube a GitHub.
- La aplicación utiliza HTTPS en producción.
- Los documentos se comprueban automáticamente.
- La liquidación no se ejecuta desde el MVP.
- La transferencia no se ejecuta desde el MVP.
- El endoso no se ejecuta desde el MVP.

---

# 23. Limitaciones del MVP

El MVP no ejecuta directamente:

- Transferencias de dinero.
- Liquidaciones bursátiles.
- Endosos.
- Firma electrónica.
- Consultas oficiales automatizadas al SRI.
- Consultas oficiales automatizadas a DECEVALE.
- Operaciones reguladas en producción.

Las fuentes externas pueden funcionar mediante:

- Datos ficticios.
- Archivos de prueba.
- Información cargada por el equipo.
- Servicios simulados.

El objetivo es demostrar el flujo funcional de extremo a extremo.

---

# 24. Mejoras futuras

- API REST.
- Aplicación móvil.
- Integración real con SRI.
- Integración real con DECEVALE.
- Microsoft Authenticator.
- Single Sign-On.
- Firma electrónica.
- Carga y almacenamiento directo de archivos.
- OCR para documentos.
- Extracción automática de PDF y XML.
- Importación masiva mediante CSV o Excel.
- Procesamiento en segundo plano.
- Colas de tareas.
- Notificaciones por correo.
- Panel de indicadores.
- Reportes analíticos.
- Integración con ERP.
- Integración con CRM.
- Integración con sistemas contables.
- Monitoreo de costos y cuota de Gemini.
- Auditoría avanzada.
- Control de versiones de documentos.
- Recuperación y respaldo de información.

---

# 👥 25. Autores

| Nombre | Descripción |
| :--- | :--- |
| **Cristina Villacís** | ` Ingeniería en Ciencias de la Computación ` |
| **Jareth Rojas** | `Ingeniería en Ciencia de Datos e IA ` |
| **Alejandro Verdesoto** | `Ingeniería en Ciencia de Datos e IA `|

Proyecto desarrollado como MVP para el Track 4 del Hackathon de Agentic Scale.

---