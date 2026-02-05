"""
IMAS Manager - Tests for Celery Tasks

Tests for async incident orchestration tasks.
"""
from __future__ import annotations

import unittest
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import Incident, IncidentEvent, Service, Team
from core.models.incident import IncidentSeverity, IncidentStatus
from core.choices import IncidentEventType

User = get_user_model()


class SetupIncidentTaskTestCase(TestCase):
    """Tests for the main orchestration task."""

    def setUp(self) -> None:
        """Set up test data."""
        self.team = Team.objects.create(
            name="Test Team",
            slug="test-team",
        )
        self.service = Service.objects.create(
            name="test-service",
            owner_team=self.team,
        )
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )
        self.incident = Incident.objects.create(
            title="Test Incident",
            description="Test description",
            service=self.service,
            severity=IncidentSeverity.SEV2_HIGH,
            status=IncidentStatus.TRIGGERED,
            lead=self.user,
        )

    def test_setup_incident_not_found(self) -> None:
        """Test handling of non-existent incident."""
        from tasks.incident_tasks import orchestrate_incident_task
        
        result = orchestrate_incident_task("00000000-0000-0000-0000-000000000000")
        
        self.assertIn("error", result)
        self.assertEqual(result["error"], "Incident not found")

    @patch("integrations.gdrive.GDriveService")
    def test_setup_incident_lid_creation_failure_continues(
        self,
        mock_gdrive_class: MagicMock,
    ) -> None:
        """Test that task continues even if LID creation fails."""
        from tasks.incident_tasks import orchestrate_incident_task
        
        # Mock GDrive to raise an exception
        mock_gdrive = MagicMock()
        mock_gdrive.create_lid_document.side_effect = Exception("API error")
        mock_gdrive_class.return_value = mock_gdrive
        
        with patch("services.notifications.router.router") as mock_router:
            result = orchestrate_incident_task(str(self.incident.id))
        
        # Task should complete despite LID failure
        self.assertFalse(result["lid_created"])
        self.assertTrue(result["notifications_sent"])

    def test_setup_incident_not_found(self) -> None:
        """Test handling of non-existent incident."""
        from tasks.incident_tasks import orchestrate_incident_task
        
        result = orchestrate_incident_task("00000000-0000-0000-0000-000000000000")
        
        self.assertIn("error", result)
        self.assertEqual(result["error"], "Incident not found")


class SendNotificationTaskTestCase(TestCase):
    """Tests for individual notification sending task."""

    def setUp(self) -> None:
        """Set up test data."""
        from core.models import NotificationProvider
        from core.choices import NotificationProviderType
        
        self.provider = NotificationProvider.objects.create(
            name="Test Slack",
            type=NotificationProviderType.SLACK,
            is_active=True,
            config={"bot_token": "xoxb-test"},
        )

    @patch("services.notifications.providers.base.NotificationProviderFactory")
    def test_send_notification_success(
        self,
        mock_factory: MagicMock,
    ) -> None:
        """Test successful notification sending."""
        from tasks.incident_tasks import send_notification_task
        
        mock_provider = MagicMock()
        mock_provider.send.return_value = True
        mock_factory.create.return_value = mock_provider
        
        result = send_notification_task(
            str(self.provider.id),
            "#test-channel",
            {"text": "Test message"},
        )
        
        self.assertTrue(result)
        mock_provider.send.assert_called_once()

    def test_send_notification_provider_not_found(self) -> None:
        """Test handling of missing provider."""
        from tasks.incident_tasks import send_notification_task
        
        result = send_notification_task(
            "00000000-0000-0000-0000-000000000000",
            "#test-channel",
            {"text": "Test message"},
        )
        
        self.assertFalse(result)


class ArchiveWarRoomTaskTestCase(TestCase):
    """Tests for War Room archival task."""

    def setUp(self) -> None:
        """Set up test data."""
        self.team = Team.objects.create(
            name="Test Team",
            slug="test-team",
        )
        self.service = Service.objects.create(
            name="test-service",
            owner_team=self.team,
        )
        self.incident = Incident.objects.create(
            title="Test Incident",
            service=self.service,
            severity=IncidentSeverity.SEV1_CRITICAL,
            status=IncidentStatus.RESOLVED,
            war_room_id="C12345",
            war_room_link="https://slack.com/channel",
        )

    @patch("services.notifications.chatops.chatops_service")
    def test_archive_war_room_success(
        self,
        mock_chatops: MagicMock,
    ) -> None:
        """Test successful War Room archival."""
        from tasks.incident_tasks import archive_war_room_task
        
        mock_chatops.archive_war_room.return_value = True
        
        result = archive_war_room_task(str(self.incident.id))
        
        self.assertTrue(result)
        mock_chatops.archive_war_room.assert_called_once_with("C12345")

    def test_archive_war_room_no_channel(self) -> None:
        """Test archival when no War Room exists."""
        from tasks.incident_tasks import archive_war_room_task
        
        # Remove war room ID
        self.incident.war_room_id = ""
        self.incident.save()
        
        result = archive_war_room_task(str(self.incident.id))
        
        # Should return True (nothing to archive)
        self.assertTrue(result)


class CheckEscalationTaskTestCase(TestCase):
    """Tests for escalation checking task."""

    def setUp(self) -> None:
        """Set up test data."""
        self.team = Team.objects.create(
            name="Test Team",
            slug="test-team",
            escalation_timeout_minutes=15,
        )
        self.service = Service.objects.create(
            name="test-service",
            owner_team=self.team,
        )
        self.user = User.objects.create_user(
            username="oncall",
            email="oncall@example.com",
        )
        self.incident = Incident.objects.create(
            title="Old Incident",
            service=self.service,
            severity=IncidentSeverity.SEV2_HIGH,
            status=IncidentStatus.TRIGGERED,
        )

    def test_escalation_skipped_not_triggered(self) -> None:
        """Test that acknowledged incidents are skipped."""
        from tasks.incident_tasks import check_escalation_task
        
        self.incident.status = IncidentStatus.ACKNOWLEDGED
        self.incident.save()
        
        result = check_escalation_task(str(self.incident.id))
        
        self.assertTrue(result.get("skipped"))
        self.assertIn("Not in TRIGGERED status", result.get("reason", ""))

    def test_escalation_skipped_timeout_not_reached(self) -> None:
        """Test that recent incidents are not escalated."""
        from tasks.incident_tasks import check_escalation_task
        
        # Incident is fresh, should not be escalated
        result = check_escalation_task(str(self.incident.id))
        
        self.assertTrue(result.get("skipped"))
        self.assertIn("Timeout not reached", result.get("reason", ""))


class PeriodicTasksTestCase(TestCase):
    """Tests for periodic Celery Beat tasks."""

    def setUp(self) -> None:
        """Set up test data."""
        self.team = Team.objects.create(
            name="Test Team",
            slug="test-team",
        )
        self.service = Service.objects.create(
            name="test-service",
            owner_team=self.team,
        )

    def test_check_pending_escalations(self) -> None:
        """Test pending escalations check queues tasks."""
        from tasks.incident_tasks import check_pending_escalations
        
        # Create some triggered incidents
        Incident.objects.create(
            title="Incident 1",
            service=self.service,
            severity=IncidentSeverity.SEV2_HIGH,
            status=IncidentStatus.TRIGGERED,
        )
        Incident.objects.create(
            title="Incident 2",
            service=self.service,
            severity=IncidentSeverity.SEV3_MEDIUM,
            status=IncidentStatus.TRIGGERED,
        )
        
        with patch("tasks.incident_tasks.check_escalation_task") as mock_task:
            result = check_pending_escalations()
        
        self.assertEqual(result["checked"], 2)
        self.assertEqual(mock_task.delay.call_count, 2)

    def test_send_unacknowledged_reminders(self) -> None:
        """Test reminder sending for old unacknowledged incidents."""
        from tasks.incident_tasks import send_unacknowledged_reminders
        
        # Create an old triggered incident
        old_incident = Incident.objects.create(
            title="Old Incident",
            service=self.service,
            severity=IncidentSeverity.SEV2_HIGH,
            status=IncidentStatus.TRIGGERED,
        )
        # Manually set old created_at
        Incident.objects.filter(pk=old_incident.pk).update(
            created_at=timezone.now() - timedelta(minutes=20)
        )
        
        with patch("services.notifications.router.router") as mock_router:
            result = send_unacknowledged_reminders()
        
        self.assertEqual(result["reminded"], 1)
        mock_router.send_reminder.assert_called_once()

    def test_auto_archive_incidents(self) -> None:
        """Test automatic archival of old resolved incidents."""
        from tasks.incident_tasks import auto_archive_incidents
        
        # Create an old resolved incident
        old_incident = Incident.objects.create(
            title="Old Resolved",
            service=self.service,
            severity=IncidentSeverity.SEV3_MEDIUM,
            status=IncidentStatus.RESOLVED,
            is_archived=False,
        )
        # Manually set old resolved_at
        Incident.objects.filter(pk=old_incident.pk).update(
            resolved_at=timezone.now() - timedelta(days=10)
        )
        
        with patch("tasks.incident_tasks.archive_war_room_task") as mock_archive:
            result = auto_archive_incidents()
        
        self.assertEqual(result["archived"], 1)
        
        # Verify incident was archived
        old_incident.refresh_from_db()
        self.assertTrue(old_incident.is_archived)

    def test_cleanup_stale_war_rooms(self) -> None:
        """Test cleanup of stale War Rooms."""
        from tasks.incident_tasks import cleanup_stale_war_rooms
        
        # Create a resolved incident with war room
        stale_incident = Incident.objects.create(
            title="Stale War Room",
            service=self.service,
            severity=IncidentSeverity.SEV1_CRITICAL,
            status=IncidentStatus.RESOLVED,
            war_room_id="C12345",
            is_archived=False,
        )
        # Manually set old resolved_at
        Incident.objects.filter(pk=stale_incident.pk).update(
            resolved_at=timezone.now() - timedelta(hours=48)
        )
        
        with patch("tasks.incident_tasks.archive_war_room_task") as mock_archive:
            result = cleanup_stale_war_rooms()
        
        self.assertEqual(result["cleaned"], 1)
        mock_archive.delay.assert_called_once()


class DailySummaryTaskTestCase(TestCase):
    """Tests for daily summary generation task."""

    def setUp(self) -> None:
        """Set up test data."""
        self.team = Team.objects.create(
            name="Test Team",
            slug="test-team",
        )
        self.service = Service.objects.create(
            name="test-service",
            owner_team=self.team,
        )

    @patch("services.metrics.metrics_service")
    def test_generate_daily_summary(
        self,
        mock_metrics: MagicMock,
    ) -> None:
        """Test daily summary generation."""
        from tasks.incident_tasks import generate_daily_summary
        
        # Create some incidents
        Incident.objects.create(
            title="Incident 1",
            service=self.service,
            severity=IncidentSeverity.SEV2_HIGH,
            status=IncidentStatus.RESOLVED,
        )
        
        mock_metrics.calculate_mtta.return_value = 5.0
        mock_metrics.calculate_mttr.return_value = 30.0
        
        result = generate_daily_summary()
        
        self.assertIn("total_incidents", result)
        self.assertIn("mtta_minutes", result)
        self.assertIn("mttr_minutes", result)
