"""
IMAS Manager - ntfy.sh Notification Provider

Implementation of ntfy.sh push notifications.
ntfy.sh is a simple HTTP-based pub-sub notification service.
Self-hostable or use the public instance at ntfy.sh.

Documentation: https://docs.ntfy.sh/
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


class NtfyProvider(BaseNotificationProvider):
    """
    ntfy.sh notification provider.
    
    Sends push notifications via ntfy.sh (self-hosted or public instance).
    Supports all ntfy.sh features: priority, tags, actions, attachments.
    
    Required configuration in NotificationProvider.config:
    {
        "server_url": "https://ntfy.sh",  # Or self-hosted instance
        "default_topic": "imas-incidents",  # Default topic for notifications
        "access_token": "tk_xxx"  # Optional: for private topics
    }
    
    Optional configuration:
    {
        "username": "user",  # Basic auth (alternative to token)
        "password": "pass",
        "default_priority": 4,  # 1-5, default notifications priority
        "default_tags": ["incident", "alert"]
    }
    """
    
    REQUIRED_CONFIG_KEYS = ["server_url", "default_topic"]
    
    # ntfy priority levels (1=min, 5=max)
    SEVERITY_PRIORITY = {
        "SEV1_CRITICAL": 5,  # max/urgent
        "SEV2_HIGH": 4,      # high
        "SEV3_MEDIUM": 3,    # default
        "SEV4_LOW": 2,       # low
    }
    
    # ntfy tags (emojis) for severities
    SEVERITY_TAGS = {
        "SEV1_CRITICAL": ["rotating_light", "fire", "sos"],
        "SEV2_HIGH": ["warning", "exclamation"],
        "SEV3_MEDIUM": ["bell", "loudspeaker"],
        "SEV4_LOW": ["information_source"],
    }
    
    STATUS_TAGS = {
        "TRIGGERED": ["rotating_light"],
        "ACKNOWLEDGED": ["eyes"],
        "MITIGATED": ["construction"],
        "RESOLVED": ["white_check_mark"],
    }

    def __init__(self, config: "NotificationProviderModel") -> None:
        super().__init__(config)
        self._http_client = None

    def _validate_config(self) -> None:
        """Validate ntfy configuration."""
        for key in self.REQUIRED_CONFIG_KEYS:
            if not self.get_config_value(key):
                raise ValueError(
                    f"Missing required ntfy config: '{key}' for provider '{self.name}'"
                )

    def _get_http_client(self):
        """Get HTTP client for ntfy requests."""
        if self._http_client is not None:
            return self._http_client
        
        try:
            import httpx
            self._http_client = httpx.Client(timeout=30.0)
            return self._http_client
        except ImportError:
            logger.error("httpx not installed. Run: pip install httpx")
            raise

    def _get_auth_headers(self) -> dict[str, str]:
        """Get authentication headers if configured."""
        headers = {}
        
        # Token-based auth (preferred)
        access_token = self.get_config_value("access_token")
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
            return headers
        
        # Basic auth fallback
        username = self.get_config_value("username")
        password = self.get_config_value("password")
        if username and password:
            import base64
            credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"
        
        return headers

    def send(
        self,
        recipient: str,
        message: dict[str, Any],
    ) -> bool:
        """
        Send a notification via ntfy.sh.
        
        Args:
            recipient: Topic name (overrides default_topic if provided).
            message: Message dict with 'title', 'body', 'severity', etc.
            
        Returns:
            True if sent successfully.
        """
        server_url = self.get_config_value("server_url", "https://ntfy.sh").rstrip("/")
        topic = recipient or self.get_config_value("default_topic")
        
        url = f"{server_url}/{topic}"
        
        # Build ntfy payload
        payload = self._build_payload(message)
        headers = self._get_auth_headers()
        
        return self._send_request(url, payload, headers)

    def send_batch(
        self,
        recipients: list[str],
        message: dict[str, Any],
    ) -> dict[str, bool]:
        """
        Send notifications to multiple topics.
        
        Args:
            recipients: List of topic names.
            message: Message content dict.
            
        Returns:
            Dict mapping topic to success status.
        """
        if not recipients:
            topic = self.get_config_value("default_topic")
            return {topic: self.send("", message)}
        
        results = {}
        for recipient in recipients:
            results[recipient] = self.send(recipient, message)
        return results

    def _send_request(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> bool:
        """
        Send HTTP request to ntfy endpoint.
        
        Args:
            url: Full ntfy URL (server/topic).
            payload: Request body with ntfy headers as JSON.
            headers: Auth headers.
            
        Returns:
            True if request succeeded.
        """
        client = self._get_http_client()
        
        # ntfy accepts headers in JSON body or as HTTP headers
        # Using JSON body for simplicity
        headers["Content-Type"] = "application/json"
        
        try:
            response = client.post(url, json=payload, headers=headers)
            
            if response.status_code == 200:
                logger.info(f"ntfy notification sent to {url}")
                return True
            else:
                logger.error(
                    f"ntfy failed: {response.status_code} - {response.text[:200]}"
                )
                return False
        except Exception as e:
            logger.error(f"ntfy request error: {e}")
            return False

    def _build_payload(self, message: dict[str, Any]) -> dict[str, Any]:
        """
        Build ntfy JSON payload.
        
        Args:
            message: Message dict with incident details.
            
        Returns:
            ntfy-compatible JSON payload.
        """
        severity = message.get("severity", "").upper().replace(" ", "_").replace("-", "_")
        status = message.get("status", "TRIGGERED").upper()
        
        # Determine priority
        priority = self.SEVERITY_PRIORITY.get(severity, 3)
        if severity == "SEV1" or "SEV1" in severity:
            priority = 5
        elif severity == "SEV2" or "SEV2" in severity:
            priority = 4
        
        # Build tags
        tags = list(self.get_config_value("default_tags", []))
        
        # Add severity tags
        for sev_key, sev_tags in self.SEVERITY_TAGS.items():
            if sev_key in severity:
                tags.extend(sev_tags)
                break
        
        # Add status tags
        tags.extend(self.STATUS_TAGS.get(status, []))
        
        # Build payload
        payload = {
            "topic": self.get_config_value("default_topic"),  # Will be overridden by URL
            "title": message.get("title", "Incident Alert"),
            "message": self._format_message_body(message),
            "priority": priority,
            "tags": tags[:5],  # ntfy limits to 5 tags
        }
        
        # Add click action if links available
        links = message.get("links", "")
        if links:
            # Use first link as click URL
            first_link = links.split(",")[0].strip() if "," in links else links.strip()
            if first_link.startswith("http"):
                payload["click"] = first_link
        
        # Add actions for high severity incidents
        if priority >= 4:
            payload["actions"] = self._build_actions(message)
        
        return payload

    def _format_message_body(self, message: dict[str, Any]) -> str:
        """
        Format message body for ntfy.
        
        Args:
            message: Message dict.
            
        Returns:
            Formatted message string.
        """
        parts = []
        
        if message.get("body"):
            parts.append(message["body"])
        
        # Add metadata
        metadata = []
        if message.get("service"):
            metadata.append(f"Service: {message['service']}")
        if message.get("severity"):
            metadata.append(f"Severity: {message['severity']}")
        if message.get("status"):
            metadata.append(f"Status: {message['status']}")
        
        if metadata:
            parts.append("\n" + " | ".join(metadata))
        
        return "\n".join(parts) if parts else "No details provided."

    def _build_actions(self, message: dict[str, Any]) -> list[dict[str, str]]:
        """
        Build ntfy action buttons.
        
        Args:
            message: Message dict.
            
        Returns:
            List of ntfy action objects.
        """
        actions = []
        
        # View incident action
        incident_id = message.get("incident_id")
        if incident_id:
            actions.append({
                "action": "view",
                "label": "View Incident",
                "url": f"https://imas.local/incidents/{incident_id}",
            })
        
        # Links from message
        links = message.get("links", "")
        if links:
            link_list = [l.strip() for l in links.split(",") if l.strip()]
            for i, link in enumerate(link_list[:2]):  # Max 2 link actions
                if "slack" in link.lower():
                    actions.append({
                        "action": "view",
                        "label": "War Room",
                        "url": link,
                    })
                elif "docs.google" in link.lower() or "drive.google" in link.lower():
                    actions.append({
                        "action": "view",
                        "label": "LID Document",
                        "url": link,
                    })
        
        return actions[:3]  # ntfy limits to 3 actions

    def send_incident_notification(
        self,
        incident: "Incident",
        topic: str = "",
    ) -> bool:
        """
        Send incident notification via ntfy.
        
        Helper method that extracts incident data.
        
        Args:
            incident: Incident model instance.
            topic: Optional topic override.
            
        Returns:
            True if sent successfully.
        """
        message = {
            "incident_id": str(incident.id),
            "title": f"[{incident.severity}] {incident.title}",
            "body": incident.description or "",
            "severity": incident.severity,
            "status": incident.status,
            "service": incident.service.name if incident.service else "",
            "links": "",
        }
        
        # Add links
        links = []
        if incident.lid_link:
            links.append(incident.lid_link)
        if incident.war_room_link:
            links.append(incident.war_room_link)
        message["links"] = ", ".join(links)
        
        return self.send(topic, message)

    def check_connectivity(self) -> bool:
        """
        Verify ntfy server connectivity.
        
        Returns:
            True if server is accessible.
        """
        server_url = self.get_config_value("server_url", "https://ntfy.sh")
        client = self._get_http_client()
        
        try:
            # ntfy health check endpoint
            response = client.get(f"{server_url}/v1/health")
            if response.status_code == 200:
                logger.info(f"ntfy server {server_url} is healthy")
                return True
            
            # Fallback: try to access root
            response = client.get(server_url)
            return response.status_code in (200, 301, 302)
        except Exception as e:
            logger.error(f"ntfy connectivity check failed: {e}")
            return False


# Register provider with factory
NotificationProviderFactory.register("NTFY", NtfyProvider)
