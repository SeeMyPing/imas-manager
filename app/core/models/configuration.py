"""
IMAS Manager - Configuration Models

Contains NotificationProvider model for dynamic notification configuration.
"""
from __future__ import annotations

import uuid

from django.db import models

from core.choices import NotificationProviderType


class NotificationProvider(models.Model):
    """
    Configuration for notification providers.
    
    Allows dynamic configuration of notification channels without redeployment.
    Each provider stores its specific configuration in the JSONField.
    
    Example configurations:
    - Slack: {"bot_token": "xoxb-...", "default_channel": "#incidents"}
    - OVH SMS: {"app_key": "...", "app_secret": "...", "consumer_key": "...", "service_name": "..."}
    - SMTP: {"host": "smtp.example.com", "port": 587, "username": "...", "password": "..."}
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    name = models.CharField(
        max_length=255,
        help_text="Friendly name for this provider (e.g., 'Slack Prod', 'SMS Astreinte').",
    )
    type = models.CharField(
        max_length=20,
        choices=NotificationProviderType.choices,
        db_index=True,
        help_text="Type of notification provider.",
    )
    config = models.JSONField(
        default=dict,
        help_text="Provider-specific configuration (tokens, webhooks, etc.). Stored as JSON.",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this provider is currently active and should be used.",
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Notification Provider"
        verbose_name_plural = "Notification Providers"
        ordering = ["type", "name"]
        indexes = [
            models.Index(fields=["type", "is_active"]),
        ]

    def __str__(self) -> str:
        status = "✓" if self.is_active else "✗"
        return f"[{status}] {self.name} ({self.get_type_display()})"

    def get_config_value(self, key: str, default: str | None = None) -> str | None:
        """
        Safely retrieve a configuration value.
        
        Args:
            key: The configuration key to retrieve.
            default: Default value if key is not found.
            
        Returns:
            The configuration value or default.
        """
        return self.config.get(key, default)
