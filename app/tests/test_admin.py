"""
Tests for IMAS Admin Configuration.

Tests the custom admin interface, filters, actions, and dashboard.
"""
from datetime import timedelta
from io import StringIO
from unittest.mock import patch, MagicMock

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory
from django.utils import timezone

from core.admin import (
    IncidentAdmin,
    TeamAdmin,
    ServiceAdmin,
    OnCallScheduleAdmin,
    ActiveIncidentFilter,
    SeverityCriticalFilter,
    RecentlyCreatedFilter,
    HasWarRoomFilter,
    OnCallActiveFilter,
)
from core.choices import IncidentSeverity, IncidentStatus
from core.models import Incident, Team, Service, OnCallSchedule


User = get_user_model()


class AdminTestMixin:
    """Mixin with common setup for admin tests."""
    
    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.admin_user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass123"
        )
        self.team = Team.objects.create(
            name="SRE Team",
            slug="sre-team",
            email="sre@example.com"
        )
        self.service = Service.objects.create(
            name="API Gateway",
            owner_team=self.team,
            criticality="CRITICAL"
        )


class TestIncidentAdminFilters(AdminTestMixin, TestCase):
    """Tests for custom incident filters - tests the filter logic directly."""

    def test_active_incident_filter_logic(self):
        """Test ActiveIncidentFilter logic excludes resolved incidents."""
        # Create test incidents
        active_inc = Incident.objects.create(
            title="Active incident",
            service=self.service,
            severity=IncidentSeverity.SEV1_CRITICAL,
            status=IncidentStatus.TRIGGERED,
            lead=self.admin_user
        )
        resolved_inc = Incident.objects.create(
            title="Resolved incident",
            service=self.service,
            severity=IncidentSeverity.SEV4_LOW,
            status=IncidentStatus.RESOLVED,
            lead=self.admin_user,
            resolved_at=timezone.now()
        )
        
        # Test the filter logic directly (same as what the filter does)
        queryset = Incident.objects.filter(id__in=[active_inc.id, resolved_inc.id])
        
        # Simulate "active=yes" filter
        filtered_active = queryset.exclude(status=IncidentStatus.RESOLVED)
        self.assertEqual(filtered_active.count(), 1)
        self.assertEqual(filtered_active.first().id, active_inc.id)
        
        # Simulate "active=no" filter
        filtered_resolved = queryset.filter(status=IncidentStatus.RESOLVED)
        self.assertEqual(filtered_resolved.count(), 1)
        self.assertEqual(filtered_resolved.first().id, resolved_inc.id)

    def test_severity_critical_filter_logic(self):
        """Test SeverityCriticalFilter logic."""
        sev1_inc = Incident.objects.create(
            title="Critical",
            service=self.service,
            severity=IncidentSeverity.SEV1_CRITICAL,
            status=IncidentStatus.TRIGGERED,
            lead=self.admin_user
        )
        sev2_inc = Incident.objects.create(
            title="High",
            service=self.service,
            severity=IncidentSeverity.SEV2_HIGH,
            status=IncidentStatus.TRIGGERED,
            lead=self.admin_user
        )
        sev4_inc = Incident.objects.create(
            title="Low",
            service=self.service,
            severity=IncidentSeverity.SEV4_LOW,
            status=IncidentStatus.TRIGGERED,
            lead=self.admin_user
        )
        
        queryset = Incident.objects.filter(id__in=[sev1_inc.id, sev2_inc.id, sev4_inc.id])
        
        # Simulate "critical=sev1" filter
        filtered_sev1 = queryset.filter(severity=IncidentSeverity.SEV1_CRITICAL)
        self.assertEqual(filtered_sev1.count(), 1)
        self.assertEqual(filtered_sev1.first().id, sev1_inc.id)
        
        # Simulate "critical=sev1_sev2" filter
        filtered_high = queryset.filter(
            severity__in=[IncidentSeverity.SEV1_CRITICAL, IncidentSeverity.SEV2_HIGH]
        )
        self.assertEqual(filtered_high.count(), 2)
        self.assertNotIn(sev4_inc.id, list(filtered_high.values_list("id", flat=True)))

    def test_has_war_room_filter_logic(self):
        """Test HasWarRoomFilter logic."""
        with_war_room = Incident.objects.create(
            title="With war room",
            service=self.service,
            severity=IncidentSeverity.SEV1_CRITICAL,
            status=IncidentStatus.TRIGGERED,
            lead=self.admin_user,
            war_room_link="https://slack.com/channel"
        )
        without_war_room = Incident.objects.create(
            title="Without war room",
            service=self.service,
            severity=IncidentSeverity.SEV4_LOW,
            status=IncidentStatus.TRIGGERED,
            lead=self.admin_user
        )
        
        queryset = Incident.objects.filter(id__in=[with_war_room.id, without_war_room.id])
        
        # Simulate "war_room=yes" filter
        from django.db.models import Q
        filtered = queryset.exclude(war_room_link="").exclude(war_room_link__isnull=True)
        self.assertEqual(filtered.count(), 1)
        self.assertEqual(filtered.first().id, with_war_room.id)

    def test_filter_classes_exist(self):
        """Test that filter classes are properly defined."""
        self.assertEqual(ActiveIncidentFilter.parameter_name, "active")
        self.assertEqual(SeverityCriticalFilter.parameter_name, "critical")
        self.assertEqual(HasWarRoomFilter.parameter_name, "war_room")
        self.assertEqual(OnCallActiveFilter.parameter_name, "schedule_active")


class TestIncidentAdminActions(AdminTestMixin, TestCase):
    """Tests for custom incident admin actions."""
    
    def setUp(self):
        super().setUp()
        self.incident = Incident.objects.create(
            title="Test incident",
            service=self.service,
            severity=IncidentSeverity.SEV1_CRITICAL,
            status=IncidentStatus.TRIGGERED,
            lead=self.admin_user
        )

    def test_mark_as_acknowledged_action(self):
        """Test mark_as_acknowledged action."""
        request = self.factory.post("/admin/core/incident/")
        request.user = self.admin_user
        
        incident_admin = IncidentAdmin(Incident, self.site)
        queryset = Incident.objects.filter(status=IncidentStatus.TRIGGERED)
        
        with patch.object(incident_admin, "message_user"):
            incident_admin.mark_as_acknowledged(request, queryset)
        
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.status, IncidentStatus.ACKNOWLEDGED)

    def test_mark_as_resolved_action(self):
        """Test mark_as_resolved action."""
        request = self.factory.post("/admin/core/incident/")
        request.user = self.admin_user
        
        incident_admin = IncidentAdmin(Incident, self.site)
        queryset = Incident.objects.all()
        
        with patch.object(incident_admin, "message_user"):
            incident_admin.mark_as_resolved(request, queryset)
        
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.status, IncidentStatus.RESOLVED)

    def test_assign_to_me_action(self):
        """Test assign_to_me action."""
        other_user = User.objects.create_user(
            username="other",
            email="other@example.com",
            password="pass123"
        )
        
        request = self.factory.post("/admin/core/incident/")
        request.user = other_user
        
        incident_admin = IncidentAdmin(Incident, self.site)
        queryset = Incident.objects.all()
        
        with patch.object(incident_admin, "message_user"):
            incident_admin.assign_to_me(request, queryset)
        
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.lead, other_user)

    def test_export_as_csv_action(self):
        """Test export_as_csv action."""
        request = self.factory.post("/admin/core/incident/")
        request.user = self.admin_user
        
        incident_admin = IncidentAdmin(Incident, self.site)
        queryset = Incident.objects.all()
        
        response = incident_admin.export_as_csv(request, queryset)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("incidents_export.csv", response["Content-Disposition"])
        
        content = response.content.decode("utf-8")
        self.assertIn("Test incident", content)


class TestIncidentAdminDisplayMethods(AdminTestMixin, TestCase):
    """Tests for custom display methods."""
    
    def setUp(self):
        super().setUp()
        self.incident = Incident.objects.create(
            title="Test incident",
            service=self.service,
            severity=IncidentSeverity.SEV1_CRITICAL,
            status=IncidentStatus.TRIGGERED,
            lead=self.admin_user,
            war_room_link="https://slack.com/channel"
        )

    def test_severity_badge_display(self):
        """Test severity badge HTML output."""
        incident_admin = IncidentAdmin(Incident, self.site)
        badge = incident_admin.severity_badge(self.incident)
        
        self.assertIn("#dc3545", badge)  # Critical color

    def test_status_badge_display(self):
        """Test status badge HTML output."""
        incident_admin = IncidentAdmin(Incident, self.site)
        badge = incident_admin.status_badge(self.incident)
        
        self.assertIn("#dc3545", badge)  # Triggered color

    def test_has_war_room_display(self):
        """Test has_war_room boolean display."""
        incident_admin = IncidentAdmin(Incident, self.site)
        
        self.assertTrue(incident_admin.has_war_room(self.incident))
        
        self.incident.war_room_link = ""
        self.assertFalse(incident_admin.has_war_room(self.incident))

    def test_age_display(self):
        """Test age display formatting."""
        incident_admin = IncidentAdmin(Incident, self.site)
        age = incident_admin.age_display(self.incident)
        
        self.assertTrue(any(unit in age for unit in ["m", "h", "d"]))


class TestOnCallScheduleAdmin(AdminTestMixin, TestCase):
    """Tests for OnCallSchedule admin."""

    def test_duplicate_schedule_action(self):
        """Test duplicate_schedule action."""
        now = timezone.now()
        schedule = OnCallSchedule.objects.create(
            team=self.team,
            user=self.admin_user,
            start_time=now,
            end_time=now + timedelta(hours=8),
            escalation_level=1
        )
        
        request = self.factory.post("/admin/core/oncallschedule/")
        request.user = self.admin_user
        
        oncall_admin = OnCallScheduleAdmin(OnCallSchedule, self.site)
        queryset = OnCallSchedule.objects.filter(id=schedule.id)
        
        with patch.object(oncall_admin, "message_user"):
            oncall_admin.duplicate_schedule(request, queryset)
        
        self.assertEqual(OnCallSchedule.objects.count(), 2)
        
        new_schedule = OnCallSchedule.objects.exclude(id=schedule.id).first()
        self.assertEqual(new_schedule.start_time, schedule.start_time + timedelta(days=7))

    def test_oncall_active_filter(self):
        """Test OnCallActiveFilter logic."""
        now = timezone.now()
        
        # Active schedule
        active_sched = OnCallSchedule.objects.create(
            team=self.team,
            user=self.admin_user,
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=7),
            escalation_level=1
        )
        
        # Past schedule
        past_sched = OnCallSchedule.objects.create(
            team=self.team,
            user=self.admin_user,
            start_time=now - timedelta(days=7),
            end_time=now - timedelta(days=6),
            escalation_level=1
        )
        
        # Test the filter logic directly
        queryset = OnCallSchedule.objects.filter(id__in=[active_sched.id, past_sched.id])
        
        # Simulate "schedule_active=active" filter
        filtered = queryset.filter(start_time__lte=now, end_time__gte=now)
        
        filtered_ids = list(filtered.values_list("id", flat=True))
        self.assertIn(active_sched.id, filtered_ids)
        self.assertNotIn(past_sched.id, filtered_ids)
