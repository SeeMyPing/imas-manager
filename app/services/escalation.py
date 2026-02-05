"""
IMAS Manager - Escalation Service

Automatic escalation of unacknowledged incidents.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:
    from core.models import Incident

logger = logging.getLogger(__name__)


class EscalationService:
    """
    Service for handling incident escalations.
    """
    
    def __init__(self, incident: "Incident"):
        self.incident = incident
        self.service = incident.service
        self.team = self.service.owner_team if self.service else None
    
    def check_and_escalate(self) -> bool:
        """
        Check if incident needs escalation and trigger if needed.
        
        Returns:
            True if an escalation was triggered
        """
        from core.models import EscalationPolicy, IncidentEscalation
        
        if not self._should_escalate():
            return False
        
        # Find applicable escalation policy
        policy = self._find_policy()
        if not policy:
            logger.debug(f"No escalation policy found for incident {self.incident.id}")
            return False
        
        # Get next escalation step
        current_level = self._get_current_escalation_level()
        next_step = policy.steps.filter(
            step_order=current_level + 1,
            is_active=True
        ).first()
        
        if not next_step:
            logger.info(f"No more escalation steps for incident {self.incident.id}")
            return False
        
        # Check if enough time has passed
        wait_time = self._get_wait_time_for_step(policy, next_step)
        time_since_detection = timezone.now() - self.incident.detected_at
        
        if time_since_detection < wait_time:
            logger.debug(
                f"Incident {self.incident.id} not ready for escalation. "
                f"Waiting: {wait_time - time_since_detection}"
            )
            return False
        
        # Trigger escalation
        return self._trigger_escalation(policy, next_step, current_level + 1)
    
    def _should_escalate(self) -> bool:
        """Check if incident is in a state that requires escalation."""
        # Only escalate triggered (unacknowledged) incidents
        if self.incident.status != "TRIGGERED":
            return False
        
        # Must be open
        if not self.incident.is_open:
            return False
        
        # Must have a team
        if not self.team:
            return False
        
        return True
    
    def _find_policy(self) -> "EscalationPolicy | None":
        """Find the applicable escalation policy."""
        from core.models import EscalationPolicy
        
        # Priority: Severity-specific > Default team policy
        
        # 1. Severity-specific policy
        policy = EscalationPolicy.objects.filter(
            team=self.team,
            severity_filter=self.incident.severity,
            is_active=True
        ).first()
        if policy:
            return policy
        
        # 2. Default team policy (no severity filter)
        policy = EscalationPolicy.objects.filter(
            team=self.team,
            is_active=True,
            severity_filter="",
        ).first()
        
        return policy
    
    def _get_current_escalation_level(self) -> int:
        """Get the current escalation level."""
        from core.models import IncidentEscalation
        
        last_escalation = IncidentEscalation.objects.filter(
            incident=self.incident
        ).order_by("-step_number").first()
        
        return last_escalation.step_number if last_escalation else 0
    
    def _get_wait_time_for_step(self, policy: "EscalationPolicy", step) -> timedelta:
        """Calculate wait time before triggering a step."""
        # Sum up delays from step 1 to this step
        total_minutes = policy.initial_delay_minutes
        
        previous_steps = policy.steps.filter(
            step_order__lt=step.step_order,
            is_active=True
        )
        
        for prev_step in previous_steps:
            total_minutes += prev_step.delay_minutes
        
        return timedelta(minutes=total_minutes)
    
    @transaction.atomic
    def _trigger_escalation(
        self, 
        policy: "EscalationPolicy", 
        step, 
        level: int
    ) -> bool:
        """Trigger an escalation."""
        from core.models import IncidentEscalation
        
        # Create escalation record
        escalation = IncidentEscalation.objects.create(
            incident=self.incident,
            policy=policy,
            step=step,
            step_number=level,
            status="PENDING",
        )
        
        # Notify targets
        targets = self._resolve_targets(step)
        notified_count = 0
        
        for target in targets:
            try:
                self._notify_target(target, level)
                notified_count += 1
            except Exception as e:
                logger.error(f"Failed to notify target {target}: {e}")
        
        # Update escalation status
        if notified_count > 0:
            escalation.status = "NOTIFIED"
            escalation.notified_at = timezone.now()
        else:
            escalation.status = "FAILED"
            escalation.error_message = "Failed to notify any targets"
        
        escalation.save()
        
        # Create incident event
        self._create_escalation_event(level, targets)
        
        logger.info(
            f"Escalation level {level} triggered for incident {self.incident.id}. "
            f"Notified {notified_count}/{len(targets)} targets."
        )
        
        return notified_count > 0
    
    def _resolve_targets(self, step) -> list[dict]:
        """Resolve notification targets for an escalation step."""
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        targets = []
        
        if step.notify_type == "USER":
            # Specific user
            if step.target_user:
                targets.append({
                    "type": "user",
                    "user": step.target_user,
                    "email": step.target_user.email,
                    "name": step.target_user.get_full_name() or step.target_user.username,
                })
        
        elif step.notify_type == "ONCALL":
            # Current on-call for the team
            if self.team:
                on_call = self.team.get_current_on_call()
                if on_call:
                    targets.append({
                        "type": "oncall",
                        "user": on_call,
                        "email": on_call.email,
                        "name": on_call.get_full_name() or on_call.username,
                    })
        
        elif step.notify_type == "TEAM":
            # All team members
            if step.target_team:
                for member in step.target_team.members.all():
                    targets.append({
                        "type": "team_member",
                        "user": member,
                        "email": member.email,
                        "name": member.get_full_name() or member.username,
                    })
        
        elif step.notify_type == "MANAGER":
            # Team manager
            if self.team and self.team.manager:
                targets.append({
                    "type": "manager",
                    "user": self.team.manager,
                    "email": self.team.manager.email,
                    "name": self.team.manager.get_full_name() or self.team.manager.username,
                })
        
        return targets
    
    def _notify_target(self, target: dict, level: int) -> None:
        """Send notification to a target."""
        from services.templates import NotificationContext, TemplateRegistry
        
        ctx = NotificationContext(
            incident=self.incident,
            custom_data={
                "escalation_level": level,
                "wait_time_seconds": int((timezone.now() - self.incident.detected_at).total_seconds()),
            }
        )
        
        # Send Slack notification
        try:
            slack_message = TemplateRegistry.get_template(
                "slack", 
                "escalation_notification", 
                ctx, 
                escalation_level=level
            )
            self._send_slack_notification(target, slack_message)
        except Exception as e:
            logger.warning(f"Failed to send Slack notification: {e}")
        
        # Send email notification
        try:
            subject, html_body = TemplateRegistry.get_template(
                "email",
                "escalation_notification",
                ctx,
                escalation_level=level
            )
            self._send_email_notification(target, subject, html_body)
        except Exception as e:
            logger.warning(f"Failed to send email notification: {e}")
    
    def _send_slack_notification(self, target: dict, message: dict) -> None:
        """Send Slack notification."""
        # Import notification service
        try:
            from services.notifications import NotificationService
            NotificationService.send_slack_dm(target["user"], message)
        except ImportError:
            logger.debug("NotificationService not available, skipping Slack")
        except Exception as e:
            logger.error(f"Slack notification failed: {e}")
    
    def _send_email_notification(self, target: dict, subject: str, body: str) -> None:
        """Send email notification."""
        from django.core.mail import send_mail
        from django.conf import settings
        
        if not target.get("email"):
            return
        
        try:
            send_mail(
                subject=subject,
                message="",  # Plain text fallback
                html_message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[target["email"]],
                fail_silently=False,
            )
        except Exception as e:
            logger.error(f"Email notification failed: {e}")
            raise
    
    def _create_escalation_event(self, level: int, targets: list[dict]) -> None:
        """Create an incident event for the escalation."""
        from core.models import IncidentEvent
        
        target_names = [t["name"] for t in targets]
        
        IncidentEvent.objects.create(
            incident=self.incident,
            event_type="ESCALATED",
            description=f"Escalated to level {level}. Notified: {', '.join(target_names)}",
            metadata={
                "escalation_level": level,
                "targets": [
                    {"name": t["name"], "type": t["type"]}
                    for t in targets
                ],
            },
        )
    
    def acknowledge_escalation(self, user) -> bool:
        """
        Acknowledge the current escalation.
        
        Returns:
            True if acknowledged successfully
        """
        from core.models import IncidentEscalation
        
        # Find pending escalation
        pending = IncidentEscalation.objects.filter(
            incident=self.incident,
            status="NOTIFIED"
        ).order_by("-step_number").first()
        
        if pending:
            pending.status = "ACKNOWLEDGED"
            pending.acknowledged_at = timezone.now()
            pending.acknowledged_by = user
            pending.save()
        
        return True


# =============================================================================
# Celery Tasks for Escalation
# =============================================================================


def get_escalation_tasks():
    """
    Return Celery tasks for escalation.
    This is called by the main celery module.
    """
    from celery import shared_task
    
    @shared_task(name="escalation.check_pending_incidents")
    def check_pending_incidents():
        """
        Check all pending incidents for escalation.
        This should run every minute.
        """
        from core.models import Incident
        
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
                logger.error(f"Error checking escalation for {incident.id}: {e}")
        
        logger.info(f"Escalation check completed. Escalated: {escalated_count}")
        return escalated_count
    
    @shared_task(name="escalation.escalate_incident")
    def escalate_incident(incident_id: str):
        """
        Check and escalate a specific incident.
        """
        from core.models import Incident
        
        try:
            incident = Incident.objects.select_related(
                "service", 
                "service__owner_team"
            ).get(id=incident_id)
        except Incident.DoesNotExist:
            logger.error(f"Incident {incident_id} not found for escalation")
            return False
        
        service = EscalationService(incident)
        return service.check_and_escalate()
    
    return {
        "check_pending_incidents": check_pending_incidents,
        "escalate_incident": escalate_incident,
    }
