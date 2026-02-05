"""
IMAS Manager - Enhanced Features Models

Contains Runbook, IncidentComment, IncidentTag, and EscalationPolicy models.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.utils import timezone

if TYPE_CHECKING:
    from django.contrib.auth.models import User

    from core.models.incident import Incident
    from core.models.organization import Service, Team


# =============================================================================
# Runbook Models
# =============================================================================


class RunbookStep(models.Model):
    """
    A single step in a runbook procedure.
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    runbook = models.ForeignKey(
        "Runbook",
        on_delete=models.CASCADE,
        related_name="steps",
    )
    order = models.PositiveIntegerField(
        help_text="Order of this step in the runbook.",
    )
    title = models.CharField(
        max_length=255,
        help_text="Short title for this step.",
    )
    description = models.TextField(
        help_text="Detailed instructions for this step.",
    )
    command = models.TextField(
        blank=True,
        help_text="Optional command to execute (for reference).",
    )
    expected_duration_minutes = models.PositiveIntegerField(
        default=5,
        help_text="Expected time to complete this step.",
    )
    is_critical = models.BooleanField(
        default=False,
        help_text="Whether this step is critical and must not be skipped.",
    )
    requires_confirmation = models.BooleanField(
        default=False,
        help_text="Whether this step requires explicit confirmation.",
    )
    rollback_instructions = models.TextField(
        blank=True,
        help_text="Instructions to rollback this step if needed.",
    )

    class Meta:
        verbose_name = "Runbook Step"
        verbose_name_plural = "Runbook Steps"
        ordering = ["runbook", "order"]
        unique_together = [["runbook", "order"]]

    def __str__(self) -> str:
        return f"Step {self.order}: {self.title}"


class Runbook(models.Model):
    """
    A runbook containing procedures for handling specific incidents.
    
    Runbooks can be linked to services, alert types, or used globally.
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    name = models.CharField(
        max_length=255,
        help_text="Name of the runbook.",
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="URL-friendly identifier.",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of when to use this runbook.",
    )
    
    # Targeting
    service: models.ForeignKey["Service"] = models.ForeignKey(
        "core.Service",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="runbooks",
        help_text="Service this runbook applies to (optional).",
    )
    alert_pattern = models.CharField(
        max_length=255,
        blank=True,
        help_text="Regex pattern to match alert names (e.g., 'HighCPU.*').",
    )
    severity_filter = models.CharField(
        max_length=20,
        blank=True,
        help_text="Only apply to this severity level (optional).",
    )
    
    # Content
    quick_actions = models.JSONField(
        default=list,
        blank=True,
        help_text="List of quick action buttons with commands.",
    )
    external_docs = models.JSONField(
        default=list,
        blank=True,
        help_text="List of external documentation links.",
    )
    
    # Metadata
    author: models.ForeignKey["User"] = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authored_runbooks",
    )
    version = models.CharField(
        max_length=20,
        default="1.0",
        help_text="Version of this runbook.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this runbook is active.",
    )
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this runbook was last used.",
    )
    usage_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of times this runbook has been used.",
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Runbook"
        verbose_name_plural = "Runbooks"
        ordering = ["service", "name"]

    def __str__(self) -> str:
        if self.service:
            return f"{self.service.name} - {self.name}"
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            base_slug = slugify(self.name)
            if self.service:
                base_slug = f"{slugify(self.service.name)}-{base_slug}"
            self.slug = base_slug
        super().save(*args, **kwargs)

    def record_usage(self):
        """Record that this runbook was used."""
        self.last_used_at = timezone.now()
        self.usage_count += 1
        self.save(update_fields=["last_used_at", "usage_count"])

    @classmethod
    def find_for_incident(cls, incident: "Incident") -> "Runbook | None":
        """
        Find the most appropriate runbook for an incident.
        
        Priority:
        1. Exact service + alert pattern match
        2. Service match only
        3. Alert pattern match (global)
        4. None
        """
        import re
        
        # Get alert name from incident (usually in title or description)
        alert_name = incident.title
        
        # Try service + pattern match
        if incident.service:
            runbooks = cls.objects.filter(
                service=incident.service,
                is_active=True,
            )
            for rb in runbooks:
                if rb.alert_pattern:
                    if re.search(rb.alert_pattern, alert_name, re.IGNORECASE):
                        return rb
                elif not rb.alert_pattern:
                    # Service-specific runbook without pattern
                    return rb
        
        # Try global pattern match
        global_runbooks = cls.objects.filter(
            service__isnull=True,
            alert_pattern__isnull=False,
            is_active=True,
        ).exclude(alert_pattern="")
        
        for rb in global_runbooks:
            if re.search(rb.alert_pattern, alert_name, re.IGNORECASE):
                return rb
        
        return None


# =============================================================================
# Incident Comments
# =============================================================================


class IncidentComment(models.Model):
    """
    Comments and updates on incidents.
    
    Used for:
    - Timeline updates from responders
    - Automated status updates
    - Post-incident notes
    """
    
    class CommentType(models.TextChoices):
        MANUAL = "manual", "Manual Comment"
        STATUS_CHANGE = "status", "Status Change"
        AUTOMATED = "auto", "Automated Update"
        ESCALATION = "escalation", "Escalation"
        RESOLUTION = "resolution", "Resolution Note"
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    incident: models.ForeignKey["Incident"] = models.ForeignKey(
        "core.Incident",
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author: models.ForeignKey["User"] = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incident_comments",
    )
    comment_type = models.CharField(
        max_length=20,
        choices=CommentType.choices,
        default=CommentType.MANUAL,
    )
    content = models.TextField(
        help_text="The comment content (supports Markdown).",
    )
    is_internal = models.BooleanField(
        default=False,
        help_text="Internal comments are not shown in public status pages.",
    )
    is_pinned = models.BooleanField(
        default=False,
        help_text="Pinned comments appear at the top.",
    )
    
    # For automated comments
    source_system = models.CharField(
        max_length=100,
        blank=True,
        help_text="Source system for automated comments (e.g., 'slack', 'pagerduty').",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional metadata for the comment.",
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Incident Comment"
        verbose_name_plural = "Incident Comments"
        ordering = ["-is_pinned", "created_at"]

    def __str__(self) -> str:
        author_name = self.author.username if self.author else "System"
        return f"{author_name}: {self.content[:50]}"


# =============================================================================
# Tags and Labels
# =============================================================================


class Tag(models.Model):
    """
    Reusable tags for categorizing incidents.
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Tag name (e.g., 'database', 'networking', 'customer-impacting').",
    )
    color = models.CharField(
        max_length=7,
        default="#6B7280",
        help_text="Hex color for display (e.g., '#FF0000').",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of when to use this tag.",
    )
    is_active = models.BooleanField(
        default=True,
    )
    
    # Auto-tagging rules
    auto_apply_pattern = models.CharField(
        max_length=255,
        blank=True,
        help_text="Regex pattern to auto-apply this tag.",
    )
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Tag"
        verbose_name_plural = "Tags"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class IncidentTag(models.Model):
    """
    Association between incidents and tags.
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    incident: models.ForeignKey["Incident"] = models.ForeignKey(
        "core.Incident",
        on_delete=models.CASCADE,
        related_name="incident_tags",
    )
    tag = models.ForeignKey(
        Tag,
        on_delete=models.CASCADE,
        related_name="incident_tags",
    )
    added_by: models.ForeignKey["User"] = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    added_at = models.DateTimeField(auto_now_add=True)
    is_auto_applied = models.BooleanField(
        default=False,
        help_text="Whether this tag was auto-applied.",
    )

    class Meta:
        verbose_name = "Incident Tag"
        verbose_name_plural = "Incident Tags"
        unique_together = [["incident", "tag"]]

    def __str__(self) -> str:
        return f"{self.incident.short_id}: {self.tag.name}"


# =============================================================================
# Escalation Policy
# =============================================================================


class EscalationPolicy(models.Model):
    """
    Defines escalation rules for incidents.
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    name = models.CharField(
        max_length=255,
        help_text="Name of the escalation policy.",
    )
    description = models.TextField(
        blank=True,
    )
    
    # Targeting
    team: models.ForeignKey["Team"] = models.ForeignKey(
        "core.Team",
        on_delete=models.CASCADE,
        related_name="escalation_policies",
        help_text="Team this policy applies to.",
    )
    severity_filter = models.CharField(
        max_length=20,
        blank=True,
        help_text="Only apply to this severity level (optional).",
    )
    
    # Escalation rules
    initial_delay_minutes = models.PositiveIntegerField(
        default=15,
        help_text="Minutes before first escalation if not acknowledged.",
    )
    repeat_interval_minutes = models.PositiveIntegerField(
        default=30,
        help_text="Minutes between repeated escalations.",
    )
    max_escalations = models.PositiveIntegerField(
        default=3,
        help_text="Maximum number of escalation attempts.",
    )
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Escalation Policy"
        verbose_name_plural = "Escalation Policies"
        ordering = ["team", "name"]

    def __str__(self) -> str:
        return f"{self.team.name}: {self.name}"


class EscalationStep(models.Model):
    """
    A step in an escalation policy.
    """
    
    class NotifyType(models.TextChoices):
        USER = "user", "Specific User"
        ON_CALL = "oncall", "Current On-Call"
        TEAM = "team", "Entire Team"
        MANAGER = "manager", "Team Manager"
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    policy = models.ForeignKey(
        EscalationPolicy,
        on_delete=models.CASCADE,
        related_name="steps",
    )
    order = models.PositiveIntegerField(
        help_text="Order in the escalation chain.",
    )
    notify_type = models.CharField(
        max_length=20,
        choices=NotifyType.choices,
        default=NotifyType.ON_CALL,
    )
    notify_user: models.ForeignKey["User"] = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="User to notify (if notify_type is 'user').",
    )
    delay_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Additional delay before this step (added to policy delay).",
    )
    notification_channels = models.JSONField(
        default=list,
        help_text="Channels to use: ['slack', 'email', 'sms', 'phone']",
    )

    class Meta:
        verbose_name = "Escalation Step"
        verbose_name_plural = "Escalation Steps"
        ordering = ["policy", "order"]
        unique_together = [["policy", "order"]]

    def __str__(self) -> str:
        return f"Step {self.order}: {self.get_notify_type_display()}"


# =============================================================================
# Incident Escalation Tracking
# =============================================================================


class IncidentEscalation(models.Model):
    """
    Tracks escalation events for an incident.
    """
    
    class EscalationStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        NOTIFIED = "notified", "Notified"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    incident: models.ForeignKey["Incident"] = models.ForeignKey(
        "core.Incident",
        on_delete=models.CASCADE,
        related_name="escalations",
    )
    policy = models.ForeignKey(
        EscalationPolicy,
        on_delete=models.SET_NULL,
        null=True,
    )
    step = models.ForeignKey(
        EscalationStep,
        on_delete=models.SET_NULL,
        null=True,
    )
    escalation_number = models.PositiveIntegerField(
        help_text="Which escalation attempt this is (1, 2, 3, ...).",
    )
    status = models.CharField(
        max_length=20,
        choices=EscalationStatus.choices,
        default=EscalationStatus.PENDING,
    )
    notified_user: models.ForeignKey["User"] = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_escalations",
    )
    channels_used = models.JSONField(
        default=list,
        help_text="Notification channels that were used.",
    )
    error_message = models.TextField(
        blank=True,
        help_text="Error message if escalation failed.",
    )
    
    scheduled_at = models.DateTimeField(
        help_text="When this escalation is/was scheduled.",
    )
    executed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this escalation was actually executed.",
    )
    acknowledged_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this escalation was acknowledged.",
    )

    class Meta:
        verbose_name = "Incident Escalation"
        verbose_name_plural = "Incident Escalations"
        ordering = ["incident", "escalation_number"]

    def __str__(self) -> str:
        return f"{self.incident.short_id} - Escalation #{self.escalation_number}"
