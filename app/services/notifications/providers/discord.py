"""
IMAS Manager - Discord Notification Provider

Full implementation of Discord integration for:
- Sending notifications to channels via webhooks or bot
- Creating War Room channels (text channels)
- Managing channel permissions
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from services.notifications.providers.base import (
    BaseNotificationProvider,
    NotificationProviderFactory,
)

if TYPE_CHECKING:
    from core.models import Incident, NotificationProvider as NotificationProviderModel

logger = logging.getLogger(__name__)


class DiscordProvider(BaseNotificationProvider):
    """
    Discord notification provider.
    
    Supports two modes:
    1. Webhook mode (simple, no bot required)
    2. Bot mode (full features including channel creation)
    
    Required configuration in NotificationProvider.config:
    
    Webhook mode:
    {
        "webhook_url": "https://discord.com/api/webhooks/..."
    }
    
    Bot mode:
    {
        "bot_token": "your-bot-token",
        "guild_id": "your-server-id",
        "incidents_category_id": "category-for-war-rooms"  # Optional
    }
    """
    
    # Discord embed color codes (decimal)
    SEVERITY_COLORS = {
        "SEV1_CRITICAL": 0xDC3545,  # Red
        "SEV2_HIGH": 0xFD7E14,      # Orange
        "SEV3_MEDIUM": 0xFFC107,    # Yellow
        "SEV4_LOW": 0x0DCAF0,       # Cyan
    }
    
    STATUS_COLORS = {
        "TRIGGERED": 0xDC3545,      # Red
        "ACKNOWLEDGED": 0xFD7E14,   # Orange
        "MITIGATED": 0x0D6EFD,      # Blue
        "RESOLVED": 0x198754,       # Green
    }

    def __init__(self, config: "NotificationProviderModel") -> None:
        super().__init__(config)
        self._client = None
        self._http_client = None

    def _validate_config(self) -> None:
        """Validate Discord configuration."""
        has_webhook = bool(self.get_config_value("webhook_url"))
        has_bot = bool(self.get_config_value("bot_token"))
        
        if not has_webhook and not has_bot:
            raise ValueError(
                f"Discord provider '{self.name}' requires either 'webhook_url' or 'bot_token'"
            )
        
        if has_bot and not self.get_config_value("guild_id"):
            raise ValueError(
                f"Discord bot mode requires 'guild_id' for provider '{self.name}'"
            )

    def _get_http_client(self):
        """Get HTTP client for webhook requests."""
        if self._http_client is not None:
            return self._http_client
        
        try:
            import httpx
            self._http_client = httpx.Client(timeout=30.0)
            return self._http_client
        except ImportError:
            logger.error("httpx not installed. Run: pip install httpx")
            raise

    def _get_bot_headers(self) -> dict[str, str]:
        """Get headers for Discord Bot API requests."""
        token = self.get_config_value("bot_token")
        return {
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
        }

    @property
    def is_webhook_mode(self) -> bool:
        """Check if using webhook mode."""
        return bool(self.get_config_value("webhook_url"))

    @property
    def is_bot_mode(self) -> bool:
        """Check if using bot mode."""
        return bool(self.get_config_value("bot_token"))

    def send(
        self,
        recipient: str,
        message: dict[str, Any],
    ) -> bool:
        """
        Send a message to Discord.
        
        Args:
            recipient: Channel ID (bot mode) or ignored (webhook mode).
            message: Message dict with 'title', 'body', 'severity', etc.
            
        Returns:
            True if sent successfully.
        """
        if self.is_webhook_mode:
            return self._send_via_webhook(message)
        else:
            return self._send_via_bot(recipient, message)

    def send_batch(
        self,
        recipients: list[str],
        message: dict[str, Any],
    ) -> dict[str, bool]:
        """
        Send notifications to multiple Discord channels.
        
        Args:
            recipients: List of channel IDs.
            message: Message content dict.
            
        Returns:
            Dict mapping channel ID to success status.
        """
        results = {}
        for recipient in recipients:
            results[recipient] = self.send(recipient, message)
        return results

    def _send_via_webhook(self, message: dict[str, Any]) -> bool:
        """Send message via Discord webhook."""
        webhook_url = self.get_config_value("webhook_url")
        client = self._get_http_client()
        
        embed = self._build_embed(message)
        payload = {
            "embeds": [embed],
            "username": "IMAS Manager",
        }
        
        try:
            response = client.post(webhook_url, json=payload)
            
            if response.status_code in (200, 204):
                logger.info("Discord webhook message sent successfully")
                return True
            else:
                logger.error(
                    f"Discord webhook failed: {response.status_code} - {response.text}"
                )
                return False
        except Exception as e:
            logger.error(f"Discord webhook error: {e}")
            return False

    def _send_via_bot(self, channel_id: str, message: dict[str, Any]) -> bool:
        """Send message via Discord Bot API."""
        client = self._get_http_client()
        headers = self._get_bot_headers()
        
        embed = self._build_embed(message)
        payload = {"embeds": [embed]}
        
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        
        try:
            response = client.post(url, json=payload, headers=headers)
            
            if response.status_code == 200:
                logger.info(f"Discord bot message sent to channel {channel_id}")
                return True
            else:
                logger.error(
                    f"Discord bot message failed: {response.status_code} - {response.text}"
                )
                return False
        except Exception as e:
            logger.error(f"Discord bot error: {e}")
            return False

    def _build_embed(self, message: dict[str, Any]) -> dict[str, Any]:
        """
        Build a Discord embed from message dict.
        
        Args:
            message: Message dict with incident details.
            
        Returns:
            Discord embed object.
        """
        severity = message.get("severity", "").upper().replace(" ", "_").replace("-", "_")
        status = message.get("status", "TRIGGERED").upper()
        
        # Get color based on severity or status
        if "SEV1" in severity:
            color = self.SEVERITY_COLORS["SEV1_CRITICAL"]
        elif "SEV2" in severity:
            color = self.SEVERITY_COLORS["SEV2_HIGH"]
        elif "SEV3" in severity:
            color = self.SEVERITY_COLORS["SEV3_MEDIUM"]
        else:
            color = self.SEVERITY_COLORS.get("SEV4_LOW", 0x6C757D)
        
        # Build fields
        fields = []
        
        if message.get("service"):
            fields.append({
                "name": "🖥️ Service",
                "value": message["service"],
                "inline": True,
            })
        
        if message.get("severity"):
            fields.append({
                "name": "⚠️ Severity",
                "value": message["severity"],
                "inline": True,
            })
        
        if message.get("status"):
            fields.append({
                "name": "📊 Status",
                "value": message["status"],
                "inline": True,
            })
        
        # Add links as a field
        if message.get("links"):
            fields.append({
                "name": "🔗 Links",
                "value": message["links"],
                "inline": False,
            })
        
        embed = {
            "title": message.get("title", "Incident Alert"),
            "description": message.get("body", "")[:4096],  # Discord limit
            "color": color,
            "fields": fields,
            "footer": {
                "text": "IMAS Manager",
            },
        }
        
        return embed

    def create_channel(
        self,
        name: str,
        topic: str = "",
    ) -> tuple[str, str] | None:
        """
        Create a Discord text channel (War Room).
        
        Requires bot mode with appropriate permissions.
        
        Args:
            name: Channel name (will be sanitized for Discord).
            topic: Channel topic/description.
            
        Returns:
            Tuple of (channel_id, channel_url) or None if failed.
        """
        if not self.is_bot_mode:
            logger.warning("Channel creation requires bot mode")
            return None
        
        guild_id = self.get_config_value("guild_id")
        category_id = self.get_config_value("incidents_category_id")
        
        client = self._get_http_client()
        headers = self._get_bot_headers()
        
        # Sanitize channel name for Discord (lowercase, no spaces)
        clean_name = name.lower().replace(" ", "-").replace("_", "-")[:100]
        
        payload = {
            "name": clean_name,
            "type": 0,  # Text channel
            "topic": topic[:1024] if topic else None,
        }
        
        if category_id:
            payload["parent_id"] = category_id
        
        url = f"https://discord.com/api/v10/guilds/{guild_id}/channels"
        
        try:
            response = client.post(url, json=payload, headers=headers)
            
            if response.status_code == 201:
                data = response.json()
                channel_id = data["id"]
                channel_url = f"https://discord.com/channels/{guild_id}/{channel_id}"
                logger.info(f"Created Discord channel: {clean_name} ({channel_id})")
                return (channel_id, channel_url)
            else:
                logger.error(
                    f"Failed to create Discord channel: {response.status_code} - {response.text}"
                )
                return None
        except Exception as e:
            logger.error(f"Discord channel creation error: {e}")
            return None

    def archive_channel(self, channel_id: str) -> bool:
        """
        Archive a Discord channel by moving it to archive category.
        
        Note: Discord doesn't have native archiving, so we rename and optionally
        move to an archive category.
        
        Args:
            channel_id: The channel ID to archive.
            
        Returns:
            True if archived successfully.
        """
        if not self.is_bot_mode:
            logger.warning("Channel archiving requires bot mode")
            return False
        
        client = self._get_http_client()
        headers = self._get_bot_headers()
        
        archive_category = self.get_config_value("archive_category_id")
        
        # Rename channel with archived- prefix
        payload = {
            "name": f"archived-{channel_id[-6:]}",
        }
        
        if archive_category:
            payload["parent_id"] = archive_category
        
        url = f"https://discord.com/api/v10/channels/{channel_id}"
        
        try:
            response = client.patch(url, json=payload, headers=headers)
            
            if response.status_code == 200:
                logger.info(f"Archived Discord channel {channel_id}")
                return True
            else:
                logger.error(
                    f"Failed to archive Discord channel: {response.status_code}"
                )
                return False
        except Exception as e:
            logger.error(f"Discord archive error: {e}")
            return False

    def delete_channel(self, channel_id: str) -> bool:
        """
        Delete a Discord channel.
        
        Args:
            channel_id: The channel ID to delete.
            
        Returns:
            True if deleted successfully.
        """
        if not self.is_bot_mode:
            return False
        
        client = self._get_http_client()
        headers = self._get_bot_headers()
        
        url = f"https://discord.com/api/v10/channels/{channel_id}"
        
        try:
            response = client.delete(url, headers=headers)
            return response.status_code in (200, 204)
        except Exception as e:
            logger.error(f"Discord delete channel error: {e}")
            return False

    def send_war_room_header(
        self,
        channel_id: str,
        incident: "Incident",
    ) -> bool:
        """
        Send the initial War Room header message.
        
        Args:
            channel_id: Discord channel ID.
            incident: The incident for the War Room.
            
        Returns:
            True if sent successfully.
        """
        embed = {
            "title": f"🚨 War Room: {incident.short_id}",
            "description": f"**{incident.title}**\n\n{incident.description or 'No description provided.'}",
            "color": self.SEVERITY_COLORS.get(incident.severity, 0xDC3545),
            "fields": [
                {
                    "name": "🖥️ Service",
                    "value": incident.service.name if incident.service else "Unknown",
                    "inline": True,
                },
                {
                    "name": "⚠️ Severity",
                    "value": incident.get_severity_display(),
                    "inline": True,
                },
                {
                    "name": "📊 Status",
                    "value": incident.get_status_display(),
                    "inline": True,
                },
            ],
        }
        
        # Add links
        links = []
        if incident.lid_link:
            links.append(f"📄 [LID Document]({incident.lid_link})")
        if incident.service and incident.service.runbook_url:
            links.append(f"📖 [Runbook]({incident.service.runbook_url})")
        
        if links:
            embed["fields"].append({
                "name": "🔗 Links",
                "value": "\n".join(links),
                "inline": False,
            })
        
        embed["footer"] = {
            "text": f"Created at {incident.created_at.strftime('%Y-%m-%d %H:%M UTC')}"
        }
        
        if not self.is_bot_mode:
            return False
        
        client = self._get_http_client()
        headers = self._get_bot_headers()
        
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        payload = {"embeds": [embed]}
        
        try:
            response = client.post(url, json=payload, headers=headers)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Discord war room header error: {e}")
            return False


# Register provider with factory
NotificationProviderFactory.register("DISCORD", DiscordProvider)