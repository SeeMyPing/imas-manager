"""
IMAS Manager - Webhook Provider Tests

Unit tests for generic webhook notification provider.
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


class TestWebhookProvider:
    """Test suite for WebhookProvider."""

    @pytest.fixture
    def json_config(self):
        """Standard JSON webhook configuration."""
        return MockNotificationProvider(
            name="JSON Webhook",
            provider_type="webhook",
            config={
                "url": "https://example.com/webhook",
                "format": "json",
            }
        )

    @pytest.fixture
    def slack_config(self):
        """Slack-compatible webhook configuration."""
        return MockNotificationProvider(
            name="Slack Webhook",
            provider_type="webhook",
            config={
                "url": "https://hooks.slack.com/services/T00/B00/XXX",
                "format": "slack",
            }
        )

    @pytest.fixture
    def teams_config(self):
        """Microsoft Teams webhook configuration."""
        return MockNotificationProvider(
            name="Teams Webhook",
            provider_type="webhook",
            config={
                "url": "https://outlook.office.com/webhook/...",
                "format": "teams",
            }
        )

    @pytest.fixture
    def pagerduty_config(self):
        """PagerDuty webhook configuration."""
        return MockNotificationProvider(
            name="PagerDuty Webhook",
            provider_type="webhook",
            config={
                "url": "https://events.pagerduty.com/v2/enqueue",
                "format": "pagerduty",
                "routing_key": "test-routing-key",
            }
        )

    @pytest.fixture
    def opsgenie_config(self):
        """Opsgenie webhook configuration."""
        return MockNotificationProvider(
            name="Opsgenie Webhook",
            provider_type="webhook",
            config={
                "url": "https://api.opsgenie.com/v2/alerts",
                "format": "opsgenie",
                "headers": {
                    "Authorization": "GenieKey test-api-key"
                }
            }
        )

    @pytest.fixture
    def custom_config(self):
        """Custom template webhook configuration."""
        return MockNotificationProvider(
            name="Custom Webhook",
            provider_type="webhook",
            config={
                "url": "https://custom.example.com/alert",
                "format": "custom",
                "template": {
                    "alert_name": "{title}",
                    "details": {
                        "svc": "{service}",
                        "priority": "{severity}",
                    }
                }
            }
        )

    def test_validation_passes_with_url(self, json_config):
        """Test validation passes with URL configured."""
        from services.notifications.providers.webhook import WebhookProvider
        
        provider = WebhookProvider(json_config)
        
        assert provider.name == "JSON Webhook"

    def test_validation_fails_without_url(self):
        """Test validation fails without URL."""
        from services.notifications.providers.webhook import WebhookProvider
        
        empty_config = MockNotificationProvider(
            name="Empty",
            provider_type="webhook",
            config={}
        )
        
        with pytest.raises(ValueError, match="url"):
            WebhookProvider(empty_config)

    def test_validation_fails_with_unsupported_format(self):
        """Test validation fails with unsupported format."""
        from services.notifications.providers.webhook import WebhookProvider
        
        bad_config = MockNotificationProvider(
            name="Bad Format",
            provider_type="webhook",
            config={
                "url": "https://example.com",
                "format": "unsupported_format"
            }
        )
        
        with pytest.raises(ValueError, match="Unsupported format"):
            WebhookProvider(bad_config)


class TestWebhookPayloadFormats:
    """Test different payload format builders."""

    @pytest.fixture
    def provider_config(self):
        """Generic config for testing formats."""
        def _make_config(fmt: str, extra: dict = None):
            config = {
                "url": "https://example.com/webhook",
                "format": fmt,
            }
            if extra:
                config.update(extra)
            return MockNotificationProvider(
                name=f"{fmt} Provider",
                provider_type="webhook",
                config=config
            )
        return _make_config

    @pytest.fixture
    def sample_message(self):
        """Sample incident message."""
        return {
            "incident_id": "inc-123",
            "title": "Database connection timeout",
            "body": "Multiple timeouts detected",
            "severity": "SEV1_CRITICAL",
            "status": "TRIGGERED",
            "service": "PostgreSQL",
            "links": "https://example.com/incident/123",
        }

    def test_json_payload(self, provider_config, sample_message):
        """Test standard JSON payload format."""
        from services.notifications.providers.webhook import WebhookProvider
        
        config = provider_config("json")
        provider = WebhookProvider(config)
        
        payload = provider._build_json_payload(sample_message)
        
        assert payload["source"] == "imas-manager"
        assert payload["event_type"] == "incident"
        assert payload["title"] == "Database connection timeout"
        assert payload["severity"] == "SEV1_CRITICAL"
        assert payload["service"] == "PostgreSQL"

    def test_slack_payload(self, provider_config, sample_message):
        """Test Slack incoming webhook payload format."""
        from services.notifications.providers.webhook import WebhookProvider
        
        config = provider_config("slack")
        provider = WebhookProvider(config)
        
        payload = provider._build_slack_payload(sample_message)
        
        assert "attachments" in payload
        assert len(payload["attachments"]) == 1
        
        attachment = payload["attachments"][0]
        assert attachment["title"] == "Database connection timeout"
        assert attachment["color"] == "#dc3545"  # Red for SEV1
        assert len(attachment["fields"]) >= 3

    def test_teams_payload(self, provider_config, sample_message):
        """Test Microsoft Teams connector payload format."""
        from services.notifications.providers.webhook import WebhookProvider
        
        config = provider_config("teams")
        provider = WebhookProvider(config)
        
        payload = provider._build_teams_payload(sample_message)
        
        assert payload["@type"] == "MessageCard"
        assert payload["themeColor"] == "dc3545"  # Red for SEV1
        assert "sections" in payload
        
        section = payload["sections"][0]
        assert section["activityTitle"] == "Database connection timeout"

    def test_pagerduty_payload(self, provider_config, sample_message):
        """Test PagerDuty Events API v2 payload format."""
        from services.notifications.providers.webhook import WebhookProvider
        
        config = provider_config("pagerduty", {"routing_key": "test-key"})
        provider = WebhookProvider(config)
        
        payload = provider._build_pagerduty_payload(sample_message)
        
        assert payload["routing_key"] == "test-key"
        assert payload["event_action"] == "trigger"
        assert payload["payload"]["severity"] == "critical"  # Mapped from SEV1

    def test_opsgenie_payload(self, provider_config, sample_message):
        """Test Opsgenie Alert API payload format."""
        from services.notifications.providers.webhook import WebhookProvider
        
        config = provider_config("opsgenie")
        provider = WebhookProvider(config)
        
        payload = provider._build_opsgenie_payload(sample_message)
        
        assert payload["message"] == "Database connection timeout"
        assert payload["priority"] == "P1"  # Mapped from SEV1
        assert payload["source"] == "imas-manager"

    def test_custom_payload_template(self, provider_config, sample_message):
        """Test custom template payload format."""
        from services.notifications.providers.webhook import WebhookProvider
        
        template = {
            "alert": "{title}",
            "metadata": {
                "svc": "{service}",
                "prio": "{severity}",
            },
            "static": "unchanged",
        }
        
        config = provider_config("custom", {"template": template})
        provider = WebhookProvider(config)
        
        payload = provider._build_custom_payload(sample_message)
        
        assert payload["alert"] == "Database connection timeout"
        assert payload["metadata"]["svc"] == "PostgreSQL"
        assert payload["metadata"]["prio"] == "SEV1_CRITICAL"
        assert payload["static"] == "unchanged"


class TestWebhookSending:
    """Test webhook HTTP request sending."""

    @pytest.fixture
    def config(self):
        """Basic webhook config."""
        return MockNotificationProvider(
            name="Test Webhook",
            provider_type="webhook",
            config={
                "url": "https://example.com/webhook",
                "format": "json",
            }
        )

    @pytest.fixture
    def config_with_headers(self):
        """Webhook config with custom headers."""
        return MockNotificationProvider(
            name="Auth Webhook",
            provider_type="webhook",
            config={
                "url": "https://example.com/webhook",
                "format": "json",
                "headers": {
                    "Authorization": "Bearer test-token",
                    "X-Custom": "value",
                }
            }
        )

    @patch("httpx.Client")
    def test_send_success(self, mock_client_class, config):
        """Test successful webhook send."""
        from services.notifications.providers.webhook import WebhookProvider
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        provider = WebhookProvider(config)
        
        result = provider.send("", {"title": "Test", "body": "Test message"})
        
        assert result is True

    @patch("httpx.Client")
    def test_send_failure_4xx(self, mock_client_class, config):
        """Test webhook failure handling for 4xx errors."""
        from services.notifications.providers.webhook import WebhookProvider
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        provider = WebhookProvider(config)
        
        result = provider.send("", {"title": "Test"})
        
        assert result is False

    @patch("httpx.Client")
    def test_send_failure_5xx(self, mock_client_class, config):
        """Test webhook failure handling for 5xx errors."""
        from services.notifications.providers.webhook import WebhookProvider
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        provider = WebhookProvider(config)
        
        result = provider.send("", {"title": "Test"})
        
        assert result is False

    @patch("httpx.Client")
    def test_send_with_custom_headers(self, mock_client_class, config_with_headers):
        """Test custom headers are included in request."""
        from services.notifications.providers.webhook import WebhookProvider
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        provider = WebhookProvider(config_with_headers)
        provider.send("", {"title": "Test"})
        
        call_kwargs = mock_client.request.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        
        assert headers["Authorization"] == "Bearer test-token"
        assert headers["X-Custom"] == "value"
        assert headers["Content-Type"] == "application/json"

    @patch("httpx.Client")
    def test_url_override_in_recipient(self, mock_client_class, config):
        """Test URL can be overridden via recipient parameter."""
        from services.notifications.providers.webhook import WebhookProvider
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        provider = WebhookProvider(config)
        provider.send("https://override.example.com/alert", {"title": "Test"})
        
        call_args = mock_client.request.call_args
        url = call_args.args[1]  # Second positional arg is URL
        
        assert url == "https://override.example.com/alert"


class TestWebhookSeverityMapping:
    """Test severity mapping for different systems."""

    def test_pagerduty_severity_mapping(self):
        """Test PagerDuty severity mapping."""
        from services.notifications.providers.webhook import WebhookProvider
        
        assert WebhookProvider.PAGERDUTY_SEVERITY["SEV1_CRITICAL"] == "critical"
        assert WebhookProvider.PAGERDUTY_SEVERITY["SEV2_HIGH"] == "error"
        assert WebhookProvider.PAGERDUTY_SEVERITY["SEV3_MEDIUM"] == "warning"
        assert WebhookProvider.PAGERDUTY_SEVERITY["SEV4_LOW"] == "info"

    def test_opsgenie_priority_mapping(self):
        """Test Opsgenie priority mapping."""
        from services.notifications.providers.webhook import WebhookProvider
        
        assert WebhookProvider.OPSGENIE_PRIORITY["SEV1_CRITICAL"] == "P1"
        assert WebhookProvider.OPSGENIE_PRIORITY["SEV2_HIGH"] == "P2"
        assert WebhookProvider.OPSGENIE_PRIORITY["SEV3_MEDIUM"] == "P3"
        assert WebhookProvider.OPSGENIE_PRIORITY["SEV4_LOW"] == "P4"
