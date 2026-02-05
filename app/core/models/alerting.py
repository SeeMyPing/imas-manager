"""
IMAS Manager - Alerting Models

Models for alert ingestion, deduplication, and auto-incident creation.
"""
from __future__ import annotations

import hashlib
import uuid
from typing import TYPE_CHECKING

from django.db import models
from django.utils import timezone

if TYPE_CHECKING:
    from core.models import Incident, Service


class AlertSource(models.TextChoices):
    """Supported alerting sources."""
    ALERTMANAGER = "ALERTMANAGER", "Prometheus Alertmanager"
    DATADOG = "DATADOG", "Datadog"
    GRAFANA = "GRAFANA", "Grafana"
    CUSTOM = "CUSTOM", "Custom Webhook"


class AlertStatus(models.TextChoices):
    """Alert lifecycle status."""
    FIRING = "FIRING", "Firing"
    RESOLVED = "RESOLVED", "Resolved"
    SUPPRESSED = "SUPPRESSED", "Suppressed"


class AlertFingerprint(models.Model):
    """
    Tracks unique alerts for deduplication.
    
    The fingerprint is a hash of key alert labels to identify
    the same alert across multiple firings.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Alert identification
    fingerprint = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="SHA256 hash of alert labels for deduplication"
    )
    source = models.CharField(
        max_length=20,
        choices=AlertSource.choices,
        default=AlertSource.CUSTOM,
    )
    alert_name = models.CharField(max_length=255, db_index=True)
    
    # Source metadata
    labels = models.JSONField(default=dict, help_text="Original alert labels")
    annotations = models.JSONField(default=dict, help_text="Alert annotations")
    
    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=AlertStatus.choices,
        default=AlertStatus.FIRING,
    )
    fire_count = models.PositiveIntegerField(
        default=1,
        help_text="Number of times this alert has fired"
    )
    
    # Timestamps
    first_fired_at = models.DateTimeField(auto_now_add=True)
    last_fired_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    # Link to created incident (if any)
    incident = models.ForeignKey(
        "core.Incident",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_alerts",
    )
    
    # Auto-creation settings
    auto_create_incident = models.BooleanField(
        default=True,
        help_text="Whether to auto-create incident for this alert"
    )
    
    class Meta:
        ordering = ["-last_fired_at"]
        indexes = [
            models.Index(fields=["source", "alert_name"]),
            models.Index(fields=["status", "last_fired_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.alert_name} ({self.fingerprint[:8]})"

    @classmethod
    def compute_fingerprint(
        cls,
        alert_name: str,
        labels: dict,
        source: str = "CUSTOM",
    ) -> str:
        """
        Compute a unique fingerprint for an alert.
        
        Uses alert name + sorted labels to create a stable hash.
        
        Args:
            alert_name: Name of the alert.
            labels: Dict of alert labels.
            source: Alert source type.
            
        Returns:
            SHA256 hex digest.
        """
        # Sort labels for stable hashing
        sorted_labels = sorted(labels.items())
        fingerprint_data = f"{source}:{alert_name}:{sorted_labels}"
        return hashlib.sha256(fingerprint_data.encode()).hexdigest()

    def mark_resolved(self) -> None:
        """Mark this alert as resolved."""
        self.status = AlertStatus.RESOLVED
        self.resolved_at = timezone.now()
        self.save(update_fields=["status", "resolved_at"])

    def increment_fire_count(self) -> None:
        """Increment fire count and update timestamp."""
        self.fire_count += 1
        self.last_fired_at = timezone.now()
        self.status = AlertStatus.FIRING
        self.resolved_at = None
        self.save(update_fields=["fire_count", "last_fired_at", "status", "resolved_at"])


class AlertRule(models.Model):
    """
    Rules for mapping alerts to incident severity and services.
    
    Allows configuring how incoming alerts should create incidents.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    # Matching criteria
    source = models.CharField(
        max_length=20,
        choices=AlertSource.choices,
        blank=True,
        help_text="Match specific source, or empty for all"
    )
    alert_name_pattern = models.CharField(
        max_length=255,
        blank=True,
        help_text="Regex pattern to match alert names"
    )
    label_matchers = models.JSONField(
        default=dict,
        help_text="Label key-value pairs that must match"
    )
    
    # Incident creation settings
    target_service = models.ForeignKey(
        "core.Service",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Service to assign to created incidents"
    )
    severity_mapping = models.JSONField(
        default=dict,
        help_text="Map alert severity labels to incident severity"
    )
    default_severity = models.CharField(
        max_length=20,
        default="SEV3_MEDIUM",
        help_text="Default severity if no mapping matches"
    )
    
    # Behavior
    auto_create = models.BooleanField(
        default=True,
        help_text="Automatically create incidents for matching alerts"
    )
    auto_resolve = models.BooleanField(
        default=False,
        help_text="Auto-resolve incident when alert resolves"
    )
    suppress_duplicates_minutes = models.PositiveIntegerField(
        default=5,
        help_text="Suppress duplicate alerts within this window"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name

    def matches_alert(self, alert_name: str, labels: dict, source: str) -> bool:
        """
        Check if this rule matches an incoming alert.
        
        Args:
            alert_name: Name of the alert.
            labels: Alert labels.
            source: Alert source.
            
        Returns:
            True if rule matches.
        """
        import re
        
        # Check source
        if self.source and self.source != source:
            return False
        
        # Check alert name pattern
        if self.alert_name_pattern:
            if not re.match(self.alert_name_pattern, alert_name, re.IGNORECASE):
                return False
        
        # Check label matchers
        for key, value in self.label_matchers.items():
            if labels.get(key) != value:
                return False
        
        return True

    def get_severity(self, labels: dict) -> str:
        """
        Get incident severity based on alert labels.
        
        Args:
            labels: Alert labels.
            
        Returns:
            Incident severity string.
        """
        # Check severity mapping
        for label_key, mapping in self.severity_mapping.items():
            label_value = labels.get(label_key, "")
            if label_value in mapping:
                return mapping[label_value]
        
        return self.default_severity
