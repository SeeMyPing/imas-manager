"""
IMAS Manager - Dashboard App Configuration
"""
from django.apps import AppConfig


class DashboardConfig(AppConfig):
    """Dashboard application configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "dashboard"
    verbose_name = "IMAS Dashboard"
