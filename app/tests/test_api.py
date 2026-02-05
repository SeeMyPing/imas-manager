"""
IMAS Manager - API Tests

Tests for REST API endpoints.
"""
from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status

from core.choices import IncidentSeverity, IncidentStatus
from core.models import Incident


@pytest.mark.django_db
class TestHealthCheck:
    """Tests for health check endpoint."""

    def test_health_check(self, api_client):
        """Test health check returns 200."""
        response = api_client.get("/api/v1/health/")
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "healthy"
        assert response.data["service"] == "imas-manager"


@pytest.mark.django_db
class TestIncidentAPI:
    """Tests for Incident API endpoints."""

    def test_list_incidents_unauthenticated(self, api_client):
        """Test that unauthenticated requests are rejected."""
        response = api_client.get("/api/v1/incidents/")
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_incidents_authenticated(self, authenticated_client, incident):
        """Test listing incidents with authentication."""
        response = authenticated_client.get("/api/v1/incidents/")
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) >= 1

    def test_create_incident(self, authenticated_client, service):
        """Test creating an incident via API."""
        data = {
            "title": "API Test Incident",
            "description": "Created via API",
            "service": str(service.id),
            "severity": "SEV2_HIGH",
        }
        
        response = authenticated_client.post("/api/v1/incidents/", data)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["title"] == "API Test Incident"
        assert response.data["status"] == "TRIGGERED"

    def test_create_incident_by_service_name(self, authenticated_client, service):
        """Test creating an incident using service name instead of UUID."""
        data = {
            "title": "Incident by Service Name",
            "service_name": service.name,
            "severity": "SEV3_MEDIUM",
        }
        
        response = authenticated_client.post("/api/v1/incidents/", data)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["service"] == str(service.id)

    def test_create_incident_deduplication(self, authenticated_client, service):
        """Test that duplicate incidents are deduplicated."""
        # Create first incident
        data = {
            "title": "First Incident",
            "service": str(service.id),
            "severity": "SEV1_CRITICAL",
        }
        response1 = authenticated_client.post("/api/v1/incidents/", data)
        assert response1.status_code == status.HTTP_201_CREATED
        incident_id = response1.data["id"]
        
        # Try to create duplicate
        data["title"] = "Duplicate Incident"
        response2 = authenticated_client.post("/api/v1/incidents/", data)
        
        # Should return existing incident (200 OK, not 201 Created)
        assert response2.status_code == status.HTTP_200_OK
        assert response2.data["id"] == incident_id

    def test_get_incident_detail(self, authenticated_client, incident):
        """Test retrieving incident details."""
        response = authenticated_client.get(f"/api/v1/incidents/{incident.id}/")
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == str(incident.id)
        assert response.data["title"] == incident.title
        assert "events" in response.data

    def test_acknowledge_incident(self, authenticated_client, incident):
        """Test acknowledging an incident."""
        response = authenticated_client.post(
            f"/api/v1/incidents/{incident.id}/acknowledge/"
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "ACKNOWLEDGED"
        
        # Verify in database
        incident.refresh_from_db()
        assert incident.status == IncidentStatus.ACKNOWLEDGED
        assert incident.acknowledged_at is not None

    def test_acknowledge_already_acknowledged(self, authenticated_client, incident):
        """Test acknowledging an already acknowledged incident."""
        incident.status = IncidentStatus.ACKNOWLEDGED
        incident.save()
        
        response = authenticated_client.post(
            f"/api/v1/incidents/{incident.id}/acknowledge/"
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_resolve_incident(self, authenticated_client, incident):
        """Test resolving an incident."""
        response = authenticated_client.post(
            f"/api/v1/incidents/{incident.id}/resolve/",
            {"note": "Issue fixed by restarting service"},
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "RESOLVED"
        
        # Verify in database
        incident.refresh_from_db()
        assert incident.status == IncidentStatus.RESOLVED
        assert incident.resolved_at is not None

    def test_resolve_already_resolved(self, authenticated_client, incident):
        """Test resolving an already resolved incident."""
        incident.status = IncidentStatus.RESOLVED
        incident.save()
        
        response = authenticated_client.post(
            f"/api/v1/incidents/{incident.id}/resolve/"
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestServiceAPI:
    """Tests for Service API endpoints."""

    def test_list_services(self, authenticated_client, service):
        """Test listing services."""
        response = authenticated_client.get("/api/v1/services/")
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) >= 1


@pytest.mark.django_db
class TestTeamAPI:
    """Tests for Team API endpoints."""

    def test_list_teams(self, authenticated_client, team):
        """Test listing teams."""
        response = authenticated_client.get("/api/v1/teams/")
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) >= 1


@pytest.mark.django_db
class TestTokenAuthentication:
    """Tests for Token authentication endpoints."""

    def test_obtain_token(self, api_client, user):
        """Test obtaining a token."""
        response = api_client.post(
            "/api/token/obtain/",
            {"username": "testuser", "password": "testpass123"},
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert "token" in response.data
        assert response.data["username"] == "testuser"

    def test_obtain_token_invalid_credentials(self, api_client):
        """Test obtaining token with invalid credentials."""
        response = api_client.post(
            "/api/token/obtain/",
            {"username": "invalid", "password": "wrong"},
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_verify_token(self, authenticated_client, user):
        """Test verifying a valid token."""
        response = authenticated_client.get("/api/token/verify/")
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data["valid"] is True
        assert response.data["username"] == user.username

    def test_revoke_token(self, authenticated_client, user):
        """Test revoking a token."""
        response = authenticated_client.post("/api/token/revoke/")
        
        assert response.status_code == status.HTTP_200_OK
        
        # Token should no longer work
        response = authenticated_client.get("/api/v1/incidents/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_regenerate_token(self, authenticated_client, user):
        """Test regenerating a token."""
        # Get current token
        from rest_framework.authtoken.models import Token
        old_token = Token.objects.get(user=user).key
        
        response = authenticated_client.post("/api/token/regenerate/")
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data["token"] != old_token
