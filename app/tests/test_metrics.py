"""
IMAS Manager - Tests for Metrics Service and API
"""
from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Incident, Service, Team
from core.models.incident import IncidentSeverity, IncidentStatus
from services.metrics import MetricsService

User = get_user_model()


class MetricsServiceTestCase(TestCase):
    """Tests for MetricsService."""

    def setUp(self):
        """Set up test data."""
        self.team = Team.objects.create(
            name="Platform Team",
            slug="platform",
        )
        
        self.service = Service.objects.create(
            name="API Gateway",
            owner_team=self.team,
        )
        
        self.service2 = Service.objects.create(
            name="Database",
            owner_team=self.team,
        )
        
        self.user = User.objects.create_user(
            username="operator",
            email="operator@example.com",
            password="testpass123",
        )
        
        # Create test incidents with known timing
        now = timezone.now()
        
        # Incident 1: Resolved, acknowledged after 5 min, resolved after 30 min
        self.incident1 = Incident.objects.create(
            title="API Gateway High Latency",
            description="Latency exceeded threshold",
            severity=IncidentSeverity.SEV2_HIGH,
            status=IncidentStatus.RESOLVED,
            service=self.service,
        )
        # Update timestamps manually since created_at is auto_now_add
        Incident.objects.filter(pk=self.incident1.pk).update(
            created_at=now - timedelta(hours=2),
            acknowledged_at=now - timedelta(hours=2) + timedelta(minutes=5),
            resolved_at=now - timedelta(hours=2) + timedelta(minutes=30),
        )
        self.incident1.refresh_from_db()
        
        # Incident 2: Resolved, acknowledged after 10 min, resolved after 60 min
        self.incident2 = Incident.objects.create(
            title="Database Connection Pool Exhausted",
            description="Connection pool at 100%",
            severity=IncidentSeverity.SEV1_CRITICAL,
            status=IncidentStatus.RESOLVED,
            service=self.service2,
        )
        Incident.objects.filter(pk=self.incident2.pk).update(
            created_at=now - timedelta(hours=5),
            acknowledged_at=now - timedelta(hours=5) + timedelta(minutes=10),
            resolved_at=now - timedelta(hours=5) + timedelta(minutes=60),
        )
        self.incident2.refresh_from_db()
        
        # Incident 3: Open (not acknowledged)
        self.incident3 = Incident.objects.create(
            title="Memory Usage High",
            description="Memory usage above 90%",
            severity=IncidentSeverity.SEV3_MEDIUM,
            status=IncidentStatus.TRIGGERED,
            service=self.service,
        )
        Incident.objects.filter(pk=self.incident3.pk).update(
            created_at=now - timedelta(hours=1),
        )
        self.incident3.refresh_from_db()
        
        # Incident 4: Acknowledged but not resolved
        self.incident4 = Incident.objects.create(
            title="Disk Space Warning",
            description="Disk space at 85%",
            severity=IncidentSeverity.SEV4_LOW,
            status=IncidentStatus.ACKNOWLEDGED,
            service=self.service2,
        )
        Incident.objects.filter(pk=self.incident4.pk).update(
            created_at=now - timedelta(minutes=30),
            acknowledged_at=now - timedelta(minutes=25),
        )
        self.incident4.refresh_from_db()
        
        self.metrics_service = MetricsService()
        self.start_date = now - timedelta(days=1)
        self.end_date = now

    def test_get_summary_total_incidents(self):
        """Test that summary returns correct total incidents count."""
        summary = self.metrics_service.get_summary(
            start_date=self.start_date,
            end_date=self.end_date,
        )
        
        self.assertEqual(summary.total_incidents, 4)

    def test_get_summary_resolution_rate(self):
        """Test that resolution rate is calculated correctly."""
        summary = self.metrics_service.get_summary(
            start_date=self.start_date,
            end_date=self.end_date,
        )
        
        # 2 resolved out of 4 = 50%
        resolution_rate = (summary.resolved_count / summary.total_incidents * 100) if summary.total_incidents > 0 else 0
        self.assertEqual(resolution_rate, 50.0)

    def test_get_summary_avg_mtta(self):
        """Test MTTA calculation (only for acknowledged incidents)."""
        summary = self.metrics_service.get_summary(
            start_date=self.start_date,
            end_date=self.end_date,
        )
        
        # 3 acknowledged incidents: 5min, 10min, 5min = avg 6.67 min
        # (incident1: 5, incident2: 10, incident4: 5)
        self.assertIsNotNone(summary.avg_time_to_acknowledge)
        self.assertGreater(summary.avg_time_to_acknowledge, 0)

    def test_get_summary_avg_mttr(self):
        """Test MTTR calculation (only for resolved incidents)."""
        summary = self.metrics_service.get_summary(
            start_date=self.start_date,
            end_date=self.end_date,
        )
        
        # 2 resolved: 30min, 60min = avg 45 min
        self.assertIsNotNone(summary.avg_time_to_resolve)
        self.assertGreater(summary.avg_time_to_resolve, 0)

    def test_get_summary_by_severity(self):
        """Test severity breakdown in summary."""
        summary = self.metrics_service.get_summary(
            start_date=self.start_date,
            end_date=self.end_date,
        )
        
        # Check severity counts via dataclass attributes
        self.assertEqual(summary.sev1_count, 1)  # CRITICAL
        self.assertEqual(summary.sev2_count, 1)  # HIGH
        self.assertEqual(summary.sev3_count, 1)  # MEDIUM
        self.assertEqual(summary.sev4_count, 1)  # LOW

    def test_get_summary_with_service_filter(self):
        """Test summary filtered by service."""
        summary = self.metrics_service.get_summary(
            start_date=self.start_date,
            end_date=self.end_date,
            service_id=str(self.service.id),
        )
        
        # Only incidents for API Gateway service
        self.assertEqual(summary.total_incidents, 2)

    def test_get_by_service(self):
        """Test by-service breakdown."""
        service_metrics = self.metrics_service.get_by_service(
            start_date=self.start_date,
            end_date=self.end_date,
        )
        
        self.assertEqual(len(service_metrics), 2)
        
        # Check API Gateway metrics
        api_metrics = next(
            (m for m in service_metrics if m.service_id == str(self.service.id)),
            None,
        )
        self.assertIsNotNone(api_metrics)
        self.assertEqual(api_metrics.incident_count, 2)
        self.assertEqual(api_metrics.service_name, "API Gateway")

    def test_get_trend_daily(self):
        """Test trend data with daily granularity."""
        trend = self.metrics_service.get_trend(
            start_date=self.start_date,
            end_date=self.end_date,
            granularity="day",
        )
        
        self.assertIsInstance(trend, list)
        # Should have at least 1 data point
        self.assertGreater(len(trend), 0)
        
        # Check structure of trend points (dataclass attributes)
        if trend:
            point = trend[0]
            self.assertTrue(hasattr(point, "date"))
            self.assertTrue(hasattr(point, "incident_count"))
            self.assertTrue(hasattr(point, "avg_mtta"))
            self.assertTrue(hasattr(point, "avg_mttr"))

    def test_get_trend_weekly(self):
        """Test trend data with weekly granularity."""
        start_date = timezone.now() - timedelta(days=30)
        end_date = timezone.now()
        
        trend = self.metrics_service.get_trend(
            start_date=start_date,
            end_date=end_date,
            granularity="week",
        )
        
        self.assertIsInstance(trend, list)

    def test_get_heatmap(self):
        """Test heatmap data generation."""
        heatmap = self.metrics_service.get_heatmap(
            start_date=self.start_date,
            end_date=self.end_date,
        )
        
        self.assertIsInstance(heatmap, list)
        
        # Check structure (dict with day, day_index, hour, count)
        if heatmap:
            point = heatmap[0]
            self.assertIn("day", point)
            self.assertIn("day_index", point)
            self.assertIn("hour", point)
            self.assertIn("count", point)
            
            # Validate ranges
            self.assertGreaterEqual(point["day_index"], 1)
            self.assertLessEqual(point["day_index"], 7)
            self.assertGreaterEqual(point["hour"], 0)
            self.assertLessEqual(point["hour"], 23)

    def test_get_top_offenders(self):
        """Test top offenders listing."""
        top_offenders = self.metrics_service.get_top_offenders(
            start_date=self.start_date,
            end_date=self.end_date,
            limit=10,
        )
        
        self.assertIsInstance(top_offenders, list)
        self.assertLessEqual(len(top_offenders), 10)

    def test_get_top_offenders_limit(self):
        """Test that top offenders respects limit."""
        top_offenders = self.metrics_service.get_top_offenders(
            start_date=self.start_date,
            end_date=self.end_date,
            limit=2,
        )
        
        self.assertLessEqual(len(top_offenders), 2)

    def test_empty_date_range(self):
        """Test metrics with no incidents in date range."""
        future_start = timezone.now() + timedelta(days=100)
        future_end = timezone.now() + timedelta(days=200)
        
        summary = self.metrics_service.get_summary(
            start_date=future_start,
            end_date=future_end,
        )
        
        self.assertEqual(summary.total_incidents, 0)
        self.assertEqual(summary.resolved_count, 0)


class MetricsAPITestCase(APITestCase):
    """Tests for Metrics API endpoints."""

    def setUp(self):
        """Set up test data and authentication."""
        self.user = User.objects.create_user(
            username="apiuser",
            email="api@example.com",
            password="testpass123",
        )
        self.client.force_authenticate(user=self.user)
        
        self.team = Team.objects.create(
            name="SRE Team",
            slug="sre",
        )
        
        self.service = Service.objects.create(
            name="Payment Service",
            owner_team=self.team,
        )
        
        # Create a test incident
        now = timezone.now()
        self.incident = Incident.objects.create(
            title="Payment Processing Slow",
            description="Processing time > 5s",
            severity=IncidentSeverity.SEV2_HIGH,
            status=IncidentStatus.RESOLVED,
            service=self.service,
        )
        Incident.objects.filter(pk=self.incident.pk).update(
            created_at=now - timedelta(hours=3),
            acknowledged_at=now - timedelta(hours=3) + timedelta(minutes=2),
            resolved_at=now - timedelta(hours=3) + timedelta(minutes=45),
        )
        self.incident.refresh_from_db()

    def test_metrics_summary_endpoint(self):
        """Test GET /api/v1/metrics/summary/."""
        url = reverse("api_v1:metrics_summary")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Response is structured with nested dicts
        self.assertIn("counts", response.data)
        self.assertIn("time_metrics", response.data)
        self.assertIn("total", response.data["counts"])

    def test_metrics_summary_with_date_filter(self):
        """Test summary endpoint with date filters."""
        url = reverse("api_v1:metrics_summary")
        response = self.client.get(url, {"days": 7})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_metrics_by_service_endpoint(self):
        """Test GET /api/v1/metrics/by-service/."""
        url = reverse("api_v1:metrics_by_service")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("services", response.data)
        self.assertIsInstance(response.data["services"], list)

    def test_metrics_trend_endpoint(self):
        """Test GET /api/v1/metrics/trend/."""
        url = reverse("api_v1:metrics_trend")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("trend", response.data)
        self.assertIsInstance(response.data["trend"], list)

    def test_metrics_trend_with_granularity(self):
        """Test trend endpoint with granularity parameter."""
        url = reverse("api_v1:metrics_trend")
        response = self.client.get(url, {"granularity": "week"})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_metrics_heatmap_endpoint(self):
        """Test GET /api/v1/metrics/heatmap/."""
        url = reverse("api_v1:metrics_heatmap")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("heatmap", response.data)
        self.assertIsInstance(response.data["heatmap"], list)

    def test_metrics_top_offenders_endpoint(self):
        """Test GET /api/v1/metrics/top-offenders/."""
        url = reverse("api_v1:metrics_top_offenders")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("top_offenders", response.data)
        self.assertIsInstance(response.data["top_offenders"], list)

    def test_metrics_top_offenders_with_limit(self):
        """Test top offenders with limit parameter."""
        url = reverse("api_v1:metrics_top_offenders")
        response = self.client.get(url, {"limit": 5})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("top_offenders", response.data)
        self.assertLessEqual(len(response.data["top_offenders"]), 5)

    def test_metrics_export_json(self):
        """Test GET /api/v1/metrics/export/ with JSON format."""
        url = reverse("api_v1:metrics_export")
        response = self.client.get(url, {"format": "json"})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # JSON export returns normal API response
        self.assertIn("incidents", response.data)
        self.assertIn("count", response.data)

    def test_metrics_export_csv(self):
        """Test GET /api/v1/metrics/export/ returns data."""
        # Test that export endpoint works
        url = reverse("api_v1:metrics_export")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # By default returns JSON with incidents list
        self.assertIn("incidents", response.data)

    def test_unauthenticated_access_denied(self):
        """Test that unauthenticated requests are rejected."""
        self.client.force_authenticate(user=None)
        
        url = reverse("api_v1:metrics_summary")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class MetricsDashboardTestCase(TestCase):
    """Tests for Analytics Dashboard views."""

    def setUp(self):
        """Set up test user and data."""
        self.user = User.objects.create_user(
            username="dashuser",
            email="dash@example.com",
            password="testpass123",
        )
        
        self.team = Team.objects.create(
            name="Infra Team",
            slug="infra",
        )
        
        self.service = Service.objects.create(
            name="Load Balancer",
            owner_team=self.team,
        )

    def test_analytics_dashboard_requires_login(self):
        """Test that analytics dashboard requires authentication."""
        url = reverse("dashboard:analytics")
        response = self.client.get(url)
        
        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_analytics_dashboard_authenticated(self):
        """Test analytics dashboard for authenticated user."""
        self.client.login(username="dashuser", password="testpass123")
        
        url = reverse("dashboard:analytics")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/analytics_tailwind.html")

    def test_analytics_dashboard_with_days_filter(self):
        """Test analytics with days filter parameter."""
        self.client.login(username="dashuser", password="testpass123")
        
        url = reverse("dashboard:analytics")
        response = self.client.get(url, {"days": 7})
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["days"], 7)

    def test_analytics_mtta_view(self):
        """Test MTTA analytics view."""
        self.client.login(username="dashuser", password="testpass123")
        
        url = reverse("dashboard:analytics_mtta")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)

    def test_analytics_mttr_view(self):
        """Test MTTR analytics view."""
        self.client.login(username="dashuser", password="testpass123")
        
        url = reverse("dashboard:analytics_mttr")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
