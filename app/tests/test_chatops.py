"""
IMAS Manager - Tests for ChatOps Service and Slack API
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import unittest
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Incident, Service, Team
from core.models.incident import IncidentSeverity, IncidentStatus
from services.chatops import (
    ChatOpsService,
    OnCallService,
    SlackCommand,
    SlackCommandResult,
    SlackCommandType,
    SlackSignatureVerifier,
)

User = get_user_model()


class SlackSignatureVerifierTestCase(TestCase):
    """Tests for Slack signature verification."""

    def setUp(self):
        self.signing_secret = "test_secret_12345"
        self.verifier = SlackSignatureVerifier(self.signing_secret)

    def test_valid_signature(self):
        """Test that valid signature is accepted."""
        timestamp = str(int(time.time()))
        body = b"token=test&command=/incident&text=help"
        
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        expected_sig = (
            "v0="
            + hmac.new(
                self.signing_secret.encode(),
                sig_basestring.encode(),
                hashlib.sha256,
            ).hexdigest()
        )
        
        self.assertTrue(
            self.verifier.verify(expected_sig, timestamp, body)
        )

    def test_invalid_signature(self):
        """Test that invalid signature is rejected."""
        timestamp = str(int(time.time()))
        body = b"token=test&command=/incident&text=help"
        
        self.assertFalse(
            self.verifier.verify("v0=invalid_signature", timestamp, body)
        )

    def test_old_timestamp_rejected(self):
        """Test that old timestamps are rejected."""
        old_timestamp = str(int(time.time()) - 600)  # 10 minutes ago
        body = b"test"
        
        sig_basestring = f"v0:{old_timestamp}:{body.decode('utf-8')}"
        signature = (
            "v0="
            + hmac.new(
                self.signing_secret.encode(),
                sig_basestring.encode(),
                hashlib.sha256,
            ).hexdigest()
        )
        
        self.assertFalse(
            self.verifier.verify(signature, old_timestamp, body)
        )


class ChatOpsCommandParsingTestCase(TestCase):
    """Tests for parsing Slack slash commands."""

    def setUp(self):
        self.chatops = ChatOpsService()

    def test_parse_help_command(self):
        """Test parsing /incident help."""
        command = self.chatops.parse_command("help")
        
        self.assertEqual(command.action, SlackCommandType.HELP)

    def test_parse_create_command(self):
        """Test parsing /incident create <title>."""
        command = self.chatops.parse_command("create High latency on API Gateway")
        
        self.assertEqual(command.action, SlackCommandType.CREATE)
        self.assertEqual(command.args, ["High latency on API Gateway"])

    def test_parse_ack_command(self):
        """Test parsing /incident ack <id>."""
        command = self.chatops.parse_command("ack INC-123")
        
        self.assertEqual(command.action, SlackCommandType.ACK)
        self.assertEqual(command.incident_id, "123")

    def test_parse_ack_uuid(self):
        """Test parsing ack with UUID."""
        uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        command = self.chatops.parse_command(f"ack {uuid}")
        
        self.assertEqual(command.action, SlackCommandType.ACK)
        self.assertEqual(command.incident_id, uuid)

    def test_parse_resolve_with_message(self):
        """Test parsing /incident resolve <id> <message>."""
        command = self.chatops.parse_command("resolve INC-456 Hotfix deployed")
        
        self.assertEqual(command.action, SlackCommandType.RESOLVE)
        self.assertEqual(command.incident_id, "456")
        self.assertEqual(command.args, ["Hotfix deployed"])

    def test_parse_list_command(self):
        """Test parsing /incident list."""
        command = self.chatops.parse_command("list")
        
        self.assertEqual(command.action, SlackCommandType.LIST)

    def test_parse_list_all(self):
        """Test parsing /incident list all."""
        command = self.chatops.parse_command("list all")
        
        self.assertEqual(command.action, SlackCommandType.LIST)
        self.assertIn("all", command.args)

    def test_parse_status_command(self):
        """Test parsing /incident status <id>."""
        command = self.chatops.parse_command("status INC-789")
        
        self.assertEqual(command.action, SlackCommandType.STATUS)
        self.assertEqual(command.incident_id, "789")

    def test_parse_escalate_command(self):
        """Test parsing /incident escalate <id>."""
        command = self.chatops.parse_command("escalate INC-100")
        
        self.assertEqual(command.action, SlackCommandType.ESCALATE)
        self.assertEqual(command.incident_id, "100")

    def test_parse_empty_defaults_to_help(self):
        """Test that empty command defaults to help."""
        command = self.chatops.parse_command("")
        
        self.assertEqual(command.action, SlackCommandType.HELP)

    def test_parse_unknown_command(self):
        """Test that unknown command defaults to help."""
        command = self.chatops.parse_command("unknown_action")
        
        self.assertEqual(command.action, SlackCommandType.HELP)


class ChatOpsCommandExecutionTestCase(TestCase):
    """Tests for executing ChatOps commands."""

    def setUp(self):
        self.team = Team.objects.create(
            name="Platform Team",
            slug="platform",
        )
        
        self.service = Service.objects.create(
            name="API Gateway",
            owner_team=self.team,
        )
        
        self.user = User.objects.create_user(
            username="operator",
            email="operator@example.com",
            password="testpass123",
        )
        
        # Create test incident
        self.incident = Incident.objects.create(
            title="Test Incident",
            description="Test description",
            severity=IncidentSeverity.SEV3_MEDIUM,
            status=IncidentStatus.TRIGGERED,
            service=self.service,
        )
        
        self.chatops = ChatOpsService()

    def test_execute_help_command(self):
        """Test executing help command."""
        command = SlackCommand(
            action=SlackCommandType.HELP,
            args=[],
        )
        
        result = self.chatops.execute_command_sync(
            command=command,
            user_id="U12345",
        )
        
        self.assertTrue(result.success)
        self.assertIn("Commandes disponibles", result.text)

    @unittest.skip("Requires PostgreSQL for async operations - SQLite locks")
    def test_execute_create_command(self):
        """Test executing create command."""
        command = SlackCommand(
            action=SlackCommandType.CREATE,
            args=["New incident from Slack"],
        )
        
        result = self.chatops.execute_command_sync(
            command=command,
            user_id="U12345",
        )
        
        self.assertTrue(result.success)
        self.assertIn("Incident créé", result.text)
        
        # Verify incident was created
        self.assertTrue(
            Incident.objects.filter(title="New incident from Slack").exists()
        )

    @unittest.skip("Requires PostgreSQL for async operations - SQLite locks")
    def test_execute_ack_command(self):
        """Test executing ack command."""
        command = SlackCommand(
            action=SlackCommandType.ACK,
            args=[],
            incident_id=str(self.incident.id),
        )
        
        result = self.chatops.execute_command_sync(
            command=command,
            user_id="U12345",
            user_email="operator@example.com",
        )
        
        self.assertTrue(result.success)
        self.assertIn("acquitté", result.text)
        
        # Verify incident was acknowledged
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.status, IncidentStatus.ACKNOWLEDGED)
        self.assertIsNotNone(self.incident.acknowledged_at)

    @unittest.skip("Requires PostgreSQL for async operations - SQLite locks")
    def test_execute_ack_already_acknowledged(self):
        """Test ack on already acknowledged incident."""
        self.incident.status = IncidentStatus.ACKNOWLEDGED
        self.incident.acknowledged_at = timezone.now()
        self.incident.acknowledged_by = self.user
        self.incident.save()
        
        command = SlackCommand(
            action=SlackCommandType.ACK,
            args=[],
            incident_id=str(self.incident.id),
        )
        
        result = self.chatops.execute_command_sync(
            command=command,
            user_id="U12345",
        )
        
        self.assertFalse(result.success)
        self.assertIn("déjà acquitté", result.text)

    @unittest.skip("Requires PostgreSQL for async operations - SQLite locks")
    def test_execute_resolve_command(self):
        """Test executing resolve command."""
        command = SlackCommand(
            action=SlackCommandType.RESOLVE,
            args=["Fixed with hotfix"],
            incident_id=str(self.incident.id),
        )
        
        result = self.chatops.execute_command_sync(
            command=command,
            user_id="U12345",
            user_email="operator@example.com",
        )
        
        self.assertTrue(result.success)
        self.assertIn("résolu", result.text)
        
        # Verify incident was resolved
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.status, IncidentStatus.RESOLVED)
        self.assertIsNotNone(self.incident.resolved_at)

    @unittest.skip("Requires PostgreSQL for async operations - SQLite locks")
    def test_execute_escalate_command(self):
        """Test executing escalate command."""
        self.incident.severity = IncidentSeverity.SEV4_LOW
        self.incident.save()
        
        command = SlackCommand(
            action=SlackCommandType.ESCALATE,
            args=[],
            incident_id=str(self.incident.id),
        )
        
        result = self.chatops.execute_command_sync(
            command=command,
            user_id="U12345",
        )
        
        self.assertTrue(result.success)
        self.assertIn("escaladé", result.text)
        
        # Verify severity was increased
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.severity, IncidentSeverity.SEV3_MEDIUM)

    @unittest.skip("Requires PostgreSQL for async operations - SQLite locks")
    def test_execute_escalate_already_critical(self):
        """Test escalate on already critical incident."""
        self.incident.severity = IncidentSeverity.SEV1_CRITICAL
        self.incident.save()
        
        command = SlackCommand(
            action=SlackCommandType.ESCALATE,
            args=[],
            incident_id=str(self.incident.id),
        )
        
        result = self.chatops.execute_command_sync(
            command=command,
            user_id="U12345",
        )
        
        self.assertFalse(result.success)
        self.assertIn("maximum", result.text)

    @unittest.skip("Requires PostgreSQL for async operations - SQLite locks")
    def test_execute_list_command(self):
        """Test executing list command."""
        command = SlackCommand(
            action=SlackCommandType.LIST,
            args=[],
        )
        
        result = self.chatops.execute_command_sync(
            command=command,
            user_id="U12345",
        )
        
        self.assertTrue(result.success)
        self.assertIsNotNone(result.blocks)

    @unittest.skip("Requires PostgreSQL for async operations - SQLite locks")
    def test_execute_status_command(self):
        """Test executing status command."""
        command = SlackCommand(
            action=SlackCommandType.STATUS,
            args=[],
            incident_id=str(self.incident.id),
        )
        
        result = self.chatops.execute_command_sync(
            command=command,
            user_id="U12345",
        )
        
        self.assertTrue(result.success)
        self.assertIsNotNone(result.blocks)

    @unittest.skip("Requires PostgreSQL for async operations - SQLite locks")
    def test_incident_not_found(self):
        """Test command with non-existent incident."""
        command = SlackCommand(
            action=SlackCommandType.ACK,
            args=[],
            incident_id="nonexistent",
        )
        
        result = self.chatops.execute_command_sync(
            command=command,
            user_id="U12345",
        )
        
        self.assertFalse(result.success)
        # Error message can be "non trouvé" or UUID validation error
        self.assertTrue(
            "non trouvé" in result.text or "erreur" in result.text.lower()
        )


@override_settings(SLACK_SIGNING_SECRET="test_secret")
class SlackAPIViewsTestCase(TestCase):
    """Tests for Slack API endpoints."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="slackuser",
            email="slack@example.com",
            password="testpass123",
        )
        
        self.team = Team.objects.create(
            name="SRE Team",
            slug="sre",
        )
        
        self.service = Service.objects.create(
            name="Payment Service",
            owner_team=self.team,
        )

    def _generate_signature(self, body: bytes, timestamp: str) -> str:
        """Generate valid Slack signature for testing."""
        signing_secret = "test_secret"
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        return (
            "v0="
            + hmac.new(
                signing_secret.encode(),
                sig_basestring.encode(),
                hashlib.sha256,
            ).hexdigest()
        )

    def test_slash_command_endpoint_help(self):
        """Test POST /api/v1/slack/commands/ with help."""
        url = reverse("api_v1:slack_commands")
        
        body = "command=/incident&text=help&user_id=U12345&user_name=testuser&channel_id=C12345"
        timestamp = str(int(time.time()))
        signature = self._generate_signature(body.encode(), timestamp)
        
        response = self.client.post(
            url,
            body,
            content_type="application/x-www-form-urlencoded",
            HTTP_X_SLACK_SIGNATURE=signature,
            HTTP_X_SLACK_REQUEST_TIMESTAMP=timestamp,
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("text", data)

    def test_slash_command_invalid_signature(self):
        """Test that invalid signature is rejected."""
        url = reverse("api_v1:slack_commands")
        
        body = "command=/incident&text=help&user_id=U12345"
        timestamp = str(int(time.time()))
        
        response = self.client.post(
            url,
            body,
            content_type="application/x-www-form-urlencoded",
            HTTP_X_SLACK_SIGNATURE="v0=invalid",
            HTTP_X_SLACK_REQUEST_TIMESTAMP=timestamp,
        )
        
        self.assertEqual(response.status_code, 401)

    def test_events_url_verification(self):
        """Test Slack Events API URL verification challenge."""
        url = reverse("api_v1:slack_events")
        
        payload = {
            "type": "url_verification",
            "challenge": "test_challenge_token",
        }
        
        response = self.client.post(
            url,
            json.dumps(payload),
            content_type="application/json",
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["challenge"], "test_challenge_token")

    @unittest.skip("Requires PostgreSQL for async operations - SQLite locks")
    def test_interactive_ack_button(self):
        """Test interactive ack button click."""
        # Create an incident first
        incident = Incident.objects.create(
            title="Test Incident",
            description="Test",
            severity=IncidentSeverity.SEV2_HIGH,
            status=IncidentStatus.TRIGGERED,
            service=self.service,
        )
        
        url = reverse("api_v1:slack_interactive")
        
        payload = {
            "type": "block_actions",
            "user": {"id": "U12345"},
            "actions": [
                {
                    "action_id": "ack_incident",
                    "value": str(incident.id),
                }
            ],
        }
        
        body = f"payload={json.dumps(payload)}"
        timestamp = str(int(time.time()))
        signature = self._generate_signature(body.encode(), timestamp)
        
        response = self.client.post(
            url,
            body,
            content_type="application/x-www-form-urlencoded",
            HTTP_X_SLACK_SIGNATURE=signature,
            HTTP_X_SLACK_REQUEST_TIMESTAMP=timestamp,
        )
        
        self.assertEqual(response.status_code, 200)
        
        # Verify incident was acknowledged
        incident.refresh_from_db()
        self.assertEqual(incident.status, IncidentStatus.ACKNOWLEDGED)


class OnCallServiceTestCase(TestCase):
    """Tests for OnCall service."""

    def setUp(self):
        self.team = Team.objects.create(
            name="SRE Team",
            slug="sre",
        )
        
        self.user = User.objects.create_user(
            username="oncall_user",
            email="oncall@example.com",
            password="testpass123",
            first_name="On",
            last_name="Call",
        )

    @unittest.skip("Requires PostgreSQL for async operations - SQLite locks")
    def test_no_oncall_returns_warning(self):
        """Test that empty on-call returns appropriate message."""
        import asyncio
        
        oncall_service = OnCallService()
        
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(
            oncall_service.get_current_oncall()
        )
        loop.close()
        
        self.assertTrue(result.success)
        self.assertIn("Aucune astreinte", result.text)
