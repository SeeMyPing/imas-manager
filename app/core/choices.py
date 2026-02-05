"""
IMAS Manager - Choice Fields

Centralized definition of all ChoiceField options used across models.
Using Django's TextChoices for better type safety and admin display.
"""
from __future__ import annotations

from django.db import models


class ServiceCriticality(models.TextChoices):
    """
    Service criticality levels.
    
    Determines the priority of incident response based on the affected service.
    """
    TIER_1_CRITICAL = "TIER_1_CRITICAL", "Tier 1 - Critical"
    TIER_2 = "TIER_2", "Tier 2 - High"
    TIER_3 = "TIER_3", "Tier 3 - Standard"


class IncidentSeverity(models.TextChoices):
    """
    Incident severity levels.
    
    SEV1 and SEV2 trigger War Room creation automatically.
    """
    SEV1_CRITICAL = "SEV1_CRITICAL", "SEV1 - Critical"
    SEV2_HIGH = "SEV2_HIGH", "SEV2 - High"
    SEV3_MEDIUM = "SEV3_MEDIUM", "SEV3 - Medium"
    SEV4_LOW = "SEV4_LOW", "SEV4 - Low"


class IncidentStatus(models.TextChoices):
    """
    Incident lifecycle status.
    
    Transitions:
    - TRIGGERED -> ACKNOWLEDGED (sets acknowledged_at)
    - ACKNOWLEDGED -> MITIGATED
    - MITIGATED -> RESOLVED (sets resolved_at)
    - Any -> RESOLVED (sets resolved_at)
    """
    TRIGGERED = "TRIGGERED", "Triggered"
    ACKNOWLEDGED = "ACKNOWLEDGED", "Acknowledged"
    MITIGATED = "MITIGATED", "Mitigated"
    RESOLVED = "RESOLVED", "Resolved"


class IncidentEventType(models.TextChoices):
    """
    Types of events that can occur during incident lifecycle.
    
    Used for the audit log / timeline.
    """
    STATUS_CHANGE = "STATUS_CHANGE", "Status Change"
    NOTE = "NOTE", "Note Added"
    ALERT_SENT = "ALERT_SENT", "Alert Sent"
    DOCUMENT_CREATED = "DOCUMENT_CREATED", "Document Created"
    SCOPE_ADDED = "SCOPE_ADDED", "Impact Scope Added"
    WAR_ROOM_CREATED = "WAR_ROOM_CREATED", "War Room Created"
    ESCALATION = "ESCALATION", "Escalation"
    REMINDER = "REMINDER", "Reminder Sent"
    ARCHIVED = "ARCHIVED", "Archived"


class NotificationProviderType(models.TextChoices):
    """
    Supported notification provider types.
    
    Each type requires specific configuration in the JSONField.
    """
    # Chat/Collaboration
    SLACK = "SLACK", "Slack"
    DISCORD = "DISCORD", "Discord"
    TEAMS = "TEAMS", "Microsoft Teams"
    
    # SMS
    OVH_SMS = "OVH_SMS", "OVH SMS"
    
    # Email
    SMTP = "SMTP", "SMTP Email"
    SCALEWAY_TEM = "SCALEWAY_TEM", "Scaleway Transactional Email"
    
    # Webhooks / External Alerting
    WEBHOOK = "WEBHOOK", "Generic Webhook"
    PAGERDUTY = "PAGERDUTY", "PagerDuty"
    OPSGENIE = "OPSGENIE", "Opsgenie"
    
    # Push Notifications
    NTFY = "NTFY", "ntfy.sh"
