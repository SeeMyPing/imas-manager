"""
IMAS Manager - Metrics Service

Service for calculating incident performance metrics:
- MTTA (Mean Time To Acknowledge)
- MTTR (Mean Time To Resolve)
- Incident counts by severity, service, team
- Trend analysis
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.db.models import Avg, Count, F, Q
from django.db.models.functions import ExtractHour, ExtractWeekDay, TruncDate, TruncWeek
from django.utils import timezone

if TYPE_CHECKING:
    from django.db.models import QuerySet

logger = logging.getLogger(__name__)


@dataclass
class MetricsSummary:
    """Summary of incident metrics for a time period."""
    
    # Counts
    total_incidents: int = 0
    sev1_count: int = 0
    sev2_count: int = 0
    sev3_count: int = 0
    sev4_count: int = 0
    
    # By status
    triggered_count: int = 0
    acknowledged_count: int = 0
    mitigated_count: int = 0
    resolved_count: int = 0
    
    # Time metrics (in minutes)
    avg_time_to_acknowledge: float | None = None
    avg_time_to_resolve: float | None = None
    
    # Percentiles
    p50_time_to_acknowledge: float | None = None
    p90_time_to_acknowledge: float | None = None
    p50_time_to_resolve: float | None = None
    p90_time_to_resolve: float | None = None
    
    # Comparison with previous period
    incident_count_change_pct: float | None = None
    mtta_change_pct: float | None = None
    mttr_change_pct: float | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "counts": {
                "total": self.total_incidents,
                "by_severity": {
                    "sev1_critical": self.sev1_count,
                    "sev2_high": self.sev2_count,
                    "sev3_medium": self.sev3_count,
                    "sev4_low": self.sev4_count,
                },
                "by_status": {
                    "triggered": self.triggered_count,
                    "acknowledged": self.acknowledged_count,
                    "mitigated": self.mitigated_count,
                    "resolved": self.resolved_count,
                },
            },
            "time_metrics": {
                "mtta_minutes": self.avg_time_to_acknowledge,
                "mttr_minutes": self.avg_time_to_resolve,
                "mtta_formatted": self._format_duration(self.avg_time_to_acknowledge),
                "mttr_formatted": self._format_duration(self.avg_time_to_resolve),
            },
            "percentiles": {
                "p50_tta": self.p50_time_to_acknowledge,
                "p90_tta": self.p90_time_to_acknowledge,
                "p50_ttr": self.p50_time_to_resolve,
                "p90_ttr": self.p90_time_to_resolve,
            },
            "trends": {
                "incident_count_change_pct": self.incident_count_change_pct,
                "mtta_change_pct": self.mtta_change_pct,
                "mttr_change_pct": self.mttr_change_pct,
            },
        }

    @staticmethod
    def _format_duration(minutes: float | None) -> str | None:
        """Format minutes as human-readable duration."""
        if minutes is None:
            return None
        
        if minutes < 60:
            return f"{int(minutes)}m"
        elif minutes < 1440:  # Less than 24 hours
            hours = int(minutes // 60)
            mins = int(minutes % 60)
            return f"{hours}h {mins}m"
        else:
            days = int(minutes // 1440)
            hours = int((minutes % 1440) // 60)
            return f"{days}d {hours}h"


@dataclass
class ServiceMetrics:
    """Metrics for a specific service."""
    service_id: str
    service_name: str
    incident_count: int = 0
    sev1_count: int = 0
    sev2_count: int = 0
    avg_mtta: float | None = None
    avg_mttr: float | None = None


@dataclass
class TrendDataPoint:
    """Single data point for trend analysis."""
    date: str
    incident_count: int = 0
    sev1_count: int = 0
    sev2_count: int = 0
    avg_mtta: float | None = None
    avg_mttr: float | None = None


class MetricsService:
    """
    Service for calculating and aggregating incident metrics.
    """

    def get_summary(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        service_id: str | None = None,
        team_id: str | None = None,
        include_comparison: bool = True,
    ) -> MetricsSummary:
        """
        Get summary metrics for a time period.
        
        Args:
            start_date: Start of period (default: 30 days ago)
            end_date: End of period (default: now)
            service_id: Filter by service
            team_id: Filter by team
            include_comparison: Include comparison with previous period
            
        Returns:
            MetricsSummary with calculated metrics
        """
        from core.models import Incident
        
        # Default to last 30 days
        if end_date is None:
            end_date = timezone.now()
        if start_date is None:
            start_date = end_date - timedelta(days=30)
        
        # Build base queryset
        queryset = Incident.objects.filter(
            created_at__gte=start_date,
            created_at__lte=end_date,
        )
        
        if service_id:
            queryset = queryset.filter(service_id=service_id)
        if team_id:
            queryset = queryset.filter(service__owner_team_id=team_id)
        
        summary = MetricsSummary()
        
        # Count by severity
        severity_counts = queryset.values("severity").annotate(count=Count("id"))
        for item in severity_counts:
            summary.total_incidents += item["count"]
            if "SEV1" in item["severity"]:
                summary.sev1_count = item["count"]
            elif "SEV2" in item["severity"]:
                summary.sev2_count = item["count"]
            elif "SEV3" in item["severity"]:
                summary.sev3_count = item["count"]
            elif "SEV4" in item["severity"]:
                summary.sev4_count = item["count"]
        
        # Count by status
        status_counts = queryset.values("status").annotate(count=Count("id"))
        for item in status_counts:
            if item["status"] == "TRIGGERED":
                summary.triggered_count = item["count"]
            elif item["status"] == "ACKNOWLEDGED":
                summary.acknowledged_count = item["count"]
            elif item["status"] == "MITIGATED":
                summary.mitigated_count = item["count"]
            elif item["status"] == "RESOLVED":
                summary.resolved_count = item["count"]
        
        # Calculate MTTA and MTTR
        time_metrics = self._calculate_time_metrics(queryset)
        summary.avg_time_to_acknowledge = time_metrics.get("mtta")
        summary.avg_time_to_resolve = time_metrics.get("mttr")
        summary.p50_time_to_acknowledge = time_metrics.get("p50_tta")
        summary.p90_time_to_acknowledge = time_metrics.get("p90_tta")
        summary.p50_time_to_resolve = time_metrics.get("p50_ttr")
        summary.p90_time_to_resolve = time_metrics.get("p90_ttr")
        
        # Calculate comparison with previous period
        if include_comparison:
            period_length = end_date - start_date
            prev_end = start_date
            prev_start = prev_end - period_length
            
            prev_summary = self.get_summary(
                start_date=prev_start,
                end_date=prev_end,
                service_id=service_id,
                team_id=team_id,
                include_comparison=False,
            )
            
            # Calculate percentage changes
            if prev_summary.total_incidents > 0:
                summary.incident_count_change_pct = (
                    (summary.total_incidents - prev_summary.total_incidents)
                    / prev_summary.total_incidents * 100
                )
            
            if prev_summary.avg_time_to_acknowledge and summary.avg_time_to_acknowledge:
                summary.mtta_change_pct = (
                    (summary.avg_time_to_acknowledge - prev_summary.avg_time_to_acknowledge)
                    / prev_summary.avg_time_to_acknowledge * 100
                )
            
            if prev_summary.avg_time_to_resolve and summary.avg_time_to_resolve:
                summary.mttr_change_pct = (
                    (summary.avg_time_to_resolve - prev_summary.avg_time_to_resolve)
                    / prev_summary.avg_time_to_resolve * 100
                )
        
        return summary

    def _calculate_time_metrics(self, queryset: "QuerySet") -> dict:
        """Calculate time-based metrics from queryset."""
        mtta_values = []
        mttr_values = []
        
        incidents = queryset.filter(
            Q(acknowledged_at__isnull=False) | Q(resolved_at__isnull=False)
        ).values("created_at", "acknowledged_at", "resolved_at")
        
        for incident in incidents:
            created = incident["created_at"]
            
            if incident["acknowledged_at"]:
                tta = (incident["acknowledged_at"] - created).total_seconds() / 60
                if tta >= 0:
                    mtta_values.append(tta)
            
            if incident["resolved_at"]:
                ttr = (incident["resolved_at"] - created).total_seconds() / 60
                if ttr >= 0:
                    mttr_values.append(ttr)
        
        result = {}
        
        if mtta_values:
            mtta_values.sort()
            result["mtta"] = sum(mtta_values) / len(mtta_values)
            result["p50_tta"] = mtta_values[len(mtta_values) // 2]
            result["p90_tta"] = mtta_values[int(len(mtta_values) * 0.9)]
        
        if mttr_values:
            mttr_values.sort()
            result["mttr"] = sum(mttr_values) / len(mttr_values)
            result["p50_ttr"] = mttr_values[len(mttr_values) // 2]
            result["p90_ttr"] = mttr_values[int(len(mttr_values) * 0.9)]
        
        return result

    def get_by_service(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 10,
    ) -> list[ServiceMetrics]:
        """
        Get metrics grouped by service.
        
        Args:
            start_date: Start of period
            end_date: End of period
            limit: Max number of services to return
            
        Returns:
            List of ServiceMetrics sorted by incident count
        """
        from core.models import Incident
        
        if end_date is None:
            end_date = timezone.now()
        if start_date is None:
            start_date = end_date - timedelta(days=30)
        
        queryset = Incident.objects.filter(
            created_at__gte=start_date,
            created_at__lte=end_date,
            service__isnull=False,
        )
        
        service_data = queryset.values(
            "service_id", "service__name"
        ).annotate(
            incident_count=Count("id"),
            sev1_count=Count("id", filter=Q(severity__icontains="SEV1")),
            sev2_count=Count("id", filter=Q(severity__icontains="SEV2")),
        ).order_by("-incident_count")[:limit]
        
        results = []
        for item in service_data:
            metrics = ServiceMetrics(
                service_id=str(item["service_id"]),
                service_name=item["service__name"],
                incident_count=item["incident_count"],
                sev1_count=item["sev1_count"],
                sev2_count=item["sev2_count"],
            )
            results.append(metrics)
        
        return results

    def get_trend(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        granularity: str = "day",
        service_id: str | None = None,
    ) -> list[TrendDataPoint]:
        """
        Get incident trend over time.
        
        Args:
            start_date: Start of period
            end_date: End of period
            granularity: "day" or "week"
            service_id: Filter by service
            
        Returns:
            List of TrendDataPoint
        """
        from core.models import Incident
        
        if end_date is None:
            end_date = timezone.now()
        if start_date is None:
            start_date = end_date - timedelta(days=30)
        
        queryset = Incident.objects.filter(
            created_at__gte=start_date,
            created_at__lte=end_date,
        )
        
        if service_id:
            queryset = queryset.filter(service_id=service_id)
        
        # Choose truncation based on granularity
        if granularity == "week":
            trunc_func = TruncWeek("created_at")
        else:
            trunc_func = TruncDate("created_at")
        
        trend_data = queryset.annotate(
            period=trunc_func
        ).values("period").annotate(
            incident_count=Count("id"),
            sev1_count=Count("id", filter=Q(severity__icontains="SEV1")),
            sev2_count=Count("id", filter=Q(severity__icontains="SEV2")),
        ).order_by("period")
        
        results = []
        for item in trend_data:
            point = TrendDataPoint(
                date=item["period"].isoformat() if item["period"] else "",
                incident_count=item["incident_count"],
                sev1_count=item["sev1_count"],
                sev2_count=item["sev2_count"],
            )
            results.append(point)
        
        return results

    def get_heatmap(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict]:
        """
        Get incident heatmap data (day of week x hour of day).
        
        Returns:
            List of {day_of_week, hour, count}
        """
        from core.models import Incident
        
        if end_date is None:
            end_date = timezone.now()
        if start_date is None:
            start_date = end_date - timedelta(days=90)
        
        queryset = Incident.objects.filter(
            created_at__gte=start_date,
            created_at__lte=end_date,
        )
        
        heatmap_data = queryset.annotate(
            day_of_week=ExtractWeekDay("created_at"),
            hour=ExtractHour("created_at"),
        ).values("day_of_week", "hour").annotate(
            count=Count("id")
        ).order_by("day_of_week", "hour")
        
        # Django weekday: 1=Sunday, 2=Monday, ... 7=Saturday
        day_names = {
            1: "Sunday",
            2: "Monday",
            3: "Tuesday",
            4: "Wednesday",
            5: "Thursday",
            6: "Friday",
            7: "Saturday",
        }
        
        results = []
        for item in heatmap_data:
            results.append({
                "day": day_names.get(item["day_of_week"], "Unknown"),
                "day_index": item["day_of_week"],
                "hour": item["hour"],
                "count": item["count"],
            })
        
        return results

    def get_top_offenders(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """
        Get services with most high-severity incidents.
        
        Returns:
            List of {service_name, sev1_count, sev2_count, total}
        """
        from core.models import Incident
        
        if end_date is None:
            end_date = timezone.now()
        if start_date is None:
            start_date = end_date - timedelta(days=30)
        
        queryset = Incident.objects.filter(
            created_at__gte=start_date,
            created_at__lte=end_date,
            service__isnull=False,
        ).filter(
            Q(severity__icontains="SEV1") | Q(severity__icontains="SEV2")
        )
        
        data = queryset.values(
            "service__name"
        ).annotate(
            sev1_count=Count("id", filter=Q(severity__icontains="SEV1")),
            sev2_count=Count("id", filter=Q(severity__icontains="SEV2")),
            total=Count("id"),
        ).order_by("-total")[:limit]
        
        return list(data)


# Singleton instance
metrics_service = MetricsService()
