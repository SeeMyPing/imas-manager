"""
IMAS Manager - Audit Log Models

Tracks all security-relevant actions in the system.
"""
from __future__ import annotations

import uuid
from django.conf import settings
from django.db import models


class AuditAction(models.TextChoices):
    """Types of audited actions."""
    # Authentication
    LOGIN = "LOGIN", "User Login"
    LOGOUT = "LOGOUT", "User Logout"
    LOGIN_FAILED = "LOGIN_FAILED", "Failed Login Attempt"
    TOKEN_CREATED = "TOKEN_CREATED", "API Token Created"
    TOKEN_REVOKED = "TOKEN_REVOKED", "API Token Revoked"
    
    # Incident actions
    INCIDENT_CREATED = "INCIDENT_CREATED", "Incident Created"
    INCIDENT_VIEWED = "INCIDENT_VIEWED", "Incident Viewed"
    INCIDENT_UPDATED = "INCIDENT_UPDATED", "Incident Updated"
    INCIDENT_ACKNOWLEDGED = "INCIDENT_ACKNOWLEDGED", "Incident Acknowledged"
    INCIDENT_RESOLVED = "INCIDENT_RESOLVED", "Incident Resolved"
    INCIDENT_ESCALATED = "INCIDENT_ESCALATED", "Incident Escalated"
    
    # Team/Service actions
    TEAM_CREATED = "TEAM_CREATED", "Team Created"
    TEAM_UPDATED = "TEAM_UPDATED", "Team Updated"
    SERVICE_CREATED = "SERVICE_CREATED", "Service Created"
    SERVICE_UPDATED = "SERVICE_UPDATED", "Service Updated"
    
    # API actions
    API_REQUEST = "API_REQUEST", "API Request"
    API_ERROR = "API_ERROR", "API Error"
    
    # Admin actions
    USER_CREATED = "USER_CREATED", "User Created"
    USER_UPDATED = "USER_UPDATED", "User Updated"
    PERMISSION_CHANGED = "PERMISSION_CHANGED", "Permission Changed"
    
    # Notification actions
    NOTIFICATION_SENT = "NOTIFICATION_SENT", "Notification Sent"
    NOTIFICATION_FAILED = "NOTIFICATION_FAILED", "Notification Failed"


class AuditLog(models.Model):
    """
    Audit log entry for security and compliance tracking.
    
    Captures who did what, when, from where, and what changed.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # When
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    
    # Who
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    username = models.CharField(max_length=150, blank=True)  # Preserved even if user deleted
    
    # What
    action = models.CharField(max_length=50, choices=AuditAction.choices, db_index=True)
    resource_type = models.CharField(max_length=100, blank=True)  # e.g., "Incident", "Team"
    resource_id = models.CharField(max_length=100, blank=True)  # UUID or ID of the resource
    
    # Details
    description = models.TextField(blank=True)
    changes = models.JSONField(default=dict, blank=True)  # Before/after for updates
    
    # Where (request metadata)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    request_method = models.CharField(max_length=10, blank=True)
    request_path = models.CharField(max_length=500, blank=True)
    
    # Status
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["user", "-timestamp"]),
            models.Index(fields=["action", "-timestamp"]),
            models.Index(fields=["resource_type", "resource_id"]),
            models.Index(fields=["-timestamp"]),
        ]
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"

    def __str__(self) -> str:
        user_str = self.username or "Anonymous"
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {user_str}: {self.get_action_display()}"

    @classmethod
    def log(
        cls,
        action: str,
        user=None,
        request=None,
        resource_type: str = "",
        resource_id: str = "",
        description: str = "",
        changes: dict = None,
        success: bool = True,
        error_message: str = "",
    ) -> "AuditLog":
        """
        Create an audit log entry.
        
        Args:
            action: AuditAction value
            user: User performing the action (optional)
            request: HTTP request for metadata (optional)
            resource_type: Type of resource affected
            resource_id: ID of the resource affected
            description: Human-readable description
            changes: Dict with before/after values
            success: Whether the action succeeded
            error_message: Error message if failed
        
        Returns:
            Created AuditLog instance
        """
        log_entry = cls(
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else "",
            description=description,
            changes=changes or {},
            success=success,
            error_message=error_message,
        )
        
        # User info
        if user and hasattr(user, "username"):
            log_entry.user = user if user.is_authenticated else None
            log_entry.username = user.username if user.is_authenticated else ""
        
        # Request metadata
        if request:
            log_entry.ip_address = cls._get_client_ip(request)
            log_entry.user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]
            log_entry.request_method = request.method
            log_entry.request_path = request.path[:500]
            
            # Try to get user from request if not provided
            if not user and hasattr(request, "user") and request.user.is_authenticated:
                log_entry.user = request.user
                log_entry.username = request.user.username
        
        log_entry.save()
        return log_entry

    @staticmethod
    def _get_client_ip(request) -> str:
        """Extract client IP from request, handling proxies."""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "")
