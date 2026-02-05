"""
IMAS Manager - URL Configuration
"""
from __future__ import annotations

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from api.health import health_check, health_detailed, health_live, health_ready

urlpatterns = [
    # Health Checks (before auth to ensure availability)
    path("health/", health_check, name="health"),
    path("health/live/", health_live, name="health-live"),
    path("health/ready/", health_ready, name="health-ready"),
    path("health/detailed/", health_detailed, name="health-detailed"),
    
    # Admin
    path("admin/", admin.site.urls),
    
    # Dashboard (Web UI)
    path("", include("dashboard.urls")),
    
    # Authentication
    path("accounts/login/", admin.site.login, name="login"),
    path("accounts/logout/", admin.site.logout, name="logout"),
    
    # API v1
    path("api/v1/", include("api.v1.urls")),
    
    # API Authentication (obtain token)
    path("api/auth/", include("rest_framework.urls")),
    path("api/token/", include("api.auth.urls")),
    
    # API Documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui-alt"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

# Admin site customization
admin.site.site_header = "IMAS Manager"
admin.site.site_title = "IMAS Admin"
admin.site.index_title = "Incident Management At Scale"
