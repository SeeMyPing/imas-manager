"""
IMAS Manager - Google Drive Service

Handles LID (Lead Incident Document) creation via Google Drive API.

Configuration (via .env):
    GOOGLE_SERVICE_ACCOUNT_FILE: Path to service account JSON
    GOOGLE_LID_TEMPLATE_ID: Template document ID to copy
    GOOGLE_DRIVE_FOLDER_ID: Destination folder ID (optional)
    GOOGLE_DRIVE_DOMAIN: Domain for domain-wide reader access (optional)
"""
from __future__ import annotations

import json
import logging
from functools import cached_property
from typing import TYPE_CHECKING, Any

from django.conf import settings

if TYPE_CHECKING:
    from core.models import Incident

logger = logging.getLogger(__name__)

# API Scopes required
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",  # Create/edit own files
    "https://www.googleapis.com/auth/drive.readonly",  # Read template
]


class GDriveError(Exception):
    """Base exception for Google Drive operations."""

    pass


class GDriveConfigError(GDriveError):
    """Configuration error for Google Drive."""

    pass


class GDriveAPIError(GDriveError):
    """API error from Google Drive."""

    pass


class GDriveService:
    """
    Google Drive integration for LID document management.
    
    Creates incident documents from a template and manages permissions.
    Requires a Google Service Account with Drive API access.
    
    Usage:
        service = GDriveService()
        doc_url = service.create_lid_document(incident)
        
    Environment Variables:
        GOOGLE_SERVICE_ACCOUNT_FILE: Path to JSON credentials
        GOOGLE_LID_TEMPLATE_ID: ID of template Google Doc
        GOOGLE_DRIVE_FOLDER_ID: Target folder for created docs
        GOOGLE_DRIVE_DOMAIN: Domain for viewer permissions (optional)
    """

    def __init__(self) -> None:
        """Initialize the Google Drive service."""
        self._service = None
        self._docs_service = None

    @cached_property
    def _template_id(self) -> str | None:
        """Get the LID template document ID."""
        return getattr(settings, "GOOGLE_LID_TEMPLATE_ID", None)

    @cached_property
    def _folder_id(self) -> str | None:
        """Get the destination folder ID."""
        return getattr(settings, "GOOGLE_DRIVE_FOLDER_ID", None)

    @cached_property
    def _domain(self) -> str | None:
        """Get the domain for viewer permissions."""
        return getattr(settings, "GOOGLE_DRIVE_DOMAIN", None)

    @cached_property
    def _credentials_path(self) -> str | None:
        """Get the service account credentials path."""
        return getattr(settings, "GOOGLE_SERVICE_ACCOUNT_FILE", None)

    @cached_property
    def _credentials_json(self) -> dict | None:
        """Get service account credentials from JSON env var."""
        json_str = getattr(settings, "GOOGLE_SERVICE_ACCOUNT_JSON", None)
        if json_str:
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                logger.error("Invalid GOOGLE_SERVICE_ACCOUNT_JSON format")
        return None

    def _get_credentials(self):
        """
        Build credentials from service account.
        
        Supports both file path and JSON string configuration.
        
        Returns:
            Google OAuth2 credentials.
            
        Raises:
            GDriveConfigError: If credentials are not configured.
        """
        try:
            from google.oauth2 import service_account
        except ImportError as e:
            raise GDriveConfigError(
                "google-auth library not installed. "
                "Run: pip install google-auth google-auth-oauthlib"
            ) from e

        # Try JSON credentials first (for Docker/K8s secrets)
        if self._credentials_json:
            return service_account.Credentials.from_service_account_info(
                self._credentials_json,
                scopes=SCOPES,
            )

        # Fall back to file path
        if self._credentials_path:
            return service_account.Credentials.from_service_account_file(
                self._credentials_path,
                scopes=SCOPES,
            )

        raise GDriveConfigError(
            "Google Drive credentials not configured. "
            "Set GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_SERVICE_ACCOUNT_JSON"
        )

    def _get_drive_service(self):
        """
        Get or create the Google Drive API service.
        
        Returns:
            Google Drive API service (v3).
            
        Raises:
            GDriveConfigError: If credentials are not configured.
            GDriveAPIError: If API client creation fails.
        """
        if self._service is not None:
            return self._service

        try:
            from googleapiclient.discovery import build
            from googleapiclient.errors import Error as GoogleAPIError
        except ImportError as e:
            raise GDriveConfigError(
                "google-api-python-client not installed. "
                "Run: pip install google-api-python-client"
            ) from e

        try:
            credentials = self._get_credentials()
            self._service = build(
                "drive",
                "v3",
                credentials=credentials,
                cache_discovery=False,  # Avoid file cache issues
            )
            return self._service
        except GoogleAPIError as e:
            raise GDriveAPIError(f"Failed to create Drive API client: {e}") from e

    def _get_docs_service(self):
        """
        Get or create the Google Docs API service.
        
        Used for document content manipulation.
        
        Returns:
            Google Docs API service (v1).
        """
        if self._docs_service is not None:
            return self._docs_service

        try:
            from googleapiclient.discovery import build
        except ImportError:
            return None

        try:
            credentials = self._get_credentials()
            self._docs_service = build(
                "docs",
                "v1",
                credentials=credentials,
                cache_discovery=False,
            )
            return self._docs_service
        except Exception as e:
            logger.warning(f"Failed to create Docs API client: {e}")
            return None

    def is_configured(self) -> bool:
        """
        Check if the Google Drive service is properly configured.
        
        Returns:
            True if credentials are present (template is optional).
        """
        return bool(self._credentials_path or self._credentials_json)

    def has_template(self) -> bool:
        """Check if a LID template is configured."""
        return bool(self._template_id)

    def create_lid_document(self, incident: "Incident") -> str | None:
        """
        Create a LID document for an incident.
        
        If a template is configured, copies and populates it.
        Otherwise, creates a new document with standard LID structure.
        
        Args:
            incident: The incident to create a document for.
            
        Returns:
            URL of the created document, or None if creation failed.
            
        Raises:
            GDriveConfigError: If service is not configured.
            GDriveAPIError: If API call fails.
        """
        if not self.is_configured():
            logger.warning("Google Drive service not configured")
            return None

        # If no template, use the from-scratch method
        if not self._template_id:
            logger.info("No LID template configured, creating from scratch")
            return self.create_document_from_scratch(incident)

        # Build document title
        title_suffix = incident.title[:50] if incident.title else "Incident"
        doc_title = f"INC-{incident.short_id} | {title_suffix}"

        try:
            service = self._get_drive_service()

            # Build file metadata
            file_metadata: dict[str, Any] = {"name": doc_title}
            if self._folder_id:
                file_metadata["parents"] = [self._folder_id]

            # Copy the template document
            copied_file = (
                service.files()
                .copy(
                    fileId=self._template_id,
                    body=file_metadata,
                    supportsAllDrives=True,  # Support shared drives
                )
                .execute()
            )

            doc_id = copied_file.get("id")
            if not doc_id:
                logger.error("Document copy returned no ID")
                return None

            doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"

            # Populate document placeholders
            self._populate_document(doc_id, incident)

            # Set permissions
            self._set_permissions(doc_id, incident)

            logger.info(
                f"Created LID document for incident {incident.short_id}: {doc_url}"
            )
            return doc_url

        except GDriveError:
            raise
        except Exception as e:
            logger.exception(f"Failed to create LID document: {e}")
            raise GDriveAPIError(f"Document creation failed: {e}") from e

    def _populate_document(self, doc_id: str, incident: "Incident") -> None:
        """
        Replace placeholders in the document with incident data.
        
        Placeholder format: {{PLACEHOLDER_NAME}}
        
        Supported placeholders:
            {{INCIDENT_ID}} - Short ID (e.g., "ABC123")
            {{INCIDENT_TITLE}} - Incident title
            {{SEVERITY}} - Severity level
            {{STATUS}} - Current status
            {{SERVICE_NAME}} - Affected service name
            {{TEAM_NAME}} - Owner team name
            {{CREATED_AT}} - Creation timestamp
            {{DESCRIPTION}} - Incident description
            
        Args:
            doc_id: The Google Doc ID.
            incident: The incident with data to populate.
        """
        docs_service = self._get_docs_service()
        if not docs_service:
            logger.debug("Docs API not available, skipping placeholder replacement")
            return

        # Build replacement map
        team_name = ""
        if incident.service and incident.service.owner_team:
            team_name = incident.service.owner_team.name
            
        replacements = {
            "{{INCIDENT_ID}}": incident.short_id or "",
            "{{INCIDENT_TITLE}}": incident.title or "",
            "{{SEVERITY}}": incident.get_severity_display() if incident.severity else "",
            "{{STATUS}}": incident.get_status_display() if incident.status else "",
            "{{SERVICE_NAME}}": incident.service.name if incident.service else "",
            "{{TEAM_NAME}}": team_name,
            "{{CREATED_AT}}": (
                incident.created_at.strftime("%Y-%m-%d %H:%M UTC")
                if incident.created_at
                else ""
            ),
            "{{DESCRIPTION}}": incident.description or "",
            "{{LEAD_NAME}}": incident.lead.get_full_name() if incident.lead else "Unassigned",
            "{{LEAD_EMAIL}}": incident.lead.email if incident.lead else "",
        }

        # Build batch update requests
        requests = []
        for placeholder, value in replacements.items():
            requests.append(
                {
                    "replaceAllText": {
                        "containsText": {
                            "text": placeholder,
                            "matchCase": True,
                        },
                        "replaceText": str(value),
                    }
                }
            )

        if not requests:
            return

        try:
            docs_service.documents().batchUpdate(
                documentId=doc_id,
                body={"requests": requests},
            ).execute()
            logger.debug(f"Populated {len(requests)} placeholders in document {doc_id}")
        except Exception as e:
            logger.warning(f"Failed to populate document placeholders: {e}")
            # Don't raise - document is still usable without placeholders

    def _set_permissions(self, doc_id: str, incident: "Incident") -> None:
        """
        Set document permissions for incident stakeholders.
        
        Permission levels:
        - Writer: Incident lead (if email available)
        - Writer: Owner team members (if emails available)
        - Reader: Domain-wide (if GOOGLE_DRIVE_DOMAIN configured)
        
        Args:
            doc_id: Google Drive document ID.
            incident: The incident for permission context.
        """
        service = self._get_drive_service()
        permissions_api = service.permissions()

        # Collect emails for writer access
        writer_emails: set[str] = set()

        # Add incident lead if they have an email
        if incident.lead and hasattr(incident.lead, "email") and incident.lead.email:
            writer_emails.add(incident.lead.email)

        # Add owner team members if available
        team = incident.service.owner_team if incident.service else None
        if team:
            # If team has an email distribution list
            if hasattr(team, "email") and team.email:
                writer_emails.add(team.email)

        # Grant writer access to collected emails
        for email in writer_emails:
            try:
                permissions_api.create(
                    fileId=doc_id,
                    body={
                        "type": "user",
                        "role": "writer",
                        "emailAddress": email,
                    },
                    sendNotificationEmail=False,
                    supportsAllDrives=True,
                ).execute()
                logger.debug(f"Granted writer access to {email}")
            except Exception as e:
                logger.warning(f"Failed to grant writer access to {email}: {e}")

        # Grant domain-wide reader access if configured
        if self._domain:
            try:
                permissions_api.create(
                    fileId=doc_id,
                    body={
                        "type": "domain",
                        "role": "reader",
                        "domain": self._domain,
                    },
                    supportsAllDrives=True,
                ).execute()
                logger.debug(f"Granted domain reader access to {self._domain}")
            except Exception as e:
                logger.warning(f"Failed to grant domain access: {e}")

    def get_document_url(self, doc_id: str) -> str:
        """
        Get the edit URL for a Google Doc.
        
        Args:
            doc_id: The Google Doc ID.
            
        Returns:
            The document edit URL.
        """
        return f"https://docs.google.com/document/d/{doc_id}/edit"

    def get_document_metadata(self, doc_id: str) -> dict[str, Any] | None:
        """
        Get metadata for a Google Drive document.
        
        Args:
            doc_id: The Google Drive file ID.
            
        Returns:
            Document metadata dict, or None if not found.
        """
        try:
            service = self._get_drive_service()
            return (
                service.files()
                .get(
                    fileId=doc_id,
                    fields="id,name,mimeType,webViewLink,createdTime,modifiedTime",
                    supportsAllDrives=True,
                )
                .execute()
            )
        except Exception as e:
            logger.warning(f"Failed to get document metadata: {e}")
            return None

    def delete_document(self, doc_id: str) -> bool:
        """
        Delete a Google Drive document.
        
        Note: This permanently deletes the file, not trash.
        
        Args:
            doc_id: The Google Drive file ID.
            
        Returns:
            True if deleted successfully.
        """
        try:
            service = self._get_drive_service()
            service.files().delete(
                fileId=doc_id,
                supportsAllDrives=True,
            ).execute()
            logger.info(f"Deleted document {doc_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete document {doc_id}: {e}")
            return False

    def create_document_from_scratch(self, incident: "Incident") -> str | None:
        """
        Create a LID document without using a template.
        
        Fallback method when no template is configured.
        Creates a new Google Doc with pre-populated LID structure.
        
        Args:
            incident: The incident to create a document for.
            
        Returns:
            URL of the created document, or None if creation failed.
        """
        title_suffix = incident.title[:50] if incident.title else "Incident"
        doc_title = f"INC-{incident.short_id} | {title_suffix}"

        try:
            service = self._get_drive_service()

            # Create empty Google Doc
            file_metadata: dict[str, Any] = {
                "name": doc_title,
                "mimeType": "application/vnd.google-apps.document",
            }
            if self._folder_id:
                file_metadata["parents"] = [self._folder_id]

            created_file = (
                service.files()
                .create(
                    body=file_metadata,
                    supportsAllDrives=True,
                )
                .execute()
            )

            doc_id = created_file.get("id")
            if not doc_id:
                logger.error("Document creation returned no ID")
                return None

            doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"

            # Populate with LID structure
            self._populate_new_document(doc_id, incident)

            # Set permissions
            self._set_permissions(doc_id, incident)

            logger.info(
                f"Created LID document from scratch for {incident.short_id}: {doc_url}"
            )
            return doc_url

        except Exception as e:
            logger.exception(f"Failed to create LID document from scratch: {e}")
            return None

    def _populate_new_document(self, doc_id: str, incident: "Incident") -> None:
        """
        Populate a newly created document with LID structure.
        
        Inserts the standard LID template content into the document.
        
        Args:
            doc_id: The Google Doc ID.
            incident: The incident with data to populate.
        """
        docs_service = self._get_docs_service()
        if not docs_service:
            logger.debug("Docs API not available")
            return

        # Get team name
        team_name = ""
        if incident.service and incident.service.owner_team:
            team_name = incident.service.owner_team.name

        # Build document content
        lead_name = incident.lead.get_full_name() if incident.lead else "Unassigned"
        created_at = (
            incident.created_at.strftime("%Y-%m-%d %H:%M UTC")
            if incident.created_at
            else "N/A"
        )

        # Content to insert (in reverse order for insertText at index 1)
        content_sections = [
            "\n\n📋 POST-MORTEM\n" + "=" * 40 + "\n",
            "• Root Cause:\n\n• Contributing Factors:\n\n• Action Items:\n  - [ ] \n\n",
            
            "\n📊 TIMELINE\n" + "=" * 40 + "\n",
            f"• {created_at} - Incident created\n• \n\n",
            
            "\n🔧 RESOLUTION\n" + "=" * 40 + "\n",
            "• Actions Taken:\n\n• Workarounds Applied:\n\n",
            
            "\n📝 INVESTIGATION NOTES\n" + "=" * 40 + "\n",
            "• Initial Hypothesis:\n\n• Findings:\n\n",
            
            "\n📞 COMMUNICATION\n" + "=" * 40 + "\n",
            "• Stakeholders Notified:\n• External Communication:\n\n",
            
            "\n📌 INCIDENT DETAILS\n" + "=" * 40 + "\n",
            f"• ID: INC-{incident.short_id}\n",
            f"• Title: {incident.title}\n",
            f"• Severity: {incident.get_severity_display() if incident.severity else 'N/A'}\n",
            f"• Status: {incident.get_status_display() if incident.status else 'N/A'}\n",
            f"• Service: {incident.service.name if incident.service else 'N/A'}\n",
            f"• Team: {team_name or 'N/A'}\n",
            f"• Lead: {lead_name}\n",
            f"• Created: {created_at}\n\n",
            f"• Description:\n{incident.description or 'No description provided.'}\n",
            
            f"🚨 LEAD INCIDENT DOCUMENT (LID)\n" + "=" * 40 + "\n",
            f"INC-{incident.short_id} | {incident.title[:50] if incident.title else 'Incident'}\n\n",
        ]

        # Build insert requests (insert in reverse to maintain order)
        requests = []
        for content in reversed(content_sections):
            requests.append({
                "insertText": {
                    "location": {"index": 1},
                    "text": content,
                }
            })

        try:
            docs_service.documents().batchUpdate(
                documentId=doc_id,
                body={"requests": requests},
            ).execute()
            logger.debug(f"Populated new LID document {doc_id}")
        except Exception as e:
            logger.warning(f"Failed to populate new document: {e}")

    def update_incident_status(self, doc_id: str, incident: "Incident") -> bool:
        """
        Update the status section in an existing LID document.
        
        Useful for keeping the document in sync with incident state changes.
        
        Args:
            doc_id: Google Doc ID.
            incident: The incident with updated data.
            
        Returns:
            True if update succeeded.
        """
        docs_service = self._get_docs_service()
        if not docs_service:
            return False

        try:
            # Update status placeholder
            requests = [
                {
                    "replaceAllText": {
                        "containsText": {
                            "text": "{{STATUS}}",
                            "matchCase": True,
                        },
                        "replaceText": incident.get_status_display() or "",
                    }
                }
            ]

            docs_service.documents().batchUpdate(
                documentId=doc_id,
                body={"requests": requests},
            ).execute()

            return True
        except Exception as e:
            logger.warning(f"Failed to update document status: {e}")
            return False

    def add_timeline_entry(
        self,
        doc_id: str,
        timestamp: str,
        entry: str,
    ) -> bool:
        """
        Add a timeline entry to the LID document.
        
        Appends to the TIMELINE section of the document.
        
        Args:
            doc_id: Google Doc ID.
            timestamp: Timestamp string for the entry.
            entry: Description of the timeline event.
            
        Returns:
            True if entry was added successfully.
        """
        docs_service = self._get_docs_service()
        if not docs_service:
            return False

        try:
            # Find and append to timeline section
            # This is a simplified approach - in production you'd want
            # to find the exact location of the TIMELINE section
            
            # For now, we'll use search and insert after
            doc = docs_service.documents().get(documentId=doc_id).execute()
            content = doc.get("body", {}).get("content", [])

            # Find "TIMELINE" section
            timeline_index = None
            for element in content:
                if "paragraph" in element:
                    for text_run in element["paragraph"].get("elements", []):
                        text_content = text_run.get("textRun", {}).get("content", "")
                        if "TIMELINE" in text_content:
                            timeline_index = element.get("endIndex", 1)
                            break

            if timeline_index:
                entry_text = f"\n• {timestamp} - {entry}"
                requests = [
                    {
                        "insertText": {
                            "location": {"index": timeline_index},
                            "text": entry_text,
                        }
                    }
                ]

                docs_service.documents().batchUpdate(
                    documentId=doc_id,
                    body={"requests": requests},
                ).execute()

                logger.debug(f"Added timeline entry to document {doc_id}")
                return True

            logger.warning("TIMELINE section not found in document")
            return False

        except Exception as e:
            logger.warning(f"Failed to add timeline entry: {e}")
            return False


# Singleton instance for convenience
_gdrive_service: GDriveService | None = None


def get_gdrive_service() -> GDriveService:
    """
    Get the singleton GDriveService instance.
    
    Returns:
        Configured GDriveService instance.
    """
    global _gdrive_service
    if _gdrive_service is None:
        _gdrive_service = GDriveService()
    return _gdrive_service
