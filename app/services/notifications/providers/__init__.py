"""
IMAS Manager - Notification Providers Package

Contains provider implementations for different notification channels.
"""
from __future__ import annotations

from services.notifications.providers.base import (
    BaseNotificationProvider,
    NotificationProviderFactory,
)
from services.notifications.providers.slack import SlackProvider
from services.notifications.providers.email import EmailProvider
from services.notifications.providers.discord import DiscordProvider
from services.notifications.providers.ovh_sms import OVHSMSProvider
from services.notifications.providers.webhook import WebhookProvider
from services.notifications.providers.ntfy import NtfyProvider

__all__ = [
    "BaseNotificationProvider",
    "NotificationProviderFactory",
    "SlackProvider",
    "EmailProvider",
    "DiscordProvider",
    "OVHSMSProvider",
    "WebhookProvider",
    "NtfyProvider",
]
