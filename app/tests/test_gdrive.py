"""
IMAS Manager - Google Drive Integration Tests

Tests for GDriveService LID document creation.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from integrations.gdrive import (
    GDriveAPIError,
    GDriveConfigError,
    GDriveService,
    get_gdrive_service,
)


@pytest.fixture
def gdrive_service():
    """Create a fresh GDriveService instance."""
    return GDriveService()


@pytest.fixture
def mock_incident():
    """Create a mock incident for testing."""
    incident = MagicMock()
    incident.id = "550e8400-e29b-41d4-a716-446655440000"
    incident.short_id = "ABC123"
    incident.title = "Database connection timeout"
    incident.description = "Users experiencing slow database queries"
    incident.severity = "P1"
    incident.status = "INVESTIGATING"
    incident.get_severity_display.return_value = "P1 - Critical"
    incident.get_status_display.return_value = "Investigating"
    incident.created_at = MagicMock()
    incident.created_at.strftime.return_value = "2024-01-15 10:30 UTC"
    
    # Service and team
    incident.service = MagicMock()
    incident.service.name = "Payment API"
    incident.service.owner_team = MagicMock()
    incident.service.owner_team.name = "Platform Team"
    incident.service.owner_team.email = "platform-team@example.com"
    
    # Lead
    incident.lead = MagicMock()
    incident.lead.email = "lead@example.com"
    incident.lead.get_full_name.return_value = "John Doe"
    
    return incident


class TestGDriveServiceConfiguration:
    """Tests for GDriveService configuration."""

    def test_is_configured_returns_false_without_credentials(self, gdrive_service):
        """Test is_configured returns False when no credentials."""
        with patch.object(gdrive_service, "_credentials_path", None):
            with patch.object(gdrive_service, "_credentials_json", None):
                assert gdrive_service.is_configured() is False

    def test_is_configured_returns_true_with_file_path(self, gdrive_service):
        """Test is_configured returns True with file path."""
        with patch.object(gdrive_service, "_credentials_path", "/path/to/creds.json"):
            assert gdrive_service.is_configured() is True

    def test_is_configured_returns_true_with_json(self, gdrive_service):
        """Test is_configured returns True with JSON credentials."""
        with patch.object(gdrive_service, "_credentials_json", {"type": "service_account"}):
            with patch.object(gdrive_service, "_credentials_path", None):
                assert gdrive_service.is_configured() is True

    def test_has_template_returns_false_without_template(self, gdrive_service):
        """Test has_template returns False without template ID."""
        with patch.object(gdrive_service, "_template_id", None):
            assert gdrive_service.has_template() is False

    def test_has_template_returns_true_with_template(self, gdrive_service):
        """Test has_template returns True with template ID."""
        with patch.object(gdrive_service, "_template_id", "template-id"):
            assert gdrive_service.has_template() is True


class TestGDriveServiceCredentials:
    """Tests for credential handling."""

    def test_get_credentials_raises_without_config(self, gdrive_service):
        """Test _get_credentials raises GDriveConfigError without config."""
        with patch.object(gdrive_service, "_credentials_path", None):
            with patch.object(gdrive_service, "_credentials_json", None):
                with pytest.raises(GDriveConfigError) as exc_info:
                    gdrive_service._get_credentials()
                # Could be "not configured" or "not installed" depending on environment
                assert "not" in str(exc_info.value).lower()

    def test_get_credentials_raises_without_library(self, gdrive_service):
        """Test _get_credentials raises when google-auth not installed."""
        with patch.object(gdrive_service, "_credentials_path", "/path/to/creds.json"):
            with patch.dict("sys.modules", {"google.oauth2": None}):
                with patch("builtins.__import__", side_effect=ImportError):
                    with pytest.raises(GDriveConfigError) as exc_info:
                        gdrive_service._get_credentials()
                    assert "not installed" in str(exc_info.value)


class TestGDriveServiceDocumentCreation:
    """Tests for document creation."""

    def test_create_lid_document_falls_back_to_scratch_without_template(
        self, gdrive_service, mock_incident
    ):
        """Test create_lid_document falls back to from_scratch without template ID."""
        with patch.object(gdrive_service, "_template_id", None):
            with patch.object(gdrive_service, "is_configured", return_value=True):
                with patch.object(
                    gdrive_service, "create_document_from_scratch", return_value="http://doc"
                ) as mock_scratch:
                    result = gdrive_service.create_lid_document(mock_incident)
                    mock_scratch.assert_called_once_with(mock_incident)
                    assert result == "http://doc"

    def test_create_lid_document_returns_none_when_not_configured(
        self, gdrive_service, mock_incident
    ):
        """Test create_lid_document returns None when not fully configured."""
        with patch.object(gdrive_service, "is_configured", return_value=False):
            result = gdrive_service.create_lid_document(mock_incident)
            assert result is None

    @patch("integrations.gdrive.GDriveService._get_drive_service")
    def test_create_lid_document_success(
        self, mock_get_service, gdrive_service, mock_incident
    ):
        """Test successful document creation."""
        # Setup mock
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        
        mock_service.files.return_value.copy.return_value.execute.return_value = {
            "id": "new-doc-id-123"
        }
        
        with patch.object(gdrive_service, "_template_id", "template-id"):
            with patch.object(gdrive_service, "_folder_id", "folder-id"):
                with patch.object(gdrive_service, "is_configured", return_value=True):
                    with patch.object(gdrive_service, "_populate_document"):
                        with patch.object(gdrive_service, "_set_permissions"):
                            result = gdrive_service.create_lid_document(mock_incident)
        
        assert result == "https://docs.google.com/document/d/new-doc-id-123/edit"
        
        # Verify copy was called with correct arguments
        mock_service.files.return_value.copy.assert_called_once()
        call_kwargs = mock_service.files.return_value.copy.call_args
        assert call_kwargs.kwargs["fileId"] == "template-id"
        assert "INC-ABC123" in call_kwargs.kwargs["body"]["name"]

    @patch("integrations.gdrive.GDriveService._get_drive_service")
    def test_create_lid_document_handles_api_error(
        self, mock_get_service, gdrive_service, mock_incident
    ):
        """Test document creation handles API errors."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.files.return_value.copy.return_value.execute.side_effect = (
            Exception("API Error")
        )
        
        with patch.object(gdrive_service, "_template_id", "template-id"):
            with patch.object(gdrive_service, "is_configured", return_value=True):
                with pytest.raises(GDriveAPIError):
                    gdrive_service.create_lid_document(mock_incident)


class TestGDriveServiceDocumentPopulation:
    """Tests for document placeholder population."""

    @patch("integrations.gdrive.GDriveService._get_docs_service")
    def test_populate_document_replaces_placeholders(
        self, mock_get_docs, gdrive_service, mock_incident
    ):
        """Test _populate_document replaces all placeholders."""
        mock_docs = MagicMock()
        mock_get_docs.return_value = mock_docs
        
        gdrive_service._populate_document("doc-id", mock_incident)
        
        # Verify batchUpdate was called
        mock_docs.documents.return_value.batchUpdate.assert_called_once()
        call_args = mock_docs.documents.return_value.batchUpdate.call_args
        
        # Check that requests contain expected placeholders
        requests = call_args.kwargs["body"]["requests"]
        placeholders = [r["replaceAllText"]["containsText"]["text"] for r in requests]
        
        assert "{{INCIDENT_ID}}" in placeholders
        assert "{{INCIDENT_TITLE}}" in placeholders
        assert "{{SEVERITY}}" in placeholders
        assert "{{STATUS}}" in placeholders

    @patch("integrations.gdrive.GDriveService._get_docs_service")
    def test_populate_document_skips_without_docs_service(
        self, mock_get_docs, gdrive_service, mock_incident
    ):
        """Test _populate_document gracefully skips if Docs API unavailable."""
        mock_get_docs.return_value = None
        
        # Should not raise
        gdrive_service._populate_document("doc-id", mock_incident)


class TestGDriveServicePermissions:
    """Tests for permission management."""

    @patch("integrations.gdrive.GDriveService._get_drive_service")
    def test_set_permissions_grants_writer_to_lead(
        self, mock_get_service, gdrive_service, mock_incident
    ):
        """Test _set_permissions grants writer access to incident lead."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        
        with patch.object(gdrive_service, "_domain", None):
            gdrive_service._set_permissions("doc-id", mock_incident)
        
        # Verify permission was created for lead
        calls = mock_service.permissions.return_value.create.call_args_list
        emails = [
            c.kwargs["body"]["emailAddress"]
            for c in calls
            if c.kwargs["body"].get("type") == "user"
        ]
        assert "lead@example.com" in emails

    @patch("integrations.gdrive.GDriveService._get_drive_service")
    def test_set_permissions_grants_domain_reader(
        self, mock_get_service, gdrive_service, mock_incident
    ):
        """Test _set_permissions grants domain-wide reader access."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        
        with patch.object(gdrive_service, "_domain", "example.com"):
            gdrive_service._set_permissions("doc-id", mock_incident)
        
        # Verify domain permission was created
        calls = mock_service.permissions.return_value.create.call_args_list
        domains = [
            c.kwargs["body"]["domain"]
            for c in calls
            if c.kwargs["body"].get("type") == "domain"
        ]
        assert "example.com" in domains


class TestGDriveServiceUtilities:
    """Tests for utility methods."""

    def test_get_document_url(self, gdrive_service):
        """Test get_document_url returns correct URL."""
        url = gdrive_service.get_document_url("abc123")
        assert url == "https://docs.google.com/document/d/abc123/edit"

    @patch("integrations.gdrive.GDriveService._get_drive_service")
    def test_get_document_metadata(self, mock_get_service, gdrive_service):
        """Test get_document_metadata returns file info."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.files.return_value.get.return_value.execute.return_value = {
            "id": "doc-id",
            "name": "Test Document",
            "mimeType": "application/vnd.google-apps.document",
        }
        
        result = gdrive_service.get_document_metadata("doc-id")
        
        assert result["id"] == "doc-id"
        assert result["name"] == "Test Document"

    @patch("integrations.gdrive.GDriveService._get_drive_service")
    def test_delete_document_success(self, mock_get_service, gdrive_service):
        """Test delete_document returns True on success."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        
        result = gdrive_service.delete_document("doc-id")
        
        assert result is True
        mock_service.files.return_value.delete.assert_called_once()

    @patch("integrations.gdrive.GDriveService._get_drive_service")
    def test_delete_document_handles_error(self, mock_get_service, gdrive_service):
        """Test delete_document returns False on error."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.files.return_value.delete.return_value.execute.side_effect = (
            Exception("Not found")
        )
        
        result = gdrive_service.delete_document("doc-id")
        
        assert result is False


class TestGDriveServiceSingleton:
    """Tests for singleton pattern."""

    def test_get_gdrive_service_returns_instance(self):
        """Test get_gdrive_service returns a GDriveService instance."""
        # Reset singleton
        import integrations.gdrive as gdrive_module
        gdrive_module._gdrive_service = None
        
        service = get_gdrive_service()
        
        assert isinstance(service, GDriveService)

    def test_get_gdrive_service_returns_same_instance(self):
        """Test get_gdrive_service returns the same instance."""
        service1 = get_gdrive_service()
        service2 = get_gdrive_service()
        
        assert service1 is service2
