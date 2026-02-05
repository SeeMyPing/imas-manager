"""
IMAS Manager - Alert Ingestion Service

Core service for processing incoming alerts from monitoring systems.
Handles deduplication, rule matching, and incident creation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:
    from core.models import AlertFingerprint, AlertRule, Incident, Service

logger = logging.getLogger(__name__)


@dataclass
class AlertPayload:
    """Normalized alert payload from any source."""
    source: str
    alert_name: str
    status: str  # "firing" or "resolved"
    labels: dict
    annotations: dict
    starts_at: str | None = None
    ends_at: str | None = None
    generator_url: str | None = None
    
    @property
    def title(self) -> str:
        """Get alert title from annotations or name."""
        return (
            self.annotations.get("summary")
            or self.annotations.get("title")
            or self.annotations.get("message")
            or self.alert_name
        )
    
    @property
    def description(self) -> str:
        """Get alert description from annotations."""
        return (
            self.annotations.get("description")
            or self.annotations.get("message")
            or ""
        )
    
    @property
    def severity_label(self) -> str:
        """Get severity from labels."""
        return (
            self.labels.get("severity")
            or self.labels.get("priority")
            or self.labels.get("level")
            or "warning"
        )


class AlertIngestionService:
    """
    Service for ingesting and processing alerts.
    
    Responsibilities:
    - Parse alerts from different sources
    - Deduplicate alerts using fingerprints
    - Match alerts to rules
    - Create incidents based on rules
    """

    def process_alert(self, payload: AlertPayload) -> dict:
        """
        Process an incoming alert.
        
        Args:
            payload: Normalized alert payload.
            
        Returns:
            Dict with processing result.
        """
        from core.models import AlertFingerprint, AlertSource, AlertStatus
        
        # Compute fingerprint
        fingerprint = AlertFingerprint.compute_fingerprint(
            alert_name=payload.alert_name,
            labels=payload.labels,
            source=payload.source,
        )
        
        # Check for existing fingerprint
        existing = AlertFingerprint.objects.filter(fingerprint=fingerprint).first()
        
        if payload.status.lower() == "resolved":
            return self._handle_resolved(existing, payload, fingerprint)
        else:
            return self._handle_firing(existing, payload, fingerprint)

    def _handle_firing(
        self,
        existing: "AlertFingerprint | None",
        payload: AlertPayload,
        fingerprint: str,
    ) -> dict:
        """Handle a firing alert."""
        from core.models import AlertFingerprint, AlertStatus
        
        if existing:
            # Check suppression window
            if self._is_suppressed(existing, payload):
                logger.info(f"Alert {payload.alert_name} suppressed (duplicate)")
                return {
                    "action": "suppressed",
                    "fingerprint": fingerprint,
                    "incident_id": str(existing.incident_id) if existing.incident else None,
                }
            
            # Increment fire count
            existing.increment_fire_count()
            alert_fp = existing
            is_new = False
        else:
            # Create new fingerprint
            alert_fp = AlertFingerprint.objects.create(
                fingerprint=fingerprint,
                source=payload.source,
                alert_name=payload.alert_name,
                labels=payload.labels,
                annotations=payload.annotations,
                status=AlertStatus.FIRING,
            )
            is_new = True
        
        # Find matching rule and create incident
        incident = None
        if alert_fp.auto_create_incident and (is_new or not alert_fp.incident):
            incident = self._create_incident_from_alert(alert_fp, payload)
            if incident:
                alert_fp.incident = incident
                alert_fp.save(update_fields=["incident"])
        
        return {
            "action": "created" if is_new else "updated",
            "fingerprint": fingerprint,
            "fire_count": alert_fp.fire_count,
            "incident_id": str(incident.id) if incident else None,
            "incident_short_id": incident.short_id if incident else None,
        }

    def _handle_resolved(
        self,
        existing: "AlertFingerprint | None",
        payload: AlertPayload,
        fingerprint: str,
    ) -> dict:
        """Handle a resolved alert."""
        if not existing:
            logger.warning(f"Resolved alert without firing: {payload.alert_name}")
            return {
                "action": "ignored",
                "reason": "no_matching_alert",
                "fingerprint": fingerprint,
            }
        
        existing.mark_resolved()
        
        # Check if we should auto-resolve the incident
        if existing.incident:
            rule = self._find_matching_rule(payload)
            if rule and rule.auto_resolve:
                self._auto_resolve_incident(existing.incident)
        
        return {
            "action": "resolved",
            "fingerprint": fingerprint,
            "incident_id": str(existing.incident_id) if existing.incident else None,
        }

    def _is_suppressed(
        self,
        existing: "AlertFingerprint",
        payload: AlertPayload,
    ) -> bool:
        """Check if alert should be suppressed."""
        rule = self._find_matching_rule(payload)
        suppress_minutes = rule.suppress_duplicates_minutes if rule else 5
        
        threshold = timezone.now() - timedelta(minutes=suppress_minutes)
        return existing.last_fired_at > threshold

    def _find_matching_rule(self, payload: AlertPayload) -> "AlertRule | None":
        """Find first matching alert rule."""
        from core.models import AlertRule
        
        rules = AlertRule.objects.filter(is_active=True)
        
        for rule in rules:
            if rule.matches_alert(payload.alert_name, payload.labels, payload.source):
                return rule
        
        return None

    def _create_incident_from_alert(
        self,
        alert_fp: "AlertFingerprint",
        payload: AlertPayload,
    ) -> "Incident | None":
        """Create an incident from an alert."""
        from core.models import Incident
        from core.choices import IncidentSeverity, IncidentStatus
        
        rule = self._find_matching_rule(payload)
        
        # Determine severity
        if rule:
            severity = rule.get_severity(payload.labels)
        else:
            severity = self._map_default_severity(payload.severity_label)
        
        # Determine service
        service = rule.target_service if rule else self._find_service(payload.labels)
        
        if not service:
            logger.warning(f"No service found for alert {payload.alert_name}")
            # Still create incident but without service link
        
        with transaction.atomic():
            incident = Incident.objects.create(
                title=payload.title,
                description=self._build_description(payload),
                service=service,
                severity=severity,
                status=IncidentStatus.TRIGGERED,
                detected_at=timezone.now(),
            )
            
            # Add event log
            from core.models import IncidentEvent
            from core.choices import IncidentEventType
            
            IncidentEvent.objects.create(
                incident=incident,
                type=IncidentEventType.STATUS_CHANGE,
                message=f"Incident auto-created from {payload.source} alert: {payload.alert_name}",
            )
            
            logger.info(f"Created incident {incident.short_id} from alert {payload.alert_name}")
            
            # Trigger notifications asynchronously
            self._trigger_notifications(incident)
        
        return incident

    def _map_default_severity(self, severity_label: str) -> str:
        """Map common severity labels to incident severity."""
        from core.choices import IncidentSeverity
        
        severity_lower = severity_label.lower()
        
        if severity_lower in ("critical", "fatal", "emergency", "p1"):
            return IncidentSeverity.SEV1_CRITICAL
        elif severity_lower in ("high", "error", "p2"):
            return IncidentSeverity.SEV2_HIGH
        elif severity_lower in ("medium", "warning", "warn", "p3"):
            return IncidentSeverity.SEV3_MEDIUM
        else:
            return IncidentSeverity.SEV4_LOW

    def _find_service(self, labels: dict) -> "Service | None":
        """Try to find a service based on alert labels."""
        from core.models import Service
        
        # Common label names for service identification
        service_labels = ["service", "job", "app", "application", "component"]
        
        for label in service_labels:
            if label in labels:
                service_name = labels[label]
                service = Service.objects.filter(name__iexact=service_name).first()
                if service:
                    return service
        
        return None

    def _build_description(self, payload: AlertPayload) -> str:
        """Build incident description from alert."""
        lines = []
        
        if payload.description:
            lines.append(payload.description)
        
        lines.append("")
        lines.append("**Alert Details:**")
        lines.append(f"- Source: {payload.source}")
        lines.append(f"- Alert Name: {payload.alert_name}")
        
        if payload.labels:
            lines.append("")
            lines.append("**Labels:**")
            for key, value in sorted(payload.labels.items()):
                lines.append(f"- {key}: {value}")
        
        if payload.generator_url:
            lines.append("")
            lines.append(f"[View in monitoring]({payload.generator_url})")
        
        return "\n".join(lines)

    def _auto_resolve_incident(self, incident: "Incident") -> None:
        """Auto-resolve an incident."""
        from core.choices import IncidentStatus
        
        if incident.status == IncidentStatus.RESOLVED:
            return
        
        incident.status = IncidentStatus.RESOLVED
        incident.resolved_at = timezone.now()
        incident.save(update_fields=["status", "resolved_at"])
        
        from core.models import IncidentEvent
        from core.choices import IncidentEventType
        
        IncidentEvent.objects.create(
            incident=incident,
            type=IncidentEventType.STATUS_CHANGE,
            message="Incident auto-resolved: source alert resolved",
        )
        
        logger.info(f"Auto-resolved incident {incident.short_id}")

    def _trigger_notifications(self, incident: "Incident") -> None:
        """Trigger async notifications for new incident."""
        try:
            from tasks.incident_tasks import send_incident_notifications
            send_incident_notifications.delay(str(incident.id))
        except Exception as e:
            logger.error(f"Failed to trigger notifications: {e}")


# Singleton instance
alert_service = AlertIngestionService()
