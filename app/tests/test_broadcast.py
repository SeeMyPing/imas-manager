"""
IMAS Manager - WebSocket Broadcast Tests

Tests for real-time broadcasting utilities.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from core.broadcast import (
    broadcast_incident_acknowledged,
    broadcast_incident_created,
    broadcast_incident_event,
    broadcast_incident_resolved,
    broadcast_incident_updated,
    get_incident_serialized,
)
from core.choices import IncidentSeverity, IncidentStatus
from core.models import Incident, Service, Team

User = get_user_model()


class IncidentSerializationTestCase(TestCase):
    """Test incident serialization for WebSocket."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="wstest", password="test123", email="ws@test.com"
        )
        cls.team = Team.objects.create(name="WS Team", slug="ws-team")
        cls.service = Service.objects.create(
            name="WS Service",
            criticality="TIER2_HIGH",
            owner_team=cls.team,
        )

    def test_serialize_incident_basic(self):
        """Test basic incident serialization."""
        incident = Incident.objects.create(
            title="WebSocket Test Incident",
            severity=IncidentSeverity.SEV2_HIGH,
            status=IncidentStatus.TRIGGERED,
            service=self.service,
            lead=self.user,
        )
        
        serialized = get_incident_serialized(incident)
        
        self.assertEqual(serialized["id"], str(incident.id))
        self.assertEqual(serialized["short_id"], incident.short_id)
        self.assertEqual(serialized["title"], "WebSocket Test Incident")
        self.assertEqual(serialized["severity"], "SEV2_HIGH")
        self.assertEqual(serialized["status"], "TRIGGERED")
        self.assertEqual(serialized["service"], "WS Service")
        self.assertEqual(serialized["lead"], "wstest")

    def test_serialize_incident_without_lead(self):
        """Test serialization when lead is None."""
        incident = Incident.objects.create(
            title="No Lead Incident",
            severity=IncidentSeverity.SEV3_MEDIUM,
            status=IncidentStatus.TRIGGERED,
            service=self.service,
            # lead is not set
        )
        
        serialized = get_incident_serialized(incident)
        
        self.assertEqual(serialized["service"], "WS Service")
        self.assertIsNone(serialized["lead"])


class BroadcastFunctionsTestCase(TestCase):
    """Test broadcast functions."""

    @classmethod
    def setUpTestData(cls):
        cls.team = Team.objects.create(name="Broadcast Team", slug="broadcast-team")
        cls.service = Service.objects.create(
            name="Broadcast Service",
            criticality="TIER2_HIGH",
            owner_team=cls.team,
        )
        cls.incident = Incident.objects.create(
            title="Broadcast Test",
            severity=IncidentSeverity.SEV2_HIGH,
            status=IncidentStatus.TRIGGERED,
            service=cls.service,
        )

    @patch("core.broadcast.get_channel_layer")
    @patch("core.broadcast.async_to_sync")
    def test_broadcast_incident_created(self, mock_async, mock_layer):
        """Test broadcasting incident created event."""
        mock_channel_layer = MagicMock()
        mock_layer.return_value = mock_channel_layer
        mock_async.return_value = MagicMock()
        
        broadcast_incident_created(self.incident)
        
        # Should call async_to_sync for group_send
        self.assertTrue(mock_async.called)

    @patch("core.broadcast.get_channel_layer")
    @patch("core.broadcast.async_to_sync")
    def test_broadcast_incident_updated(self, mock_async, mock_layer):
        """Test broadcasting incident updated event."""
        mock_channel_layer = MagicMock()
        mock_layer.return_value = mock_channel_layer
        mock_async.return_value = MagicMock()
        
        changes = {"status": {"old": "TRIGGERED", "new": "ACKNOWLEDGED"}}
        broadcast_incident_updated(self.incident, changes=changes)
        
        self.assertTrue(mock_async.called)

    @patch("core.broadcast.get_channel_layer")
    @patch("core.broadcast.async_to_sync")
    def test_broadcast_incident_acknowledged(self, mock_async, mock_layer):
        """Test broadcasting incident acknowledged event."""
        mock_channel_layer = MagicMock()
        mock_layer.return_value = mock_channel_layer
        mock_async.return_value = MagicMock()
        
        broadcast_incident_acknowledged(self.incident, acknowledged_by="testuser")
        
        self.assertTrue(mock_async.called)

    @patch("core.broadcast.get_channel_layer")
    @patch("core.broadcast.async_to_sync")
    def test_broadcast_incident_resolved(self, mock_async, mock_layer):
        """Test broadcasting incident resolved event."""
        mock_channel_layer = MagicMock()
        mock_layer.return_value = mock_channel_layer
        mock_async.return_value = MagicMock()
        
        broadcast_incident_resolved(self.incident, resolved_by="resolver")
        
        self.assertTrue(mock_async.called)

    @patch("core.broadcast.get_channel_layer")
    @patch("core.broadcast.async_to_sync")
    def test_broadcast_incident_event(self, mock_async, mock_layer):
        """Test broadcasting timeline event."""
        mock_channel_layer = MagicMock()
        mock_layer.return_value = mock_channel_layer
        mock_async.return_value = MagicMock()
        
        event_data = {"type": "note", "message": "Test note"}
        broadcast_incident_event(str(self.incident.id), event_data)
        
        self.assertTrue(mock_async.called)

    @patch("core.broadcast.get_channel_layer")
    def test_broadcast_handles_no_channel_layer(self, mock_layer):
        """Test broadcast gracefully handles missing channel layer."""
        mock_layer.return_value = None
        
        # Should not raise
        broadcast_incident_created(self.incident)
        broadcast_incident_updated(self.incident)
        broadcast_incident_acknowledged(self.incident)
        broadcast_incident_resolved(self.incident)

    @patch("core.broadcast.get_channel_layer")
    @patch("core.broadcast.async_to_sync")
    def test_broadcast_handles_exception(self, mock_async, mock_layer):
        """Test broadcast handles exceptions gracefully."""
        mock_layer.return_value = MagicMock()
        mock_async.side_effect = Exception("Channel error")
        
        # Should not raise, just log error
        broadcast_incident_created(self.incident)

    @patch("core.broadcast.get_channel_layer")
    @patch("core.broadcast.async_to_sync")
    def test_critical_incident_triggers_alert(self, mock_async, mock_layer):
        """Test that critical incidents trigger dashboard alert."""
        mock_channel_layer = MagicMock()
        mock_layer.return_value = mock_channel_layer
        mock_group_send = MagicMock()
        mock_async.return_value = mock_group_send
        
        # Create critical incident
        critical_incident = Incident.objects.create(
            title="Critical Incident",
            severity=IncidentSeverity.SEV1_CRITICAL,
            status=IncidentStatus.TRIGGERED,
            service=self.service,
        )
        
        broadcast_incident_created(critical_incident)
        
        # Should have called group_send multiple times (incidents_all, dashboard stats, critical_alert)
        self.assertGreaterEqual(mock_async.call_count, 2)
