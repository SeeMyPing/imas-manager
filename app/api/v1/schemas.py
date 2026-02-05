"""
IMAS Manager - API Schemas for OpenAPI Documentation

Additional serializers for webhook payloads and metrics responses.
"""
from __future__ import annotations

from rest_framework import serializers


# =============================================================================
# Webhook Request/Response Schemas
# =============================================================================


class AlertmanagerAlertSchema(serializers.Serializer):
    """Schema for a single Alertmanager alert."""
    status = serializers.ChoiceField(
        choices=["firing", "resolved"],
        help_text="Alert status"
    )
    labels = serializers.DictField(
        child=serializers.CharField(),
        help_text="Alert labels (alertname, severity, etc.)"
    )
    annotations = serializers.DictField(
        child=serializers.CharField(),
        help_text="Alert annotations (summary, description)"
    )
    startsAt = serializers.DateTimeField(help_text="When the alert started")
    endsAt = serializers.DateTimeField(
        required=False,
        help_text="When the alert ended (for resolved alerts)"
    )
    generatorURL = serializers.URLField(
        required=False,
        help_text="Link back to the alert source"
    )


class AlertmanagerWebhookRequestSchema(serializers.Serializer):
    """Schema for Prometheus Alertmanager webhook payload."""
    version = serializers.CharField(help_text="Alertmanager version")
    groupKey = serializers.CharField(help_text="Alert group key")
    status = serializers.ChoiceField(
        choices=["firing", "resolved"],
        help_text="Overall status of the alert group"
    )
    receiver = serializers.CharField(help_text="Receiver name")
    alerts = AlertmanagerAlertSchema(many=True, help_text="List of alerts")


class DatadogWebhookRequestSchema(serializers.Serializer):
    """Schema for Datadog webhook payload."""
    id = serializers.CharField(help_text="Event ID")
    title = serializers.CharField(help_text="Event title")
    body = serializers.CharField(required=False, help_text="Event body/description")
    priority = serializers.ChoiceField(
        choices=["normal", "low"],
        default="normal",
        help_text="Event priority"
    )
    tags = serializers.CharField(
        required=False,
        help_text="Comma-separated tags"
    )
    alert_type = serializers.ChoiceField(
        choices=["error", "warning", "info", "success"],
        help_text="Alert type/severity"
    )
    alert_status = serializers.ChoiceField(
        choices=["Triggered", "Recovered", "Re-Triggered", "Warn", "No Data"],
        help_text="Alert status"
    )
    hostname = serializers.CharField(required=False, help_text="Source hostname")
    url = serializers.URLField(required=False, help_text="Link to Datadog")


class GrafanaAlertSchema(serializers.Serializer):
    """Schema for a single Grafana alert."""
    status = serializers.ChoiceField(
        choices=["firing", "resolved"],
        help_text="Alert status"
    )
    labels = serializers.DictField(
        child=serializers.CharField(),
        help_text="Alert labels"
    )
    annotations = serializers.DictField(
        child=serializers.CharField(),
        help_text="Alert annotations"
    )
    startsAt = serializers.DateTimeField(help_text="When the alert started")
    endsAt = serializers.DateTimeField(required=False)
    generatorURL = serializers.URLField(required=False)
    fingerprint = serializers.CharField(required=False, help_text="Alert fingerprint")
    silenceURL = serializers.URLField(required=False)
    dashboardURL = serializers.URLField(required=False)
    panelURL = serializers.URLField(required=False)
    imageURL = serializers.URLField(required=False)


class GrafanaWebhookRequestSchema(serializers.Serializer):
    """Schema for Grafana webhook payload."""
    version = serializers.CharField(help_text="Schema version")
    groupKey = serializers.CharField(help_text="Alert group key")
    orgId = serializers.IntegerField(help_text="Grafana organization ID")
    status = serializers.ChoiceField(
        choices=["firing", "resolved"],
        help_text="Overall status"
    )
    receiver = serializers.CharField(help_text="Receiver name")
    alerts = GrafanaAlertSchema(many=True)
    title = serializers.CharField(required=False)
    message = serializers.CharField(required=False)


class CustomWebhookRequestSchema(serializers.Serializer):
    """Schema for generic/custom webhook payload."""
    source = serializers.CharField(
        required=False,
        help_text="Source system name"
    )
    alert_name = serializers.CharField(help_text="Alert name")
    status = serializers.ChoiceField(
        choices=["firing", "resolved"],
        default="firing",
        help_text="Alert status"
    )
    severity = serializers.ChoiceField(
        choices=["SEV1", "SEV2", "SEV3", "SEV4", "critical", "warning", "info"],
        required=False,
        help_text="Alert severity"
    )
    service = serializers.CharField(required=False, help_text="Service name")
    description = serializers.CharField(required=False, help_text="Alert description")
    labels = serializers.DictField(
        child=serializers.CharField(),
        required=False,
        help_text="Additional labels"
    )
    url = serializers.URLField(required=False, help_text="Link to source")


class WebhookResultSchema(serializers.Serializer):
    """Schema for a single webhook processing result."""
    alert_name = serializers.CharField()
    action = serializers.ChoiceField(
        choices=["created", "updated", "deduplicated", "skipped"],
        help_text="Action taken"
    )
    incident_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="Created or matched incident ID"
    )


class WebhookResponseSchema(serializers.Serializer):
    """Schema for webhook response."""
    status = serializers.CharField(help_text="Processing status")
    processed = serializers.IntegerField(help_text="Number of alerts processed")
    results = WebhookResultSchema(many=True, help_text="Processing results")


# =============================================================================
# Metrics Response Schemas
# =============================================================================


class MetricsSummarySchema(serializers.Serializer):
    """Schema for metrics summary response."""
    total_incidents = serializers.IntegerField(
        help_text="Total number of incidents"
    )
    open_incidents = serializers.IntegerField(
        help_text="Currently open incidents"
    )
    resolved_today = serializers.IntegerField(
        help_text="Incidents resolved today"
    )
    created_today = serializers.IntegerField(
        help_text="Incidents created today"
    )
    by_severity = serializers.DictField(
        child=serializers.IntegerField(),
        help_text="Incident count by severity level"
    )
    by_status = serializers.DictField(
        child=serializers.IntegerField(),
        help_text="Incident count by status"
    )
    mttr_avg_hours = serializers.FloatField(
        allow_null=True,
        help_text="Average MTTR in hours (last 30 days)"
    )
    mtta_avg_minutes = serializers.FloatField(
        allow_null=True,
        help_text="Average MTTA in minutes (last 30 days)"
    )


class ServiceMetricsSchema(serializers.Serializer):
    """Schema for per-service metrics."""
    service_id = serializers.UUIDField()
    service_name = serializers.CharField()
    total_incidents = serializers.IntegerField()
    open_incidents = serializers.IntegerField()
    avg_mttr_hours = serializers.FloatField(allow_null=True)
    last_incident_at = serializers.DateTimeField(allow_null=True)


class MetricsByServiceResponseSchema(serializers.Serializer):
    """Schema for metrics by service response."""
    services = ServiceMetricsSchema(many=True)
    period_start = serializers.DateTimeField()
    period_end = serializers.DateTimeField()


class TrendDataPointSchema(serializers.Serializer):
    """Schema for a single trend data point."""
    date = serializers.DateField()
    count = serializers.IntegerField()
    severity_sev1 = serializers.IntegerField(default=0)
    severity_sev2 = serializers.IntegerField(default=0)
    severity_sev3 = serializers.IntegerField(default=0)
    severity_sev4 = serializers.IntegerField(default=0)


class MetricsTrendResponseSchema(serializers.Serializer):
    """Schema for metrics trend response."""
    period = serializers.CharField(help_text="Trend period (7d, 30d, 90d)")
    data = TrendDataPointSchema(many=True)


class HeatmapDataSchema(serializers.Serializer):
    """Schema for heatmap data."""
    hour = serializers.IntegerField(min_value=0, max_value=23)
    day = serializers.IntegerField(
        min_value=0,
        max_value=6,
        help_text="Day of week (0=Monday)"
    )
    count = serializers.IntegerField()


class MetricsHeatmapResponseSchema(serializers.Serializer):
    """Schema for incident heatmap response."""
    data = HeatmapDataSchema(many=True)
    period_days = serializers.IntegerField()


class TopOffenderSchema(serializers.Serializer):
    """Schema for top offender service."""
    service_id = serializers.UUIDField()
    service_name = serializers.CharField()
    incident_count = serializers.IntegerField()
    sev1_count = serializers.IntegerField()
    sev2_count = serializers.IntegerField()
    total_downtime_hours = serializers.FloatField()


class MetricsTopOffendersResponseSchema(serializers.Serializer):
    """Schema for top offenders response."""
    period = serializers.CharField()
    services = TopOffenderSchema(many=True)
