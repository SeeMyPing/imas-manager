"""
IMAS Manager - Discord Provider Tests

Unit tests for Discord notification provider.
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


class TestDiscordProvider:
    """Test suite for DiscordProvider."""

    @pytest.fixture
    def webhook_config(self):
        """Discord webhook configuration."""
        return MockNotificationProvider(
            name="Discord Webhook",
            provider_type="discord",
            config={
                "webhook_url": "https://discord.com/api/webhooks/123456/abcdef"
            }
        )

    @pytest.fixture
    def bot_config(self):
        """Discord bot configuration."""
        return MockNotificationProvider(
            name="Discord Bot",
            provider_type="discord",
            config={
                "bot_token": "test-bot-token",
                "guild_id": "123456789",
                "incidents_category_id": "987654321"
            }
        )

    @pytest.fixture
    def mock_httpx_client(self):
        """Mock httpx client."""
        with patch("httpx.Client") as mock:
            client_instance = MagicMock()
            mock.return_value = client_instance
            yield client_instance

    def test_webhook_mode_detection(self, webhook_config):
        """Test webhook mode is detected correctly."""
        from services.notifications.providers.discord import DiscordProvider
        
        provider = DiscordProvider(webhook_config)
        
        assert provider.is_webhook_mode is True
        assert provider.is_bot_mode is False

    def test_bot_mode_detection(self, bot_config):
        """Test bot mode is detected correctly."""
        from services.notifications.providers.discord import DiscordProvider
        
        provider = DiscordProvider(bot_config)
        
        assert provider.is_bot_mode is True
        # Bot mode can also have webhook mode if both configured
        assert provider.is_webhook_mode is False

    def test_validation_fails_without_config(self):
        """Test validation fails without required config."""
        from services.notifications.providers.discord import DiscordProvider
        
        empty_config = MockNotificationProvider(
            name="Empty",
            provider_type="discord",
            config={}
        )
        
        with pytest.raises(ValueError, match="requires either"):
            DiscordProvider(empty_config)

    def test_bot_mode_requires_guild_id(self):
        """Test bot mode requires guild_id."""
        from services.notifications.providers.discord import DiscordProvider
        
        incomplete_config = MockNotificationProvider(
            name="Incomplete Bot",
            provider_type="discord",
            config={"bot_token": "token-only"}
        )
        
        with pytest.raises(ValueError, match="guild_id"):
            DiscordProvider(incomplete_config)

    def test_build_embed_sev1(self, webhook_config):
        """Test embed building for SEV1 incident."""
        from services.notifications.providers.discord import DiscordProvider
        
        provider = DiscordProvider(webhook_config)
        
        message = {
            "title": "Database outage",
            "body": "Primary database is unreachable",
            "severity": "SEV1 - Critical",
            "status": "TRIGGERED",
            "service": "PostgreSQL",
        }
        
        embed = provider._build_embed(message)
        
        assert embed["title"] == "Database outage"
        assert embed["description"] == "Primary database is unreachable"
        assert embed["color"] == 0xDC3545  # Red for SEV1
        assert len(embed["fields"]) >= 3

    def test_build_embed_sev3(self, webhook_config):
        """Test embed building for SEV3 incident."""
        from services.notifications.providers.discord import DiscordProvider
        
        provider = DiscordProvider(webhook_config)
        
        message = {
            "title": "Minor latency",
            "severity": "SEV3 - Medium",
        }
        
        embed = provider._build_embed(message)
        
        assert embed["color"] == 0xFFC107  # Yellow for SEV3

    @patch("httpx.Client")
    def test_send_via_webhook_success(self, mock_client_class, webhook_config):
        """Test successful webhook send."""
        from services.notifications.providers.discord import DiscordProvider
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        provider = DiscordProvider(webhook_config)
        
        result = provider.send("", {"title": "Test", "body": "Test message"})
        
        assert result is True
        mock_client.post.assert_called_once()

    @patch("httpx.Client")
    def test_send_via_webhook_failure(self, mock_client_class, webhook_config):
        """Test webhook send failure handling."""
        from services.notifications.providers.discord import DiscordProvider
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        provider = DiscordProvider(webhook_config)
        
        result = provider.send("", {"title": "Test"})
        
        assert result is False

    @patch("httpx.Client")
    def test_create_channel_requires_bot_mode(self, mock_client_class, webhook_config):
        """Test channel creation requires bot mode."""
        from services.notifications.providers.discord import DiscordProvider
        
        provider = DiscordProvider(webhook_config)
        
        result = provider.create_channel("test-channel")
        
        assert result is None

    @patch("httpx.Client")
    def test_create_channel_success(self, mock_client_class, bot_config):
        """Test successful channel creation."""
        from services.notifications.providers.discord import DiscordProvider
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "new-channel-123"}
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        provider = DiscordProvider(bot_config)
        
        result = provider.create_channel(
            name="incident-2024-01-01",
            topic="War room for INC-001"
        )
        
        assert result is not None
        channel_id, channel_url = result
        assert channel_id == "new-channel-123"
        assert "discord.com/channels" in channel_url

    @patch("httpx.Client")
    def test_archive_channel(self, mock_client_class, bot_config):
        """Test channel archiving."""
        from services.notifications.providers.discord import DiscordProvider
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.patch.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        provider = DiscordProvider(bot_config)
        
        result = provider.archive_channel("channel-to-archive")
        
        assert result is True
        mock_client.patch.assert_called_once()


class TestDiscordProviderIntegration:
    """Integration tests for Discord provider (requires mocking)."""

    @pytest.fixture
    def full_config(self):
        """Full bot configuration."""
        return MockNotificationProvider(
            name="Discord Full",
            provider_type="discord",
            config={
                "bot_token": "test-token",
                "guild_id": "guild123",
                "incidents_category_id": "category456",
                "archive_category_id": "archive789",
            }
        )

    @patch("httpx.Client")
    def test_send_bot_message(self, mock_client_class, full_config):
        """Test sending message via bot."""
        from services.notifications.providers.discord import DiscordProvider
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        provider = DiscordProvider(full_config)
        
        message = {
            "title": "Production Incident",
            "body": "API is returning 500 errors",
            "severity": "SEV2",
            "service": "api-gateway",
            "status": "TRIGGERED",
        }
        
        result = provider.send("channel123", message)
        
        assert result is True
        
        # Verify correct headers
        call_kwargs = mock_client.post.call_args
        assert "Authorization" in call_kwargs.kwargs.get("headers", {})
