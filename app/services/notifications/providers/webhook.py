"""
IMAS Manager - Webhook Notification Provider

Generic webhook provider for integrating with external systems:
- PagerDuty
- Opsgenie
- Custom alerting systems
- Slack-compatible webhooks
- Microsoft Teams
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from services.notifications.providers.base import (
    BaseNotificationProvider,
    NotificationProviderFactory,
)

if TYPE_CHECKING:
    from core.models import Incident, NotificationProvider as NotificationProviderModel

logger = logging.getLogger(__name__)


class WebhookProvider(BaseNotificationProvider):
    """
    Generic webhook notification provider.
    
    Supports multiple payload formats for different systems.
    
    Required configuration in NotificationProvider.config:
    {
        "url": "https://your-webhook-endpoint.com/webhook",
        "method": "POST",  # Optional, defaults to POST
        "format": "json",  # json, slack, teams, pagerduty, opsgenie, custom
        "headers": {  # Optional custom headers
            "Authorization": "Bearer xxx"
        },
        "template": {}  # Optional custom payload template
    }
    
    Payload Formats:
    - json: Standard JSON with incident fields
    - slack: Slack-compatible incoming webhook
    - teams: Microsoft Teams connector
    - pagerduty: PagerDuty Events API v2
    - opsgenie: Opsgenie Alert API
    - custom: Use 'template' config with variable substitution
    """
    
    REQUIRED_CONFIG_KEYS = ["url"]
    
    SUPPORTED_FORMATS = ["json", "slack", "teams", "pagerduty", "opsgenie", "custom"]
    
    # Severity mapping for external systems
    PAGERDUTY_SEVERITY = {
        "SEV1_CRITICAL": "critical",
        "SEV2_HIGH": "error",
        "SEV3_MEDIUM": "warning",
        "SEV4_LOW": "info",
    }
    
    OPSGENIE_PRIORITY = {
        "SEV1_CRITICAL": "P1",
        "SEV2_HIGH": "P2",
        "SEV3_MEDIUM": "P3",
        "SEV4_LOW": "P4",
    }

    def __init__(self, config: "NotificationProviderModel") -> None:
        super().__init__(config)
        self._http_client = None

    def _validate_config(self) -> None:
        """Validate webhook configuration."""
        if not self.get_config_value("url"):
            raise ValueError(
                f"Missing required webhook config: 'url' for provider '{self.name}'"
            )
        
        fmt = self.get_config_value("format", "json")
        if fmt not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported format '{fmt}'. Supported: {self.SUPPORTED_FORMATS}"
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

    def send(
        self,
        recipient: str,
        message: dict[str, Any],
    ) -> bool:
        """
        Send a webhook notification.
        
        Args:
            recipient: Ignored for most formats (URL from config).
                      Can override URL if needed.
            message: Message dict with incident details.
            
        Returns:
            True if sent successfully.
        """
        url = recipient if recipient.startswith("http") else self.get_config_value("url")
        method = self.get_config_value("method", "POST").upper()
        fmt = self.get_config_value("format", "json")
        
        # Build payload based on format
        payload = self._build_payload(message, fmt)
        
        # Get headers
        headers = {"Content-Type": "application/json"}
        custom_headers = self.get_config_value("headers", {})
        if custom_headers:
            headers.update(custom_headers)
        
        return self._send_request(url, method, payload, headers)

    def send_batch(
        self,
        recipients: list[str],
        message: dict[str, Any],
    ) -> dict[str, bool]:
        """
        Send webhook notifications to multiple URLs.
        
        Args:
            recipients: List of webhook URLs (or empty to use config URL).
            message: Message content dict.
            
        Returns:
            Dict mapping URL to success status.
        """
        if not recipients:
            # Single send to configured URL
            url = self.get_config_value("url")
            return {url: self.send("", message)}
        
        results = {}
        for recipient in recipients:
            results[recipient] = self.send(recipient, message)
        return results

    def _send_request(
        self,
        url: str,
        method: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> bool:
        """
        Send HTTP request to webhook endpoint.
        
        Args:
            url: Webhook URL.
            method: HTTP method.
            payload: Request body.
            headers: Request headers.
            
        Returns:
            True if request succeeded.
        """
        client = self._get_http_client()
        
        try:
            if method == "GET":
                response = client.get(url, headers=headers, params=payload)
            else:
                response = client.request(method, url, headers=headers, json=payload)
            
            # Most webhooks return 2xx on success
            if 200 <= response.status_code < 300:
                logger.info(f"Webhook sent successfully to {url}")
                return True
            else:
                logger.error(
                    f"Webhook failed: {response.status_code} - {response.text[:200]}"
                )
                return False
        except Exception as e:
            logger.error(f"Webhook request error: {e}")
            return False

    def _build_payload(
        self,
        message: dict[str, Any],
        fmt: str,
    ) -> dict[str, Any]:
        """
        Build payload based on format type.
        
        Args:
            message: Message dict with incident details.
            fmt: Target format (json, slack, teams, etc.)
            
        Returns:
            Formatted payload dict.
        """
        if fmt == "slack":
            return self._build_slack_payload(message)
        elif fmt == "teams":
            return self._build_teams_payload(message)
        elif fmt == "pagerduty":
            return self._build_pagerduty_payload(message)
        elif fmt == "opsgenie":
            return self._build_opsgenie_payload(message)
        elif fmt == "custom":
            return self._build_custom_payload(message)
        else:
            return self._build_json_payload(message)

    def _build_json_payload(self, message: dict[str, Any]) -> dict[str, Any]:
        """Build standard JSON payload."""
        return {
            "source": "imas-manager",
            "event_type": "incident",
            "title": message.get("title", "Incident Alert"),
            "description": message.get("body", ""),
            "severity": message.get("severity", "unknown"),
            "status": message.get("status", "triggered"),
            "service": message.get("service", ""),
            "links": message.get("links", ""),
            "incident_id": message.get("incident_id", ""),
            "timestamp": message.get("timestamp", ""),
        }

    def _build_slack_payload(self, message: dict[str, Any]) -> dict[str, Any]:
        """Build Slack incoming webhook payload."""
        severity = message.get("severity", "")
        
        # Color based on severity
        if "SEV1" in str(severity).upper():
            color = "#dc3545"
        elif "SEV2" in str(severity).upper():
            color = "#fd7e14"
        elif "SEV3" in str(severity).upper():
            color = "#ffc107"
        else:
            color = "#0dcaf0"
        
        return {
            "attachments": [
                {
                    "color": color,
                    "title": message.get("title", "Incident Alert"),
                    "text": message.get("body", ""),
                    "fields": [
                        {
                            "title": "Service",
                            "value": message.get("service", "N/A"),
                            "short": True,
                        },
                        {
                            "title": "Severity",
                            "value": severity,
                            "short": True,
                        },
                        {
                            "title": "Status",
                            "value": message.get("status", "N/A"),
                            "short": True,
                        },
                    ],
                    "footer": "IMAS Manager",
                }
            ]
        }

    def _build_teams_payload(self, message: dict[str, Any]) -> dict[str, Any]:
        """Build Microsoft Teams connector payload."""
        severity = message.get("severity", "")
        
        # Theme color based on severity
        if "SEV1" in str(severity).upper():
            theme_color = "dc3545"
        elif "SEV2" in str(severity).upper():
            theme_color = "fd7e14"
        else:
            theme_color = "0078d4"
        
        return {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": theme_color,
            "summary": message.get("title", "Incident Alert"),
            "sections": [
                {
                    "activityTitle": message.get("title", "Incident Alert"),
                    "facts": [
                        {"name": "Service", "value": message.get("service", "N/A")},
                        {"name": "Severity", "value": severity},
                        {"name": "Status", "value": message.get("status", "N/A")},
                    ],
                    "text": message.get("body", ""),
                }
            ],
        }

    def _build_pagerduty_payload(self, message: dict[str, Any]) -> dict[str, Any]:
        """Build PagerDuty Events API v2 payload."""
        severity = message.get("severity", "SEV3_MEDIUM")
        pd_severity = self.PAGERDUTY_SEVERITY.get(severity, "warning")
        
        routing_key = self.get_config_value("routing_key", "")
        
        return {
            "routing_key": routing_key,
            "event_action": "trigger",
            "dedup_key": message.get("incident_id", ""),
            "payload": {
                "summary": message.get("title", "Incident Alert"),
                "source": "imas-manager",
                "severity": pd_severity,
                "custom_details": {
                    "service": message.get("service", ""),
                    "status": message.get("status", ""),
                    "description": message.get("body", ""),
                    "links": message.get("links", ""),
                },
            },
        }

    def _build_opsgenie_payload(self, message: dict[str, Any]) -> dict[str, Any]:
        """Build Opsgenie Alert API payload."""
        severity = message.get("severity", "SEV3_MEDIUM")
        priority = self.OPSGENIE_PRIORITY.get(severity, "P3")
        
        return {
            "message": message.get("title", "Incident Alert"),
            "description": message.get("body", ""),
            "priority": priority,
            "source": "imas-manager",
            "alias": message.get("incident_id", ""),
            "details": {
                "service": message.get("service", ""),
                "status": message.get("status", ""),
                "severity": message.get("severity", ""),
            },
        }

    def _build_custom_payload(self, message: dict[str, Any]) -> dict[str, Any]:
        """
        Build custom payload from template.
        
        Template uses Python string formatting with message dict values.
        Example template:
        {
            "alert": "{title}",
            "details": {
                "svc": "{service}",
                "prio": "{severity}"
            }
        }
        """
        template = self.get_config_value("template", {})
        
        if not template:
            return self._build_json_payload(message)
        
        def substitute(obj):
            """Recursively substitute variables in template."""
            if isinstance(obj, str):
                try:
                    return obj.format(**message)
                except KeyError:
                    return obj
            elif isinstance(obj, dict):
                return {k: substitute(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [substitute(item) for item in obj]
            else:
                return obj
        
        return substitute(template)

    def send_incident_event(
        self,
        incident: "Incident",
        event_type: str = "trigger",
    ) -> bool:
        """
        Send incident event to webhook.
        
        Helper method that extracts incident data and sends.
        
        Args:
            incident: Incident model instance.
            event_type: Event type (trigger, acknowledge, resolve).
            
        Returns:
            True if sent successfully.
        """
        message = {
            "incident_id": str(incident.id),
            "short_id": incident.short_id,
            "title": incident.title,
            "body": incident.description or "",
            "severity": incident.severity,
            "status": incident.status,
            "service": incident.service.name if incident.service else "",
            "event_type": event_type,
            "links": "",
        }
        
        # Add links
        links = []
        if incident.lid_link:
            links.append(incident.lid_link)
        if incident.war_room_link:
            links.append(incident.war_room_link)
        message["links"] = ", ".join(links)
        
        return self.send("", message)


# Register providers with factory
NotificationProviderFactory.register("WEBHOOK", WebhookProvider)
NotificationProviderFactory.register("PAGERDUTY", WebhookProvider)
NotificationProviderFactory.register("OPSGENIE", WebhookProvider)
NotificationProviderFactory.register("TEAMS", WebhookProvider)