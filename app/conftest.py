"""
IMAS Manager - Test Configuration

Shared fixtures and configuration for pytest.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


@pytest.fixture
def api_client() -> APIClient:
    """Return an unauthenticated API client."""
    return APIClient()


@pytest.fixture
def user(db) -> User:
    """Create and return a test user."""
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )


@pytest.fixture
def admin_user(db) -> User:
    """Create and return an admin user."""
    return User.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="adminpass123",
    )


@pytest.fixture
def authenticated_client(api_client: APIClient, user: User) -> APIClient:
    """Return an authenticated API client."""
    from rest_framework.authtoken.models import Token
    
    token, _ = Token.objects.get_or_create(user=user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return api_client


@pytest.fixture
def team(db):
    """Create and return a test team."""
    from core.models import Team
    
    return Team.objects.create(
        name="Test Team",
        slack_channel_id="C0123456789",
    )


@pytest.fixture
def service(db, team):
    """Create and return a test service."""
    from core.models import Service
    from core.choices import ServiceCriticality
    
    return Service.objects.create(
        name="test-service",
        owner_team=team,
        runbook_url="https://docs.example.com/runbook",
        criticality=ServiceCriticality.TIER_2,
    )


@pytest.fixture
def impact_scope(db):
    """Create and return a test impact scope."""
    from core.models import ImpactScope
    
    return ImpactScope.objects.create(
        name="Security",
        description="Security-related impact",
        mandatory_notify_email="security@example.com",
        is_active=True,
    )


@pytest.fixture
def incident(db, service, user):
    """Create and return a test incident."""
    from core.models import Incident
    from core.choices import IncidentSeverity, IncidentStatus
    
    return Incident.objects.create(
        title="Test Incident",
        description="This is a test incident.",
        service=service,
        severity=IncidentSeverity.SEV2_HIGH,
        status=IncidentStatus.TRIGGERED,
        lead=user,
    )


@pytest.fixture
def notification_provider_slack(db):
    """Create and return a test Slack provider."""
    from core.models import NotificationProvider
    from core.choices import NotificationProviderType
    
    return NotificationProvider.objects.create(
        name="Test Slack",
        type=NotificationProviderType.SLACK,
        config={
            "bot_token": "xoxb-test-token",
            "default_channel": "#test-incidents",
        },
        is_active=True,
    )
