"""
IMAS Manager - Dashboard Tests

Tests for dashboard views and forms.
"""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.choices import IncidentSeverity, IncidentStatus
from core.models import (
    ImpactScope,
    Incident,
    IncidentEvent,
    Service,
    Team,
)
from dashboard.forms import IncidentCreateForm, IncidentNoteForm, IncidentResolveForm

User = get_user_model()


class DashboardTestMixin:
    """Mixin with common setup for dashboard tests."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        cls.team = Team.objects.create(
            name="Test Team"
        )
        cls.service = Service.objects.create(
            name="Test Service",
            owner_team=cls.team,
            is_active=True
        )
        cls.impact_scope = ImpactScope.objects.create(
            name="Legal",
            is_active=True
        )

    def setUp(self):
        """Log in the test user."""
        self.client = Client()
        self.client.login(username="testuser", password="testpass123")


class TestDashboardHomeView(DashboardTestMixin, TestCase):
    """Tests for dashboard home view."""

    def test_home_view_requires_login(self):
        """Test home view requires authentication."""
        self.client.logout()
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_home_view_renders(self):
        """Test home view renders successfully."""
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/home_tailwind.html")

    def test_home_view_context_contains_kpis(self):
        """Test home view context contains KPI data."""
        response = self.client.get(reverse("dashboard:home"))
        
        self.assertIn("active_count", response.context)
        self.assertIn("critical_count", response.context)
        self.assertIn("resolved_count_30d", response.context)
        self.assertIn("avg_mttr_hours", response.context)

    def test_home_view_shows_active_incidents(self):
        """Test home view shows active incidents."""
        incident = Incident.objects.create(
            title="Active incident for home",
            service=self.service,
            severity=IncidentSeverity.SEV1_CRITICAL,
            status=IncidentStatus.TRIGGERED,
            lead=self.user
        )
        
        response = self.client.get(reverse("dashboard:home"))
        
        self.assertIn(incident, response.context["active_incidents"])
        self.assertGreaterEqual(response.context["critical_count"], 1)


class TestIncidentListView(DashboardTestMixin, TestCase):
    """Tests for incident list view."""

    def test_list_view_renders(self):
        """Test incident list view renders."""
        response = self.client.get(reverse("dashboard:incident_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/incidents/list_tailwind.html")

    def test_list_view_paginates(self):
        """Test incident list is paginated."""
        # Create 25 incidents
        for i in range(25):
            Incident.objects.create(
                title=f"Incident {i} for pagination test",
                service=self.service,
                severity=IncidentSeverity.SEV3_MEDIUM,
                status=IncidentStatus.RESOLVED,
                lead=self.user,
                resolved_at=timezone.now()
            )
        
        response = self.client.get(reverse("dashboard:incident_list"))
        self.assertTrue(response.context["is_paginated"])
        self.assertEqual(len(response.context["incidents"]), 20)

    def test_list_view_filters_by_status(self):
        """Test list view filters by status."""
        triggered = Incident.objects.create(
            title="Triggered incident for filter test",
            service=self.service,
            severity=IncidentSeverity.SEV3_MEDIUM,
            status=IncidentStatus.TRIGGERED,
            lead=self.user
        )
        resolved = Incident.objects.create(
            title="Resolved incident for filter test",
            service=self.service,
            severity=IncidentSeverity.SEV3_MEDIUM,
            status=IncidentStatus.RESOLVED,
            lead=self.user,
            resolved_at=timezone.now()
        )
        
        response = self.client.get(
            reverse("dashboard:incident_list"),
            {"status": IncidentStatus.TRIGGERED}
        )
        
        incidents = list(response.context["incidents"])
        self.assertIn(triggered, incidents)
        self.assertNotIn(resolved, incidents)

    def test_list_view_filters_by_severity(self):
        """Test list view filters by severity."""
        sev1 = Incident.objects.create(
            title="Critical incident for severity filter",
            service=self.service,
            severity=IncidentSeverity.SEV1_CRITICAL,
            status=IncidentStatus.TRIGGERED,
            lead=self.user
        )
        sev4 = Incident.objects.create(
            title="Low incident for severity filter",
            service=self.service,
            severity=IncidentSeverity.SEV4_LOW,
            status=IncidentStatus.TRIGGERED,
            lead=self.user
        )
        
        response = self.client.get(
            reverse("dashboard:incident_list"),
            {"severity": IncidentSeverity.SEV1_CRITICAL}
        )
        
        incidents = list(response.context["incidents"])
        self.assertIn(sev1, incidents)
        self.assertNotIn(sev4, incidents)

    def test_list_view_search(self):
        """Test list view search functionality."""
        incident = Incident.objects.create(
            title="Unique searchable incident title xyz123",
            service=self.service,
            severity=IncidentSeverity.SEV3_MEDIUM,
            status=IncidentStatus.TRIGGERED,
            lead=self.user
        )
        
        # Search by title
        response = self.client.get(
            reverse("dashboard:incident_list"),
            {"q": "xyz123"}
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertIn(incident, response.context["incidents"])


class TestIncidentDetailView(DashboardTestMixin, TestCase):
    """Tests for incident detail view."""

    def setUp(self):
        super().setUp()
        self.incident = Incident.objects.create(
            title="Test incident for detail",
            description="Test description",
            service=self.service,
            severity=IncidentSeverity.SEV2_HIGH,
            status=IncidentStatus.TRIGGERED,
            lead=self.user
        )

    def test_detail_view_renders(self):
        """Test detail view renders."""
        response = self.client.get(
            reverse("dashboard:incident_detail", kwargs={"pk": self.incident.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/incidents/detail_tailwind.html")

    def test_detail_view_shows_incident(self):
        """Test detail view shows incident data."""
        response = self.client.get(
            reverse("dashboard:incident_detail", kwargs={"pk": self.incident.pk})
        )
        
        self.assertEqual(response.context["incident"], self.incident)
        self.assertContains(response, self.incident.title)
        self.assertContains(response, self.incident.short_id)

    def test_detail_view_shows_timeline(self):
        """Test detail view shows timeline events."""
        event = IncidentEvent.objects.create(
            incident=self.incident,
            type="NOTE",
            message="Test event message",
            created_by=self.user
        )
        
        response = self.client.get(
            reverse("dashboard:incident_detail", kwargs={"pk": self.incident.pk})
        )
        
        self.assertIn(event, response.context["events"])

    def test_detail_view_can_acknowledge_triggered(self):
        """Test detail view shows acknowledge button for triggered incidents."""
        response = self.client.get(
            reverse("dashboard:incident_detail", kwargs={"pk": self.incident.pk})
        )
        
        self.assertTrue(response.context["can_acknowledge"])

    def test_detail_view_cannot_acknowledge_resolved(self):
        """Test detail view hides acknowledge for resolved incidents."""
        self.incident.status = IncidentStatus.RESOLVED
        self.incident.resolved_at = timezone.now()
        self.incident.save()
        
        response = self.client.get(
            reverse("dashboard:incident_detail", kwargs={"pk": self.incident.pk})
        )
        
        self.assertFalse(response.context["can_acknowledge"])


class TestIncidentCreateView(DashboardTestMixin, TestCase):
    """Tests for incident create view."""

    def test_create_view_renders(self):
        """Test create view renders."""
        response = self.client.get(reverse("dashboard:incident_create"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/incidents/create_tailwind.html")

    def test_create_view_form_submission(self):
        """Test creating an incident via form."""
        data = {
            "title": "New incident created via form",
            "description": "Test description",
            "service": str(self.service.id),
            "severity": IncidentSeverity.SEV3_MEDIUM,
        }
        
        response = self.client.post(
            reverse("dashboard:incident_create"),
            data,
            follow=True
        )
        
        # Should redirect to detail page
        self.assertEqual(response.status_code, 200)
        
        # Incident should be created
        self.assertTrue(
            Incident.objects.filter(title="New incident created via form").exists()
        )

    def test_create_view_validates_title_length(self):
        """Test create view validates minimum title length."""
        data = {
            "title": "Short",  # Less than 10 chars
            "service": str(self.service.id),
            "severity": IncidentSeverity.SEV3_MEDIUM,
        }
        
        response = self.client.post(reverse("dashboard:incident_create"), data)
        
        self.assertEqual(response.status_code, 200)  # Form re-rendered with errors
        self.assertFormError(
            response.context["form"],
            "title",
            "Le titre doit contenir au moins 10 caractères."
        )


class TestIncidentAcknowledgeView(DashboardTestMixin, TestCase):
    """Tests for incident acknowledge view."""

    def test_acknowledge_triggered_incident(self):
        """Test acknowledging a triggered incident."""
        incident = Incident.objects.create(
            title="Incident to acknowledge",
            service=self.service,
            severity=IncidentSeverity.SEV2_HIGH,
            status=IncidentStatus.TRIGGERED,
            lead=self.user
        )
        
        response = self.client.post(
            reverse("dashboard:incident_acknowledge", kwargs={"pk": incident.pk}),
            follow=True
        )
        
        self.assertEqual(response.status_code, 200)
        incident.refresh_from_db()
        self.assertEqual(incident.status, IncidentStatus.ACKNOWLEDGED)

    def test_acknowledge_non_triggered_incident_fails(self):
        """Test acknowledging a non-triggered incident shows warning."""
        incident = Incident.objects.create(
            title="Already acknowledged incident",
            service=self.service,
            severity=IncidentSeverity.SEV2_HIGH,
            status=IncidentStatus.ACKNOWLEDGED,
            lead=self.user,
            acknowledged_at=timezone.now()
        )
        
        response = self.client.post(
            reverse("dashboard:incident_acknowledge", kwargs={"pk": incident.pk}),
            follow=True
        )
        
        self.assertEqual(response.status_code, 200)
        # Status should not change
        incident.refresh_from_db()
        self.assertEqual(incident.status, IncidentStatus.ACKNOWLEDGED)


class TestIncidentResolveView(DashboardTestMixin, TestCase):
    """Tests for incident resolve view."""

    def test_resolve_view_renders(self):
        """Test resolve view renders."""
        incident = Incident.objects.create(
            title="Incident to resolve",
            service=self.service,
            severity=IncidentSeverity.SEV3_MEDIUM,
            status=IncidentStatus.ACKNOWLEDGED,
            lead=self.user
        )
        
        response = self.client.get(
            reverse("dashboard:incident_resolve", kwargs={"pk": incident.pk})
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/incidents/resolve_tailwind.html")

    def test_resolve_incident(self):
        """Test resolving an incident."""
        incident = Incident.objects.create(
            title="Incident to resolve test",
            service=self.service,
            severity=IncidentSeverity.SEV3_MEDIUM,
            status=IncidentStatus.ACKNOWLEDGED,
            lead=self.user
        )
        
        response = self.client.post(
            reverse("dashboard:incident_resolve", kwargs={"pk": incident.pk}),
            {"resolution_note": "Fixed the issue", "confirm": True},
            follow=True
        )
        
        self.assertEqual(response.status_code, 200)
        incident.refresh_from_db()
        self.assertEqual(incident.status, IncidentStatus.RESOLVED)


class TestIncidentAddNoteView(DashboardTestMixin, TestCase):
    """Tests for add note view."""

    def test_add_note_to_incident(self):
        """Test adding a note to an incident."""
        incident = Incident.objects.create(
            title="Incident for note test",
            service=self.service,
            severity=IncidentSeverity.SEV3_MEDIUM,
            status=IncidentStatus.TRIGGERED,
            lead=self.user
        )
        
        response = self.client.post(
            reverse("dashboard:incident_add_note", kwargs={"pk": incident.pk}),
            {"message": "This is a test note with enough chars"},
            follow=True
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            IncidentEvent.objects.filter(
                incident=incident,
                type="NOTE",
                message="This is a test note with enough chars"
            ).exists()
        )

    def test_add_short_note_fails(self):
        """Test adding too short note fails."""
        incident = Incident.objects.create(
            title="Incident for short note test",
            service=self.service,
            severity=IncidentSeverity.SEV3_MEDIUM,
            status=IncidentStatus.TRIGGERED,
            lead=self.user
        )
        
        initial_count = IncidentEvent.objects.filter(incident=incident).count()
        
        self.client.post(
            reverse("dashboard:incident_add_note", kwargs={"pk": incident.pk}),
            {"message": "Hi"},  # Too short
        )
        
        # No new event should be created
        self.assertEqual(
            IncidentEvent.objects.filter(incident=incident).count(),
            initial_count
        )


class TestServiceListView(DashboardTestMixin, TestCase):
    """Tests for service list view."""

    def test_service_list_renders(self):
        """Test service list view renders."""
        response = self.client.get(reverse("dashboard:service_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/services/list_tailwind.html")

    def test_service_list_shows_active_services(self):
        """Test service list shows active services."""
        response = self.client.get(reverse("dashboard:service_list"))
        self.assertIn(self.service, response.context["services"])


class TestTeamListView(DashboardTestMixin, TestCase):
    """Tests for team list view."""

    def test_team_list_renders(self):
        """Test team list view renders."""
        response = self.client.get(reverse("dashboard:team_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/teams/list_tailwind.html")

    def test_team_list_shows_teams(self):
        """Test team list shows teams."""
        response = self.client.get(reverse("dashboard:team_list"))
        self.assertIn(self.team, response.context["teams"])


class TestAnalyticsViews(DashboardTestMixin, TestCase):
    """Tests for analytics views."""

    def test_analytics_dashboard_renders(self):
        """Test analytics dashboard renders."""
        response = self.client.get(reverse("dashboard:analytics"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/analytics_tailwind.html")

    def test_analytics_mtta_renders(self):
        """Test MTTA analytics view renders."""
        response = self.client.get(reverse("dashboard:analytics_mtta"))
        self.assertEqual(response.status_code, 200)

    def test_analytics_mttr_renders(self):
        """Test MTTR analytics view renders."""
        response = self.client.get(reverse("dashboard:analytics_mttr"))
        self.assertEqual(response.status_code, 200)


class TestIncidentForms(TestCase):
    """Tests for dashboard forms."""

    @classmethod
    def setUpTestData(cls):
        cls.team = Team.objects.create(name="Form Test Team")
        cls.service = Service.objects.create(
            name="Form Test Service",
            owner_team=cls.team,
            is_active=True
        )

    def test_incident_create_form_valid(self):
        """Test IncidentCreateForm with valid data."""
        form = IncidentCreateForm(data={
            "title": "Valid incident title here",
            "description": "Description",
            "service": self.service.id,
            "severity": IncidentSeverity.SEV3_MEDIUM,
        })
        self.assertTrue(form.is_valid())

    def test_incident_create_form_short_title_invalid(self):
        """Test IncidentCreateForm rejects short title."""
        form = IncidentCreateForm(data={
            "title": "Short",
            "service": self.service.id,
            "severity": IncidentSeverity.SEV3_MEDIUM,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("title", form.errors)

    def test_incident_note_form_valid(self):
        """Test IncidentNoteForm with valid data."""
        form = IncidentNoteForm(data={
            "message": "This is a valid note message"
        })
        self.assertTrue(form.is_valid())

    def test_incident_note_form_short_message_invalid(self):
        """Test IncidentNoteForm rejects short message."""
        form = IncidentNoteForm(data={
            "message": "Hi"
        })
        self.assertFalse(form.is_valid())
        self.assertIn("message", form.errors)

    def test_incident_resolve_form_valid(self):
        """Test IncidentResolveForm with valid data."""
        form = IncidentResolveForm(data={
            "resolution_note": "Issue was fixed by restarting the service",
            "confirm": True
        })
        self.assertTrue(form.is_valid())

    def test_incident_resolve_form_requires_confirm(self):
        """Test IncidentResolveForm requires confirmation."""
        form = IncidentResolveForm(data={
            "resolution_note": "Note",
            "confirm": False
        })
        self.assertFalse(form.is_valid())
        self.assertIn("confirm", form.errors)
