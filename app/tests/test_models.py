"""
IMAS Manager - Model Tests

Tests for Django models: Team, Service, Incident, etc.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from core.choices import IncidentSeverity, IncidentStatus
from core.models import (
    ImpactScope,
    Incident,
    IncidentEvent,
    NotificationProvider,
    Service,
    Team,
)


@pytest.mark.django_db
class TestTeamModel:
    """Tests for Team model."""

    def test_create_team(self):
        """Test creating a team."""
        team = Team.objects.create(
            name="SRE Team",
            slack_channel_id="C0123456789",
        )
        
        assert team.id is not None
        assert team.name == "SRE Team"
        assert str(team) == "SRE Team"

    def test_team_services_relationship(self, team, service):
        """Test team -> services relationship."""
        assert service in team.services.all()
        assert team.services.count() == 1


@pytest.mark.django_db
class TestServiceModel:
    """Tests for Service model."""

    def test_create_service(self, team):
        """Test creating a service."""
        service = Service.objects.create(
            name="api-gateway",
            owner_team=team,
            runbook_url="https://docs.example.com/api-gateway",
        )
        
        assert service.id is not None
        assert service.name == "api-gateway"
        assert service.owner_team == team

    def test_service_unique_name(self, team):
        """Test that service names must be unique."""
        Service.objects.create(name="unique-service", owner_team=team)
        
        with pytest.raises(Exception):  # IntegrityError
            Service.objects.create(name="unique-service", owner_team=team)


@pytest.mark.django_db
class TestImpactScopeModel:
    """Tests for ImpactScope model."""

    def test_create_impact_scope(self):
        """Test creating an impact scope."""
        scope = ImpactScope.objects.create(
            name="GDPR/Legal",
            description="Data protection and legal impact",
            mandatory_notify_email="dpo@example.com",
        )
        
        assert scope.id is not None
        assert scope.is_active is True
        assert "GDPR" in str(scope)


@pytest.mark.django_db
class TestIncidentModel:
    """Tests for Incident model."""

    def test_create_incident(self, service, user):
        """Test creating an incident."""
        incident = Incident.objects.create(
            title="Database outage",
            description="Primary database is unreachable",
            service=service,
            severity=IncidentSeverity.SEV1_CRITICAL,
            lead=user,
        )
        
        assert incident.id is not None
        assert incident.status == IncidentStatus.TRIGGERED
        assert incident.short_id == str(incident.id)[:8].upper()

    def test_incident_is_critical_sev1(self, service):
        """Test is_critical for SEV1."""
        incident = Incident.objects.create(
            title="Critical",
            service=service,
            severity=IncidentSeverity.SEV1_CRITICAL,
        )
        assert incident.is_critical is True

    def test_incident_is_critical_sev2(self, service):
        """Test is_critical for SEV2."""
        incident = Incident.objects.create(
            title="High",
            service=service,
            severity=IncidentSeverity.SEV2_HIGH,
        )
        assert incident.is_critical is True

    def test_incident_is_not_critical_sev3(self, service):
        """Test is_critical for SEV3."""
        incident = Incident.objects.create(
            title="Medium",
            service=service,
            severity=IncidentSeverity.SEV3_MEDIUM,
        )
        assert incident.is_critical is False

    def test_incident_is_open(self, incident):
        """Test is_open property."""
        assert incident.is_open is True
        
        incident.status = IncidentStatus.RESOLVED
        incident.save()
        assert incident.is_open is False

    def test_incident_mttd_calculation(self, service):
        """Test MTTD calculation."""
        detected = timezone.now() - timedelta(minutes=5)
        incident = Incident.objects.create(
            title="Test",
            service=service,
            detected_at=detected,
        )
        
        assert incident.mttd is not None
        assert incident.mttd.total_seconds() >= 300  # At least 5 minutes
        assert incident.mttd_seconds >= 300

    def test_incident_mtta_calculation(self, service):
        """Test MTTA calculation."""
        incident = Incident.objects.create(
            title="Test",
            service=service,
        )
        
        # Initially no MTTA
        assert incident.mtta is None
        
        # Acknowledge
        incident.acknowledged_at = timezone.now() + timedelta(minutes=2)
        incident.save()
        
        assert incident.mtta is not None
        assert incident.mtta_seconds >= 120

    def test_incident_mttr_calculation(self, service):
        """Test MTTR calculation."""
        incident = Incident.objects.create(
            title="Test",
            service=service,
        )
        
        # Initially no MTTR
        assert incident.mttr is None
        
        # Resolve
        incident.resolved_at = timezone.now() + timedelta(hours=1)
        incident.save()
        
        assert incident.mttr is not None
        assert incident.mttr_seconds >= 3600

    def test_incident_impacted_scopes_m2m(self, incident, impact_scope):
        """Test many-to-many relationship with ImpactScope."""
        incident.impacted_scopes.add(impact_scope)
        
        assert impact_scope in incident.impacted_scopes.all()
        assert incident in impact_scope.incidents.all()


@pytest.mark.django_db
class TestIncidentEventModel:
    """Tests for IncidentEvent model."""

    def test_create_event(self, incident):
        """Test creating an incident event."""
        event = IncidentEvent.objects.create(
            incident=incident,
            type="STATUS_CHANGE",
            message="Incident acknowledged by user",
        )
        
        assert event.id is not None
        assert event.timestamp is not None
        assert event in incident.events.all()

    def test_events_ordering(self, incident):
        """Test events are ordered by timestamp descending."""
        IncidentEvent.objects.create(
            incident=incident,
            type="NOTE",
            message="First event",
        )
        IncidentEvent.objects.create(
            incident=incident,
            type="NOTE",
            message="Second event",
        )
        
        events = list(incident.events.all())
        assert events[0].message == "Second event"


@pytest.mark.django_db
class TestNotificationProviderModel:
    """Tests for NotificationProvider model."""

    def test_create_provider(self):
        """Test creating a notification provider."""
        provider = NotificationProvider.objects.create(
            name="Slack Prod",
            type="SLACK",
            config={"bot_token": "xoxb-xxx", "channel": "#alerts"},
            is_active=True,
        )
        
        assert provider.id is not None
        assert provider.get_config_value("bot_token") == "xoxb-xxx"
        assert provider.get_config_value("missing", "default") == "default"

    def test_provider_str(self):
        """Test provider string representation."""
        active = NotificationProvider.objects.create(
            name="Active Provider",
            type="SLACK",
            is_active=True,
        )
        inactive = NotificationProvider.objects.create(
            name="Inactive Provider",
            type="SMTP",
            is_active=False,
        )
        
        assert "✓" in str(active)
        assert "✗" in str(inactive)
