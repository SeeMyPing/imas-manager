"""
IMAS Manager - Webhook Tests

Tests for alert ingestion webhooks.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    """Create an API test client."""
    return APIClient()


@pytest.fixture
def service(db):
    """Create a test service."""
    from core.models import Service, Team
    
    team = Team.objects.create(name="SRE Team")
    return Service.objects.create(
        name="api-gateway",
        owner_team=team,
        criticality="TIER_1_CRITICAL",
    )


class TestAlertmanagerWebhook:
    """Tests for Prometheus Alertmanager webhook."""

    @pytest.fixture
    def alertmanager_payload(self):
        """Sample Alertmanager webhook payload."""
        return {
            "version": "4",
            "groupKey": "{}:{alertname=\"HighErrorRate\"}",
            "status": "firing",
            "receiver": "imas-webhook",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "HighErrorRate",
                        "severity": "critical",
                        "service": "api-gateway",
                        "instance": "api-gateway:8080",
                    },
                    "annotations": {
                        "summary": "High error rate on API Gateway",
                        "description": "Error rate is above 5% for 5 minutes",
                    },
                    "startsAt": "2024-01-01T12:00:00Z",
                    "endsAt": "0001-01-01T00:00:00Z",
                    "generatorURL": "http://prometheus:9090/graph?...",
                }
            ],
        }

    @pytest.mark.django_db
    def test_alertmanager_webhook_creates_incident(
        self, api_client, alertmanager_payload, service
    ):
        """Test that Alertmanager webhook creates an incident."""
        url = reverse("api_v1:webhook_alertmanager")
        
        with patch("services.alerting.alert_service._trigger_notifications"):
            response = api_client.post(
                url,
                data=alertmanager_payload,
                format="json",
            )
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "ok"
        assert response.data["processed"] == 1
        
        # Check incident was created
        from core.models import Incident
        incident = Incident.objects.first()
        assert incident is not None
        assert "HighErrorRate" in incident.title or "High error rate" in incident.title
        assert incident.severity == "SEV1_CRITICAL"

    @pytest.mark.django_db
    def test_alertmanager_resolved_alert(self, api_client, alertmanager_payload):
        """Test handling of resolved alerts."""
        url = reverse("api_v1:webhook_alertmanager")
        
        # First fire the alert
        with patch("services.alerting.alert_service._trigger_notifications"):
            api_client.post(url, data=alertmanager_payload, format="json")
        
        # Now resolve it
        alertmanager_payload["status"] = "resolved"
        alertmanager_payload["alerts"][0]["status"] = "resolved"
        
        response = api_client.post(url, data=alertmanager_payload, format="json")
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"][0]["action"] == "resolved"

    @pytest.mark.django_db
    def test_alertmanager_deduplication(self, api_client, alertmanager_payload):
        """Test that duplicate alerts are suppressed."""
        url = reverse("api_v1:webhook_alertmanager")
        
        with patch("services.alerting.alert_service._trigger_notifications"):
            # First alert
            response1 = api_client.post(url, data=alertmanager_payload, format="json")
            assert response1.data["results"][0]["action"] == "created"
            
            # Same alert again (should be suppressed)
            response2 = api_client.post(url, data=alertmanager_payload, format="json")
            assert response2.data["results"][0]["action"] == "suppressed"

    @pytest.mark.django_db
    def test_alertmanager_multiple_alerts(self, api_client):
        """Test handling multiple alerts in single webhook."""
        url = reverse("api_v1:webhook_alertmanager")
        
        payload = {
            "version": "4",
            "status": "firing",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {"alertname": "Alert1", "severity": "warning"},
                    "annotations": {"summary": "First alert"},
                },
                {
                    "status": "firing",
                    "labels": {"alertname": "Alert2", "severity": "critical"},
                    "annotations": {"summary": "Second alert"},
                },
            ],
        }
        
        with patch("services.alerting.alert_service._trigger_notifications"):
            response = api_client.post(url, data=payload, format="json")
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data["processed"] == 2


class TestDatadogWebhook:
    """Tests for Datadog webhook."""

    @pytest.fixture
    def datadog_payload(self):
        """Sample Datadog webhook payload."""
        return {
            "id": "123456789",
            "title": "[Triggered] High CPU Usage on web-01",
            "body": "CPU usage has exceeded 90% for 10 minutes",
            "priority": "normal",
            "tags": "env:production,service:web-app,team:sre",
            "alert_id": "1234",
            "alert_type": "error",
            "alert_status": "Triggered",
            "alert_title": "High CPU Usage",
            "hostname": "web-01",
            "url": "https://app.datadoghq.com/monitors/1234",
            "date": 1704110400,
        }

    @pytest.mark.django_db
    def test_datadog_webhook_creates_incident(self, api_client, datadog_payload):
        """Test that Datadog webhook creates an incident."""
        url = reverse("api_v1:webhook_datadog")
        
        with patch("services.alerting.alert_service._trigger_notifications"):
            response = api_client.post(url, data=datadog_payload, format="json")
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "ok"
        
        from core.models import Incident
        incident = Incident.objects.first()
        assert incident is not None
        assert "High CPU Usage" in incident.title

    @pytest.mark.django_db
    def test_datadog_recovered_alert(self, api_client, datadog_payload):
        """Test handling of recovered Datadog alerts."""
        url = reverse("api_v1:webhook_datadog")
        
        # First trigger
        with patch("services.alerting.alert_service._trigger_notifications"):
            api_client.post(url, data=datadog_payload, format="json")
        
        # Now recover
        datadog_payload["alert_status"] = "Recovered"
        datadog_payload["title"] = "[Recovered] High CPU Usage on web-01"
        
        response = api_client.post(url, data=datadog_payload, format="json")
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"][0]["action"] == "resolved"

    @pytest.mark.django_db
    def test_datadog_tags_parsing(self, api_client, datadog_payload):
        """Test that Datadog tags are properly parsed."""
        url = reverse("api_v1:webhook_datadog")
        
        with patch("services.alerting.alert_service._trigger_notifications"):
            response = api_client.post(url, data=datadog_payload, format="json")
        
        from core.models import AlertFingerprint
        fingerprint = AlertFingerprint.objects.first()
        
        assert fingerprint is not None
        assert fingerprint.labels.get("env") == "production"
        assert fingerprint.labels.get("service") == "web-app"


class TestGrafanaWebhook:
    """Tests for Grafana webhook."""

    @pytest.fixture
    def grafana_unified_payload(self):
        """Sample Grafana unified alerting payload."""
        return {
            "receiver": "imas-webhook",
            "status": "firing",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "HighMemoryUsage",
                        "severity": "warning",
                        "grafana_folder": "Infrastructure",
                    },
                    "annotations": {
                        "summary": "Memory usage is high",
                        "description": "Memory usage exceeded 85%",
                    },
                    "startsAt": "2024-01-01T12:00:00Z",
                    "generatorURL": "http://grafana:3000/alerting/list",
                    "dashboardURL": "http://grafana:3000/d/abc123",
                }
            ],
            "commonLabels": {"team": "sre"},
            "commonAnnotations": {},
            "externalURL": "http://grafana:3000",
        }

    @pytest.fixture
    def grafana_legacy_payload(self):
        """Sample Grafana legacy alerting payload."""
        return {
            "title": "[Alerting] Memory Alert",
            "ruleId": 42,
            "ruleName": "High Memory Alert",
            "ruleUrl": "http://grafana:3000/alerting/42",
            "state": "alerting",
            "message": "Memory usage is above threshold",
            "evalMatches": [
                {"metric": "memory_percent", "value": 92.5}
            ],
        }

    @pytest.mark.django_db
    def test_grafana_unified_webhook(self, api_client, grafana_unified_payload):
        """Test Grafana unified alerting webhook."""
        url = reverse("api_v1:webhook_grafana")
        
        with patch("services.alerting.alert_service._trigger_notifications"):
            response = api_client.post(
                url, data=grafana_unified_payload, format="json"
            )
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data["processed"] == 1
        
        from core.models import Incident
        incident = Incident.objects.first()
        assert incident is not None
        assert "HighMemoryUsage" in incident.title or "Memory" in incident.title

    @pytest.mark.django_db
    def test_grafana_legacy_webhook(self, api_client, grafana_legacy_payload):
        """Test Grafana legacy alerting webhook."""
        url = reverse("api_v1:webhook_grafana")
        
        with patch("services.alerting.alert_service._trigger_notifications"):
            response = api_client.post(
                url, data=grafana_legacy_payload, format="json"
            )
        
        assert response.status_code == status.HTTP_200_OK
        
        from core.models import AlertFingerprint
        fingerprint = AlertFingerprint.objects.first()
        assert fingerprint is not None
        assert fingerprint.alert_name == "High Memory Alert"

    @pytest.mark.django_db
    def test_grafana_ok_state_resolves(self, api_client, grafana_legacy_payload):
        """Test that Grafana 'ok' state resolves alert."""
        url = reverse("api_v1:webhook_grafana")
        
        # First fire
        with patch("services.alerting.alert_service._trigger_notifications"):
            api_client.post(url, data=grafana_legacy_payload, format="json")
        
        # Now resolve
        grafana_legacy_payload["state"] = "ok"
        response = api_client.post(url, data=grafana_legacy_payload, format="json")
        
        assert response.data["results"][0]["action"] == "resolved"


class TestCustomWebhook:
    """Tests for custom/generic webhook."""

    @pytest.fixture
    def custom_payload(self):
        """Sample custom webhook payload."""
        return {
            "alert_name": "CustomAlert",
            "status": "firing",
            "severity": "high",
            "title": "Custom monitoring alert",
            "description": "Something went wrong",
            "labels": {
                "environment": "staging",
                "component": "database",
            },
            "url": "https://monitoring.example.com/alert/123",
        }

    @pytest.mark.django_db
    def test_custom_webhook(self, api_client, custom_payload):
        """Test custom webhook handling."""
        url = reverse("api_v1:webhook_custom")
        
        with patch("services.alerting.alert_service._trigger_notifications"):
            response = api_client.post(url, data=custom_payload, format="json")
        
        assert response.status_code == status.HTTP_200_OK
        
        from core.models import Incident
        incident = Incident.objects.first()
        assert incident is not None
        assert incident.severity == "SEV2_HIGH"

    @pytest.mark.django_db
    def test_custom_webhook_array(self, api_client):
        """Test custom webhook with array of alerts."""
        url = reverse("api_v1:webhook_custom")
        
        payload = [
            {"alert_name": "Alert1", "status": "firing", "severity": "low"},
            {"alert_name": "Alert2", "status": "firing", "severity": "medium"},
        ]
        
        with patch("services.alerting.alert_service._trigger_notifications"):
            response = api_client.post(url, data=payload, format="json")
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data["processed"] == 2


class TestAlertFingerprint:
    """Tests for AlertFingerprint model."""

    @pytest.mark.django_db
    def test_compute_fingerprint_stable(self):
        """Test that fingerprint is stable for same inputs."""
        from core.models import AlertFingerprint
        
        fp1 = AlertFingerprint.compute_fingerprint(
            "TestAlert",
            {"env": "prod", "host": "web-01"},
            "ALERTMANAGER",
        )
        fp2 = AlertFingerprint.compute_fingerprint(
            "TestAlert",
            {"host": "web-01", "env": "prod"},  # Different order
            "ALERTMANAGER",
        )
        
        assert fp1 == fp2

    @pytest.mark.django_db
    def test_compute_fingerprint_different(self):
        """Test that different inputs produce different fingerprints."""
        from core.models import AlertFingerprint
        
        fp1 = AlertFingerprint.compute_fingerprint(
            "TestAlert",
            {"env": "prod"},
            "ALERTMANAGER",
        )
        fp2 = AlertFingerprint.compute_fingerprint(
            "TestAlert",
            {"env": "staging"},
            "ALERTMANAGER",
        )
        
        assert fp1 != fp2


class TestAlertRule:
    """Tests for AlertRule model."""

    @pytest.fixture
    def alert_rule(self, db, service):
        """Create a test alert rule."""
        from core.models import AlertRule
        
        return AlertRule.objects.create(
            name="API Gateway Alerts",
            source="ALERTMANAGER",
            alert_name_pattern=".*Error.*",
            label_matchers={"service": "api-gateway"},
            target_service=service,
            severity_mapping={
                "severity": {
                    "critical": "SEV1_CRITICAL",
                    "warning": "SEV3_MEDIUM",
                }
            },
            default_severity="SEV3_MEDIUM",
        )

    @pytest.mark.django_db
    def test_rule_matches_alert(self, alert_rule):
        """Test alert rule matching."""
        assert alert_rule.matches_alert(
            "HighErrorRate",
            {"service": "api-gateway"},
            "ALERTMANAGER",
        )
        
        # Wrong source
        assert not alert_rule.matches_alert(
            "HighErrorRate",
            {"service": "api-gateway"},
            "DATADOG",
        )
        
        # Wrong service label
        assert not alert_rule.matches_alert(
            "HighErrorRate",
            {"service": "other-service"},
            "ALERTMANAGER",
        )

    @pytest.mark.django_db
    def test_rule_severity_mapping(self, alert_rule):
        """Test severity mapping from labels."""
        assert alert_rule.get_severity({"severity": "critical"}) == "SEV1_CRITICAL"
        assert alert_rule.get_severity({"severity": "warning"}) == "SEV3_MEDIUM"
        assert alert_rule.get_severity({"severity": "unknown"}) == "SEV3_MEDIUM"  # Default
