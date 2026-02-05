"""
IMAS Manager - API v1 Serializers
"""
from __future__ import annotations

from rest_framework import serializers

from core.models import (
    EscalationPolicy,
    EscalationStep,
    ImpactScope,
    Incident,
    IncidentComment,
    IncidentEvent,
    IncidentTag,
    Runbook,
    RunbookStep,
    Service,
    Tag,
    Team,
)


class TeamSerializer(serializers.ModelSerializer):
    """Serializer for Team model."""
    
    on_call_username = serializers.CharField(
        source="current_on_call.username",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = Team
        fields = [
            "id",
            "name",
            "slack_channel_id",
            "on_call_username",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class ServiceSerializer(serializers.ModelSerializer):
    """Serializer for Service model."""
    
    owner_team_name = serializers.CharField(
        source="owner_team.name",
        read_only=True,
    )

    class Meta:
        model = Service
        fields = [
            "id",
            "name",
            "owner_team",
            "owner_team_name",
            "runbook_url",
            "criticality",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class ImpactScopeSerializer(serializers.ModelSerializer):
    """Serializer for ImpactScope model."""

    class Meta:
        model = ImpactScope
        fields = [
            "id",
            "name",
            "description",
            "is_active",
        ]
        read_only_fields = ["id"]


class IncidentEventSerializer(serializers.ModelSerializer):
    """Serializer for IncidentEvent model."""
    
    created_by_username = serializers.CharField(
        source="created_by.username",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = IncidentEvent
        fields = [
            "id",
            "type",
            "message",
            "timestamp",
            "created_by_username",
        ]
        read_only_fields = ["id", "timestamp"]


class IncidentSerializer(serializers.ModelSerializer):
    """Serializer for Incident model."""
    
    service_name = serializers.CharField(
        source="service.name",
        read_only=True,
    )
    lead_username = serializers.CharField(
        source="lead.username",
        read_only=True,
        allow_null=True,
    )
    impacted_scope_names = serializers.StringRelatedField(
        source="impacted_scopes",
        many=True,
        read_only=True,
    )
    short_id = serializers.CharField(read_only=True)
    is_critical = serializers.BooleanField(read_only=True)
    is_open = serializers.BooleanField(read_only=True)
    
    # KPIs
    mttd_seconds = serializers.IntegerField(read_only=True)
    mtta_seconds = serializers.IntegerField(read_only=True)
    mttr_seconds = serializers.IntegerField(read_only=True)

    class Meta:
        model = Incident
        fields = [
            "id",
            "short_id",
            "title",
            "description",
            "service",
            "service_name",
            "impacted_scopes",
            "impacted_scope_names",
            "lead",
            "lead_username",
            "severity",
            "status",
            "is_critical",
            "is_open",
            "lid_link",
            "war_room_link",
            "detected_at",
            "created_at",
            "acknowledged_at",
            "resolved_at",
            "mttd_seconds",
            "mtta_seconds",
            "mttr_seconds",
        ]
        read_only_fields = [
            "id",
            "short_id",
            "created_at",
            "acknowledged_at",
            "resolved_at",
            "lid_link",
            "war_room_link",
            "war_room_id",
        ]


class IncidentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating incidents via API."""
    
    service_name = serializers.CharField(
        write_only=True,
        required=False,
        help_text="Service name for lookup (alternative to service UUID).",
    )

    class Meta:
        model = Incident
        fields = [
            "title",
            "description",
            "service",
            "service_name",
            "severity",
            "impacted_scopes",
            "detected_at",
        ]
        extra_kwargs = {
            "service": {"required": False},
        }

    def validate(self, data):
        """Validate that either service or service_name is provided."""
        service = data.get("service")
        service_name = data.pop("service_name", None)
        
        if not service and not service_name:
            raise serializers.ValidationError(
                {"service": "Either 'service' UUID or 'service_name' is required."}
            )
        
        if service_name and not service:
            try:
                data["service"] = Service.objects.get(name=service_name)
            except Service.DoesNotExist:
                raise serializers.ValidationError(
                    {"service_name": f"Service '{service_name}' not found."}
                )
        
        return data


class IncidentDetailSerializer(IncidentSerializer):
    """Detailed serializer for Incident including events."""
    
    events = IncidentEventSerializer(many=True, read_only=True)
    service = ServiceSerializer(read_only=True)

    class Meta(IncidentSerializer.Meta):
        fields = IncidentSerializer.Meta.fields + ["events"]


# =============================================================================
# API Documentation Serializers
# =============================================================================


class ErrorSerializer(serializers.Serializer):
    """
    Standard error response format.
    
    Used in OpenAPI schema for error responses.
    """
    error = serializers.CharField(
        help_text="Human-readable error message"
    )
    code = serializers.CharField(
        required=False,
        help_text="Machine-readable error code"
    )
    details = serializers.DictField(
        required=False,
        child=serializers.ListField(child=serializers.CharField()),
        help_text="Field-level validation errors"
    )


class IncidentResolveRequestSerializer(serializers.Serializer):
    """Request serializer for resolving an incident."""
    note = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Resolution note describing the fix or root cause"
    )


class IncidentAcknowledgeResponseSerializer(serializers.Serializer):
    """Response serializer for acknowledging an incident."""
    id = serializers.UUIDField(help_text="Incident UUID")
    short_id = serializers.CharField(help_text="Human-readable incident ID")
    status = serializers.CharField(help_text="New status (acknowledged)")
    acknowledged_at = serializers.DateTimeField(help_text="Acknowledgement timestamp")


class TokenObtainSerializer(serializers.Serializer):
    """Request serializer for obtaining an API token."""
    username = serializers.CharField(
        help_text="Username for authentication"
    )
    password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
        help_text="Password for authentication"
    )


class TokenResponseSerializer(serializers.Serializer):
    """Response serializer for token endpoint."""
    token = serializers.CharField(
        help_text="API token to use in Authorization header"
    )
    user_id = serializers.IntegerField(
        help_text="Authenticated user ID"
    )
    username = serializers.CharField(
        help_text="Authenticated username"
    )
    email = serializers.EmailField(
        help_text="User email address"
    )


class HealthCheckSerializer(serializers.Serializer):
    """Response serializer for health check endpoints."""
    status = serializers.CharField(
        help_text="Health status (healthy, degraded, unhealthy)"
    )
    service = serializers.CharField(
        help_text="Service name"
    )
    version = serializers.CharField(
        help_text="Application version"
    )


class HealthDetailedSerializer(serializers.Serializer):
    """Response serializer for detailed health check."""
    status = serializers.CharField()
    service = serializers.CharField()
    version = serializers.CharField()
    checks = serializers.DictField(
        child=serializers.DictField(),
        help_text="Individual component health checks"
    )
    timestamp = serializers.DateTimeField()


class PaginatedResponseSerializer(serializers.Serializer):
    """Base serializer for paginated responses."""
    count = serializers.IntegerField(help_text="Total number of items")
    next = serializers.URLField(
        allow_null=True,
        help_text="URL to next page"
    )
    previous = serializers.URLField(
        allow_null=True,
        help_text="URL to previous page"
    )
    results = serializers.ListField(
        help_text="Array of items for current page"
    )

# =============================================================================
# Comment Serializers
# =============================================================================


class IncidentCommentSerializer(serializers.ModelSerializer):
    """Serializer for incident comments."""
    
    author_username = serializers.CharField(
        source="author.username",
        read_only=True,
        allow_null=True,
    )
    author_full_name = serializers.CharField(
        source="author.get_full_name",
        read_only=True,
        allow_null=True,
    )
    
    class Meta:
        model = IncidentComment
        fields = [
            "id",
            "incident",
            "author",
            "author_username",
            "author_full_name",
            "content",
            "comment_type",
            "is_pinned",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "author", "created_at", "updated_at"]


class IncidentCommentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating incident comments."""
    
    class Meta:
        model = IncidentComment
        fields = ["content", "comment_type", "is_pinned"]
        
    def validate_content(self, value):
        if not value or len(value.strip()) == 0:
            raise serializers.ValidationError("Content cannot be empty.")
        return value


# =============================================================================
# Tag Serializers
# =============================================================================


class TagSerializer(serializers.ModelSerializer):
    """Serializer for tags."""
    
    usage_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Tag
        fields = [
            "id",
            "name",
            "description",
            "color",
            "auto_apply_pattern",
            "is_active",
            "usage_count",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
    
    def get_usage_count(self, obj) -> int:
        return obj.incident_tags.count()


class IncidentTagSerializer(serializers.ModelSerializer):
    """Serializer for incident tags."""
    
    tag_name = serializers.CharField(source="tag.name", read_only=True)
    tag_color = serializers.CharField(source="tag.color", read_only=True)
    added_by_username = serializers.CharField(
        source="added_by.username",
        read_only=True,
        allow_null=True,
    )
    
    class Meta:
        model = IncidentTag
        fields = [
            "id",
            "tag",
            "tag_name",
            "tag_color",
            "added_by",
            "added_by_username",
            "added_at",
            "is_auto_applied",
        ]
        read_only_fields = ["id", "added_by", "added_at"]


class ApplyTagSerializer(serializers.Serializer):
    """Serializer for applying a tag to an incident."""
    tag_name = serializers.CharField(
        max_length=50,
        help_text="Name of the tag to apply (creates if not exists)"
    )


# =============================================================================
# Runbook Serializers
# =============================================================================


class RunbookStepSerializer(serializers.ModelSerializer):
    """Serializer for runbook steps."""
    
    class Meta:
        model = RunbookStep
        fields = [
            "id",
            "order",
            "title",
            "description",
            "command",
            "expected_duration_minutes",
            "is_critical",
            "requires_confirmation",
            "rollback_instructions",
        ]
        read_only_fields = ["id"]


class RunbookSerializer(serializers.ModelSerializer):
    """Serializer for runbooks."""
    
    steps = RunbookStepSerializer(many=True, read_only=True)
    service_name = serializers.CharField(
        source="service.name",
        read_only=True,
        allow_null=True,
    )
    author_username = serializers.CharField(
        source="author.username",
        read_only=True,
        allow_null=True,
    )
    
    class Meta:
        model = Runbook
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "service",
            "service_name",
            "alert_pattern",
            "severity_filter",
            "quick_actions",
            "external_docs",
            "version",
            "is_active",
            "usage_count",
            "steps",
            "author",
            "author_username",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "author", "created_at", "updated_at", "usage_count"]


class RunbookListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for runbook lists."""
    
    service_name = serializers.CharField(
        source="service.name",
        read_only=True,
        allow_null=True,
    )
    steps_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Runbook
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "service",
            "service_name",
            "is_active",
            "steps_count",
            "usage_count",
            "created_at",
        ]
    
    def get_steps_count(self, obj) -> int:
        return obj.steps.count()


# =============================================================================
# Escalation Serializers
# =============================================================================


class EscalationStepSerializer(serializers.ModelSerializer):
    """Serializer for escalation steps."""
    
    notify_user_name = serializers.CharField(
        source="notify_user.username",
        read_only=True,
        allow_null=True,
    )
    
    class Meta:
        model = EscalationStep
        fields = [
            "id",
            "order",
            "delay_minutes",
            "notify_type",
            "notify_user",
            "notify_user_name",
            "notification_channels",
        ]
        read_only_fields = ["id"]


class EscalationPolicySerializer(serializers.ModelSerializer):
    """Serializer for escalation policies."""
    
    steps = EscalationStepSerializer(many=True, read_only=True)
    team_name = serializers.CharField(
        source="team.name",
        read_only=True,
    )
    
    class Meta:
        model = EscalationPolicy
        fields = [
            "id",
            "name",
            "description",
            "team",
            "team_name",
            "severity_filter",
            "initial_delay_minutes",
            "repeat_interval_minutes",
            "max_escalations",
            "is_active",
            "steps",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class EscalationPolicyListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for escalation policy lists."""
    
    team_name = serializers.CharField(
        source="team.name",
        read_only=True,
    )
    steps_count = serializers.SerializerMethodField()
    
    class Meta:
        model = EscalationPolicy
        fields = [
            "id",
            "name",
            "team",
            "team_name",
            "initial_delay_minutes",
            "is_active",
            "steps_count",
        ]
    
    def get_steps_count(self, obj) -> int:
        return obj.steps.count()