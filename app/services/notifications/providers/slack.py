"""
IMAS Manager - Slack Notification Provider

Full implementation of Slack integration for:
- Sending notifications to channels and users
- Creating War Room channels
- Inviting users to channels
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.conf import settings

from services.notifications.providers.base import BaseNotificationProvider

if TYPE_CHECKING:
    from core.models import NotificationProvider

logger = logging.getLogger(__name__)


class SlackProvider(BaseNotificationProvider):
    """
    Slack notification provider.
    
    Required configuration in NotificationProvider.config:
    {
        "bot_token": "xoxb-...",  # Bot User OAuth Token
        "default_channel": "#incidents",  # Optional default channel
    }
    """
    
    REQUIRED_CONFIG_KEYS = ["bot_token"]

    def __init__(self, config: "NotificationProvider") -> None:
        super().__init__(config)
        self._client = None

    def _validate_config(self) -> None:
        """Validate required Slack configuration."""
        for key in self.REQUIRED_CONFIG_KEYS:
            if not self.get_config_value(key):
                raise ValueError(
                    f"Missing required Slack config: '{key}' for provider '{self.name}'"
                )

    def _get_client(self):
        """
        Get or create the Slack WebClient.
        
        Returns:
            Slack WebClient instance.
        """
        if self._client is not None:
            return self._client
        
        try:
            from slack_sdk import WebClient
            from slack_sdk.errors import SlackApiError  # noqa: F401
            
            self._client = WebClient(token=self.get_config_value("bot_token"))
            return self._client
        except ImportError:
            logger.error("slack_sdk not installed. Run: pip install slack-sdk")
            raise

    def send(
        self,
        recipient: str,
        message: dict[str, Any],
    ) -> bool:
        """
        Send a message to a Slack channel or user.
        
        Args:
            recipient: Channel ID (C0123456789) or User ID (U0123456789).
            message: Message dict with 'title', 'body', 'severity', 'links'.
            
        Returns:
            True if sent successfully.
        """
        client = self._get_client()
        
        try:
            blocks = self._format_incident_blocks(message)
            text = message.get("title", "New Incident Alert")
            
            response = client.chat_postMessage(
                channel=recipient,
                text=text,
                blocks=blocks,
                unfurl_links=False,
                unfurl_media=False,
            )
            
            if response["ok"]:
                logger.info(f"Slack message sent to {recipient}")
                return True
            else:
                logger.error(f"Slack API error: {response.get('error')}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send Slack message to {recipient}: {e}")
            return False

    def send_batch(
        self,
        recipients: list[str],
        message: dict[str, Any],
    ) -> dict[str, bool]:
        """
        Send messages to multiple recipients.
        
        Args:
            recipients: List of channel/user IDs.
            message: Message content.
            
        Returns:
            Dict mapping recipient to success status.
        """
        results = {}
        for recipient in recipients:
            results[recipient] = self.send(recipient, message)
        return results

    def _format_incident_blocks(self, message: dict[str, Any]) -> list[dict]:
        """
        Format message as Slack Block Kit blocks.
        
        Creates a rich, formatted incident notification.
        """
        severity = message.get("severity", "Unknown")
        severity_emoji = self._get_severity_emoji(severity)
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{severity_emoji} {message.get('title', 'Incident Alert')}",
                    "emoji": True,
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity:*\n{severity}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Service:*\n{message.get('service', 'Unknown')}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Status:*\n{message.get('status', 'Triggered')}",
                    },
                ]
            },
        ]
        
        # Add description if present
        if body := message.get("body"):
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Description:*\n{body[:500]}",
                }
            })
        
        # Add links section
        if links := message.get("links"):
            blocks.append({"type": "divider"})
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Quick Links:*\n{links}",
                }
            })
        
        # Add action buttons
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "🔍 View Incident",
                        "emoji": True,
                    },
                    "style": "primary",
                    "url": message.get("incident_url", "#"),
                },
            ]
        })
        
        return blocks

    def _get_severity_emoji(self, severity: str) -> str:
        """Get emoji for severity level."""
        emoji_map = {
            "SEV1 - Critical": "🔴",
            "SEV1_CRITICAL": "🔴",
            "SEV2 - High": "🟠",
            "SEV2_HIGH": "🟠",
            "SEV3 - Medium": "🟡",
            "SEV3_MEDIUM": "🟡",
            "SEV4 - Low": "🟢",
            "SEV4_LOW": "🟢",
        }
        return emoji_map.get(severity, "⚪")

    # -------------------------------------------------------------------------
    # War Room Methods
    # -------------------------------------------------------------------------

    def create_channel(self, name: str, is_private: bool = False) -> tuple[str, str] | None:
        """
        Create a new Slack channel for War Room.
        
        Args:
            name: Channel name (will be prefixed with 'inc-').
            is_private: Whether to create a private channel.
            
        Returns:
            Tuple of (channel_id, channel_url) or None if failed.
        """
        client = self._get_client()
        
        # Sanitize channel name (lowercase, no spaces, max 80 chars)
        channel_name = f"inc-{name}".lower().replace(" ", "-")[:80]
        
        try:
            response = client.conversations_create(
                name=channel_name,
                is_private=is_private,
            )
            
            if response["ok"]:
                channel = response["channel"]
                channel_id = channel["id"]
                # Construct channel URL
                team_id = self._get_team_id()
                channel_url = f"https://slack.com/app_redirect?channel={channel_id}"
                if team_id:
                    channel_url = f"https://app.slack.com/client/{team_id}/{channel_id}"
                
                logger.info(f"Created Slack channel: {channel_name} ({channel_id})")
                return channel_id, channel_url
            else:
                logger.error(f"Failed to create channel: {response.get('error')}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating Slack channel {channel_name}: {e}")
            return None

    def invite_users(self, channel_id: str, user_ids: list[str]) -> bool:
        """
        Invite users to a channel.
        
        Args:
            channel_id: The channel ID.
            user_ids: List of Slack user IDs.
            
        Returns:
            True if all invitations succeeded.
        """
        if not user_ids:
            return True
        
        client = self._get_client()
        
        try:
            response = client.conversations_invite(
                channel=channel_id,
                users=",".join(user_ids),
            )
            
            if response["ok"]:
                logger.info(f"Invited {len(user_ids)} users to {channel_id}")
                return True
            else:
                logger.error(f"Failed to invite users: {response.get('error')}")
                return False
                
        except Exception as e:
            # Handle "already_in_channel" gracefully
            if "already_in_channel" in str(e):
                logger.info(f"Users already in channel {channel_id}")
                return True
            logger.error(f"Error inviting users to {channel_id}: {e}")
            return False

    def lookup_user_by_email(self, email: str) -> str | None:
        """
        Find a Slack user ID by email address.
        
        Args:
            email: User's email address.
            
        Returns:
            Slack user ID or None if not found.
        """
        client = self._get_client()
        
        try:
            response = client.users_lookupByEmail(email=email)
            
            if response["ok"]:
                return response["user"]["id"]
            else:
                logger.warning(f"User not found for email {email}")
                return None
                
        except Exception as e:
            logger.error(f"Error looking up user by email {email}: {e}")
            return None

    def set_channel_topic(self, channel_id: str, topic: str) -> bool:
        """
        Set the channel topic.
        
        Args:
            channel_id: The channel ID.
            topic: Topic text.
            
        Returns:
            True if successful.
        """
        client = self._get_client()
        
        try:
            response = client.conversations_setTopic(
                channel=channel_id,
                topic=topic[:250],  # Slack limit
            )
            return response["ok"]
        except Exception as e:
            logger.error(f"Error setting channel topic: {e}")
            return False

    def archive_channel(self, channel_id: str) -> bool:
        """
        Archive a channel (after incident resolution).
        
        Args:
            channel_id: The channel ID.
            
        Returns:
            True if successful.
        """
        client = self._get_client()
        
        try:
            response = client.conversations_archive(channel=channel_id)
            if response["ok"]:
                logger.info(f"Archived Slack channel {channel_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error archiving channel {channel_id}: {e}")
            return False

    def _get_team_id(self) -> str | None:
        """Get the Slack workspace team ID."""
        client = self._get_client()
        
        try:
            response = client.auth_test()
            if response["ok"]:
                return response.get("team_id")
        except Exception:
            pass
        return None


# Register with factory
from services.notifications.providers.base import NotificationProviderFactory
NotificationProviderFactory.register("SLACK", SlackProvider)
