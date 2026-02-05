"""
IMAS Manager - OVH SMS Provider Tests

Unit tests for OVH SMS notification provider.
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


class TestOVHSMSProvider:
    """Test suite for OVHSMSProvider."""

    @pytest.fixture
    def valid_config(self):
        """Valid OVH SMS configuration."""
        return MockNotificationProvider(
            name="OVH SMS",
            provider_type="ovh_sms",
            config={
                "application_key": "app-key-123",
                "application_secret": "app-secret-456",
                "consumer_key": "consumer-key-789",
                "service_name": "sms-test-1",
                "sender": "IMAS",
            }
        )

    @pytest.fixture
    def minimal_config(self):
        """Minimal OVH SMS configuration (no sender)."""
        return MockNotificationProvider(
            name="OVH SMS Minimal",
            provider_type="ovh_sms",
            config={
                "application_key": "app-key",
                "application_secret": "app-secret",
                "consumer_key": "consumer-key",
                "service_name": "sms-test-1",
            }
        )

    def test_validation_passes_with_required_config(self, valid_config):
        """Test validation passes with all required config."""
        from services.notifications.providers.ovh_sms import OVHSMSProvider
        
        provider = OVHSMSProvider(valid_config)
        
        assert provider.name == "OVH SMS"

    def test_validation_fails_without_application_key(self):
        """Test validation fails without application_key."""
        from services.notifications.providers.ovh_sms import OVHSMSProvider
        
        incomplete_config = MockNotificationProvider(
            name="Incomplete",
            provider_type="ovh_sms",
            config={
                "application_secret": "secret",
                "consumer_key": "consumer",
                "service_name": "sms-test",
            }
        )
        
        with pytest.raises(ValueError, match="application_key"):
            OVHSMSProvider(incomplete_config)

    def test_validation_fails_without_service_name(self):
        """Test validation fails without service_name."""
        from services.notifications.providers.ovh_sms import OVHSMSProvider
        
        incomplete_config = MockNotificationProvider(
            name="Incomplete",
            provider_type="ovh_sms",
            config={
                "application_key": "key",
                "application_secret": "secret",
                "consumer_key": "consumer",
            }
        )
        
        with pytest.raises(ValueError, match="service_name"):
            OVHSMSProvider(incomplete_config)

    def test_normalize_phone_french(self, valid_config):
        """Test French phone number normalization."""
        from services.notifications.providers.ovh_sms import OVHSMSProvider
        
        provider = OVHSMSProvider(valid_config)
        
        # French mobile number
        assert provider._normalize_phone("0612345678") == "+33612345678"
        
        # Already international
        assert provider._normalize_phone("+33612345678") == "+33612345678"
        
        # With spaces and dashes
        assert provider._normalize_phone("06 12 34 56 78") == "+33612345678"
        assert provider._normalize_phone("06-12-34-56-78") == "+33612345678"

    def test_normalize_phone_international(self, valid_config):
        """Test international phone number normalization."""
        from services.notifications.providers.ovh_sms import OVHSMSProvider
        
        provider = OVHSMSProvider(valid_config)
        
        # Belgian number
        assert provider._normalize_phone("+32478123456") == "+32478123456"
        
        # Without + (assumes international)
        assert provider._normalize_phone("32478123456") == "+32478123456"

    def test_format_sms_text_sev1(self, valid_config):
        """Test SMS text formatting for SEV1."""
        from services.notifications.providers.ovh_sms import OVHSMSProvider
        
        provider = OVHSMSProvider(valid_config)
        
        message = {
            "title": "Database completely down affecting all users",
            "severity": "SEV1 - Critical",
            "service": "PostgreSQL",
        }
        
        text = provider._format_sms_text(message)
        
        assert "🔴" in text  # Red emoji for SEV1
        assert "SEV1" in text
        assert "PostgreSQL" in text
        assert len(text) <= 160  # Single SMS limit

    def test_format_sms_text_sev2(self, valid_config):
        """Test SMS text formatting for SEV2."""
        from services.notifications.providers.ovh_sms import OVHSMSProvider
        
        provider = OVHSMSProvider(valid_config)
        
        message = {
            "title": "Payment gateway degraded",
            "severity": "SEV2",
            "service": "Payments",
        }
        
        text = provider._format_sms_text(message)
        
        assert "🟠" in text  # Orange emoji for SEV2

    def test_format_sms_text_truncation(self, valid_config):
        """Test SMS text is truncated to fit limit."""
        from services.notifications.providers.ovh_sms import OVHSMSProvider
        
        provider = OVHSMSProvider(valid_config)
        
        long_title = "This is a very long incident title that exceeds the normal SMS length limit and should be truncated to ensure the message fits in a single SMS segment for cost efficiency"
        
        message = {
            "title": long_title,
            "severity": "SEV1",
            "service": "API",
        }
        
        text = provider._format_sms_text(message)
        
        assert len(text) <= 160

    def test_generate_signature(self, valid_config):
        """Test OVH signature generation."""
        from services.notifications.providers.ovh_sms import OVHSMSProvider
        
        provider = OVHSMSProvider(valid_config)
        
        signature = provider._generate_signature(
            method="POST",
            url="https://eu.api.ovh.com/1.0/sms/sms-test-1/jobs",
            body='{"receivers":["+33612345678"],"message":"Test"}',
            timestamp="1234567890",
        )
        
        # Signature should start with $1$ (OVH format)
        assert signature.startswith("$1$")
        # SHA1 produces 40 hex characters
        assert len(signature) == 44  # $1$ + 40 chars

    @patch("httpx.Client")
    def test_send_sms_success(self, mock_client_class, valid_config):
        """Test successful SMS sending."""
        from services.notifications.providers.ovh_sms import OVHSMSProvider
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ids": [12345]}
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        provider = OVHSMSProvider(valid_config)
        
        result = provider.send_sms(
            phone_number="+33612345678",
            message={"title": "Test alert", "severity": "SEV1"}
        )
        
        assert result is True
        mock_client.post.assert_called_once()

    @patch("httpx.Client")
    def test_send_sms_failure(self, mock_client_class, valid_config):
        """Test SMS sending failure handling."""
        from services.notifications.providers.ovh_sms import OVHSMSProvider
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Invalid credentials"
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        provider = OVHSMSProvider(valid_config)
        
        result = provider.send_sms(
            phone_number="+33612345678",
            message={"title": "Test"}
        )
        
        assert result is False

    @patch("httpx.Client")
    def test_send_batch(self, mock_client_class, valid_config):
        """Test batch SMS sending."""
        from services.notifications.providers.ovh_sms import OVHSMSProvider
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ids": [1, 2, 3]}
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        provider = OVHSMSProvider(valid_config)
        
        results = provider.send_batch(
            phone_numbers=["+33612345678", "+33698765432", "+32478123456"],
            message={"title": "Mass alert", "severity": "SEV1"}
        )
        
        assert all(results.values())
        assert len(results) == 3

    @patch("httpx.Client")
    def test_get_credits(self, mock_client_class, valid_config):
        """Test getting SMS credits."""
        from services.notifications.providers.ovh_sms import OVHSMSProvider
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"creditsLeft": 500}
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        provider = OVHSMSProvider(valid_config)
        
        credits = provider.get_credits()
        
        assert credits == 500

    @patch("httpx.Client")
    def test_check_connectivity(self, mock_client_class, valid_config):
        """Test connectivity check."""
        from services.notifications.providers.ovh_sms import OVHSMSProvider
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"creditsLeft": 100}
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        provider = OVHSMSProvider(valid_config)
        
        result = provider.check_connectivity()
        
        assert result is True


class TestOVHSMSProviderHeaders:
    """Test OVH API header generation."""

    @pytest.fixture
    def config(self):
        return MockNotificationProvider(
            name="OVH SMS",
            provider_type="ovh_sms",
            config={
                "application_key": "test-app-key",
                "application_secret": "test-secret",
                "consumer_key": "test-consumer",
                "service_name": "sms-test-1",
            }
        )

    @patch("time.time")
    @patch("httpx.Client")
    def test_headers_include_all_required(self, mock_client_class, mock_time, config):
        """Test all required OVH headers are included."""
        from services.notifications.providers.ovh_sms import OVHSMSProvider
        
        mock_time.return_value = 1234567890
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ids": [1]}
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        provider = OVHSMSProvider(config)
        provider.send_sms("+33612345678", {"title": "Test"})
        
        call_kwargs = mock_client.post.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        
        assert "X-Ovh-Application" in headers
        assert "X-Ovh-Consumer" in headers
        assert "X-Ovh-Timestamp" in headers
        assert "X-Ovh-Signature" in headers
        assert headers["X-Ovh-Application"] == "test-app-key"
