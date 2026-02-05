"""
IMAS Manager - Email Notification Provider

SMTP-based email provider for incident notifications.
"""
from __future__ import annotations

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection

from services.notifications.providers.base import BaseNotificationProvider

if TYPE_CHECKING:
    from core.models import NotificationProvider

logger = logging.getLogger(__name__)


class EmailProvider(BaseNotificationProvider):
    """
    Email notification provider using SMTP.
    
    Required configuration in NotificationProvider.config:
    {
        "host": "smtp.example.com",
        "port": 587,
        "username": "user@example.com",
        "password": "secret",
        "use_tls": true,
        "from_email": "incidents@example.com",
        "from_name": "IMAS Manager"
    }
    
    Or use Django's default email settings if config is empty.
    """
    
    REQUIRED_CONFIG_KEYS = []  # Can use Django defaults

    def _validate_config(self) -> None:
        """Validate email configuration."""
        # Either use custom config or Django defaults
        if self.config.config:
            # If custom config provided, host is required
            if not self.get_config_value("host"):
                # Check if we can fall back to Django settings
                if not getattr(settings, "EMAIL_HOST", None):
                    raise ValueError(
                        f"Email provider '{self.name}' requires 'host' in config "
                        "or EMAIL_HOST in Django settings"
                    )

    def _get_connection(self):
        """
        Get email connection using provider config or Django settings.
        
        Returns:
            Django email connection.
        """
        config = self.config.config
        
        if config.get("host"):
            # Use custom configuration
            return get_connection(
                host=config.get("host"),
                port=config.get("port", 587),
                username=config.get("username"),
                password=config.get("password"),
                use_tls=config.get("use_tls", True),
                use_ssl=config.get("use_ssl", False),
                fail_silently=False,
            )
        else:
            # Use Django's default email settings
            return get_connection()

    def _get_from_email(self) -> str:
        """Get the from email address."""
        config = self.config.config
        from_name = config.get("from_name", "IMAS Manager")
        from_email = config.get("from_email") or getattr(
            settings, "DEFAULT_FROM_EMAIL", "noreply@example.com"
        )
        return f"{from_name} <{from_email}>"

    def send(
        self,
        recipient: str,
        message: dict[str, Any],
    ) -> bool:
        """
        Send an email notification.
        
        Args:
            recipient: Email address.
            message: Message dict with 'title', 'body', 'severity', etc.
            
        Returns:
            True if sent successfully.
        """
        try:
            subject = message.get("title", "Incident Alert")
            text_content = self._format_text_body(message)
            html_content = self._format_html_body(message)
            
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=self._get_from_email(),
                to=[recipient],
                connection=self._get_connection(),
            )
            email.attach_alternative(html_content, "text/html")
            
            sent = email.send(fail_silently=False)
            
            if sent:
                logger.info(f"Email sent to {recipient}")
                return True
            else:
                logger.error(f"Failed to send email to {recipient}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending email to {recipient}: {e}")
            return False

    def send_batch(
        self,
        recipients: list[str],
        message: dict[str, Any],
    ) -> dict[str, bool]:
        """
        Send emails to multiple recipients.
        
        Args:
            recipients: List of email addresses.
            message: Message content.
            
        Returns:
            Dict mapping recipient to success status.
        """
        results = {}
        
        # Use a single connection for all emails
        connection = self._get_connection()
        
        try:
            connection.open()
            
            for recipient in recipients:
                try:
                    subject = message.get("title", "Incident Alert")
                    text_content = self._format_text_body(message)
                    html_content = self._format_html_body(message)
                    
                    email = EmailMultiAlternatives(
                        subject=subject,
                        body=text_content,
                        from_email=self._get_from_email(),
                        to=[recipient],
                        connection=connection,
                    )
                    email.attach_alternative(html_content, "text/html")
                    
                    sent = email.send(fail_silently=False)
                    results[recipient] = bool(sent)
                    
                except Exception as e:
                    logger.error(f"Failed to send email to {recipient}: {e}")
                    results[recipient] = False
                    
        finally:
            connection.close()
        
        return results

    def _format_text_body(self, message: dict[str, Any]) -> str:
        """Format message as plain text."""
        lines = [
            f"INCIDENT ALERT: {message.get('title', 'Unknown')}",
            "",
            f"Severity: {message.get('severity', 'Unknown')}",
            f"Service: {message.get('service', 'Unknown')}",
            f"Status: {message.get('status', 'Unknown')}",
            "",
            "Description:",
            message.get("body", "No description provided."),
            "",
        ]
        
        if links := message.get("links"):
            lines.extend(["Links:", links, ""])
        
        lines.append("---")
        lines.append("IMAS Manager - Incident Management At Scale")
        
        return "\n".join(lines)

    def _format_html_body(self, message: dict[str, Any]) -> str:
        """Format message as HTML email."""
        severity = message.get("severity", "Unknown")
        severity_color = self._get_severity_color(severity)
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            background: {severity_color};
            color: white;
            padding: 20px;
            border-radius: 8px 8px 0 0;
        }}
        .content {{
            background: #f9f9f9;
            padding: 20px;
            border: 1px solid #ddd;
            border-top: none;
            border-radius: 0 0 8px 8px;
        }}
        .field {{
            margin-bottom: 10px;
        }}
        .field-label {{
            font-weight: bold;
            color: #555;
        }}
        .links {{
            background: #e9e9e9;
            padding: 15px;
            border-radius: 4px;
            margin-top: 15px;
        }}
        .footer {{
            margin-top: 20px;
            padding-top: 15px;
            border-top: 1px solid #ddd;
            font-size: 12px;
            color: #888;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1 style="margin: 0;">🚨 {message.get('title', 'Incident Alert')}</h1>
    </div>
    <div class="content">
        <div class="field">
            <span class="field-label">Severity:</span> {severity}
        </div>
        <div class="field">
            <span class="field-label">Service:</span> {message.get('service', 'Unknown')}
        </div>
        <div class="field">
            <span class="field-label">Status:</span> {message.get('status', 'Unknown')}
        </div>
        
        <h3>Description</h3>
        <p>{message.get('body', 'No description provided.')}</p>
        
        {self._format_links_html(message.get('links', ''))}
    </div>
    <div class="footer">
        IMAS Manager - Incident Management At Scale
    </div>
</body>
</html>
"""
        return html

    def _format_links_html(self, links: str) -> str:
        """Format links section as HTML."""
        if not links:
            return ""
        
        return f"""
        <div class="links">
            <strong>Quick Links:</strong><br>
            {links.replace(chr(10), '<br>')}
        </div>
        """

    def _get_severity_color(self, severity: str) -> str:
        """Get color for severity level."""
        colors = {
            "SEV1 - Critical": "#dc3545",
            "SEV1_CRITICAL": "#dc3545",
            "SEV2 - High": "#fd7e14",
            "SEV2_HIGH": "#fd7e14",
            "SEV3 - Medium": "#ffc107",
            "SEV3_MEDIUM": "#ffc107",
            "SEV4 - Low": "#28a745",
            "SEV4_LOW": "#28a745",
        }
        return colors.get(severity, "#6c757d")


# Register with factory
from services.notifications.providers.base import NotificationProviderFactory
NotificationProviderFactory.register("SMTP", EmailProvider)
NotificationProviderFactory.register("SCALEWAY_TEM", EmailProvider)
