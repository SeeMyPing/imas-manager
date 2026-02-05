"""
IMAS Manager - Core App Configuration
"""
from __future__ import annotations

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Configuration for the Core application."""
    
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "IMAS Core"

    def ready(self) -> None:
        """Import signals when the app is ready."""
        from core import signals  # noqa: F401
