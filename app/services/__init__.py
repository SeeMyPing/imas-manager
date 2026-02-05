"""
IMAS Manager - Services Package

Contains business logic services following the Service Layer pattern.
"""
from __future__ import annotations

from services.escalation import EscalationService
from services.runbook import RunbookAutoAttacher, RunbookService, TagService
from services.templates import (
    EmailTemplates,
    NotificationContext,
    SlackTemplates,
    TemplateRegistry,
)

__all__ = [
    # Escalation
    "EscalationService",
    # Runbooks
    "RunbookService",
    "RunbookAutoAttacher",
    "TagService",
    # Templates
    "NotificationContext",
    "TemplateRegistry",
    "SlackTemplates",
    "EmailTemplates",
]
