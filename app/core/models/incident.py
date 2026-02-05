"""
IMAS Manager - Incident Models

Contains Incident and IncidentEvent models.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models

from core.choices import IncidentEventType, IncidentSeverity, IncidentStatus

if TYPE_CHECKING:
    from django.contrib.auth.models import User

    from core.models.organization import ImpactScope, Service


class Incident(models.Model):
    """
    Core incident model representing a technical incident.
    
    Tracks the full lifecycle from detection to resolution,
    including automation links (LID, War Room) and KPI timestamps.
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for the incident.",
    )
    title = models.CharField(
        max_length=500,
        help_text="Short descriptive title of the incident.",
    )
    description = models.TextField(
        blank=True,
        help_text="Detailed description of the incident.",
    )
    
    # -------------------------------------------------------------------------
    # Relations
    # -------------------------------------------------------------------------
    service: models.ForeignKey["Service"] = models.ForeignKey(
        "core.Service",
        on_delete=models.PROTECT,
        related_name="incidents",
        help_text="The primary service affected by this incident.",
    )
    impacted_scopes: models.ManyToManyField["ImpactScope"] = models.ManyToManyField(
        "core.ImpactScope",
        blank=True,
        related_name="incidents",
        help_text="Functional domains impacted (Legal, Security, PR, etc.).",
    )
    lead: models.ForeignKey["User"] = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="led_incidents",
        help_text="Person leading the incident response.",
    )
    
    # -------------------------------------------------------------------------
    # State
    # -------------------------------------------------------------------------
    severity = models.CharField(
        max_length=20,
        choices=IncidentSeverity.choices,
        default=IncidentSeverity.SEV3_MEDIUM,
        db_index=True,
        help_text="Severity level of the incident.",
    )
    status = models.CharField(
        max_length=20,
        choices=IncidentStatus.choices,
        default=IncidentStatus.TRIGGERED,
        db_index=True,
        help_text="Current status in the incident lifecycle.",
    )
    
    # -------------------------------------------------------------------------
    # Automation Links
    # -------------------------------------------------------------------------
    lid_link = models.URLField(
        blank=True,
        verbose_name="LID Link",
        help_text="Link to the Lead Incident Document (Google Doc).",
    )
    war_room_link = models.URLField(
        blank=True,
        help_text="Link to the War Room channel (Slack/Discord).",
    )
    war_room_id = models.CharField(
        max_length=50,
        blank=True,
        help_text="Technical ID of the War Room channel (for archiving).",
    )
    
    # -------------------------------------------------------------------------
    # Timestamps (KPIs)
    # -------------------------------------------------------------------------
    detected_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the incident was detected by monitoring (from external alert).",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the incident was created in IMAS.",
    )
    acknowledged_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When a human first acknowledged the incident.",
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the incident was marked as resolved.",
    )
    
    # -------------------------------------------------------------------------
    # Archival
    # -------------------------------------------------------------------------
    is_archived = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this incident has been archived.",
    )

    class Meta:
        verbose_name = "Incident"
        verbose_name_plural = "Incidents"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "severity"]),
            models.Index(fields=["service", "status"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self) -> str:
        return f"INC-{self.short_id} | {self.title[:50]}"

    @property
    def short_id(self) -> str:
        """
        Short identifier for display (first 8 chars of UUID, uppercase).
        
        Example: "A1B2C3D4"
        """
        return str(self.id)[:8].upper()

    # -------------------------------------------------------------------------
    # Computed Properties (KPIs)
    # -------------------------------------------------------------------------
    @property
    def mttd(self) -> timedelta | None:
        """
        Mean Time To Detect.
        
        Time between external detection and incident creation in IMAS.
        Returns None if detected_at is not set.
        """
        if self.detected_at and self.created_at:
            return self.created_at - self.detected_at
        return None

    @property
    def mttd_seconds(self) -> int | None:
        """MTTD in seconds for API serialization."""
        return int(self.mttd.total_seconds()) if self.mttd else None

    @property
    def mtta(self) -> timedelta | None:
        """
        Mean Time To Acknowledge.
        
        Time between incident creation and first human acknowledgement.
        """
        if self.acknowledged_at and self.created_at:
            return self.acknowledged_at - self.created_at
        return None

    @property
    def mtta_seconds(self) -> int | None:
        """MTTA in seconds for API serialization."""
        return int(self.mtta.total_seconds()) if self.mtta else None

    @property
    def mttr(self) -> timedelta | None:
        """
        Mean Time To Resolve.
        
        Time between incident creation and resolution.
        """
        if self.resolved_at and self.created_at:
            return self.resolved_at - self.created_at
        return None

    @property
    def mttr_seconds(self) -> int | None:
        """MTTR in seconds for API serialization."""
        return int(self.mttr.total_seconds()) if self.mttr else None

    @property
    def is_critical(self) -> bool:
        """
        Determines if the incident requires a War Room.
        
        Returns True for SEV1 and SEV2 incidents.
        """
        return self.severity in [
            IncidentSeverity.SEV1_CRITICAL,
            IncidentSeverity.SEV2_HIGH,
        ]

    @property
    def is_open(self) -> bool:
        """Returns True if the incident is not yet resolved."""
        return self.status != IncidentStatus.RESOLVED

    @property
    def short_id(self) -> str:
        """Returns the first 8 characters of the UUID for display."""
        return str(self.id)[:8].upper()


class IncidentEvent(models.Model):
    """
    Audit log entry for incident timeline.
    
    Records all significant events during incident lifecycle:
    status changes, notes, alerts sent, documents created, etc.
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    incident = models.ForeignKey(
        Incident,
        on_delete=models.CASCADE,
        related_name="events",
        help_text="The incident this event belongs to.",
    )
    type = models.CharField(
        max_length=30,
        choices=IncidentEventType.choices,
        db_index=True,
        help_text="Type of event.",
    )
    message = models.TextField(
        help_text="Description of what happened.",
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When this event occurred.",
    )
    
    # Optional: who triggered this event
    created_by: models.ForeignKey["User"] = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incident_events",
        help_text="User who triggered this event (if applicable).",
    )

    class Meta:
        verbose_name = "Incident Event"
        verbose_name_plural = "Incident Events"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["incident", "-timestamp"]),
        ]

    def __str__(self) -> str:
        return f"[{self.get_type_display()}] {self.message[:50]}"
