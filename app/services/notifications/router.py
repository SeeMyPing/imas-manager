"""
IMAS Manager - Notification Router

Intelligent routing service that determines who to notify for an incident.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.choices import IncidentSeverity

if TYPE_CHECKING:
    from core.models import Incident

logger = logging.getLogger(__name__)


@dataclass
class NotificationRecipients:
    """Container for aggregated notification recipients."""
    
    slack_channels: list[str] = field(default_factory=list)
    slack_user_ids: list[str] = field(default_factory=list)
    sms_numbers: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    discord_channels: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        """Check if there are any recipients."""
        return not any([
            self.slack_channels,
            self.slack_user_ids,
            self.sms_numbers,
            self.emails,
            self.discord_channels,
        ])


class NotificationRouter:
    """
    Routes notifications to the appropriate recipients.
    
    Determines who to notify based on:
    - Affected service's owner team
    - Impact scopes (Legal, Security, etc.)
    - Incident severity
    """

    def get_recipients(self, incident: "Incident") -> NotificationRecipients:
        """
        Aggregate all recipients for an incident.
        
        Args:
            incident: The incident to get recipients for.
            
        Returns:
            NotificationRecipients with all channels and contacts.
        """
        recipients = NotificationRecipients()
        
        # 1. Technical Recipients (from service owner team)
        self._add_technical_recipients(incident, recipients)
        
        # 2. Functional Recipients (from impact scopes)
        self._add_scope_recipients(incident, recipients)
        
        logger.info(
            f"Incident {incident.short_id}: "
            f"{len(recipients.slack_channels)} Slack channels, "
            f"{len(recipients.emails)} emails, "
            f"{len(recipients.sms_numbers)} SMS"
        )
        
        return recipients

    def _add_technical_recipients(
        self,
        incident: "Incident",
        recipients: NotificationRecipients,
    ) -> None:
        """Add recipients from the service owner team."""
        team = incident.service.owner_team
        
        # Add team's Slack channel
        if team.slack_channel_id:
            recipients.slack_channels.append(team.slack_channel_id)
        
        # Add on-call person
        if on_call := team.current_on_call:
            # For SEV1, use SMS; otherwise Slack
            if incident.severity == IncidentSeverity.SEV1_CRITICAL:
                # TODO: Get phone number from user profile
                # recipients.sms_numbers.append(on_call.phone_number)
                pass
            if on_call.email:
                recipients.emails.append(on_call.email)

    def _add_scope_recipients(
        self,
        incident: "Incident",
        recipients: NotificationRecipients,
    ) -> None:
        """Add recipients from impacted scopes."""
        for scope in incident.impacted_scopes.filter(is_active=True):
            if scope.mandatory_notify_email:
                if scope.mandatory_notify_email not in recipients.emails:
                    recipients.emails.append(scope.mandatory_notify_email)

    def build_message(self, incident: "Incident") -> dict[str, str]:
        """
        Build notification message content.
        
        Args:
            incident: The incident to build message for.
            
        Returns:
            Dict with 'title', 'body', 'links' for notification.
        """
        links = []
        if incident.lid_link:
            links.append(f"📄 LID: {incident.lid_link}")
        if incident.war_room_link:
            links.append(f"💬 War Room: {incident.war_room_link}")
        if incident.service.runbook_url:
            links.append(f"📖 Runbook: {incident.service.runbook_url}")
        
        return {
            "title": f"🚨 [{incident.get_severity_display()}] {incident.title}",
            "body": incident.description or "No description provided.",
            "service": incident.service.name,
            "severity": incident.get_severity_display(),
            "status": incident.get_status_display(),
            "links": "\n".join(links) if links else "No links available yet.",
        }

    def broadcast(self, incident: "Incident") -> None:
        """
        Send notifications to all recipients.
        
        This is a stub - actual implementation in Phase 2.
        
        Args:
            incident: The incident to broadcast.
        """
        recipients = self.get_recipients(incident)
        
        if recipients.is_empty():
            logger.warning(f"No recipients found for incident {incident.short_id}")
            return
        
        message = self.build_message(incident)
        
        # TODO: Phase 2 - Implement actual sending via providers
        logger.info(f"Broadcasting incident {incident.short_id} to recipients")

    def send_escalation_alert(
        self,
        incident: "Incident",
        user,
        escalation_level: int,
    ) -> None:
        """
        Send an escalation notification to a specific user.
        
        Escalation alerts are more urgent and may use different channels
        (e.g., SMS for high-severity incidents).
        
        Args:
            incident: The incident being escalated.
            user: The user to notify (from escalation chain).
            escalation_level: The escalation tier (2, 3, etc.).
        """
        from core.choices import IncidentSeverity
        
        logger.info(
            f"Sending escalation alert for {incident.short_id} "
            f"to {user.username} (level {escalation_level})"
        )
        
        # Build escalation message
        message = {
            "title": f"⚠️ ESCALATION [{incident.get_severity_display()}] {incident.title}",
            "body": (
                f"This incident has not been acknowledged and has been escalated to you.\n\n"
                f"Service: {incident.service.name}\n"
                f"Created: {incident.created_at.strftime('%Y-%m-%d %H:%M UTC')}\n"
                f"Escalation Level: {escalation_level}"
            ),
            "service": incident.service.name,
            "severity": incident.get_severity_display(),
            "status": incident.get_status_display(),
            "escalation_level": escalation_level,
        }
        
        # Add links
        links = []
        if incident.lid_link:
            links.append(f"📄 LID: {incident.lid_link}")
        if incident.war_room_link:
            links.append(f"💬 War Room: {incident.war_room_link}")
        message["links"] = "\n".join(links) if links else ""
        
        # Determine notification channels based on severity
        if incident.severity in [
            IncidentSeverity.SEV1_CRITICAL,
            IncidentSeverity.SEV2_HIGH,
        ]:
            # High severity: use SMS + Slack + Email
            if hasattr(user, 'phone_number') and user.phone_number:
                self._send_sms(user.phone_number, message)
        
        # Always send email for escalations
        if user.email:
            self._send_email(user.email, message)
        
        # Always try Slack DM
        self._send_slack_dm(user, message)
        
        logger.info(f"Escalation alert sent for {incident.short_id}")

    def _send_sms(self, phone_number: str, message: dict) -> bool:
        """Send SMS notification (stub for now)."""
        logger.info(f"Would send SMS to {phone_number}")
        return True

    def _send_email(self, email: str, message: dict) -> bool:
        """Send email notification."""
        from services.notifications.providers import EmailProvider
        from core.models import NotificationProvider
        
        try:
            # Get active email provider
            email_config = NotificationProvider.objects.filter(
                type="SMTP",
                is_active=True,
            ).first()
            
            if email_config:
                provider = EmailProvider(email_config.config)
                return provider.send(recipient=email, message=message)
            else:
                logger.warning("No active email provider configured")
                return False
        except Exception as e:
            logger.error(f"Failed to send escalation email: {e}")
            return False

    def _send_slack_dm(self, user, message: dict) -> bool:
        """Send Slack direct message."""
        from services.notifications.providers import SlackProvider
        from core.models import NotificationProvider
        
        try:
            slack_config = NotificationProvider.objects.filter(
                type="SLACK",
                is_active=True,
            ).first()
            
            if slack_config and hasattr(user, 'email') and user.email:
                provider = SlackProvider(slack_config.config)
                # Lookup user by email and send DM
                slack_user_id = provider.get_user_id_by_email(user.email)
                if slack_user_id:
                    return provider.send(recipient=slack_user_id, message=message)
            return False
        except Exception as e:
            logger.error(f"Failed to send Slack DM: {e}")
            return False

    def send_reminder(self, incident: "Incident") -> None:
        """
        Send a reminder notification for an unacknowledged incident.
        
        Reminders are sent to the on-call responders when an incident
        has not been acknowledged within the expected time.
        
        Args:
            incident: The unacknowledged incident.
        """
        logger.info(f"Sending reminder for unacknowledged incident {incident.short_id}")
        
        message = {
            "title": f"⏰ REMINDER [{incident.get_severity_display()}] {incident.title}",
            "body": (
                f"This incident has not been acknowledged.\n\n"
                f"Service: {incident.service.name}\n"
                f"Created: {incident.created_at.strftime('%Y-%m-%d %H:%M UTC')}\n"
                f"Time since creation: {self._format_duration(incident.created_at)}"
            ),
            "service": incident.service.name,
            "severity": incident.get_severity_display(),
            "status": incident.get_status_display(),
        }
        
        # Add links
        links = []
        if incident.lid_link:
            links.append(f"📄 LID: {incident.lid_link}")
        if incident.war_room_link:
            links.append(f"💬 War Room: {incident.war_room_link}")
        message["links"] = "\n".join(links) if links else ""
        
        # Get recipients from the incident's team
        recipients = self.get_recipients(incident)
        
        # Send to Slack channels
        for channel in recipients.slack_channels:
            self._send_to_slack_channel(channel, message)
        
        # Send email to on-call if available
        if incident.owner_team:
            on_call = incident.owner_team.current_on_call
            if on_call and on_call.email:
                self._send_email(on_call.email, message)
        
        logger.info(f"Reminder sent for {incident.short_id}")

    def _format_duration(self, start_time) -> str:
        """Format duration since start time as human-readable string."""
        from django.utils import timezone
        
        delta = timezone.now() - start_time
        minutes = int(delta.total_seconds() // 60)
        
        if minutes < 60:
            return f"{minutes} minutes"
        
        hours = minutes // 60
        remaining_minutes = minutes % 60
        
        if hours < 24:
            return f"{hours}h {remaining_minutes}min"
        
        days = hours // 24
        remaining_hours = hours % 24
        return f"{days}d {remaining_hours}h"

    def _send_to_slack_channel(self, channel_id: str, message: dict) -> bool:
        """Send message to a Slack channel."""
        from services.notifications.providers import SlackProvider
        from core.models import NotificationProvider
        
        try:
            slack_config = NotificationProvider.objects.filter(
                type="SLACK",
                is_active=True,
            ).first()
            
            if slack_config:
                provider = SlackProvider(slack_config.config)
                return provider.send(recipient=channel_id, message=message)
            return False
        except Exception as e:
            logger.error(f"Failed to send to Slack channel: {e}")
            return False


# Singleton instance
router = NotificationRouter()
