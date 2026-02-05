"""
IMAS Manager - OVH SMS Notification Provider

Implementation of OVH SMS API for critical alerts.
Used for SEV1/SEV2 incidents when immediate attention is required.
"""
from __future__ import annotations

import hashlib
import logging
import time
from typing import TYPE_CHECKING, Any

from services.notifications.providers.base import (
    BaseNotificationProvider,
    NotificationProviderFactory,
)

if TYPE_CHECKING:
    from core.models import NotificationProvider as NotificationProviderModel

logger = logging.getLogger(__name__)


class OVHSMSProvider(BaseNotificationProvider):
    """
    OVH SMS notification provider.
    
    Uses OVH API v1 for sending SMS messages.
    
    Required configuration in NotificationProvider.config:
    {
        "application_key": "your-app-key",
        "application_secret": "your-app-secret",
        "consumer_key": "your-consumer-key",
        "service_name": "sms-xxxxx-1",  # Your SMS service name
        "sender": "IMAS"  # Optional, defaults to short code
    }
    
    To get API credentials:
    1. Go to https://api.ovh.com/createToken/
    2. Create a token with POST /sms/{serviceName}/jobs rights
    """
    
    OVH_API_ENDPOINT = "https://eu.api.ovh.com/1.0"
    REQUIRED_CONFIG_KEYS = [
        "application_key",
        "application_secret",
        "consumer_key",
        "service_name",
    ]

    def __init__(self, config: "NotificationProviderModel") -> None:
        super().__init__(config)
        self._http_client = None

    def _validate_config(self) -> None:
        """Validate required OVH configuration."""
        for key in self.REQUIRED_CONFIG_KEYS:
            if not self.get_config_value(key):
                raise ValueError(
                    f"Missing required OVH SMS config: '{key}' for provider '{self.name}'"
                )

    def _get_http_client(self):
        """Get HTTP client for OVH API requests."""
        if self._http_client is not None:
            return self._http_client
        
        try:
            import httpx
            self._http_client = httpx.Client(timeout=30.0)
            return self._http_client
        except ImportError:
            logger.error("httpx not installed. Run: pip install httpx")
            raise

    def _generate_signature(
        self,
        method: str,
        url: str,
        body: str,
        timestamp: str,
    ) -> str:
        """
        Generate OVH API signature.
        
        The signature is computed as:
        "$1$" + SHA1(AS+"+"+CK+"+"+METHOD+"+"+QUERY+"+"+BODY+"+"+TSTAMP)
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full URL including query params
            body: Request body as string
            timestamp: Unix timestamp as string
            
        Returns:
            OVH signature string.
        """
        app_secret = self.get_config_value("application_secret")
        consumer_key = self.get_config_value("consumer_key")
        
        to_sign = "+".join([
            app_secret,
            consumer_key,
            method.upper(),
            url,
            body,
            timestamp,
        ])
        
        signature = hashlib.sha1(to_sign.encode("utf-8")).hexdigest()
        return f"$1${signature}"

    def _get_timestamp(self) -> str:
        """Get current Unix timestamp as string."""
        return str(int(time.time()))

    def _make_request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
    ) -> dict | None:
        """
        Make authenticated request to OVH API.
        
        Args:
            method: HTTP method.
            path: API path (e.g., "/sms/sms-xxx/jobs").
            body: Request body dict (will be JSON encoded).
            
        Returns:
            Response JSON or None on error.
        """
        import json
        
        client = self._get_http_client()
        url = f"{self.OVH_API_ENDPOINT}{path}"
        body_str = json.dumps(body) if body else ""
        timestamp = self._get_timestamp()
        
        headers = {
            "Content-Type": "application/json",
            "X-Ovh-Application": self.get_config_value("application_key"),
            "X-Ovh-Consumer": self.get_config_value("consumer_key"),
            "X-Ovh-Timestamp": timestamp,
            "X-Ovh-Signature": self._generate_signature(method, url, body_str, timestamp),
        }
        
        try:
            if method.upper() == "GET":
                response = client.get(url, headers=headers)
            elif method.upper() == "POST":
                response = client.post(url, headers=headers, content=body_str)
            else:
                response = client.request(method, url, headers=headers, content=body_str)
            
            if response.status_code in (200, 201):
                return response.json()
            else:
                logger.error(
                    f"OVH API error: {response.status_code} - {response.text}"
                )
                return None
        except Exception as e:
            logger.error(f"OVH API request failed: {e}")
            return None

    def send(
        self,
        recipient: str,
        message: dict[str, Any],
    ) -> bool:
        """
        Send an SMS message.
        
        Args:
            recipient: Phone number in international format (e.g., +33612345678).
            message: Message dict with 'title' and 'body'.
            
        Returns:
            True if sent successfully.
        """
        return self.send_sms(recipient, message)

    def send_sms(
        self,
        phone_number: str,
        message: dict[str, Any],
    ) -> bool:
        """
        Send SMS to a single phone number.
        
        Args:
            phone_number: Phone number in international format.
            message: Message dict to format.
            
        Returns:
            True if sent successfully.
        """
        service_name = self.get_config_value("service_name")
        sender = self.get_config_value("sender", "")
        
        # Format SMS text (160 char limit for single SMS)
        sms_text = self._format_sms_text(message)
        
        # Normalize phone number
        phone = self._normalize_phone(phone_number)
        
        payload = {
            "receivers": [phone],
            "message": sms_text,
            "noStopClause": True,  # For alerts, no STOP mention needed
            "priority": "high",
        }
        
        if sender:
            payload["sender"] = sender
        
        path = f"/sms/{service_name}/jobs"
        result = self._make_request("POST", path, payload)
        
        if result:
            job_ids = result.get("ids", [])
            logger.info(f"OVH SMS sent to {phone}: job IDs {job_ids}")
            return True
        else:
            logger.error(f"Failed to send SMS to {phone}")
            return False

    def send_batch(
        self,
        phone_numbers: list[str],
        message: dict[str, Any],
    ) -> dict[str, bool]:
        """
        Send SMS to multiple phone numbers.
        
        OVH supports batch sending in a single API call.
        
        Args:
            phone_numbers: List of phone numbers.
            message: Message dict to format.
            
        Returns:
            Dict mapping phone number to success status.
        """
        service_name = self.get_config_value("service_name")
        sender = self.get_config_value("sender", "")
        
        sms_text = self._format_sms_text(message)
        phones = [self._normalize_phone(p) for p in phone_numbers]
        
        payload = {
            "receivers": phones,
            "message": sms_text,
            "noStopClause": True,
            "priority": "high",
        }
        
        if sender:
            payload["sender"] = sender
        
        path = f"/sms/{service_name}/jobs"
        result = self._make_request("POST", path, payload)
        
        if result:
            # OVH returns list of job IDs
            job_ids = result.get("ids", [])
            logger.info(f"OVH batch SMS sent to {len(phones)} recipients")
            return {phone: True for phone in phone_numbers}
        else:
            return {phone: False for phone in phone_numbers}

    def _format_sms_text(self, message: dict[str, Any]) -> str:
        """
        Format message for SMS.
        
        SMS are limited to 160 characters for single segment.
        We try to stay under this limit for cost efficiency.
        
        Args:
            message: Message dict with incident details.
            
        Returns:
            Formatted SMS text.
        """
        title = message.get("title", "Alert")
        severity = message.get("severity", "")
        service = message.get("service", "")
        
        # Build compact message
        parts = []
        
        # Severity emoji
        if "SEV1" in str(severity).upper():
            parts.append("🔴")
        elif "SEV2" in str(severity).upper():
            parts.append("🟠")
        else:
            parts.append("⚠️")
        
        # Core message
        if severity:
            parts.append(f"[{severity}]")
        
        # Add service if space permits
        if service:
            parts.append(f"{service}:")
        
        # Add truncated title
        header = " ".join(parts)
        remaining = 160 - len(header) - 1
        title_part = title[:remaining] if len(title) > remaining else title
        
        return f"{header} {title_part}"

    def _normalize_phone(self, phone: str) -> str:
        """
        Normalize phone number to international format.
        
        Args:
            phone: Phone number in various formats.
            
        Returns:
            Phone number with + prefix.
        """
        # Remove spaces, dashes, dots
        phone = "".join(c for c in phone if c.isdigit() or c == "+")
        
        # Add + if missing
        if not phone.startswith("+"):
            # Assume French number if starts with 0
            if phone.startswith("0"):
                phone = "+33" + phone[1:]
            else:
                phone = "+" + phone
        
        return phone

    def get_credits(self) -> int | None:
        """
        Get remaining SMS credits.
        
        Returns:
            Number of remaining credits, or None on error.
        """
        service_name = self.get_config_value("service_name")
        path = f"/sms/{service_name}"
        
        result = self._make_request("GET", path)
        
        if result:
            return result.get("creditsLeft", 0)
        return None

    def check_connectivity(self) -> bool:
        """
        Verify OVH API connectivity and credentials.
        
        Returns:
            True if API is accessible and credentials are valid.
        """
        credits = self.get_credits()
        if credits is not None:
            logger.info(f"OVH SMS connected. Credits remaining: {credits}")
            return True
        return False


# Register provider with factory
NotificationProviderFactory.register("OVH_SMS", OVHSMSProvider)