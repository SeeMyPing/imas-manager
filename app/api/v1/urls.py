"""
IMAS Manager - API v1 URL Configuration
"""
from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from api.v1 import views
from api.v1.features import (
    EscalationPolicyViewSet,
    IncidentCommentViewSet,
    IncidentTagViewSet,
    RunbookViewSet,
    TagViewSet,
)
from api.v1.metrics import (
    MetricsByServiceView,
    MetricsExportView,
    MetricsHeatmapView,
    MetricsSummaryView,
    MetricsTopOffendersView,
    MetricsTrendView,
)
from api.v1.slack import (
    SlackEventsView,
    SlackInteractiveView,
    SlackSlashCommandView,
)
from api.v1.webhooks import (
    AlertmanagerWebhookView,
    CustomWebhookView,
    DatadogWebhookView,
    GrafanaWebhookView,
)

app_name = "api_v1"

# Router for ViewSets
router = DefaultRouter()
router.register(r"runbooks", RunbookViewSet, basename="runbook")
router.register(r"tags", TagViewSet, basename="tag")
router.register(r"escalation-policies", EscalationPolicyViewSet, basename="escalation-policy")

# Nested routers for incident sub-resources
incident_comments_list = IncidentCommentViewSet.as_view({
    "get": "list",
    "post": "create",
})
incident_comments_detail = IncidentCommentViewSet.as_view({
    "get": "retrieve",
    "put": "update",
    "patch": "partial_update",
    "delete": "destroy",
})
incident_comments_pinned = IncidentCommentViewSet.as_view({
    "get": "pinned",
})
incident_comments_toggle_pin = IncidentCommentViewSet.as_view({
    "post": "toggle_pin",
})

incident_tags_list = IncidentTagViewSet.as_view({
    "get": "list",
    "post": "create",
})
incident_tags_detail = IncidentTagViewSet.as_view({
    "delete": "destroy",
})

urlpatterns = [
    # Health check
    path("health/", views.health_check, name="health_check"),
    
    # Incidents
    path("incidents/", views.IncidentListCreateView.as_view(), name="incident_list"),
    path("incidents/<uuid:pk>/", views.IncidentDetailView.as_view(), name="incident_detail"),
    path(
        "incidents/<uuid:pk>/acknowledge/",
        views.IncidentAcknowledgeView.as_view(),
        name="incident_acknowledge",
    ),
    path(
        "incidents/<uuid:pk>/resolve/",
        views.IncidentResolveView.as_view(),
        name="incident_resolve",
    ),
    
    # Services
    path("services/", views.ServiceListView.as_view(), name="service_list"),
    
    # Teams
    path("teams/", views.TeamListView.as_view(), name="team_list"),
    
    # Webhooks - Alert Ingestion
    path(
        "webhooks/alertmanager/",
        AlertmanagerWebhookView.as_view(),
        name="webhook_alertmanager",
    ),
    path(
        "webhooks/datadog/",
        DatadogWebhookView.as_view(),
        name="webhook_datadog",
    ),
    path(
        "webhooks/grafana/",
        GrafanaWebhookView.as_view(),
        name="webhook_grafana",
    ),
    path(
        "webhooks/custom/",
        CustomWebhookView.as_view(),
        name="webhook_custom",
    ),
    
    # Metrics & Analytics
    path(
        "metrics/summary/",
        MetricsSummaryView.as_view(),
        name="metrics_summary",
    ),
    path(
        "metrics/by-service/",
        MetricsByServiceView.as_view(),
        name="metrics_by_service",
    ),
    path(
        "metrics/trend/",
        MetricsTrendView.as_view(),
        name="metrics_trend",
    ),
    path(
        "metrics/heatmap/",
        MetricsHeatmapView.as_view(),
        name="metrics_heatmap",
    ),
    path(
        "metrics/top-offenders/",
        MetricsTopOffendersView.as_view(),
        name="metrics_top_offenders",
    ),
    path(
        "metrics/export/",
        MetricsExportView.as_view(),
        name="metrics_export",
    ),
    
    # Slack ChatOps
    path(
        "slack/commands/",
        SlackSlashCommandView.as_view(),
        name="slack_commands",
    ),
    path(
        "slack/interactive/",
        SlackInteractiveView.as_view(),
        name="slack_interactive",
    ),
    path(
        "slack/events/",
        SlackEventsView.as_view(),
        name="slack_events",
    ),
    
    # Incident Comments (nested resource)
    path(
        "incidents/<uuid:incident_id>/comments/",
        incident_comments_list,
        name="incident_comments_list",
    ),
    path(
        "incidents/<uuid:incident_id>/comments/pinned/",
        incident_comments_pinned,
        name="incident_comments_pinned",
    ),
    path(
        "incidents/<uuid:incident_id>/comments/<uuid:pk>/",
        incident_comments_detail,
        name="incident_comments_detail",
    ),
    path(
        "incidents/<uuid:incident_id>/comments/<uuid:pk>/toggle-pin/",
        incident_comments_toggle_pin,
        name="incident_comments_toggle_pin",
    ),
    
    # Incident Tags (nested resource)
    path(
        "incidents/<uuid:incident_id>/tags/",
        incident_tags_list,
        name="incident_tags_list",
    ),
    path(
        "incidents/<uuid:incident_id>/tags/<uuid:pk>/",
        incident_tags_detail,
        name="incident_tags_detail",
    ),
    
    # Router URLs (Runbooks, Tags, Escalation Policies)
    path("", include(router.urls)),
]
