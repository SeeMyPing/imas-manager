"""
IMAS Manager - Django Settings

Production-ready configuration using django-environ for environment variables.
"""
from __future__ import annotations

import os
from pathlib import Path

import environ
from celery.schedules import crontab

# =============================================================================
# Base Directory
# =============================================================================
BASE_DIR = Path(__file__).resolve().parent.parent

# =============================================================================
# Environment Configuration
# =============================================================================
env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
)

# Read .env file if it exists
environ.Env.read_env(os.path.join(BASE_DIR.parent, ".env"))

# =============================================================================
# Core Settings
# =============================================================================
DEBUG = env("DEBUG")
SECRET_KEY = env("SECRET_KEY", default="django-insecure-change-me-in-production")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# =============================================================================
# Application Definition
# =============================================================================
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
    "channels",
]

LOCAL_APPS = [
    "core",
    "dashboard",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# =============================================================================
# ASGI / Channels Configuration
# =============================================================================
ASGI_APPLICATION = "config.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [env("REDIS_URL", default="redis://localhost:6379/2")],
        },
    },
}

# =============================================================================
# Middleware
# =============================================================================
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
    "core.middleware.RateLimitByIPMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.AuditLogMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

# =============================================================================
# Templates
# =============================================================================
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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

# =============================================================================
# Database
# =============================================================================
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://imas_user:imas_secret@localhost:5432/imas_db",
    )
}

# =============================================================================
# Password Validation
# =============================================================================
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# =============================================================================
# Internationalization
# =============================================================================
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# =============================================================================
# Static Files
# =============================================================================
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []

# WhiteNoise configuration for production
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# =============================================================================
# Default Primary Key
# =============================================================================
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# =============================================================================
# Django REST Framework
# =============================================================================
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
    },
}

# =============================================================================
# =============================================================================
# DRF Spectacular (OpenAPI Schema)
# =============================================================================
SPECTACULAR_SETTINGS = {
    "TITLE": "IMAS Manager API",
    "DESCRIPTION": """
# IMAS Manager - Incident Management At Scale

Backend API for incident response orchestration.

## Features

- **Incident Management**: Create, track, and resolve incidents
- **Smart Notifications**: Multi-channel alerting (Slack, Email, SMS)
- **War Room Automation**: Automatic Slack channel creation for critical incidents
- **LID Documents**: Auto-generate Google Docs for incident documentation
- **On-Call Management**: Rotation scheduling with escalation support

## Authentication

All API endpoints (except health checks) require authentication via Token.

```
Authorization: Token <your-api-token>
```

Obtain a token via `POST /api/token/obtain/` with username/password.

## Severity Levels

| Level | Description | Actions |
|-------|-------------|---------|
| SEV1 | Critical outage | War Room + LID + SMS alerts |
| SEV2 | Major degradation | War Room + LID + Slack alerts |
| SEV3 | Minor impact | LID + Slack alerts |
| SEV4 | Cosmetic/Low | Slack alerts only |

## Rate Limits

- Anonymous: 100 requests/hour
- Authenticated: 1000 requests/hour

## Webhooks

IMAS Manager can send webhooks to external systems when incidents are created or updated.
Configure webhook URLs in the admin panel.

## Error Responses

All errors follow a consistent format:
```json
{
  "error": "Human-readable error message",
  "code": "MACHINE_READABLE_CODE",
  "details": {"field": ["Field-specific errors"]}
}
```
""",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "CONTACT": {
        "name": "IMAS Team",
        "email": "imas-support@example.com",
    },
    "LICENSE": {
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    "TAGS": [
        {
            "name": "incidents",
            "description": "Incident lifecycle management - create, acknowledge, resolve",
            "externalDocs": {
                "description": "Incident Management Guide",
                "url": "https://github.com/SeeMyPing/imas-manager/blob/main/docs/03_business_logic.md",
            },
        },
        {
            "name": "services",
            "description": "Service catalog - list and manage services",
        },
        {
            "name": "teams",
            "description": "Team management and on-call rotation",
        },
        {
            "name": "webhooks",
            "description": "Webhook endpoints for receiving alerts from monitoring systems",
        },
        {
            "name": "metrics",
            "description": "Incident metrics, analytics, and reporting",
        },
        {
            "name": "auth",
            "description": "Authentication - obtain, verify, revoke API tokens",
        },
        {
            "name": "health",
            "description": "Health check endpoints for monitoring and load balancers",
        },
    ],
    "EXTERNAL_DOCS": {
        "description": "IMAS Manager Documentation",
        "url": "https://github.com/SeeMyPing/imas-manager",
    },
    # Schema configuration
    "SCHEMA_PATH_PREFIX": "/api/v[0-9]",
    "SCHEMA_PATH_PREFIX_TRIM": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "COMPONENT_NO_READ_ONLY_REQUIRED": True,
    "SORT_OPERATIONS": False,
    "SORT_OPERATION_PARAMETERS": True,
    # Security
    "SECURITY": [{"TokenAuth": []}],
    "APPEND_COMPONENTS": {
        "securitySchemes": {
            "TokenAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "Authorization",
                "description": "Token-based authentication. Format: `Token <api-token>`",
            },
        },
    },
    # Enum handling
    "ENUM_NAME_OVERRIDES": {
        "SeverityEnum": "core.choices.Severity",
        "IncidentStatusEnum": "core.choices.IncidentStatus",
    },
    # Postprocessing
    "POSTPROCESSING_HOOKS": [],
    # Swagger UI settings
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayOperationId": False,
        "filter": True,
        "docExpansion": "list",
        "defaultModelsExpandDepth": 2,
        "syntaxHighlight.theme": "monokai",
    },
    # ReDoc settings
    "REDOC_UI_SETTINGS": {
        "hideDownloadButton": False,
        "expandResponses": "200,201",
        "pathInMiddlePanel": True,
    },
}

# Application version
VERSION = "1.0.0"

# =============================================================================
# Celery Configuration
# =============================================================================
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes

# =============================================================================
# Cache Configuration (Redis)
# =============================================================================
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://localhost:6379/1"),
        "TIMEOUT": 300,  # 5 minutes default TTL
        "KEY_PREFIX": "imas",
    }
}

# Cache timeouts for different data types (in seconds)
CACHE_TIMEOUTS = {
    "dashboard_stats": 60,       # 1 minute for dashboard KPIs
    "incident_list": 30,         # 30 seconds for incident lists
    "service_list": 300,         # 5 minutes for services (rarely changes)
    "team_list": 300,            # 5 minutes for teams
    "metrics": 120,              # 2 minutes for metrics
}

# Celery Beat Schedule (Periodic Tasks)
CELERY_BEAT_SCHEDULE = {
    # Check for incidents needing escalation every 5 minutes
    "check-pending-escalations": {
        "task": "tasks.incident_tasks.check_pending_escalations",
        "schedule": 300.0,  # 5 minutes
    },
    # Send reminder for unacknowledged incidents every 15 minutes
    "send-unacknowledged-reminders": {
        "task": "tasks.incident_tasks.send_unacknowledged_reminders",
        "schedule": 900.0,  # 15 minutes
    },
    # Auto-archive resolved incidents older than 7 days (daily at 2 AM)
    "auto-archive-old-incidents": {
        "task": "tasks.incident_tasks.auto_archive_incidents",
        "schedule": crontab(hour=2, minute=0),
    },
    # Generate daily incident summary report (daily at 8 AM)
    "daily-incident-summary": {
        "task": "tasks.incident_tasks.generate_daily_summary",
        "schedule": crontab(hour=8, minute=0),
    },
    # Cleanup stale War Rooms (daily at 3 AM)
    "cleanup-stale-war-rooms": {
        "task": "tasks.incident_tasks.cleanup_stale_war_rooms",
        "schedule": crontab(hour=3, minute=0),
    },
}

# =============================================================================
# Logging
# =============================================================================
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": env("DJANGO_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
        "celery": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# =============================================================================
# Google Drive Integration
# =============================================================================
# Option 1: Path to service account JSON file
GOOGLE_SERVICE_ACCOUNT_FILE = env("GOOGLE_SERVICE_ACCOUNT_FILE", default=None)

# Option 2: Service account JSON as string (for Docker/K8s secrets)
GOOGLE_SERVICE_ACCOUNT_JSON = env("GOOGLE_SERVICE_ACCOUNT_JSON", default=None)

# LID Template document ID
GOOGLE_LID_TEMPLATE_ID = env("GOOGLE_LID_TEMPLATE_ID", default=None)

# Destination folder for created documents
GOOGLE_DRIVE_FOLDER_ID = env("GOOGLE_DRIVE_FOLDER_ID", default=None)

# Domain for domain-wide reader access
GOOGLE_DRIVE_DOMAIN = env("GOOGLE_DRIVE_DOMAIN", default=None)

# =============================================================================
# Slack Integration
# =============================================================================
SLACK_BOT_TOKEN = env("SLACK_BOT_TOKEN", default=None)
SLACK_SIGNING_SECRET = env("SLACK_SIGNING_SECRET", default=None)

# =============================================================================
# Email / SMTP Configuration
# =============================================================================
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="imas@localhost")
