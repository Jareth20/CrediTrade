from pathlib import Path
import os

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / ".env.local", override=True)

APP_NAME = "CrediTrade"

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() in {"1", "true", "yes", "on"}
DEMO_LOGIN_PREFILL = os.getenv("DEMO_LOGIN_PREFILL", "True").lower() in {"1", "true", "yes", "on"}

if not SECRET_KEY:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY no está configurada. Copia .env.example a .env y complétala."
    )

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv(
        "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,.vercel.app"
    ).split(",")
    if host.strip()
]

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CSRF_TRUSTED_ORIGINS",
        "http://localhost:8000,http://127.0.0.1:8000,https://*.vercel.app",
    ).split(",")
    if origin.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "credit_notes",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "creditrade.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "creditrade.wsgi.application"
ASGI_APPLICATION = "creditrade.asgi.application"

# La aplicación no usa SQLite como respaldo. La URL de PostgreSQL es obligatoria.
USE_UNPOOLED_DATABASE = os.getenv("DJANGO_USE_UNPOOLED", "False").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
DATABASE_VARIABLE = (
    "DATABASE_URL_UNPOOLED" if USE_UNPOOLED_DATABASE else "DATABASE_URL"
)
DATABASE_URL = os.getenv(DATABASE_VARIABLE, "").strip()

if not DATABASE_URL:
    raise ImproperlyConfigured(
        f"{DATABASE_VARIABLE} no está configurada. CrediTrade requiere PostgreSQL en Neon."
    )

ALLOW_NON_POSTGRES_FOR_TESTS = os.getenv(
    "DJANGO_ALLOW_NON_POSTGRES_FOR_TESTS", "False"
).lower() in {"1", "true", "yes", "on"}

if not DATABASE_URL.startswith(("postgres://", "postgresql://")) and not ALLOW_NON_POSTGRES_FOR_TESTS:
    raise ImproperlyConfigured(
        "DATABASE_URL debe ser una conexión PostgreSQL. Para pruebas aisladas use "
        "DJANGO_ALLOW_NON_POSTGRES_FOR_TESTS=True de forma explícita."
    )

DB_CONN_MAX_AGE = int(os.getenv("DB_CONN_MAX_AGE", "60"))

DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=DB_CONN_MAX_AGE,
        conn_health_checks=True,
        ssl_require=DATABASE_URL.startswith(
            ("postgres://", "postgresql://")
        ),
    )
}

DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-ec"
TIME_ZONE = "America/Guayaquil"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.Operador"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip()
GEMINI_FAST_MODEL = os.getenv("GEMINI_FAST_MODEL", GEMINI_MODEL).strip()
GEMINI_DEEP_MODEL = os.getenv("GEMINI_DEEP_MODEL", GEMINI_MODEL).strip()
GEMINI_FAST_THINKING_LEVEL = os.getenv(
    "GEMINI_FAST_THINKING_LEVEL", "minimal"
).strip()
GEMINI_DEEP_THINKING_LEVEL = os.getenv(
    "GEMINI_DEEP_THINKING_LEVEL", "low"
).strip()
GEMINI_MAX_OUTPUT_TOKENS = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "900"))
GEMINI_TIMEOUT_MS = int(os.getenv("GEMINI_TIMEOUT_MS", "60000"))
GEMINI_MAX_RETRIES = int(os.getenv("GEMINI_MAX_RETRIES", "1"))
GEMINI_RETRY_BASE_SECONDS = float(os.getenv("GEMINI_RETRY_BASE_SECONDS", "1"))
GEMINI_MAX_RETRY_WAIT_SECONDS = float(
    os.getenv("GEMINI_MAX_RETRY_WAIT_SECONDS", "8")
)
GEMINI_QUOTA_COOLDOWN_SECONDS = int(
    os.getenv("GEMINI_QUOTA_COOLDOWN_SECONDS", "900")
)
GEMINI_CACHE_SECONDS = int(os.getenv("GEMINI_CACHE_SECONDS", "86400"))
AI_OPERATION_LOCK_SECONDS = int(os.getenv("AI_OPERATION_LOCK_SECONDS", "300"))
GEMINI_EMBEDDING_MODEL = os.getenv(
    "GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"
).strip()
RAG_EMBEDDING_DIMENSIONS = int(os.getenv("RAG_EMBEDDING_DIMENSIONS", "768"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "4"))
RAG_MIN_RELEVANCE = float(os.getenv("RAG_MIN_RELEVANCE", "0.20"))
RAG_MAX_CONTEXT_CHARS = int(os.getenv("RAG_MAX_CONTEXT_CHARS", "4000"))
RAG_MAX_DOCUMENTS = int(os.getenv("RAG_MAX_DOCUMENTS", "12"))
RAG_MAX_CHUNKS_PER_DOCUMENT = int(
    os.getenv("RAG_MAX_CHUNKS_PER_DOCUMENT", "12")
)
RAG_MAX_EMBEDDING_BATCH = int(os.getenv("RAG_MAX_EMBEDDING_BATCH", "48"))
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "credit_notes": {
            "handlers": ["console"],
            "level": os.getenv("CREDITRADE_LOG_LEVEL", "INFO"),
            "propagate": False,
        }
    },
}

# Límites conservadores para un MVP serverless.
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
    SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "True").lower() == "true"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "3600"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = (
        os.getenv("SECURE_HSTS_INCLUDE_SUBDOMAINS", "False").lower() == "true"
    )
    SECURE_HSTS_PRELOAD = os.getenv("SECURE_HSTS_PRELOAD", "False").lower() == "true"
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
