"""
IMAS Manager - Tests for Enhanced Features

Tests for Runbooks, Comments, Tags, and Escalation Policies.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from core.models import (
    EscalationPolicy,
    EscalationStep,
    Incident,
    IncidentComment,
    IncidentTag,
    Runbook,
    RunbookStep,
    Service,
    Tag,
    Team,
)

User = get_user_model()


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def user(db):
    """Create a test user."""
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )


@pytest.fixture
def team(db, user):
    """Create a test team."""
    team = Team.objects.create(
        name="Platform Team",
        slug="platform",
        current_on_call=user,
    )
    return team


@pytest.fixture
def service(db, team):
    """Create a test service."""
    return Service.objects.create(
        name="API Gateway",
        owner_team=team,
        criticality="HIGH",
    )


@pytest.fixture
def incident(db, service, user):
    """Create a test incident."""
    return Incident.objects.create(
        title="High CPU Usage",
        description="API Gateway CPU at 95%",
        severity="SEV2",
        status="TRIGGERED",
        service=service,
        detected_at=timezone.now(),
    )


# =============================================================================
# Tag Tests
# =============================================================================


@pytest.mark.django_db
class TestTagModel:
    """Tests for Tag model."""
    
    def test_create_tag(self):
        """Test creating a tag."""
        tag = Tag.objects.create(
            name="database",
            description="Database related incidents",
            color="#3B82F6",
        )
        assert tag.name == "database"
        assert tag.color == "#3B82F6"
        assert tag.is_active is True
    
    def test_tag_auto_apply_pattern(self):
        """Test auto-apply pattern matching."""
        tag = Tag.objects.create(
            name="memory",
            auto_apply_pattern=r"memory|oom|heap",
        )
        assert tag.auto_apply_pattern == r"memory|oom|heap"
    
    def test_tag_uniqueness(self, db):
        """Test tag name uniqueness."""
        Tag.objects.create(name="unique-tag")
        with pytest.raises(Exception):  # IntegrityError
            Tag.objects.create(name="unique-tag")


@pytest.mark.django_db
class TestIncidentTag:
    """Tests for incident tagging."""
    
    def test_apply_tag_to_incident(self, incident, user):
        """Test applying a tag to an incident."""
        tag = Tag.objects.create(name="high-priority")
        
        incident_tag = IncidentTag.objects.create(
            incident=incident,
            tag=tag,
            added_by=user,
        )
        
        assert incident_tag.tag == tag
        assert incident_tag.added_by == user
        assert incident_tag.added_at is not None
    
    def test_tag_service_auto_apply(self, incident):
        """Test TagService auto-apply."""
        from services.runbook import TagService
        
        # Create tag with pattern matching incident title
        Tag.objects.create(
            name="cpu",
            auto_apply_pattern=r"cpu|processor",
        )
        
        applied = TagService.auto_apply_tags(incident)
        
        assert len(applied) == 1
        assert applied[0].name == "cpu"
    
    def test_tag_service_manual_apply(self, incident, user):
        """Test TagService manual apply."""
        from services.runbook import TagService
        
        tag = TagService.apply_tag(incident, "manual-tag", user)
        
        assert tag is not None
        assert tag.name == "manual-tag"
        assert IncidentTag.objects.filter(incident=incident, tag=tag).exists()
    
    def test_tag_service_remove(self, incident, user):
        """Test TagService remove."""
        from services.runbook import TagService
        
        TagService.apply_tag(incident, "to-remove", user)
        removed = TagService.remove_tag(incident, "to-remove")
        
        assert removed is True
        assert not IncidentTag.objects.filter(
            incident=incident,
            tag__name="to-remove"
        ).exists()


# =============================================================================
# Comment Tests
# =============================================================================


@pytest.mark.django_db
class TestIncidentComment:
    """Tests for incident comments."""
    
    def test_create_comment(self, incident, user):
        """Test creating a comment."""
        comment = IncidentComment.objects.create(
            incident=incident,
            author=user,
            content="Initial investigation started.",
            comment_type="manual",
        )
        
        assert comment.content == "Initial investigation started."
        assert comment.author == user
        assert comment.comment_type == "manual"
    
    def test_comment_types(self, incident, user):
        """Test different comment types."""
        types = ["manual", "status", "auto", "escalation", "resolution"]
        
        for comment_type in types:
            comment = IncidentComment.objects.create(
                incident=incident,
                content=f"Comment of type {comment_type}",
                comment_type=comment_type,
            )
            assert comment.comment_type == comment_type
    
    def test_pinned_comment(self, incident, user):
        """Test pinning a comment."""
        comment = IncidentComment.objects.create(
            incident=incident,
            author=user,
            content="Important note",
            is_pinned=True,
        )
        
        assert comment.is_pinned is True
        
        # Test pinned filter
        pinned = IncidentComment.objects.filter(incident=incident, is_pinned=True)
        assert comment in pinned
    
    def test_comment_metadata(self, incident, user):
        """Test comment metadata storage."""
        comment = IncidentComment.objects.create(
            incident=incident,
            author=user,
            content="Automated update",
            comment_type="auto",
            metadata={
                "source": "monitoring",
                "metric_value": 95.5,
            }
        )
        
        assert comment.metadata["source"] == "monitoring"
        assert comment.metadata["metric_value"] == 95.5


# =============================================================================
# Runbook Tests
# =============================================================================


@pytest.mark.django_db
class TestRunbook:
    """Tests for Runbook model."""
    
    def test_create_runbook(self, service, user):
        """Test creating a runbook."""
        runbook = Runbook.objects.create(
            name="API Gateway Recovery",
            slug="api-gateway-recovery",
            description="Steps to recover API Gateway",
            service=service,
            author=user,
        )
        
        assert runbook.name == "API Gateway Recovery"
        assert runbook.service == service
        assert runbook.is_active is True
    
    def test_runbook_with_steps(self, service, user):
        """Test runbook with steps."""
        runbook = Runbook.objects.create(
            name="Database Recovery",
            slug="database-recovery",
            service=service,
            author=user,
        )
        
        step1 = RunbookStep.objects.create(
            runbook=runbook,
            order=1,
            title="Check connection pool",
            description="Verify connection pool status",
        )
        
        step2 = RunbookStep.objects.create(
            runbook=runbook,
            order=2,
            title="Restart service",
            description="Restart the database service",
            command="systemctl restart postgresql",
        )
        
        assert runbook.steps.count() == 2
        assert step1.order < step2.order
    
    def test_runbook_alert_pattern(self, service, user, incident):
        """Test runbook alert pattern matching."""
        runbook = Runbook.objects.create(
            name="CPU Alert Runbook",
            slug="cpu-alert-runbook",
            service=service,
            alert_pattern=r"cpu|processor",
            author=user,
        )
        
        matched = Runbook.find_for_incident(incident)
        
        assert matched == runbook
    
    def test_runbook_quick_actions(self, service, user):
        """Test runbook quick actions."""
        runbook = Runbook.objects.create(
            name="Quick Actions Test",
            slug="quick-actions-test",
            service=service,
            author=user,
            quick_actions=[
                {"id": "restart", "label": "Restart Service", "type": "action"},
                {"id": "logs", "label": "View Logs", "type": "link", "url": "/logs"},
            ],
        )
        
        assert len(runbook.quick_actions) == 2
        assert runbook.quick_actions[0]["label"] == "Restart Service"


@pytest.mark.django_db
class TestRunbookService:
    """Tests for RunbookService."""
    
    def test_find_runbook(self, incident, service, user):
        """Test finding runbook for incident."""
        from services.runbook import RunbookService
        
        runbook = Runbook.objects.create(
            name="Test Runbook",
            slug="test-runbook",
            service=service,
            alert_pattern=r"cpu",
            author=user,
        )
        
        service_obj = RunbookService(incident)
        found = service_obj.find_runbook()
        
        assert found == runbook
    
    def test_get_runbook_steps(self, incident, service, user):
        """Test getting runbook steps."""
        from services.runbook import RunbookService
        
        runbook = Runbook.objects.create(
            name="Test Runbook",
            slug="test-runbook-2",
            service=service,
            author=user,
        )
        
        RunbookStep.objects.create(
            runbook=runbook,
            order=1,
            title="Step 1",
            description="First step",
        )
        
        service_obj = RunbookService(incident)
        steps = service_obj.get_runbook_steps(runbook)
        
        assert len(steps) == 1
        assert steps[0]["title"] == "Step 1"


# =============================================================================
# Escalation Policy Tests
# =============================================================================


@pytest.mark.django_db
class TestEscalationPolicy:
    """Tests for EscalationPolicy model."""
    
    def test_create_policy(self, team):
        """Test creating an escalation policy."""
        policy = EscalationPolicy.objects.create(
            name="Default Escalation",
            team=team,
            initial_delay_minutes=5,
        )
        
        assert policy.name == "Default Escalation"
        assert policy.team == team
        assert policy.initial_delay_minutes == 5
    
    def test_policy_with_steps(self, team, user):
        """Test policy with escalation steps."""
        policy = EscalationPolicy.objects.create(
            name="Multi-level Escalation",
            team=team,
            initial_delay_minutes=5,
        )
        
        step1 = EscalationStep.objects.create(
            policy=policy,
            order=1,
            delay_minutes=5,
            notify_type="oncall",
        )
        
        step2 = EscalationStep.objects.create(
            policy=policy,
            order=2,
            delay_minutes=10,
            notify_type="manager",
        )
        
        step3 = EscalationStep.objects.create(
            policy=policy,
            order=3,
            delay_minutes=15,
            notify_type="user",
            notify_user=user,
        )
        
        assert policy.steps.count() == 3
        assert step1.notify_type == "oncall"
        assert step3.notify_user == user
    
    def test_policy_severity_filter(self, team):
        """Test policy with severity filter."""
        policy = EscalationPolicy.objects.create(
            name="SEV1 Escalation",
            team=team,
            severity_filter="SEV1",
            initial_delay_minutes=2,
        )
        
        assert policy.severity_filter == "SEV1"
    
    def test_policy_service_filter(self, team, service):
        """Test policy creation (no services filter in this model)."""
        policy = EscalationPolicy.objects.create(
            name="API Gateway Escalation",
            team=team,
            initial_delay_minutes=5,
        )
        
        assert policy.is_active is True


@pytest.mark.django_db
class TestEscalationService:
    """Tests for EscalationService."""
    
    def test_should_not_escalate_acknowledged(self, incident, team, user):
        """Test that acknowledged incidents don't escalate."""
        from services.escalation import EscalationService
        
        incident.status = "ACKNOWLEDGED"
        incident.save()
        
        service = EscalationService(incident)
        assert service._should_escalate() is False
    
    def test_should_escalate_triggered(self, incident, team):
        """Test that triggered incidents should escalate."""
        from services.escalation import EscalationService
        
        service = EscalationService(incident)
        assert service._should_escalate() is True
    
    def test_find_policy(self, incident, team, user):
        """Test finding escalation policy."""
        from services.escalation import EscalationService
        
        policy = EscalationPolicy.objects.create(
            name="Default",
            team=team,
            initial_delay_minutes=5,
        )
        
        EscalationStep.objects.create(
            policy=policy,
            order=1,
            delay_minutes=5,
            notify_type="oncall",
        )
        
        service = EscalationService(incident)
        found = service._find_policy()
        
        assert found == policy


# =============================================================================
# Notification Template Tests
# =============================================================================


@pytest.mark.django_db
class TestNotificationTemplates:
    """Tests for notification templates."""
    
    def test_slack_incident_created(self, incident):
        """Test Slack incident created template."""
        from services.templates import NotificationContext, SlackTemplates
        
        ctx = NotificationContext(incident=incident)
        message = SlackTemplates.incident_created(ctx)
        
        assert "attachments" in message
        assert len(message["attachments"]) > 0
    
    def test_slack_escalation_template(self, incident):
        """Test Slack escalation template."""
        from services.templates import NotificationContext, SlackTemplates
        
        ctx = NotificationContext(
            incident=incident,
            custom_data={"wait_time_seconds": 600}
        )
        message = SlackTemplates.escalation_notification(ctx, escalation_level=2)
        
        assert "blocks" in message
        # Check for escalation level in header
        header_found = False
        for block in message["blocks"]:
            if block.get("type") == "header":
                if "Level 2" in block.get("text", {}).get("text", ""):
                    header_found = True
        assert header_found
    
    def test_email_incident_created(self, incident):
        """Test email incident created template."""
        from services.templates import EmailTemplates, NotificationContext
        
        ctx = NotificationContext(incident=incident)
        subject, body = EmailTemplates.incident_created(ctx)
        
        assert incident.severity in subject
        assert incident.short_id in subject
        assert "<html>" in body
    
    def test_notification_context(self, incident):
        """Test notification context building."""
        from services.templates import NotificationContext
        
        ctx = NotificationContext(incident=incident)
        data = ctx.to_dict()
        
        assert data["incident_id"] == str(incident.id)
        assert data["incident_severity"] == incident.severity
        assert data["incident_title"] == incident.title
        assert data["is_open"] == incident.is_open
    
    def test_template_registry(self, incident):
        """Test template registry."""
        from services.templates import NotificationContext, TemplateRegistry
        
        ctx = NotificationContext(incident=incident)
        
        # Slack template
        slack = TemplateRegistry.get_template("slack", "incident_created", ctx)
        assert slack is not None
        
        # Email template
        email = TemplateRegistry.get_template("email", "incident_created", ctx)
        assert email is not None
        assert len(email) == 2  # (subject, body)


# =============================================================================
# API Tests
# =============================================================================


@pytest.mark.django_db
class TestFeaturesAPI:
    """Tests for features API endpoints."""
    
    def test_list_tags(self, client, user):
        """Test listing tags."""
        from rest_framework.test import APIClient
        
        client = APIClient()
        client.force_authenticate(user=user)
        
        Tag.objects.create(name="tag1")
        Tag.objects.create(name="tag2")
        
        response = client.get("/api/v1/tags/")
        
        assert response.status_code == 200
        assert len(response.data) >= 2
    
    def test_create_comment(self, client, user, incident):
        """Test creating a comment."""
        from rest_framework.test import APIClient
        
        client = APIClient()
        client.force_authenticate(user=user)
        
        response = client.post(
            f"/api/v1/incidents/{incident.id}/comments/",
            {"content": "Test comment", "comment_type": "manual"},
            format="json",
        )
        
        assert response.status_code == 201
    
    def test_list_runbooks(self, client, user, service):
        """Test listing runbooks."""
        from rest_framework.test import APIClient
        
        client = APIClient()
        client.force_authenticate(user=user)
        
        Runbook.objects.create(
            name="Test Runbook",
            slug="test-runbook-api",
            service=service,
            author=user,
        )
        
        response = client.get("/api/v1/runbooks/")
        
        assert response.status_code == 200
        assert len(response.data) >= 1
    
    def test_list_escalation_policies(self, client, user, team):
        """Test listing escalation policies."""
        from rest_framework.test import APIClient
        
        client = APIClient()
        client.force_authenticate(user=user)
        
        EscalationPolicy.objects.create(
            name="Test Policy",
            team=team,
            initial_delay_minutes=5,
        )
        
        response = client.get("/api/v1/escalation-policies/")
        
        assert response.status_code == 200
        assert len(response.data) >= 1
