"""
IMAS Manager - ntfy.sh Provider Tests

Unit tests for ntfy.sh notification provider.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class MockNotificationProvider:
    """Mock NotificationProvider model for testing."""
    
    def __init__(self, name: str, provider_type: str, config: dict):
        self.name = name
        self.type = provider_type
        self.config = config


class TestNtfyProvider:
    """Test suite for NtfyProvider."""

    @pytest.fixture
    def basic_config(self):
        """Basic ntfy configuration."""
        return MockNotificationProvider(
            name="ntfy Alerts",
            provider_type="ntfy",
            config={
                "server_url": "https://ntfy.sh",
                "default_topic": "imas-incidents",
            }
        )

    @pytest.fixture
    def full_config(self):
        """Full ntfy configuration with auth."""
        return MockNotificationProvider(
            name="ntfy Private",
            provider_type="ntfy",
            config={
                "server_url": "https://ntfy.example.com",
                "default_topic": "imas-alerts",
                "access_token": "tk_test_token",
                "default_priority": 4,
                "default_tags": ["incident", "production"],
            }
        )

    @pytest.fixture
    def basic_auth_config(self):
        """ntfy configuration with basic auth."""
        return MockNotificationProvider(
            name="ntfy Basic",
            provider_type="ntfy",
            config={
                "server_url": "https://ntfy.example.com",
                "default_topic": "alerts",
                "username": "testuser",
                "password": "testpass",
            }
        )

    def test_validation_passes_with_required_config(self, basic_config):
        """Test validation passes with all required config."""
        from services.notifications.providers.ntfy import NtfyProvider
        
        provider = NtfyProvider(basic_config)
        
        assert provider.name == "ntfy Alerts"

    def test_validation_fails_without_server_url(self):
        """Test validation fails without server_url."""
        from services.notifications.providers.ntfy import NtfyProvider
        
        incomplete_config = MockNotificationProvider(
            name="Incomplete",
            provider_type="ntfy",
            config={"default_topic": "test"}
        )
        
        with pytest.raises(ValueError, match="server_url"):
            NtfyProvider(incomplete_config)

    def test_validation_fails_without_topic(self):
        """Test validation fails without default_topic."""
        from services.notifications.providers.ntfy import NtfyProvider
        
        incomplete_config = MockNotificationProvider(
            name="Incomplete",
            provider_type="ntfy",
            config={"server_url": "https://ntfy.sh"}
        )
        
        with pytest.raises(ValueError, match="default_topic"):
            NtfyProvider(incomplete_config)

    def test_token_auth_headers(self, full_config):
        """Test token-based auth headers."""
        from services.notifications.providers.ntfy import NtfyProvider
        
        provider = NtfyProvider(full_config)
        headers = provider._get_auth_headers()
        
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer tk_test_token"

    def test_basic_auth_headers(self, basic_auth_config):
        """Test basic auth headers."""
        from services.notifications.providers.ntfy import NtfyProvider
        
        provider = NtfyProvider(basic_auth_config)
        headers = provider._get_auth_headers()
        
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Basic ")

    def test_no_auth_headers(self, basic_config):
        """Test no auth headers when not configured."""
        from services.notifications.providers.ntfy import NtfyProvider
        
        provider = NtfyProvider(basic_config)
        headers = provider._get_auth_headers()
        
        assert headers == {}


class TestNtfyPayload:
    """Test ntfy payload building."""

    @pytest.fixture
    def config(self):
        return MockNotificationProvider(
            name="ntfy Test",
            provider_type="ntfy",
            config={
                "server_url": "https://ntfy.sh",
                "default_topic": "test-topic",
                "default_tags": ["imas"],
            }
        )

    def test_build_payload_sev1(self, config):
        """Test payload for SEV1 incident."""
        from services.notifications.providers.ntfy import NtfyProvider
        
        provider = NtfyProvider(config)
        
        message = {
            "title": "Database outage",
            "body": "Primary database is unreachable",
            "severity": "SEV1_CRITICAL",
            "status": "TRIGGERED",
            "service": "PostgreSQL",
        }
        
        payload = provider._build_payload(message)
        
        assert payload["title"] == "Database outage"
        assert payload["priority"] == 5  # Max priority for SEV1
        assert "rotating_light" in payload["tags"]
        assert "imas" in payload["tags"]  # Default tag

    def test_build_payload_sev3(self, config):
        """Test payload for SEV3 incident."""
        from services.notifications.providers.ntfy import NtfyProvider
        
        provider = NtfyProvider(config)
        
        message = {
            "title": "Minor latency",
            "severity": "SEV3_MEDIUM",
            "status": "ACKNOWLEDGED",
        }
        
        payload = provider._build_payload(message)
        
        assert payload["priority"] == 3
        assert "eyes" in payload["tags"]  # Status tag for acknowledged

    def test_build_payload_with_links(self, config):
        """Test payload includes click action for links."""
        from services.notifications.providers.ntfy import NtfyProvider
        
        provider = NtfyProvider(config)
        
        message = {
            "title": "Test incident",
            "severity": "SEV2",
            "links": "https://docs.google.com/doc/123, https://slack.com/channel",
        }
        
        payload = provider._build_payload(message)
        
        assert "click" in payload
        assert payload["click"] == "https://docs.google.com/doc/123"

    def test_build_payload_actions_high_priority(self, config):
        """Test actions are added for high priority."""
        from services.notifications.providers.ntfy import NtfyProvider
        
        provider = NtfyProvider(config)
        
        message = {
            "title": "Critical alert",
            "severity": "SEV1_CRITICAL",
            "incident_id": "inc-123",
            "links": "https://docs.google.com/doc/abc",
        }
        
        payload = provider._build_payload(message)
        
        assert "actions" in payload
        assert len(payload["actions"]) >= 1

    def test_format_message_body(self, config):
        """Test message body formatting."""
        from services.notifications.providers.ntfy import NtfyProvider
        
        provider = NtfyProvider(config)
        
        message = {
            "body": "API is returning 500 errors",
            "service": "api-gateway",
            "severity": "SEV2_HIGH",
            "status": "TRIGGERED",
        }
        
        body = provider._format_message_body(message)
        
        assert "API is returning 500 errors" in body
        assert "Service: api-gateway" in body
        assert "Severity: SEV2_HIGH" in body

    def test_tags_limited_to_five(self, config):
        """Test tags are limited to 5."""
        from services.notifications.providers.ntfy import NtfyProvider
        
        # Config with many default tags
        config.config["default_tags"] = ["tag1", "tag2", "tag3", "tag4"]
        
        provider = NtfyProvider(config)
        
        message = {
            "title": "Test",
            "severity": "SEV1_CRITICAL",  # Adds 3 more tags
            "status": "TRIGGERED",  # Adds 1 more tag
        }
        
        payload = provider._build_payload(message)
        
        assert len(payload["tags"]) <= 5


class TestNtfySending:
    """Test ntfy HTTP request sending."""

    @pytest.fixture
    def config(self):
        return MockNotificationProvider(
            name="ntfy Test",
            provider_type="ntfy",
            config={
                "server_url": "https://ntfy.sh",
                "default_topic": "test-topic",
            }
        )

    @patch("httpx.Client")
    def test_send_success(self, mock_client_class, config):
        """Test successful send."""
        from services.notifications.providers.ntfy import NtfyProvider
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        provider = NtfyProvider(config)
        
        result = provider.send("", {"title": "Test", "body": "Test message"})
        
        assert result is True
        mock_client.post.assert_called_once()
        
        # Verify URL includes topic
        call_args = mock_client.post.call_args
        assert "test-topic" in call_args.args[0]

    @patch("httpx.Client")
    def test_send_custom_topic(self, mock_client_class, config):
        """Test send to custom topic."""
        from services.notifications.providers.ntfy import NtfyProvider
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        provider = NtfyProvider(config)
        provider.send("custom-topic", {"title": "Test"})
        
        call_args = mock_client.post.call_args
        assert "custom-topic" in call_args.args[0]

    @patch("httpx.Client")
    def test_send_failure(self, mock_client_class, config):
        """Test send failure handling."""
        from services.notifications.providers.ntfy import NtfyProvider
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        provider = NtfyProvider(config)
        
        result = provider.send("", {"title": "Test"})
        
        assert result is False

    @patch("httpx.Client")
    def test_send_batch(self, mock_client_class, config):
        """Test batch sending to multiple topics."""
        from services.notifications.providers.ntfy import NtfyProvider
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        provider = NtfyProvider(config)
        
        results = provider.send_batch(
            ["topic1", "topic2", "topic3"],
            {"title": "Broadcast"}
        )
        
        assert all(results.values())
        assert len(results) == 3
        assert mock_client.post.call_count == 3

    @patch("httpx.Client")
    def test_check_connectivity(self, mock_client_class, config):
        """Test connectivity check."""
        from services.notifications.providers.ntfy import NtfyProvider
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        provider = NtfyProvider(config)
        
        result = provider.check_connectivity()
        
        assert result is True


class TestNtfySeverityMapping:
    """Test severity to priority mapping."""

    def test_severity_priority_mapping(self):
        """Test severity to ntfy priority mapping."""
        from services.notifications.providers.ntfy import NtfyProvider
        
        assert NtfyProvider.SEVERITY_PRIORITY["SEV1_CRITICAL"] == 5
        assert NtfyProvider.SEVERITY_PRIORITY["SEV2_HIGH"] == 4
        assert NtfyProvider.SEVERITY_PRIORITY["SEV3_MEDIUM"] == 3
        assert NtfyProvider.SEVERITY_PRIORITY["SEV4_LOW"] == 2

    def test_severity_tags_mapping(self):
        """Test severity to ntfy tags mapping."""
        from services.notifications.providers.ntfy import NtfyProvider
        
        assert "rotating_light" in NtfyProvider.SEVERITY_TAGS["SEV1_CRITICAL"]
        assert "warning" in NtfyProvider.SEVERITY_TAGS["SEV2_HIGH"]
        assert "bell" in NtfyProvider.SEVERITY_TAGS["SEV3_MEDIUM"]
