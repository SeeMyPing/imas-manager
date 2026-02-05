"""
IMAS Manager - Incident Tasks

Celery tasks for async incident orchestration.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
)
def orchestrate_incident_task(self, incident_id: str) -> dict[str, Any]:
    """
    Main orchestration task for incident setup.
    
    Executed asynchronously after incident creation:
    1. Create LID document (Google Docs)
    2. Create War Room (Slack/Discord) if severity <= SEV2
    3. Send notifications to all recipients
    
    Args:
        incident_id: UUID of the incident to orchestrate.
        
    Returns:
        Dict with orchestration results.
    """
    from core.models import Incident, IncidentEvent
    from core.choices import IncidentEventType
    from integrations.gdrive import get_gdrive_service
    from services.notifications.router import router
    from services.notifications.chatops import chatops_service
    
    logger.info(f"Starting orchestration for incident {incident_id}")
    
    try:
        incident = Incident.objects.get(pk=incident_id)
    except Incident.DoesNotExist:
        logger.error(f"Incident {incident_id} not found")
        return {"error": "Incident not found"}
    
    results = {
        "incident_id": str(incident_id),
        "lid_created": False,
        "war_room_created": False,
        "notifications_sent": False,
    }
    
    # 1. Create LID Document
    gdrive_service = get_gdrive_service()
    try:
        lid_url = gdrive_service.create_lid_document(incident)
        if lid_url:
            incident.lid_link = lid_url
            incident.save(update_fields=["lid_link"])
            results["lid_created"] = True
            
            IncidentEvent.objects.create(
                incident=incident,
                type=IncidentEventType.DOCUMENT_CREATED,
                message=f"LID document created: {lid_url}",
            )
    except Exception as e:
        logger.error(f"Failed to create LID for {incident_id}: {e}")
    
    # 2. Create War Room (if critical)
    if incident.is_critical:
        try:
            result = chatops_service.create_war_room(incident)
            if result:
                war_room_id, war_room_url = result
                incident.war_room_id = war_room_id
                incident.war_room_link = war_room_url
                incident.save(update_fields=["war_room_id", "war_room_link"])
                results["war_room_created"] = True
                
                # Invite responders
                chatops_service.invite_responders(war_room_id, incident)
                
                IncidentEvent.objects.create(
                    incident=incident,
                    type=IncidentEventType.WAR_ROOM_CREATED,
                    message=f"War Room created: {war_room_url}",
                )
            else:
                logger.warning(f"War Room creation returned None for {incident.short_id}")
        except Exception as e:
            logger.error(f"Failed to create War Room for {incident_id}: {e}")
    
    # 3. Send Notifications
    try:
        router.broadcast(incident)
        results["notifications_sent"] = True
        
        IncidentEvent.objects.create(
            incident=incident,
            type=IncidentEventType.ALERT_SENT,
            message="Notifications broadcast to recipients",
        )
    except Exception as e:
        logger.error(f"Failed to send notifications for {incident_id}: {e}")
    
    # Log completion
    IncidentEvent.objects.create(
        incident=incident,
        type=IncidentEventType.NOTE,
        message="Orchestration completed",
    )
    
    logger.info(f"Orchestration completed for incident {incident.short_id}: {results}")
    return results


@shared_task(
    bind=True,
    max_retries=5,
    default_retry_delay=30,
)
def send_notification_task(
    self,
    provider_id: str,
    recipient: str,
    message: dict[str, Any],
) -> bool:
    """
    Send a single notification via a specific provider.
    
    This task is retry-able and isolated per notification.
    
    Args:
        provider_id: UUID of the NotificationProvider to use.
        recipient: Recipient identifier (channel ID, email, phone).
        message: Message content dict.
        
    Returns:
        True if sent successfully.
    """
    from core.models import NotificationProvider
    from services.notifications.providers.base import NotificationProviderFactory
    
    try:
        config = NotificationProvider.objects.get(pk=provider_id, is_active=True)
    except NotificationProvider.DoesNotExist:
        logger.error(f"Provider {provider_id} not found or inactive")
        return False
    
    try:
        provider = NotificationProviderFactory.create(config)
        return provider.send(recipient=recipient, message=message)
    except Exception as e:
        logger.error(f"Failed to send notification via {config.name}: {e}")
        raise self.retry(exc=e)


@shared_task
def archive_war_room_task(incident_id: str) -> bool:
    """
    Archive a War Room channel after incident resolution.
    
    Called when an incident is marked as resolved.
    
    Args:
        incident_id: UUID of the resolved incident.
        
    Returns:
        True if archived successfully.
    """
    from core.models import Incident
    from services.notifications.chatops import chatops_service
    
    try:
        incident = Incident.objects.get(pk=incident_id)
    except Incident.DoesNotExist:
        logger.error(f"Incident {incident_id} not found")
        return False
    
    if not incident.war_room_id:
        logger.info(f"No War Room to archive for {incident.short_id}")
        return True
    
    try:
        chatops_service.archive_war_room(incident.war_room_id)
        logger.info(f"Archived War Room {incident.war_room_id} for {incident.short_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to archive War Room: {e}")
        return False


@shared_task(bind=True, max_retries=3)
def check_escalation_task(self, incident_id: str) -> dict[str, Any]:
    """
    Check if an incident needs escalation.
    
    Called periodically (via Celery Beat) to check for unacknowledged incidents
    that have exceeded their escalation timeout.
    
    Escalation logic:
    1. Find incidents in TRIGGERED status
    2. Check if escalation_timeout has passed since creation
    3. If so, notify the next escalation level
    
    Args:
        incident_id: UUID of the incident to check.
        
    Returns:
        Dict with escalation results.
    """
    from django.utils import timezone
    from datetime import timedelta
    
    from core.models import Incident, IncidentEvent
    from core.choices import IncidentStatus, IncidentEventType
    from services.notifications.router import router
    
    try:
        incident = Incident.objects.select_related(
            "service__owner_team", "service"
        ).get(pk=incident_id)
    except Incident.DoesNotExist:
        logger.error(f"Incident {incident_id} not found")
        return {"error": "Incident not found"}
    
    # Only escalate TRIGGERED incidents
    if incident.status != IncidentStatus.TRIGGERED:
        return {"skipped": True, "reason": "Not in TRIGGERED status"}
    
    # Get escalation timeout from team (via service)
    team = incident.service.owner_team if incident.service else None
    if not team:
        return {"skipped": True, "reason": "No owner team"}
    
    timeout_minutes = team.escalation_timeout_minutes
    escalation_threshold = incident.created_at + timedelta(minutes=timeout_minutes)
    
    if timezone.now() < escalation_threshold:
        return {"skipped": True, "reason": "Timeout not reached"}
    
    # Count previous escalations
    escalation_count = incident.events.filter(
        type=IncidentEventType.ESCALATION
    ).count()
    
    # Get next escalation level
    escalation_chain = team.get_escalation_chain()
    next_level = escalation_count + 2  # Start from level 2 (1 was initial)
    
    if next_level > len(escalation_chain) + 1:
        logger.warning(f"No more escalation levels for {incident.short_id}")
        return {"skipped": True, "reason": "Max escalation reached"}
    
    # Find next on-call user
    next_oncall = None
    for schedule in team.oncall_schedules.filter(
        escalation_level=next_level,
        start_time__lte=timezone.now(),
        end_time__gt=timezone.now(),
    ):
        next_oncall = schedule.user
        break
    
    if not next_oncall:
        logger.warning(f"No on-call user found for level {next_level}")
        return {"skipped": True, "reason": f"No on-call for level {next_level}"}
    
    # Send escalation notification
    try:
        router.send_escalation_alert(incident, next_oncall, next_level)
        
        # Log escalation event
        IncidentEvent.objects.create(
            incident=incident,
            type=IncidentEventType.ESCALATION,
            message=f"Escalated to level {next_level}: {next_oncall.username}",
        )
        
        logger.info(
            f"Escalated {incident.short_id} to {next_oncall.username} (level {next_level})"
        )
        
        return {
            "escalated": True,
            "level": next_level,
            "user": next_oncall.username,
        }
    except Exception as e:
        logger.error(f"Failed to send escalation alert: {e}")
        raise self.retry(exc=e)


@shared_task
def check_pending_escalations() -> dict[str, Any]:
    """
    Periodic task to check all pending incidents for escalation.
    
    Should be scheduled via Celery Beat (e.g., every 5 minutes).
    """
    from core.models import Incident
    from core.choices import IncidentStatus
    
    triggered_incidents = Incident.objects.filter(
        status=IncidentStatus.TRIGGERED
    ).values_list("id", flat=True)
    
    results = {
        "checked": 0,
        "escalated": 0,
    }
    
    for incident_id in triggered_incidents:
        check_escalation_task.delay(str(incident_id))
        results["checked"] += 1
    
    logger.info(f"Queued escalation checks for {results['checked']} incidents")
    return results


@shared_task
def send_unacknowledged_reminders() -> dict[str, Any]:
    """
    Send reminders for incidents that haven't been acknowledged.
    
    Triggered incidents older than the reminder threshold get a notification
    sent to the on-call responders.
    
    Scheduled every 15 minutes via Celery Beat.
    """
    from core.models import Incident, IncidentEvent
    from core.choices import IncidentStatus, IncidentEventType
    from services.notifications.router import router
    
    # Find unacknowledged incidents older than 10 minutes
    reminder_threshold = timezone.now() - timedelta(minutes=10)
    
    unacked_incidents = Incident.objects.filter(
        status=IncidentStatus.TRIGGERED,
        created_at__lt=reminder_threshold,
    ).select_related("service", "lead")
    
    results = {
        "reminded": 0,
        "skipped": 0,
    }
    
    for incident in unacked_incidents:
        # Check if we already sent a reminder in the last 15 minutes
        recent_reminder = incident.events.filter(
            type=IncidentEventType.REMINDER,
            timestamp__gt=timezone.now() - timedelta(minutes=15),
        ).exists()
        
        if recent_reminder:
            results["skipped"] += 1
            continue
        
        try:
            router.send_reminder(incident)
            
            IncidentEvent.objects.create(
                incident=incident,
                type=IncidentEventType.REMINDER,
                message="Reminder sent: Incident not yet acknowledged",
            )
            results["reminded"] += 1
            logger.info(f"Sent reminder for {incident.short_id}")
        except Exception as e:
            logger.error(f"Failed to send reminder for {incident.short_id}: {e}")
    
    logger.info(f"Sent {results['reminded']} reminders, skipped {results['skipped']}")
    return results


@shared_task
def auto_archive_incidents() -> dict[str, Any]:
    """
    Automatically archive resolved incidents older than retention period.
    
    Archives incidents that have been resolved for more than 7 days.
    Archiving involves:
    - Setting is_archived=True
    - Archiving the War Room channel
    
    Scheduled daily at 2 AM via Celery Beat.
    """
    from core.models import Incident
    from core.choices import IncidentStatus
    
    # Archive threshold: resolved more than 7 days ago
    archive_threshold = timezone.now() - timedelta(days=7)
    
    candidates = Incident.objects.filter(
        status=IncidentStatus.RESOLVED,
        resolved_at__lt=archive_threshold,
        is_archived=False,
    )
    
    results = {
        "archived": 0,
        "failed": 0,
    }
    
    for incident in candidates:
        try:
            # Archive war room if exists
            if incident.war_room_id:
                archive_war_room_task.delay(str(incident.id))
            
            # Mark as archived
            incident.is_archived = True
            incident.save(update_fields=["is_archived"])
            results["archived"] += 1
            
            logger.info(f"Archived incident {incident.short_id}")
        except Exception as e:
            logger.error(f"Failed to archive {incident.short_id}: {e}")
            results["failed"] += 1
    
    logger.info(f"Archived {results['archived']} incidents, {results['failed']} failed")
    return results


@shared_task
def generate_daily_summary() -> dict[str, Any]:
    """
    Generate and send a daily incident summary report.
    
    Summarizes the last 24 hours:
    - Total incidents created
    - Incidents by severity
    - MTTA/MTTR averages
    - Top offending services
    
    Scheduled daily at 8 AM via Celery Beat.
    """
    from core.models import Incident, NotificationProvider
    from core.choices import NotificationProviderType
    from services.metrics import metrics_service
    
    yesterday = timezone.now() - timedelta(days=1)
    today = timezone.now()
    
    # Get incidents from last 24 hours
    incidents = Incident.objects.filter(
        created_at__gte=yesterday,
        created_at__lt=today,
    )
    
    # Calculate stats
    total_incidents = incidents.count()
    resolved_incidents = incidents.filter(resolved_at__isnull=False).count()
    
    # Group by severity
    severity_breakdown = {}
    for incident in incidents:
        sev = incident.get_severity_display()
        severity_breakdown[sev] = severity_breakdown.get(sev, 0) + 1
    
    # Calculate MTTA/MTTR
    mtta = metrics_service.calculate_mtta(
        start_date=yesterday,
        end_date=today,
    )
    mttr = metrics_service.calculate_mttr(
        start_date=yesterday,
        end_date=today,
    )
    
    # Build summary message
    summary = {
        "text": f"📊 Daily Incident Summary ({yesterday.strftime('%Y-%m-%d')})",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📊 Daily Incident Summary",
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Total Incidents:*\n{total_incidents}"},
                    {"type": "mrkdwn", "text": f"*Resolved:*\n{resolved_incidents}"},
                    {"type": "mrkdwn", "text": f"*Avg MTTA:*\n{mtta:.1f} min" if mtta else "*Avg MTTA:*\nN/A"},
                    {"type": "mrkdwn", "text": f"*Avg MTTR:*\n{mttr:.1f} min" if mttr else "*Avg MTTR:*\nN/A"},
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Severity Breakdown:*\n" + "\n".join(
                        f"• {sev}: {count}" for sev, count in severity_breakdown.items()
                    ) if severity_breakdown else "_No incidents_"
                }
            },
        ]
    }
    
    # Send to Slack if configured
    try:
        provider_config = NotificationProvider.objects.get(
            type=NotificationProviderType.SLACK,
            is_active=True,
        )
        
        from services.notifications.providers.base import NotificationProviderFactory
        provider = NotificationProviderFactory.create(provider_config)
        
        # Send to default incident channel
        default_channel = provider_config.config.get("default_channel", "#incidents")
        provider.send(recipient=default_channel, message=summary)
        
        logger.info("Daily summary sent to Slack")
    except NotificationProvider.DoesNotExist:
        logger.warning("No active Slack provider for daily summary")
    except Exception as e:
        logger.error(f"Failed to send daily summary: {e}")
    
    return {
        "total_incidents": total_incidents,
        "resolved": resolved_incidents,
        "mtta_minutes": mtta,
        "mttr_minutes": mttr,
    }


@shared_task
def cleanup_stale_war_rooms() -> dict[str, Any]:
    """
    Clean up War Room channels that were orphaned or not properly archived.
    
    Finds incidents that are resolved but still have active War Rooms
    and archives them.
    
    Scheduled daily at 3 AM via Celery Beat.
    """
    from core.models import Incident
    from core.choices import IncidentStatus
    
    # Find resolved incidents with war rooms older than 24 hours
    stale_threshold = timezone.now() - timedelta(hours=24)
    
    stale_incidents = Incident.objects.filter(
        status=IncidentStatus.RESOLVED,
        war_room_id__isnull=False,
        resolved_at__lt=stale_threshold,
    ).exclude(
        is_archived=True,
    )
    
    results = {
        "cleaned": 0,
        "failed": 0,
    }
    
    for incident in stale_incidents:
        try:
            archive_war_room_task.delay(str(incident.id))
            results["cleaned"] += 1
            logger.info(f"Queued War Room cleanup for {incident.short_id}")
        except Exception as e:
            logger.error(f"Failed to queue cleanup for {incident.short_id}: {e}")
            results["failed"] += 1
    
    logger.info(f"Queued {results['cleaned']} War Room cleanups")
    return results


@shared_task(bind=True, max_retries=3)
def sync_incident_to_external_task(
    self,
    incident_id: str,
    system: str,
) -> dict[str, Any]:
    """
    Sync an incident to an external system (Jira, ServiceNow, etc.).
    
    This is a placeholder for external integrations.
    
    Args:
        incident_id: UUID of the incident to sync.
        system: Target system identifier.
        
    Returns:
        Dict with sync results.
    """
    from core.models import Incident
    
    try:
        incident = Incident.objects.get(pk=incident_id)
    except Incident.DoesNotExist:
        logger.error(f"Incident {incident_id} not found")
        return {"error": "Incident not found"}
    
    logger.info(f"Syncing {incident.short_id} to {system} (not implemented)")
    
    # TODO: Implement external system integrations
    # - Jira: Create/update ticket
    # - ServiceNow: Create/update incident record
    # - PagerDuty: Trigger/resolve incident
    
    return {
        "incident_id": str(incident_id),
        "system": system,
        "status": "not_implemented",
    }
