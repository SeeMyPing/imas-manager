"""
IMAS Manager - Models Package

Exposes all models from submodules for convenient imports.
"""
from __future__ import annotations

from core.models.alerting import AlertFingerprint, AlertRule, AlertSource, AlertStatus
from core.models.audit import AuditAction, AuditLog
from core.models.configuration import NotificationProvider
from core.models.features import (
    EscalationPolicy,
    EscalationStep,
    IncidentComment,
    IncidentEscalation,
    IncidentTag,
    Runbook,
    RunbookStep,
    Tag,
)
from core.models.incident import Incident, IncidentEvent
from core.models.organization import ImpactScope, OnCallSchedule, Service, Team

__all__ = [
    # Organization
    "Team",
    "Service",
    "ImpactScope",
    "OnCallSchedule",
    # Incident
    "Incident",
    "IncidentEvent",
    # Features
    "Runbook",
    "RunbookStep",
    "IncidentComment",
    "Tag",
    "IncidentTag",
    "EscalationPolicy",
    "EscalationStep",
    "IncidentEscalation",
    # Configuration
    "NotificationProvider",
    # Alerting
    "AlertFingerprint",
    "AlertRule",
    "AlertSource",
    "AlertStatus",
    # Audit
    "AuditLog",
    "AuditAction",
]
