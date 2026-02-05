"""
IMAS Manager - Django Signals

Handles automatic KPI timestamp updates and event logging.
"""
from __future__ import annotations

import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from core.choices import IncidentEventType, IncidentStatus
from core.models.incident import Incident, IncidentEvent

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Incident)
def auto_set_kpi_timestamps(
    sender: type[Incident],
    instance: Incident,
    **kwargs,
) -> None:
    """
    Automatically set KPI timestamps based on status transitions.
    
    - TRIGGERED -> ACKNOWLEDGED: Sets acknowledged_at
    - Any -> RESOLVED: Sets resolved_at
    """
    if not instance.pk:
        # New instance, no previous state to compare
        return
    
    try:
        old_instance = Incident.objects.get(pk=instance.pk)
    except Incident.DoesNotExist:
        return
    
    # Track if status changed
    old_status = old_instance.status
    new_status = instance.status
    
    if old_status == new_status:
        return  # No status change
    
    now = timezone.now()
    
    # TRIGGERED -> ACKNOWLEDGED: Set acknowledged_at
    if (
        old_status == IncidentStatus.TRIGGERED
        and new_status == IncidentStatus.ACKNOWLEDGED
        and not instance.acknowledged_at
    ):
        instance.acknowledged_at = now
        logger.info(
            f"Incident {instance.short_id}: acknowledged_at set to {now}"
        )
    
    # Any -> RESOLVED: Set resolved_at
    if (
        old_status != IncidentStatus.RESOLVED
        and new_status == IncidentStatus.RESOLVED
        and not instance.resolved_at
    ):
        instance.resolved_at = now
        logger.info(
            f"Incident {instance.short_id}: resolved_at set to {now}"
        )


@receiver(post_save, sender=Incident)
def log_incident_creation(
    sender: type[Incident],
    instance: Incident,
    created: bool,
    **kwargs,
) -> None:
    """
    Create an IncidentEvent when an incident is created.
    """
    if created:
        IncidentEvent.objects.create(
            incident=instance,
            type=IncidentEventType.STATUS_CHANGE,
            message=f"Incident created with status: {instance.get_status_display()}",
        )
        logger.info(f"Incident {instance.short_id}: Created with status {instance.status}")


@receiver(post_save, sender=Incident)
def log_status_change(
    sender: type[Incident],
    instance: Incident,
    created: bool,
    update_fields: frozenset[str] | None = None,
    **kwargs,
) -> None:
    """
    Create an IncidentEvent when status changes.
    
    Note: This uses a workaround to detect status changes by checking
    if the status field was in update_fields or by using instance._status_changed
    attribute set in pre_save (for full saves).
    """
    if created:
        return  # Already handled by log_incident_creation
    
    # Check if this is a status change (set by pre_save or detected here)
    # This is a simplified approach - in production you might want to use
    # django-model-utils FieldTracker or similar
    if update_fields is not None and "status" not in update_fields:
        return
    
    # We can't easily detect status changes without FieldTracker,
    # so we'll rely on explicit event creation in the service layer
    # for status changes after the initial creation.
    # This signal will be enhanced in Phase 2.
