"""
IMAS Manager - Organization Models

Contains Team, Service, ImpactScope, and OnCallSchedule models.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.choices import ServiceCriticality

if TYPE_CHECKING:
    from django.contrib.auth.models import User


class Team(models.Model):
    """
    Represents a team responsible for services and incident response.
    
    Examples: "SRE Core", "Backend Payment", "Legal Team", "Security Team"
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for the team.",
    )
    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Display name of the team.",
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        blank=True,
        help_text="URL-friendly identifier for the team.",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of the team's responsibilities.",
    )
    email = models.EmailField(
        blank=True,
        help_text="Team distribution list email.",
    )
    slack_channel = models.CharField(
        max_length=100,
        blank=True,
        help_text="Slack channel name (without #) for team notifications.",
    )
    slack_channel_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Slack channel ID for team notifications (e.g., C0123456789).",
    )
    current_on_call: models.ForeignKey["User"] = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="on_call_teams",
        help_text="The person currently on-call for this team.",
    )
    escalation_timeout_minutes = models.PositiveIntegerField(
        default=15,
        help_text="Minutes before escalating to next on-call if no acknowledgment.",
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Team"
        verbose_name_plural = "Teams"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_current_on_call(self) -> "User | None":
        """
        Get the current on-call user, checking schedule first.
        
        Priority:
        1. Active OnCallSchedule for current time
        2. Fallback to current_on_call field
        """
        now = timezone.now()
        schedule = self.oncall_schedules.filter(
            start_time__lte=now,
            end_time__gt=now,
        ).first()
        
        if schedule:
            return schedule.user
        return self.current_on_call

    def get_escalation_chain(self) -> list["User"]:
        """
        Get the escalation chain for this team.
        
        Returns list of users to escalate to in order.
        """
        now = timezone.now()
        schedules = self.oncall_schedules.filter(
            start_time__lte=now + timedelta(days=7),
            end_time__gt=now,
        ).order_by("escalation_level").select_related("user")
        
        return [s.user for s in schedules if s.user]


class Service(models.Model):
    """
    Represents a technical asset or component.
    
    Examples: "Redis Cluster", "Checkout API", "User Database"
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for the service.",
    )
    name = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Unique name of the service (used for API lookups).",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of the service.",
    )
    owner_team = models.ForeignKey(
        Team,
        on_delete=models.PROTECT,
        related_name="services",
        help_text="The team responsible for this service.",
    )
    runbook_url = models.URLField(
        blank=True,
        help_text="Link to the runbook/documentation for incident resolution.",
    )
    repository_url = models.URLField(
        blank=True,
        help_text="Link to the source code repository.",
    )
    monitoring_url = models.URLField(
        blank=True,
        help_text="Link to the monitoring dashboard (Datadog, Grafana, etc.).",
    )
    criticality = models.CharField(
        max_length=20,
        choices=ServiceCriticality.choices,
        default=ServiceCriticality.TIER_3,
        db_index=True,
        help_text="Criticality tier of the service.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this service is currently active.",
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Service"
        verbose_name_plural = "Services"
        ordering = ["criticality", "name"]
        indexes = [
            models.Index(fields=["criticality", "name"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_criticality_display()})"


class ImpactScope(models.Model):
    """
    Represents transverse/functional impact domains.
    
    Examples: "Security Breach", "GDPR/Legal", "Public Relations"
    Used to trigger specific notifications (e.g., notify DPO for GDPR).
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for the impact scope.",
    )
    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Name of the impact scope.",
    )
    description = models.TextField(
        blank=True,
        help_text="Detailed description of this impact scope.",
    )
    mandatory_notify_email = models.EmailField(
        blank=True,
        help_text="Email address that MUST be notified when this scope is impacted (e.g., dpo@company.com).",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this scope is currently active.",
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Impact Scope"
        verbose_name_plural = "Impact Scopes"
        ordering = ["name"]

    def __str__(self) -> str:
        status = "" if self.is_active else " (inactive)"
        return f"{self.name}{status}"


class OnCallSchedule(models.Model):
    """
    Represents an on-call rotation schedule entry.
    
    Used to determine who is on-call for a team at any given time.
    Supports escalation levels for multi-tier on-call.
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="oncall_schedules",
        help_text="Team this schedule belongs to.",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="oncall_schedules",
        help_text="User on-call during this period.",
    )
    start_time = models.DateTimeField(
        db_index=True,
        help_text="Start of the on-call period.",
    )
    end_time = models.DateTimeField(
        db_index=True,
        help_text="End of the on-call period.",
    )
    escalation_level = models.PositiveSmallIntegerField(
        default=1,
        help_text="Escalation tier (1=primary, 2=secondary, etc.).",
    )
    notes = models.TextField(
        blank=True,
        help_text="Notes about this on-call period (e.g., coverage reason).",
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "On-Call Schedule"
        verbose_name_plural = "On-Call Schedules"
        ordering = ["start_time", "escalation_level"]
        indexes = [
            models.Index(fields=["team", "start_time", "end_time"]),
            models.Index(fields=["user", "start_time"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_time__gt=models.F("start_time")),
                name="oncall_end_after_start",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.user} - {self.team.name} "
            f"({self.start_time.strftime('%Y-%m-%d %H:%M')} → "
            f"{self.end_time.strftime('%Y-%m-%d %H:%M')})"
        )

    @property
    def is_active(self) -> bool:
        """Check if this schedule is currently active."""
        now = timezone.now()
        return self.start_time <= now < self.end_time

    @property
    def duration_hours(self) -> float:
        """Get the duration of this on-call period in hours."""
        delta = self.end_time - self.start_time
        return delta.total_seconds() / 3600

    @classmethod
    def get_current_oncall(cls, team: Team) -> "OnCallSchedule | None":
        """Get the current primary on-call schedule for a team."""
        now = timezone.now()
        return cls.objects.filter(
            team=team,
            start_time__lte=now,
            end_time__gt=now,
            escalation_level=1,
        ).first()
