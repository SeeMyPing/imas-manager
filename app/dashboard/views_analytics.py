"""
IMAS Manager - Dashboard Analytics Views
"""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.views.generic import TemplateView

from services.metrics import MetricsService


class AnalyticsDashboardView(LoginRequiredMixin, TemplateView):
    """
    Main analytics dashboard with KPIs and charts.
    """
    
    template_name = "dashboard/analytics_tailwind.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Parse date range from query params
        days = int(self.request.GET.get("days", 30))
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)
        
        # Get service filter
        service_id = self.request.GET.get("service")
        
        # Initialize metrics service
        metrics_service = MetricsService()
        
        # Get summary metrics
        summary = metrics_service.get_summary(
            start_date=start_date,
            end_date=end_date,
            service_id=service_id,
        )
        
        # Get trend data for chart
        trend_data = metrics_service.get_trend(
            start_date=start_date,
            end_date=end_date,
            service_id=service_id,
            granularity="day" if days <= 30 else "week",
        )
        
        # Get heatmap data (doesn't support service_id filter)
        heatmap_data = metrics_service.get_heatmap(
            start_date=start_date,
            end_date=end_date,
        )
        
        # Get by-service breakdown
        service_metrics = metrics_service.get_by_service(
            start_date=start_date,
            end_date=end_date,
        )
        
        # Get top offenders
        top_offenders = metrics_service.get_top_offenders(
            start_date=start_date,
            end_date=end_date,
            limit=10,
        )
        
        # Format trend data for Chart.js
        trend_labels = [point.date for point in trend_data]
        trend_incidents = [point.incident_count for point in trend_data]
        trend_mtta = [point.avg_mtta for point in trend_data]
        trend_mttr = [point.avg_mttr for point in trend_data]
        
        # Format heatmap for Chart.js matrix
        heatmap_matrix = self._format_heatmap_matrix(heatmap_data)
        
        # Format service metrics for pie/bar chart
        service_labels = [m.service_name for m in service_metrics]
        service_counts = [m.incident_count for m in service_metrics]
        
        context.update({
            # Summary KPIs
            "summary": summary,
            
            # Date range
            "days": days,
            "start_date": start_date,
            "end_date": end_date,
            
            # Trend chart data
            "trend_labels": trend_labels,
            "trend_incidents": trend_incidents,
            "trend_mtta": trend_mtta,
            "trend_mttr": trend_mttr,
            
            # Heatmap data
            "heatmap_matrix": heatmap_matrix,
            
            # Service breakdown
            "service_labels": service_labels,
            "service_counts": service_counts,
            "service_metrics": service_metrics,
            
            # Top offenders
            "top_offenders": top_offenders,
            
            # Filters
            "selected_days": days,
            "days_options": [7, 14, 30, 60, 90],
        })
        
        return context
    
    def _format_heatmap_matrix(self, heatmap_data: list) -> list:
        """
        Format heatmap data for Chart.js matrix visualization.
        Returns a list of {x: hour, y: day, v: count} objects.
        """
        # Django weekday: 1=Sunday, 2=Monday, ..., 7=Saturday
        # Convertir en index lundi=0, ..., dimanche=6
        day_names = ["Dim", "Lun", "Mar", "Mer", "Jeu", "Ven", "Sam"]
        matrix = []
        
        for item in heatmap_data:
            day_index = item.get("day_index", item.get("day_of_week", 1))
            matrix.append({
                "x": item["hour"],
                "y": day_names[day_index - 1] if day_index else "?",
                "v": item["count"],
            })
        
        return matrix


class AnalyticsMTTAView(LoginRequiredMixin, TemplateView):
    """
    Detailed MTTA (Mean Time To Acknowledge) analytics.
    """
    
    template_name = "dashboard/analytics_mtta_tailwind.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        days = int(self.request.GET.get("days", 30))
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)
        
        metrics_service = MetricsService()
        
        # Get summary for MTTA focus
        summary = metrics_service.get_summary(
            start_date=start_date,
            end_date=end_date,
        )
        
        # Get trend data
        trend_data = metrics_service.get_trend(
            start_date=start_date,
            end_date=end_date,
            granularity="day" if days <= 30 else "week",
        )
        
        # Convert trend dataclasses to dicts for template JSON serialization
        import json
        trend_json = json.dumps([
            {"date": t.date, "avg_mtta": t.avg_mtta, "avg_mttr": t.avg_mttr}
            for t in trend_data
        ])
        
        # Get by-service MTTA
        service_metrics = metrics_service.get_by_service(
            start_date=start_date,
            end_date=end_date,
        )
        
        # Sort by MTTA (worst first)
        service_metrics_sorted = sorted(
            service_metrics,
            key=lambda x: x.avg_mtta or 0,
            reverse=True,
        )
        
        context.update({
            "summary": summary.to_dict() if hasattr(summary, 'to_dict') else {},
            "service_metrics": service_metrics_sorted,
            "trend_data": trend_json,
            "days": days,
            "start_date": start_date,
            "end_date": end_date,
        })
        
        return context


class AnalyticsMTTRView(LoginRequiredMixin, TemplateView):
    """
    Detailed MTTR (Mean Time To Resolve) analytics.
    """
    
    template_name = "dashboard/analytics_mttr_tailwind.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        days = int(self.request.GET.get("days", 30))
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)
        
        metrics_service = MetricsService()
        
        # Get summary for MTTR focus
        summary = metrics_service.get_summary(
            start_date=start_date,
            end_date=end_date,
        )
        
        # Get trend data
        trend_data = metrics_service.get_trend(
            start_date=start_date,
            end_date=end_date,
            granularity="day" if days <= 30 else "week",
        )
        
        # Convert trend dataclasses to dicts for template JSON serialization
        import json
        trend_json = json.dumps([
            {"date": t.date, "avg_mtta": t.avg_mtta, "avg_mttr": t.avg_mttr}
            for t in trend_data
        ])
        
        # Get by-service MTTR
        service_metrics = metrics_service.get_by_service(
            start_date=start_date,
            end_date=end_date,
        )
        
        # Sort by MTTR (worst first)
        service_metrics_sorted = sorted(
            service_metrics,
            key=lambda x: x.avg_mttr or 0,
            reverse=True,
        )
        
        context.update({
            "summary": summary.to_dict() if hasattr(summary, 'to_dict') else {},
            "service_metrics": service_metrics_sorted,
            "trend_data": trend_json,
            "days": days,
            "start_date": start_date,
            "end_date": end_date,
        })
        
        return context
