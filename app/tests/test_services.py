"""
IMAS Manager - Service Layer Tests

Tests for business logic services: Orchestrator, NotificationRouter, etc.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.choices import IncidentSeverity, IncidentStatus
from core.models import Incident, IncidentEvent
from services.notifications.router import NotificationRecipients, NotificationRouter
from services.orchestrator import IncidentOrchestrator


@pytest.mark.django_db
class TestIncidentOrchestrator:
    """Tests for IncidentOrchestrator service."""

    def test_create_incident(self, service, user):
        """Test creating an incident via orchestrator."""
        orchestrator = IncidentOrchestrator()
        
        data = {
            "title": "Orchestrator Test",
            "description": "Created via orchestrator",
            "service": service,
            "severity": IncidentSeverity.SEV2_HIGH,
        }
        
        incident = orchestrator.create_incident(
            data=data,
            user=user,
            trigger_orchestration=False,  # Don't trigger async
        )
        
        assert incident.id is not None
        assert incident.title == "Orchestrator Test"
        assert incident.lead == user
        assert incident.status == IncidentStatus.TRIGGERED

    def test_create_incident_by_service_name(self, service, user):
        """Test creating incident with service name lookup."""
        orchestrator = IncidentOrchestrator()
        
        data = {
            "title": "Service Name Test",
            "service": service.name,  # Use name instead of instance
        }
        
        incident = orchestrator.create_incident(
            data=data,
            trigger_orchestration=False,
        )
        
        assert incident.service == service

    def test_deduplicate_check_finds_existing(self, incident, service):
        """Test deduplication finds existing open incident."""
        orchestrator = IncidentOrchestrator()
        
        existing = orchestrator.deduplicate_check(service=service)
        
        assert existing is not None
        assert existing.id == incident.id

    def test_deduplicate_check_ignores_resolved(self, service, user):
        """Test deduplication ignores resolved incidents."""
        orchestrator = IncidentOrchestrator()
        
        # Create resolved incident
        Incident.objects.create(
            title="Resolved",
            service=service,
            status=IncidentStatus.RESOLVED,
        )
        
        existing = orchestrator.deduplicate_check(service=service)
        
        assert existing is None

    def test_acknowledge_incident(self, incident, user):
        """Test acknowledging an incident."""
        orchestrator = IncidentOrchestrator()
        
        result = orchestrator.acknowledge_incident(incident, user)
        
        assert result.status == IncidentStatus.ACKNOWLEDGED
        assert result.lead == user

    def test_resolve_incident(self, incident, user):
        """Test resolving an incident."""
        orchestrator = IncidentOrchestrator()
        
        result = orchestrator.resolve_incident(
            incident,
            user,
            resolution_note="Fixed by restart",
        )
        
        assert result.status == IncidentStatus.RESOLVED
        
        # Check event was created
        event = IncidentEvent.objects.filter(
            incident=incident,
            type="STATUS_CHANGE",
            message__contains="Fixed by restart",
        ).first()
        assert event is not None


@pytest.mark.django_db
class TestNotificationRouter:
    """Tests for NotificationRouter service."""

    def test_get_recipients_from_team(self, incident, user):
        """Test getting recipients from service owner team."""
        # Set up on-call
        incident.service.owner_team.current_on_call = user
        incident.service.owner_team.save()
        
        router = NotificationRouter()
        recipients = router.get_recipients(incident)
        
        assert isinstance(recipients, NotificationRecipients)
        assert incident.service.owner_team.slack_channel_id in recipients.slack_channels
        assert user.email in recipients.emails

    def test_get_recipients_from_scopes(self, incident, impact_scope):
        """Test getting recipients from impact scopes."""
        incident.impacted_scopes.add(impact_scope)
        
        router = NotificationRouter()
        recipients = router.get_recipients(incident)
        
        assert impact_scope.mandatory_notify_email in recipients.emails

    def test_build_message(self, incident):
        """Test building notification message."""
        incident.lid_link = "https://docs.google.com/document/d/123"
        incident.war_room_link = "https://slack.com/app/123"
        incident.save()
        
        router = NotificationRouter()
        message = router.build_message(incident)
        
        assert incident.title in message["title"]
        assert message["service"] == incident.service.name
        assert "LID" in message["links"]
        assert "War Room" in message["links"]

    def test_empty_recipients(self, service):
        """Test handling incident with no recipients."""
        # Create incident without team slack or on-call
        incident = Incident.objects.create(
            title="No Recipients",
            service=service,
        )
        service.owner_team.slack_channel_id = ""
        service.owner_team.current_on_call = None
        service.owner_team.save()
        
        router = NotificationRouter()
        recipients = router.get_recipients(incident)
        
        assert recipients.is_empty()


@pytest.mark.django_db
class TestSlackProvider:
    """Tests for SlackProvider."""

    def test_provider_initialization(self, notification_provider_slack):
        """Test initializing Slack provider."""
        from services.notifications.providers.slack import SlackProvider
        
        provider = SlackProvider(notification_provider_slack)
        
        assert provider.name == "Test Slack"
        assert provider.provider_type == "SLACK"

    def test_provider_missing_config(self):
        """Test provider raises error on missing config."""
        from core.models import NotificationProvider
        from services.notifications.providers.slack import SlackProvider
        
        bad_config = NotificationProvider(
            name="Bad Slack",
            type="SLACK",
            config={},  # Missing bot_token
        )
        
        with pytest.raises(ValueError, match="bot_token"):
            SlackProvider(bad_config)

    @patch("services.notifications.providers.slack.SlackProvider._get_client")
    def test_send_message(self, mock_get_client, notification_provider_slack):
        """Test sending a Slack message."""
        from services.notifications.providers.slack import SlackProvider
        
        # Mock Slack client
        mock_client = MagicMock()
        mock_client.chat_postMessage.return_value = {"ok": True}
        mock_get_client.return_value = mock_client
        
        provider = SlackProvider(notification_provider_slack)
        result = provider.send(
            recipient="C0123456789",
            message={
                "title": "Test Alert",
                "body": "This is a test",
                "severity": "SEV2_HIGH",
                "service": "test-service",
            },
        )
        
        assert result is True
        mock_client.chat_postMessage.assert_called_once()

    @patch("services.notifications.providers.slack.SlackProvider._get_client")
    def test_create_channel(self, mock_get_client, notification_provider_slack):
        """Test creating a Slack channel."""
        from services.notifications.providers.slack import SlackProvider
        
        mock_client = MagicMock()
        mock_client.conversations_create.return_value = {
            "ok": True,
            "channel": {"id": "C999999999"},
        }
        mock_client.auth_test.return_value = {"ok": True, "team_id": "T12345"}
        mock_get_client.return_value = mock_client
        
        provider = SlackProvider(notification_provider_slack)
        result = provider.create_channel("test-incident")
        
        assert result is not None
        channel_id, channel_url = result
        assert channel_id == "C999999999"
        assert "C999999999" in channel_url

    def test_format_incident_blocks(self, notification_provider_slack):
        """Test formatting message as Slack blocks."""
        from services.notifications.providers.slack import SlackProvider
        
        provider = SlackProvider(notification_provider_slack)
        blocks = provider._format_incident_blocks({
            "title": "Database Down",
            "body": "Primary DB unreachable",
            "severity": "SEV1_CRITICAL",
            "service": "postgres-primary",
            "status": "Triggered",
        })
        
        assert len(blocks) >= 3
        assert blocks[0]["type"] == "header"
        assert "🔴" in blocks[0]["text"]["text"]  # SEV1 emoji
