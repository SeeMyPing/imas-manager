"""
IMAS Manager - Signal Tests

Tests for Django signals: KPI timestamps, event logging.
"""
from __future__ import annotations

import pytest
from django.utils import timezone

from core.choices import IncidentStatus
from core.models import Incident, IncidentEvent


@pytest.mark.django_db
class TestIncidentSignals:
    """Tests for Incident model signals."""

    def test_acknowledged_at_auto_set(self, incident):
        """Test acknowledged_at is set on status transition."""
        assert incident.acknowledged_at is None
        
        incident.status = IncidentStatus.ACKNOWLEDGED
        incident.save()
        
        incident.refresh_from_db()
        assert incident.acknowledged_at is not None

    def test_resolved_at_auto_set(self, incident):
        """Test resolved_at is set on status transition."""
        assert incident.resolved_at is None
        
        incident.status = IncidentStatus.RESOLVED
        incident.save()
        
        incident.refresh_from_db()
        assert incident.resolved_at is not None

    def test_resolved_at_not_overwritten(self, incident):
        """Test resolved_at is not overwritten if already set."""
        original_time = timezone.now()
        incident.resolved_at = original_time
        incident.status = IncidentStatus.RESOLVED
        incident.save()
        
        incident.refresh_from_db()
        assert incident.resolved_at == original_time

    def test_event_created_on_incident_creation(self, service, user):
        """Test IncidentEvent is created when incident is created."""
        incident = Incident.objects.create(
            title="Signal Test",
            service=service,
            lead=user,
        )
        
        events = IncidentEvent.objects.filter(incident=incident)
        assert events.count() >= 1
        
        creation_event = events.filter(type="STATUS_CHANGE").first()
        assert creation_event is not None
        assert "created" in creation_event.message.lower()
