"""
IMAS Manager - Webhook Views for Alert Ingestion

API endpoints for receiving alerts from monitoring systems:
- Prometheus Alertmanager
- Datadog
- Grafana
- Generic/Custom webhooks
"""
from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.schemas import (
    AlertmanagerWebhookRequestSchema,
    CustomWebhookRequestSchema,
    DatadogWebhookRequestSchema,
    GrafanaWebhookRequestSchema,
    WebhookResponseSchema,
)
from services.alerting import AlertPayload, alert_service

logger = logging.getLogger(__name__)


class BaseWebhookView(APIView):
    """Base class for webhook endpoints."""
    
    # Webhooks are typically unauthenticated but use secrets
    permission_classes = [AllowAny]
    
    def validate_webhook_secret(self, request: Request) -> bool:
        """
        Validate webhook secret if configured.
        
        Override in subclasses for source-specific validation.
        """
        # TODO: Implement per-source secret validation
        return True

    def post(self, request: Request) -> Response:
        """Handle POST request from monitoring system."""
        if not self.validate_webhook_secret(request):
            return Response(
                {"error": "Invalid webhook secret"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        
        try:
            alerts = self.parse_alerts(request.data)
            results = []
            
            for alert in alerts:
                result = alert_service.process_alert(alert)
                results.append(result)
            
            return Response({
                "status": "ok",
                "processed": len(results),
                "results": results,
            })
        except Exception as e:
            logger.exception(f"Webhook processing error: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    def parse_alerts(self, data: dict) -> list[AlertPayload]:
        """
        Parse incoming webhook data into AlertPayload objects.
        
        Must be implemented by subclasses.
        """
        raise NotImplementedError


@extend_schema(
    tags=["webhooks"],
    summary="Alertmanager webhook",
    description="""
Receive alerts from Prometheus Alertmanager.

**Payload format:** Standard Alertmanager webhook format (v4).

**Processing:**
- Each alert in the payload is processed independently
- Severity is mapped from Alertmanager labels
- Duplicate alerts are deduplicated by service + severity
    """,
    request=AlertmanagerWebhookRequestSchema,
    responses={
        200: OpenApiResponse(
            response=WebhookResponseSchema,
            description="Alerts processed successfully",
        ),
        400: OpenApiResponse(description="Invalid payload"),
        401: OpenApiResponse(description="Invalid webhook secret"),
    },
    examples=[
        OpenApiExample(
            "Firing Alert",
            value={
                "version": "4",
                "groupKey": "{}:{alertname=\"HighLatency\"}",
                "status": "firing",
                "receiver": "imas",
                "alerts": [{
                    "status": "firing",
                    "labels": {
                        "alertname": "HighLatency",
                        "severity": "critical",
                        "service": "api-gateway"
                    },
                    "annotations": {
                        "summary": "High latency on API Gateway",
                        "description": "P99 latency > 500ms for 5 minutes"
                    },
                    "startsAt": "2024-01-15T10:00:00Z",
                    "generatorURL": "http://prometheus:9090/graph"
                }]
            },
            request_only=True,
        ),
    ],
)
class AlertmanagerWebhookView(BaseWebhookView):
    """
    Prometheus Alertmanager webhook receiver.
    """

    def parse_alerts(self, data: dict) -> list[AlertPayload]:
        """Parse Alertmanager webhook payload."""
        alerts = []
        
        for alert_data in data.get("alerts", []):
            labels = alert_data.get("labels", {})
            annotations = alert_data.get("annotations", {})
            
            alert = AlertPayload(
                source="ALERTMANAGER",
                alert_name=labels.get("alertname", "unknown"),
                status=alert_data.get("status", "firing"),
                labels=labels,
                annotations=annotations,
                starts_at=alert_data.get("startsAt"),
                ends_at=alert_data.get("endsAt"),
                generator_url=alert_data.get("generatorURL"),
            )
            alerts.append(alert)
        
        logger.info(f"Parsed {len(alerts)} alerts from Alertmanager")
        return alerts


@extend_schema(
    tags=["webhooks"],
    summary="Datadog webhook",
    description="""
Receive alerts from Datadog.

**Configuration:** In Datadog, create a webhook integration pointing to this endpoint.

**Processing:**
- Alert type is mapped to severity (error=SEV1, warning=SEV2)
- Tags are parsed and added as labels
    """,
    request=DatadogWebhookRequestSchema,
    responses={
        200: OpenApiResponse(response=WebhookResponseSchema),
        400: OpenApiResponse(description="Invalid payload"),
    },
)
class DatadogWebhookView(BaseWebhookView):
    """Datadog webhook receiver."""

    def parse_alerts(self, data: dict) -> list[AlertPayload]:
        """Parse Datadog webhook payload."""
        # Datadog sends a single alert per webhook
        alert_status = data.get("alert_status", "Triggered")
        
        # Map Datadog status to our status
        status_map = {
            "Triggered": "firing",
            "Recovered": "resolved",
            "Re-Triggered": "firing",
            "Warn": "firing",
            "No Data": "firing",
        }
        normalized_status = status_map.get(alert_status, "firing")
        
        # Build labels from Datadog fields
        labels = {
            "alertname": data.get("alert_title", data.get("title", "unknown")),
            "alert_type": data.get("alert_type", "error"),
            "priority": data.get("priority", "normal"),
            "hostname": data.get("hostname", ""),
        }
        
        # Parse tags
        tags_str = data.get("tags", "")
        if tags_str:
            for tag in tags_str.split(","):
                if ":" in tag:
                    key, value = tag.split(":", 1)
                    labels[key.strip()] = value.strip()
                else:
                    labels[tag.strip()] = "true"
        
        # Parse alert_scope
        scope = data.get("alert_scope", "")
        if scope:
            for part in scope.split(","):
                if ":" in part:
                    key, value = part.split(":", 1)
                    labels[key.strip()] = value.strip()
        
        # Map alert_type to severity
        severity_map = {
            "error": "critical",
            "warning": "warning",
            "info": "info",
            "success": "info",
        }
        labels["severity"] = severity_map.get(
            data.get("alert_type", "error"), "warning"
        )
        
        annotations = {
            "summary": data.get("title", ""),
            "description": data.get("body", ""),
        }
        
        alert = AlertPayload(
            source="DATADOG",
            alert_name=labels["alertname"],
            status=normalized_status,
            labels=labels,
            annotations=annotations,
            generator_url=data.get("url"),
        )
        
        logger.info(f"Parsed Datadog alert: {labels['alertname']}")
        return [alert]


@extend_schema(
    tags=["webhooks"],
    summary="Grafana webhook",
    description="""
Receive alerts from Grafana alerting.

**Supports:**
- Grafana Unified Alerting (v8+)
- Legacy Grafana alerting

**Configuration:** In Grafana, add a webhook contact point with this URL.
    """,
    request=GrafanaWebhookRequestSchema,
    responses={
        200: OpenApiResponse(response=WebhookResponseSchema),
        400: OpenApiResponse(description="Invalid payload"),
    },
)
class GrafanaWebhookView(BaseWebhookView):
    """Grafana alerting webhook receiver."""

    def parse_alerts(self, data: dict) -> list[AlertPayload]:
        """Parse Grafana webhook payload."""
        # Check if unified or legacy format
        if "alerts" in data:
            return self._parse_unified(data)
        else:
            return self._parse_legacy(data)

    def _parse_unified(self, data: dict) -> list[AlertPayload]:
        """Parse Grafana unified alerting format."""
        alerts = []
        common_labels = data.get("commonLabels", {})
        common_annotations = data.get("commonAnnotations", {})
        
        for alert_data in data.get("alerts", []):
            # Merge common and specific labels/annotations
            labels = {**common_labels, **alert_data.get("labels", {})}
            annotations = {**common_annotations, **alert_data.get("annotations", {})}
            
            alert = AlertPayload(
                source="GRAFANA",
                alert_name=labels.get("alertname", "unknown"),
                status=alert_data.get("status", "firing"),
                labels=labels,
                annotations=annotations,
                starts_at=alert_data.get("startsAt"),
                ends_at=alert_data.get("endsAt"),
                generator_url=alert_data.get("generatorURL") or alert_data.get("dashboardURL"),
            )
            alerts.append(alert)
        
        logger.info(f"Parsed {len(alerts)} alerts from Grafana (unified)")
        return alerts

    def _parse_legacy(self, data: dict) -> list[AlertPayload]:
        """Parse Grafana legacy alerting format."""
        state = data.get("state", "alerting")
        status_map = {
            "alerting": "firing",
            "ok": "resolved",
            "pending": "firing",
            "no_data": "firing",
            "paused": "resolved",
        }
        
        labels = {
            "alertname": data.get("ruleName", "unknown"),
            "rule_id": str(data.get("ruleId", "")),
        }
        
        # Add eval matches as labels
        for match in data.get("evalMatches", []):
            metric = match.get("metric", "value")
            labels[metric] = str(match.get("value", ""))
        
        annotations = {
            "summary": data.get("title", ""),
            "description": data.get("message", ""),
        }
        
        alert = AlertPayload(
            source="GRAFANA",
            alert_name=labels["alertname"],
            status=status_map.get(state, "firing"),
            labels=labels,
            annotations=annotations,
            generator_url=data.get("ruleUrl"),
        )
        
        logger.info(f"Parsed Grafana legacy alert: {labels['alertname']}")
        return [alert]


@extend_schema(
    tags=["webhooks"],
    summary="Custom webhook",
    description="""
Generic webhook receiver for custom integrations.

**Use cases:**
- Custom monitoring tools
- Internal alerting systems
- Integration with unsupported platforms

**Payload format:** Flexible JSON format with required `alert_name` field.
    """,
    request=CustomWebhookRequestSchema,
    responses={
        200: OpenApiResponse(response=WebhookResponseSchema),
        400: OpenApiResponse(description="Invalid payload"),
    },
    examples=[
        OpenApiExample(
            "Simple Alert",
            value={
                "alert_name": "HighCPUUsage",
                "status": "firing",
                "severity": "SEV2",
                "service": "web-frontend",
                "description": "CPU usage above 90% for 5 minutes"
            },
            request_only=True,
        ),
    ],
)
class CustomWebhookView(BaseWebhookView):
    """Generic/custom webhook receiver."""

    def parse_alerts(self, data: dict) -> list[AlertPayload]:
        """Parse custom webhook payload."""
        # Handle both single alert and array
        if isinstance(data, list):
            alerts_data = data
        elif "alerts" in data:
            alerts_data = data["alerts"]
        else:
            alerts_data = [data]
        
        alerts = []
        for alert_data in alerts_data:
            labels = alert_data.get("labels", {})
            
            # Add top-level fields to labels if not present
            if "severity" in alert_data and "severity" not in labels:
                labels["severity"] = alert_data["severity"]
            
            labels["alertname"] = alert_data.get(
                "alert_name",
                alert_data.get("name", labels.get("alertname", "custom_alert"))
            )
            
            annotations = {
                "summary": alert_data.get("title", alert_data.get("summary", "")),
                "description": alert_data.get("description", alert_data.get("message", "")),
            }
            
            alert = AlertPayload(
                source="CUSTOM",
                alert_name=labels["alertname"],
                status=alert_data.get("status", "firing"),
                labels=labels,
                annotations=annotations,
                generator_url=alert_data.get("url", alert_data.get("link")),
            )
            alerts.append(alert)
        
        logger.info(f"Parsed {len(alerts)} custom alerts")
        return alerts
