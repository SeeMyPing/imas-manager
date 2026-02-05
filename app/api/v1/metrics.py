"""
IMAS Manager - Metrics API Views

API endpoints for incident metrics and analytics.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta

from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.schemas import (
    MetricsByServiceResponseSchema,
    MetricsHeatmapResponseSchema,
    MetricsSummarySchema,
    MetricsTopOffendersResponseSchema,
    MetricsTrendResponseSchema,
)
from services.metrics import metrics_service


@extend_schema(
    tags=["metrics"],
    summary="Metrics summary",
    description="""
Get aggregated metrics summary for incidents.

**Includes:**
- Total and open incident counts
- Incidents created/resolved today
- Breakdown by severity and status
- Average MTTA and MTTR
    """,
    parameters=[
        OpenApiParameter(
            name="start_date",
            description="Start date (ISO format, default: 30 days ago)",
            required=False,
            type=str,
        ),
        OpenApiParameter(
            name="end_date",
            description="End date (ISO format, default: now)",
            required=False,
            type=str,
        ),
        OpenApiParameter(
            name="service_id",
            description="Filter by service UUID",
            required=False,
            type=str,
        ),
        OpenApiParameter(
            name="team_id",
            description="Filter by team UUID",
            required=False,
            type=str,
        ),
    ],
    responses={
        200: OpenApiResponse(
            response=MetricsSummarySchema,
            description="Metrics summary",
        ),
    },
)
class MetricsSummaryView(APIView):
    """Get summary metrics for incidents."""
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        start_date = self._parse_date(request.query_params.get("start_date"))
        end_date = self._parse_date(request.query_params.get("end_date"))
        service_id = request.query_params.get("service_id")
        team_id = request.query_params.get("team_id")
        
        summary = metrics_service.get_summary(
            start_date=start_date,
            end_date=end_date,
            service_id=service_id,
            team_id=team_id,
        )
        
        return Response(summary.to_dict())

    def _parse_date(self, date_str: str | None) -> datetime | None:
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            return None


@extend_schema(
    tags=["metrics"],
    summary="Metrics by service",
    description="Get metrics grouped by service with incident counts and MTTR.",
    parameters=[
        OpenApiParameter(name="start_date", required=False, type=str),
        OpenApiParameter(name="end_date", required=False, type=str),
        OpenApiParameter(name="limit", description="Max services to return", required=False, type=int),
    ],
    responses={200: OpenApiResponse(response=MetricsByServiceResponseSchema)},
)
class MetricsByServiceView(APIView):
    """Get metrics grouped by service."""
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        start_date = self._parse_date(request.query_params.get("start_date"))
        end_date = self._parse_date(request.query_params.get("end_date"))
        limit = int(request.query_params.get("limit", 10))
        
        services = metrics_service.get_by_service(
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        
        data = [
            {
                "service_id": s.service_id,
                "service_name": s.service_name,
                "incident_count": s.incident_count,
                "sev1_count": s.sev1_count,
                "sev2_count": s.sev2_count,
            }
            for s in services
        ]
        
        return Response({"services": data})

    def _parse_date(self, date_str: str | None) -> datetime | None:
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            return None


@extend_schema(
    tags=["metrics"],
    summary="Incident trend",
    description="Get incident count trend over time.",
    parameters=[
        OpenApiParameter(name="start_date", required=False, type=str),
        OpenApiParameter(name="end_date", required=False, type=str),
        OpenApiParameter(name="granularity", enum=["day", "week"], required=False, type=str),
        OpenApiParameter(name="service_id", required=False, type=str),
    ],
    responses={200: OpenApiResponse(response=MetricsTrendResponseSchema)},
)
class MetricsTrendView(APIView):
    """Get incident trend over time."""
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        start_date = self._parse_date(request.query_params.get("start_date"))
        end_date = self._parse_date(request.query_params.get("end_date"))
        granularity = request.query_params.get("granularity", "day")
        service_id = request.query_params.get("service_id")
        
        trend = metrics_service.get_trend(
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
            service_id=service_id,
        )
        
        data = [
            {
                "date": t.date,
                "incident_count": t.incident_count,
                "sev1_count": t.sev1_count,
                "sev2_count": t.sev2_count,
            }
            for t in trend
        ]
        
        return Response({"trend": data, "granularity": granularity})

    def _parse_date(self, date_str: str | None) -> datetime | None:
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            return None


@extend_schema(
    tags=["metrics"],
    summary="Incident heatmap",
    description="Get incident distribution by day of week and hour for pattern analysis.",
    parameters=[
        OpenApiParameter(name="start_date", required=False, type=str),
        OpenApiParameter(name="end_date", required=False, type=str),
    ],
    responses={200: OpenApiResponse(response=MetricsHeatmapResponseSchema)},
)
class MetricsHeatmapView(APIView):
    """Get incident heatmap (day of week x hour of day)."""
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        start_date = self._parse_date(request.query_params.get("start_date"))
        end_date = self._parse_date(request.query_params.get("end_date"))
        
        heatmap = metrics_service.get_heatmap(
            start_date=start_date,
            end_date=end_date,
        )
        
        return Response({"heatmap": heatmap})

    def _parse_date(self, date_str: str | None) -> datetime | None:
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            return None


@extend_schema(
    tags=["metrics"],
    summary="Top offenders",
    description="Get services with most high-severity incidents.",
    parameters=[
        OpenApiParameter(name="start_date", required=False, type=str),
        OpenApiParameter(name="end_date", required=False, type=str),
        OpenApiParameter(name="limit", required=False, type=int),
    ],
    responses={200: OpenApiResponse(response=MetricsTopOffendersResponseSchema)},
)
class MetricsTopOffendersView(APIView):
    """Get services with most high-severity incidents."""
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        start_date = self._parse_date(request.query_params.get("start_date"))
        end_date = self._parse_date(request.query_params.get("end_date"))
        limit = int(request.query_params.get("limit", 5))
        
        offenders = metrics_service.get_top_offenders(
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        
        return Response({"top_offenders": offenders})

    def _parse_date(self, date_str: str | None) -> datetime | None:
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            return None


@extend_schema(
    tags=["metrics"],
    summary="Export metrics",
    description="Export incident data as CSV or JSON for external analysis.",
    parameters=[
        OpenApiParameter(name="start_date", required=False, type=str),
        OpenApiParameter(name="end_date", required=False, type=str),
        OpenApiParameter(name="format", enum=["csv", "json"], required=False, type=str),
        OpenApiParameter(name="service_id", required=False, type=str),
    ],
    responses={
        200: OpenApiResponse(
            description="Incident data in requested format",
        ),
    },
)
class MetricsExportView(APIView):
    """Export incident data as CSV or JSON."""
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response | HttpResponse:
        from core.models import Incident
        
        start_date = self._parse_date(request.query_params.get("start_date"))
        end_date = self._parse_date(request.query_params.get("end_date"))
        export_format = request.query_params.get("format", "json")
        service_id = request.query_params.get("service_id")
        
        # Default dates
        if end_date is None:
            end_date = timezone.now()
        if start_date is None:
            start_date = end_date - timedelta(days=30)
        
        # Build queryset
        queryset = Incident.objects.filter(
            created_at__gte=start_date,
            created_at__lte=end_date,
        ).select_related("service", "service__owner_team", "lead")
        
        if service_id:
            queryset = queryset.filter(service_id=service_id)
        
        queryset = queryset.order_by("-created_at")
        
        # Export data
        incidents_data = []
        for incident in queryset:
            data = {
                "id": str(incident.id),
                "short_id": incident.short_id,
                "title": incident.title,
                "severity": incident.severity,
                "status": incident.status,
                "service": incident.service.name if incident.service else "",
                "team": incident.service.owner_team.name if incident.service and incident.service.owner_team else "",
                "lead": incident.lead.get_full_name() if incident.lead else "",
                "created_at": incident.created_at.isoformat(),
                "acknowledged_at": incident.acknowledged_at.isoformat() if incident.acknowledged_at else "",
                "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else "",
                "time_to_acknowledge_min": self._calc_tta(incident),
                "time_to_resolve_min": self._calc_ttr(incident),
            }
            incidents_data.append(data)
        
        if export_format == "csv":
            return self._export_csv(incidents_data)
        else:
            return Response({
                "incidents": incidents_data,
                "count": len(incidents_data),
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                },
            })

    def _export_csv(self, data: list[dict]) -> HttpResponse:
        """Export data as CSV file."""
        if not data:
            return HttpResponse("No data", content_type="text/plain")
        
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
        
        response = HttpResponse(output.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="incidents_export.csv"'
        return response

    def _calc_tta(self, incident) -> float | None:
        """Calculate time to acknowledge in minutes."""
        if incident.acknowledged_at and incident.created_at:
            delta = incident.acknowledged_at - incident.created_at
            return round(delta.total_seconds() / 60, 2)
        return None

    def _calc_ttr(self, incident) -> float | None:
        """Calculate time to resolve in minutes."""
        if incident.resolved_at and incident.created_at:
            delta = incident.resolved_at - incident.created_at
            return round(delta.total_seconds() / 60, 2)
        return None

    def _parse_date(self, date_str: str | None) -> datetime | None:
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            return None
