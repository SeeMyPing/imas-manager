"""
IMAS Manager - Health Check API

Provides endpoints for monitoring system health:
- /health/ - Basic liveness check
- /health/ready/ - Readiness check (DB, Redis, etc.)
- /health/live/ - Kubernetes liveness probe
"""
from __future__ import annotations

import logging
import time
from typing import Any

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views import View
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

logger = logging.getLogger(__name__)


def _check_database() -> dict[str, Any]:
    """Check database connectivity."""
    start = time.time()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        latency = (time.time() - start) * 1000
        return {
            "status": "healthy",
            "latency_ms": round(latency, 2),
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
        }


def _check_redis() -> dict[str, Any]:
    """Check Redis connectivity."""
    start = time.time()
    try:
        import redis
        
        broker_url = getattr(settings, "CELERY_BROKER_URL", None)
        if not broker_url:
            return {"status": "skipped", "reason": "No broker configured"}
        
        client = redis.from_url(broker_url)
        client.ping()
        latency = (time.time() - start) * 1000
        return {
            "status": "healthy",
            "latency_ms": round(latency, 2),
        }
    except ImportError:
        return {"status": "skipped", "reason": "Redis client not installed"}
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
        }


def _check_celery() -> dict[str, Any]:
    """Check Celery worker availability."""
    try:
        from config.celery import app as celery_app
        
        inspect = celery_app.control.inspect()
        stats = inspect.stats()
        
        if stats:
            worker_count = len(stats)
            return {
                "status": "healthy",
                "workers": worker_count,
            }
        else:
            return {
                "status": "degraded",
                "reason": "No workers responding",
            }
    except Exception as e:
        logger.warning(f"Celery health check failed: {e}")
        return {
            "status": "degraded",
            "error": str(e),
        }


@extend_schema(
    tags=["health"],
    summary="Basic health check",
    description="Quick health check returning service name and version. Suitable for liveness probes.",
    responses={
        200: OpenApiResponse(
            description="Service is running",
            examples=[
                OpenApiExample(
                    "OK",
                    value={"status": "ok", "service": "imas-manager", "version": "1.0.0"},
                )
            ],
        ),
    },
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request) -> Response:
    """
    Basic health check endpoint.
    
    Returns 200 if the application is running.
    Suitable for Kubernetes liveness probes.
    """
    return Response(
        {
            "status": "ok",
            "service": "imas-manager",
            "version": getattr(settings, "VERSION", "1.0.0"),
        },
        status=status.HTTP_200_OK,
    )


@extend_schema(
    tags=["health"],
    summary="Liveness probe",
    description="""
Kubernetes liveness probe endpoint.

Returns 200 if the application process is alive.
Does **not** check dependencies - use /health/ready/ for dependency checks.
    """,
    responses={
        200: OpenApiResponse(
            description="Process is alive",
            examples=[OpenApiExample("Alive", value={"status": "alive"})],
        ),
    },
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health_live(request) -> Response:
    """
    Kubernetes liveness probe.
    
    Returns 200 if the application process is alive.
    Does not check dependencies.
    """
    return Response({"status": "alive"}, status=status.HTTP_200_OK)


@extend_schema(
    tags=["health"],
    summary="Readiness probe",
    description="""
Kubernetes readiness probe endpoint.

Checks all dependencies:
- **Database**: PostgreSQL connectivity
- **Redis**: Cache/broker connectivity
- **Celery**: Worker availability

Returns:
- **200**: All critical dependencies healthy
- **503**: One or more critical dependencies unhealthy
    """,
    responses={
        200: OpenApiResponse(
            description="Service ready to accept traffic",
            examples=[
                OpenApiExample(
                    "Ready",
                    value={
                        "status": "ready",
                        "checks": {
                            "database": {"status": "healthy", "latency_ms": 1.5},
                            "redis": {"status": "healthy", "latency_ms": 0.8},
                            "celery": {"status": "healthy", "workers": 2},
                        },
                        "timestamp": 1704067200.0,
                    },
                )
            ],
        ),
        503: OpenApiResponse(
            description="Service not ready",
            examples=[
                OpenApiExample(
                    "Not Ready",
                    value={
                        "status": "not_ready",
                        "checks": {
                            "database": {"status": "unhealthy", "error": "Connection refused"},
                            "redis": {"status": "healthy", "latency_ms": 0.8},
                            "celery": {"status": "degraded", "reason": "No workers responding"},
                        },
                        "timestamp": 1704067200.0,
                    },
                )
            ],
        ),
    },
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health_ready(request) -> Response:
    """
    Readiness check endpoint.
    
    Checks all dependencies (database, Redis, Celery).
    Returns 200 if all dependencies are healthy, 503 otherwise.
    Suitable for Kubernetes readiness probes and load balancer health checks.
    """
    checks = {
        "database": _check_database(),
        "redis": _check_redis(),
        "celery": _check_celery(),
    }
    
    # Determine overall status
    critical_checks = ["database"]  # Redis/Celery can be degraded
    is_healthy = all(
        checks[name]["status"] in ("healthy", "skipped")
        for name in critical_checks
    )
    
    response_data = {
        "status": "ready" if is_healthy else "not_ready",
        "checks": checks,
        "timestamp": time.time(),
    }
    
    http_status = status.HTTP_200_OK if is_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return Response(response_data, status=http_status)


@extend_schema(
    tags=["health"],
    summary="Detailed health check",
    description="""
Comprehensive health check with full system information.

Returns:
- Service version and environment info
- Python and Django versions
- Dependency health status
- Active incident statistics

**Security Note:** Consider protecting this endpoint in production.
    """,
    responses={
        200: OpenApiResponse(
            description="Detailed health information",
        ),
    },
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health_detailed(request) -> Response:
    """
    Detailed health check with all system information.
    
    Includes version, environment, and dependency status.
    Should be protected in production or limited to internal networks.
    """
    import django
    import sys
    
    checks = {
        "database": _check_database(),
        "redis": _check_redis(),
        "celery": _check_celery(),
    }
    
    # Count models
    from django.apps import apps
    model_count = len(apps.get_models())
    
    # Get incident stats
    from core.models import Incident
    from core.choices import IncidentStatus
    
    active_incidents = Incident.objects.filter(
        status__in=[IncidentStatus.TRIGGERED, IncidentStatus.ACKNOWLEDGED]
    ).count()
    
    return Response({
        "status": "ok",
        "service": "imas-manager",
        "version": getattr(settings, "VERSION", "1.0.0"),
        "environment": {
            "debug": settings.DEBUG,
            "python_version": sys.version,
            "django_version": django.__version__,
        },
        "checks": checks,
        "stats": {
            "model_count": model_count,
            "active_incidents": active_incidents,
        },
        "timestamp": time.time(),
    })
