"""
IMAS Manager - Celery Tasks

Async tasks for background processing.
"""
from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


# =============================================================================
# Escalation Tasks
# =============================================================================


@shared_task(name="tasks.check_pending_escalations")
def check_pending_escalations():
    """
    Check all triggered incidents for pending escalations.
    
    This task should be scheduled to run every minute via Celery Beat.
    """
    from core.models import Incident
    from services.escalation import EscalationService
    
    # Get all triggered (unacknowledged) incidents
    pending_incidents = Incident.objects.filter(
        status="TRIGGERED",
    ).select_related(
        "service", 
        "service__owner_team"
    )
    
    escalated_count = 0
    
    for incident in pending_incidents:
        try:
            service = EscalationService(incident)
            if service.check_and_escalate():
                escalated_count += 1
        except Exception as e:
            logger.error(
                f"Error checking escalation for incident {incident.id}: {e}",
                exc_info=True
            )
    
    logger.info(
        f"Escalation check completed. "
        f"Checked: {pending_incidents.count()}, Escalated: {escalated_count}"
    )
    return {
        "checked": pending_incidents.count(),
        "escalated": escalated_count,
    }


@shared_task(name="tasks.escalate_incident")
def escalate_incident(incident_id: str):
    """
    Check and escalate a specific incident.
    
    Args:
        incident_id: UUID of the incident to escalate
    """
    from core.models import Incident
    from services.escalation import EscalationService
    
    try:
        incident = Incident.objects.select_related(
            "service", 
            "service__owner_team"
        ).get(id=incident_id)
    except Incident.DoesNotExist:
        logger.error(f"Incident {incident_id} not found for escalation")
        return {"success": False, "error": "Incident not found"}
    
    try:
        service = EscalationService(incident)
        escalated = service.check_and_escalate()
        return {"success": True, "escalated": escalated}
    except Exception as e:
        logger.error(f"Escalation failed for {incident_id}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# =============================================================================
# Runbook Tasks
# =============================================================================


@shared_task(name="tasks.attach_runbook_to_incident")
def attach_runbook_to_incident(incident_id: str):
    """
    Find and attach appropriate runbook to a new incident.
    
    Args:
        incident_id: UUID of the incident
    """
    from core.models import Incident
    from services.runbook import RunbookAutoAttacher
    
    try:
        incident = Incident.objects.select_related("service").get(id=incident_id)
    except Incident.DoesNotExist:
        logger.error(f"Incident {incident_id} not found for runbook attachment")
        return {"success": False, "error": "Incident not found"}
    
    try:
        runbook = RunbookAutoAttacher.attach_on_incident_create(incident)
        return {
            "success": True,
            "runbook_attached": runbook is not None,
            "runbook_name": runbook.name if runbook else None,
        }
    except Exception as e:
        logger.error(f"Runbook attachment failed for {incident_id}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@shared_task(name="tasks.auto_apply_tags")
def auto_apply_tags(incident_id: str):
    """
    Automatically apply matching tags to an incident.
    
    Args:
        incident_id: UUID of the incident
    """
    from core.models import Incident
    from services.runbook import TagService
    
    try:
        incident = Incident.objects.select_related("service").get(id=incident_id)
    except Incident.DoesNotExist:
        logger.error(f"Incident {incident_id} not found for tag application")
        return {"success": False, "error": "Incident not found"}
    
    try:
        applied_tags = TagService.auto_apply_tags(incident)
        return {
            "success": True,
            "tags_applied": len(applied_tags),
            "tag_names": [t.name for t in applied_tags],
        }
    except Exception as e:
        logger.error(f"Tag application failed for {incident_id}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# =============================================================================
# Notification Tasks
# =============================================================================


@shared_task(name="tasks.send_incident_notification")
def send_incident_notification(
    incident_id: str,
    notification_type: str = "created"
):
    """
    Send notification for an incident.
    
    Args:
        incident_id: UUID of the incident
        notification_type: Type of notification (created, acknowledged, resolved)
    """
    from core.models import Incident
    from services.templates import NotificationContext, TemplateRegistry
    
    try:
        incident = Incident.objects.select_related(
            "service",
            "service__owner_team",
            "lead"
        ).get(id=incident_id)
    except Incident.DoesNotExist:
        logger.error(f"Incident {incident_id} not found for notification")
        return {"success": False, "error": "Incident not found"}
    
    ctx = NotificationContext(incident=incident)
    
    try:
        # Get Slack message
        template_name = f"incident_{notification_type}"
        slack_message = TemplateRegistry.get_template("slack", template_name, ctx)
        
        # TODO: Integrate with actual Slack notification service
        logger.info(f"Would send Slack notification for incident {incident_id}: {notification_type}")
        
        return {
            "success": True,
            "notification_type": notification_type,
            "slack_message_ready": True,
        }
    except Exception as e:
        logger.error(f"Notification failed for {incident_id}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@shared_task(name="tasks.process_new_incident")
def process_new_incident(incident_id: str):
    """
    Process a newly created incident.
    
    This task orchestrates:
    1. Auto-attach runbook
    2. Auto-apply tags
    3. Send notifications
    4. Schedule first escalation check
    
    Args:
        incident_id: UUID of the incident
    """
    logger.info(f"Processing new incident: {incident_id}")
    
    # Chain of tasks for new incident
    from celery import chain
    
    workflow = chain(
        attach_runbook_to_incident.s(incident_id),
        auto_apply_tags.s(incident_id),
        send_incident_notification.s(incident_id, "created"),
    )
    
    workflow.apply_async()
    
    return {"success": True, "incident_id": incident_id}


# =============================================================================
# Cleanup Tasks
# =============================================================================


@shared_task(name="tasks.cleanup_old_comments")
def cleanup_old_comments(days: int = 365):
    """
    Archive or clean up old automated comments.
    
    Args:
        days: Delete automated comments older than this many days
    """
    from datetime import timedelta
    from core.models import IncidentComment
    
    cutoff = timezone.now() - timedelta(days=days)
    
    # Only delete automated (system) comments, not user comments
    deleted, _ = IncidentComment.objects.filter(
        comment_type="AUTOMATED",
        created_at__lt=cutoff,
        is_pinned=False,
    ).delete()
    
    logger.info(f"Deleted {deleted} old automated comments")
    return {"deleted": deleted}


# =============================================================================
# Celery Beat Schedule
# =============================================================================

# Add these to your CELERY_BEAT_SCHEDULE in settings:
#
# CELERY_BEAT_SCHEDULE = {
#     "check-pending-escalations": {
#         "task": "tasks.check_pending_escalations",
#         "schedule": 60.0,  # Every minute
#     },
#     "cleanup-old-comments": {
#         "task": "tasks.cleanup_old_comments",
#         "schedule": crontab(hour=2, minute=0),  # Daily at 2 AM
#         "kwargs": {"days": 365},
#     },
# }
