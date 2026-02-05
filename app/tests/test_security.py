"""
IMAS Manager - Security Tests

Tests for RBAC permissions, audit logging, and security middleware.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import AuditAction, AuditLog, Incident, Service, Team
from core.choices import IncidentSeverity, IncidentStatus

User = get_user_model()


class PermissionsTestCase(APITestCase):
    """Test RBAC permissions for API endpoints."""

    @classmethod
    def setUpTestData(cls):
        # Create groups
        cls.viewers_group = Group.objects.create(name="viewers")
        cls.operators_group = Group.objects.create(name="operators")
        cls.responders_group = Group.objects.create(name="responders")
        cls.managers_group = Group.objects.create(name="managers")
        
        # Create users with different roles
        cls.viewer = User.objects.create_user(
            username="viewer", password="testpass123", email="viewer@test.com"
        )
        cls.viewer.groups.add(cls.viewers_group)
        
        cls.operator = User.objects.create_user(
            username="operator", password="testpass123", email="operator@test.com"
        )
        cls.operator.groups.add(cls.operators_group)
        
        cls.responder = User.objects.create_user(
            username="responder", password="testpass123", email="responder@test.com"
        )
        cls.responder.groups.add(cls.responders_group)
        
        cls.manager = User.objects.create_user(
            username="manager", password="testpass123", email="manager@test.com"
        )
        cls.manager.groups.add(cls.managers_group)
        
        cls.staff_user = User.objects.create_user(
            username="staff", password="testpass123", email="staff@test.com",
            is_staff=True
        )
        
        # Create test data
        cls.team = Team.objects.create(
            name="Security Team",
            slug="security-team",
            current_on_call=cls.manager
        )
        cls.service = Service.objects.create(
            name="Auth Service",
            criticality="TIER1_CRITICAL",
            owner_team=cls.team
        )

    def test_unauthenticated_cannot_list_incidents(self):
        """Unauthenticated users cannot access incident list."""
        response = self.client.get(reverse("api_v1:incident_list"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_viewer_can_list_incidents(self):
        """Viewers can list incidents (read-only)."""
        self.client.force_authenticate(user=self.viewer)
        response = self.client.get(reverse("api_v1:incident_list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_create_incident(self):
        """Viewers cannot create incidents."""
        self.client.force_authenticate(user=self.viewer)
        response = self.client.post(reverse("api_v1:incident_list"), {
            "title": "Test Incident",
            "severity": "SEV3_MEDIUM",
            "service": str(self.service.id),
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_responder_can_create_incident(self):
        """Responders can create incidents."""
        self.client.force_authenticate(user=self.responder)
        response = self.client.post(reverse("api_v1:incident_list"), {
            "title": "Test Incident from Responder",
            "severity": "SEV3_MEDIUM",
            "service": str(self.service.id),
        })
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_201_CREATED])

    def test_staff_can_create_incident(self):
        """Staff users can create incidents."""
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.post(reverse("api_v1:incident_list"), {
            "title": "Test Incident from Staff",
            "severity": "SEV3_MEDIUM",
            "service": str(self.service.id),
        })
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_201_CREATED])

    def test_operator_can_acknowledge_incident(self):
        """Operators can acknowledge incidents."""
        # Create incident
        incident = Incident.objects.create(
            title="Test Acknowledge",
            severity=IncidentSeverity.SEV3_MEDIUM,
            status=IncidentStatus.TRIGGERED,
            service=self.service,
        )
        
        self.client.force_authenticate(user=self.operator)
        response = self.client.post(
            reverse("api_v1:incident_acknowledge", kwargs={"pk": str(incident.id)})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_responder_can_resolve_incident(self):
        """Responders can resolve incidents."""
        # Create acknowledged incident
        incident = Incident.objects.create(
            title="Test Resolve",
            severity=IncidentSeverity.SEV3_MEDIUM,
            status=IncidentStatus.ACKNOWLEDGED,
            service=self.service,
        )
        
        self.client.force_authenticate(user=self.responder)
        response = self.client.post(
            reverse("api_v1:incident_resolve", kwargs={"pk": str(incident.id)}),
            {"note": "Fixed the issue"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class AuditLogTestCase(TestCase):
    """Test audit logging functionality."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="audituser", password="testpass123", email="audit@test.com"
        )

    def test_create_audit_log(self):
        """Test basic audit log creation."""
        log = AuditLog.log(
            action=AuditAction.LOGIN,
            user=self.user,
            description="User logged in successfully",
        )
        
        self.assertEqual(log.action, AuditAction.LOGIN)
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.username, "audituser")
        self.assertTrue(log.success)

    def test_audit_log_without_user(self):
        """Test audit log for anonymous actions."""
        log = AuditLog.log(
            action=AuditAction.API_REQUEST,
            description="Anonymous API request",
        )
        
        self.assertIsNone(log.user)
        self.assertEqual(log.username, "")

    def test_audit_log_with_resource(self):
        """Test audit log with resource tracking."""
        log = AuditLog.log(
            action=AuditAction.INCIDENT_CREATED,
            user=self.user,
            resource_type="Incident",
            resource_id="abc123",
            description="Created new incident",
        )
        
        self.assertEqual(log.resource_type, "Incident")
        self.assertEqual(log.resource_id, "abc123")

    def test_audit_log_with_changes(self):
        """Test audit log with before/after changes."""
        log = AuditLog.log(
            action=AuditAction.INCIDENT_UPDATED,
            user=self.user,
            resource_type="Incident",
            resource_id="abc123",
            changes={
                "status": {"before": "TRIGGERED", "after": "ACKNOWLEDGED"}
            },
        )
        
        self.assertEqual(log.changes["status"]["before"], "TRIGGERED")
        self.assertEqual(log.changes["status"]["after"], "ACKNOWLEDGED")

    def test_audit_log_error(self):
        """Test audit log for failed actions."""
        log = AuditLog.log(
            action=AuditAction.API_ERROR,
            description="Failed to process request",
            success=False,
            error_message="Invalid data format",
        )
        
        self.assertFalse(log.success)
        self.assertEqual(log.error_message, "Invalid data format")


class SecurityHeadersTestCase(TestCase):
    """Test security headers middleware."""

    def test_security_headers_present(self):
        """Test that security headers are added to responses."""
        response = self.client.get("/health/")
        
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertEqual(response["X-XSS-Protection"], "1; mode=block")

    def test_referrer_policy_header(self):
        """Test Referrer-Policy header."""
        response = self.client.get("/health/")
        self.assertEqual(response["Referrer-Policy"], "strict-origin-when-cross-origin")


class RateLimitTestCase(APITestCase):
    """Test rate limiting functionality."""

    @override_settings(
        CACHES={
            'default': {
                'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            }
        },
        MIDDLEWARE=[
            "django.middleware.security.SecurityMiddleware",
            "core.middleware.RateLimitByIPMiddleware",
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.middleware.common.CommonMiddleware",
            "django.middleware.csrf.CsrfViewMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            "django.contrib.messages.middleware.MessageMiddleware",
        ]
    )
    def test_rate_limit_headers(self):
        """Test that rate limit headers are present."""
        response = self.client.get(reverse("api_v1:health_check"))
        
        self.assertIn("X-RateLimit-Limit", response)
        self.assertIn("X-RateLimit-Remaining", response)

    def test_authenticated_user_not_ip_limited(self):
        """Authenticated users use DRF throttling, not IP limiting."""
        user = User.objects.create_user(
            username="ratelimit", password="testpass123"
        )
        self.client.force_authenticate(user=user)
        
        # Make multiple requests
        for _ in range(10):
            response = self.client.get(reverse("api_v1:incident_list"))
            self.assertEqual(response.status_code, status.HTTP_200_OK)


class APIThrottlingTestCase(APITestCase):
    """Test DRF throttling configuration."""

    def test_throttle_rates_configured(self):
        """Verify throttle rates are properly configured in production settings."""
        # Import production settings directly
        from config import settings as prod_settings
        
        throttle_rates = prod_settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {})
        
        self.assertIn("anon", throttle_rates)
        self.assertIn("user", throttle_rates)
        self.assertEqual(throttle_rates["anon"], "100/hour")
        self.assertEqual(throttle_rates["user"], "1000/hour")
