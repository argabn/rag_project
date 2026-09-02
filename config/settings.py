import os
import re
import uuid
from pathlib import Path
from dotenv import load_dotenv
try:
    import environ
except ImportError:
    environ = None
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

# Load environment variables
load_dotenv()
env = environ.Env(
    DEBUG=(bool, False),
    DJANGO_DEBUG=(bool, False),
)
# Reads .env file automatically (fallback to OS env)
environ.Env.read_env()

BASE_DIR = Path(__file__).resolve().parent.parent

# -------------------------------------------------------------------
# Core security settings – values must be provided in .env
# -------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY")  # required, no default
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS",
    default=["localhost", "127.0.0.1", "0.0.0.0", "[::1]"],
)

# -------------------------------------------------------------------
# CORS configuration – whitelist specific origins in production
# -------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8001",
        "http://127.0.0.1:8001",
        "http://localhost",
        "http://127.0.0.1",
    ],
)
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:8001",
    "http://127.0.0.1:8001",
    "http://localhost",
    "http://127.0.0.1",
]
# NOTE: keep DEBUG flag for convenience in dev, but do not allow all origins.

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "pgvector.django",
    "ingestion",
    "query",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# -------------------------------------------------------------------
# Database configuration – Supabase/PostgreSQL with pgvector
# -------------------------------------------------------------------
DATABASE_URL = env("DATABASE_URL", default="postgresql://postgres:postgres@localhost:5432/postgres")
db_url = DATABASE_URL
m = re.match(
    r"postgresql://(?P<user>.*?):(?P<password>.*?)@(?P<host>.*?):(?P<port>\d+)/(?P<name>.*)",
    db_url,
)
if not m:
    raise ValueError(
        "DATABASE_URL tidak valid. Format: postgresql://user:pass@host:port/dbname"
    )

db_name = m.group("name")
TEST_DB_NAME = env("TEST_DATABASE_NAME", default=f"{db_name}_test_{uuid.uuid4().hex[:8]}")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": db_name,
        "USER": m.group("user"),
        "PASSWORD": m.group("password"),
        "HOST": m.group("host"),
        "PORT": m.group("port"),
        "TEST": {
            "NAME": TEST_DB_NAME,
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "id-id"
TIME_ZONE = "Asia/Jakarta"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# -------------------------------------------------------------------
# REST Framework – secure defaults
# -------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"user": "1000/hour"},
}

# -------------------------------------------------------------------
# Caching – Redis backend (optional, defaults to local Redis)
# -------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-snowflake",
    }
}
SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"

# -------------------------------------------------------------------
# Embedding configuration
# -------------------------------------------------------------------
EMBEDDING_PROVIDER = env("EMBEDDING_PROVIDER", default="bge-m3")
EMBEDDING_DIM = int(env("EMBEDDING_DIM", default=1024))
EXTERNAL_EMBEDDING_ENDPOINT = env("EXTERNAL_EMBEDDING_ENDPOINT", default="")
EXTERNAL_EMBEDDING_API_KEY = env("EXTERNAL_EMBEDDING_API_KEY", default="")

# -------------------------------------------------------------------
# LLM configuration
# -------------------------------------------------------------------
GROQ_API_KEY = env("GROQ_API_KEY", default="")

# -------------------------------------------------------------------
# External API tokens (integrator)
# -------------------------------------------------------------------
EOFFICE_TOKEN = env("EOFFICE_TOKEN", default="")
SIMPEG_TOKEN = env("SIMPEG_TOKEN", default="")
ARSIP_TOKEN = env("ARSIP_TOKEN", default="")

# -------------------------------------------------------------------
# MySQL source configuration (optional)
# -------------------------------------------------------------------
MYSQL_SOURCE = {
    "HOST": env("MYSQL_SOURCE_HOST", default=None),
    "USER": env("MYSQL_SOURCE_USER", default=None),
    "PASSWORD": env("MYSQL_SOURCE_PASSWORD", default=None),
    "NAME": env("MYSQL_SOURCE_DB", default=None),
    "PORT": int(env("MYSQL_SOURCE_PORT", default=3306)),
}

# -------------------------------------------------------------------
# Sentry error monitoring (optional)
# -------------------------------------------------------------------
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=1.0,
        send_default_pii=True,
    )

# -------------------------------------------------------------------
# Logging – JSON structured logs for observability
# -------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
        "file": {
            "class": "logging.FileHandler",
            "filename": str(BASE_DIR / "logs" / "app.log"),
            "formatter": "json",
        },
    },
    "root": {"handlers": ["console", "file"], "level": "INFO"},
}
