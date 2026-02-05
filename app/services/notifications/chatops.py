"""
IMAS Manager - ChatOps Service

Unified interface for War Room management across Slack/Discord.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.choices import NotificationProviderType
from core.models import NotificationProvider
from services.notifications.providers.base import NotificationProviderFactory

if TYPE_CHECKING:
    from core.models import Incident

logger = logging.getLogger(__name__)


class ChatOpsService:
    """
    High-level service for War Room management.
    
    Abstracts the underlying chat platform (Slack/Discord) and provides
    a unified interface for incident response coordination.
    """

    def __init__(self) -> None:
        self._provider = None
        self._provider_config = None

    def _get_provider(self):
        """
        Get the active chat provider (Slack or Discord).
        
        Returns:
            Configured provider instance.
            
        Raises:
            RuntimeError: If no chat provider is configured.
        """
        if self._provider is not None:
            return self._provider
        
        # Try Slack first, then Discord
        for provider_type in [NotificationProviderType.SLACK, NotificationProviderType.DISCORD]:
            try:
                config = NotificationProvider.objects.get(
                    type=provider_type,
                    is_active=True,
                )
                self._provider_config = config
                self._provider = NotificationProviderFactory.create(config)
                logger.info(f"Using {provider_type} for ChatOps")
                return self._provider
            except NotificationProvider.DoesNotExist:
                continue
            except Exception as e:
                logger.warning(f"Failed to initialize {provider_type}: {e}")
                continue
        
        raise RuntimeError("No active chat provider (Slack/Discord) configured")

    def create_war_room(self, incident: "Incident") -> tuple[str, str] | None:
        """
        Create a War Room channel for an incident.
        
        Args:
            incident: The incident requiring a War Room.
            
        Returns:
            Tuple of (channel_id, channel_url) or None if failed.
        """
        try:
            provider = self._get_provider()
        except RuntimeError as e:
            logger.error(str(e))
            return None
        
        # Generate channel name from incident
        channel_name = f"{incident.short_id}-{self._slugify(incident.title[:30])}"
        
        result = provider.create_channel(channel_name)
        
        if result:
            channel_id, channel_url = result
            
            # Set channel topic
            topic = (
                f"🚨 {incident.get_severity_display()} | "
                f"Service: {incident.service.name} | "
                f"Lead: {incident.lead.username if incident.lead else 'Unassigned'}"
            )
            provider.set_channel_topic(channel_id, topic)
            
            # Post initial message
            self._post_incident_header(provider, channel_id, incident)
            
            logger.info(f"War Room created for {incident.short_id}: {channel_url}")
            return channel_id, channel_url
        
        return None

    def invite_responders(
        self,
        channel_id: str,
        incident: "Incident",
    ) -> bool:
        """
        Invite relevant responders to the War Room.
        
        Invites:
        - Incident lead
        - Service owner team's on-call
        - Security team if security scope is impacted
        
        Args:
            channel_id: War Room channel ID.
            incident: The incident.
            
        Returns:
            True if invitations succeeded.
        """
        try:
            provider = self._get_provider()
        except RuntimeError:
            return False
        
        user_ids = []
        
        # Collect emails to look up
        emails_to_invite = []
        
        # Incident lead
        if incident.lead and incident.lead.email:
            emails_to_invite.append(incident.lead.email)
        
        # Service owner team's on-call
        if on_call := incident.service.owner_team.current_on_call:
            if on_call.email:
                emails_to_invite.append(on_call.email)
        
        # Look up Slack user IDs
        for email in emails_to_invite:
            if hasattr(provider, "lookup_user_by_email"):
                user_id = provider.lookup_user_by_email(email)
                if user_id:
                    user_ids.append(user_id)
        
        if user_ids:
            return provider.invite_users(channel_id, user_ids)
        
        return True

    def post_update(
        self,
        channel_id: str,
        message: str,
        author: str | None = None,
    ) -> bool:
        """
        Post an update message to the War Room.
        
        Args:
            channel_id: War Room channel ID.
            message: Update message.
            author: Optional author name.
            
        Returns:
            True if posted successfully.
        """
        try:
            provider = self._get_provider()
        except RuntimeError:
            return False
        
        formatted_message = {
            "title": "📝 Incident Update",
            "body": message,
            "service": author or "System",
            "status": "Update",
        }
        
        return provider.send(channel_id, formatted_message)

    def archive_war_room(self, incident: "Incident") -> bool:
        """
        Archive the War Room after incident resolution.
        
        Args:
            incident: The resolved incident.
            
        Returns:
            True if archived successfully.
        """
        if not incident.war_room_id:
            return True
        
        try:
            provider = self._get_provider()
        except RuntimeError:
            return False
        
        # Post final message
        final_message = {
            "title": "✅ Incident Resolved",
            "body": (
                f"This incident has been resolved.\n\n"
                f"*Resolution Time (MTTR):* {incident.mttr or 'N/A'}\n"
                f"*LID Document:* {incident.lid_link or 'Not created'}\n\n"
                "This channel will be archived."
            ),
            "service": incident.service.name,
            "status": "Resolved",
        }
        provider.send(incident.war_room_id, final_message)
        
        # Archive channel
        if hasattr(provider, "archive_channel"):
            return provider.archive_channel(incident.war_room_id)
        
        return True

    def _post_incident_header(
        self,
        provider,
        channel_id: str,
        incident: "Incident",
    ) -> None:
        """Post the initial incident header message."""
        header_message = {
            "title": f"🚨 Incident: {incident.title}",
            "body": incident.description or "No description provided.",
            "service": incident.service.name,
            "severity": incident.get_severity_display(),
            "status": incident.get_status_display(),
            "links": self._build_links(incident),
        }
        
        provider.send(channel_id, header_message)

    def _build_links(self, incident: "Incident") -> str:
        """Build links section for messages."""
        links = []
        
        if incident.lid_link:
            links.append(f"📄 <{incident.lid_link}|LID Document>")
        
        if incident.service.runbook_url:
            links.append(f"📖 <{incident.service.runbook_url}|Runbook>")
        
        return "\n".join(links) if links else "No links available yet."

    def _slugify(self, text: str) -> str:
        """Convert text to slug format for channel names."""
        import re
        slug = text.lower().strip()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[-\s]+", "-", slug)
        return slug[:30]


# Singleton instance
chatops_service = ChatOpsService()
