"""
IMAS Manager - Dashboard Views

Web views for incident management interface.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Avg, Count, Q
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import (
    CreateView,
    DetailView,
    FormView,
    ListView,
    TemplateView,
)

from core.choices import IncidentSeverity, IncidentStatus
from core.models import Incident, IncidentEvent, Service, Team
from services.orchestrator import orchestrator

from .forms import IncidentCreateForm, IncidentNoteForm, IncidentResolveForm

logger = logging.getLogger(__name__)


class DashboardHomeView(LoginRequiredMixin, TemplateView):
    """
    Dashboard home page with KPIs and active incidents overview.
    """

    template_name = "dashboard/home_tailwind.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        last_30_days = now - timedelta(days=30)

        # Active incidents
        active_statuses = [IncidentStatus.TRIGGERED, IncidentStatus.ACKNOWLEDGED]
        active_incidents = Incident.objects.filter(
            status__in=active_statuses
        ).select_related("service", "service__owner_team", "lead").order_by("-created_at")

        # Critical incidents (SEV1/SEV2)
        critical_incidents = active_incidents.filter(
            severity__in=[IncidentSeverity.SEV1_CRITICAL, IncidentSeverity.SEV2_HIGH]
        )

        # KPIs - Last 30 days
        resolved_incidents = Incident.objects.filter(
            status=IncidentStatus.RESOLVED,
            resolved_at__gte=last_30_days,
        )

        # Calculate average MTTR (in hours)
        mttr_data = []
        for incident in resolved_incidents:
            if incident.resolved_at and incident.created_at:
                delta = (incident.resolved_at - incident.created_at).total_seconds()
                mttr_data.append(delta / 3600)  # Convert to hours

        avg_mttr = sum(mttr_data) / len(mttr_data) if mttr_data else 0

        # Incident counts by severity
        severity_counts = (
            Incident.objects.filter(created_at__gte=last_30_days)
            .values("severity")
            .annotate(count=Count("id"))
        )
        severity_stats = {item["severity"]: item["count"] for item in severity_counts}

        # Recent incidents (last 10)
        recent_incidents = Incident.objects.select_related(
            "service", "service__owner_team", "lead"
        ).order_by("-created_at")[:10]

        context.update({
            "active_incidents": active_incidents,
            "active_count": active_incidents.count(),
            "critical_incidents": critical_incidents,
            "critical_count": critical_incidents.count(),
            "resolved_count_30d": resolved_incidents.count(),
            "avg_mttr_hours": round(avg_mttr, 2),
            "severity_stats": severity_stats,
            "recent_incidents": recent_incidents,
            "total_incidents_30d": Incident.objects.filter(
                created_at__gte=last_30_days
            ).count(),
        })

        return context


class IncidentListView(LoginRequiredMixin, ListView):
    """
    List all incidents with filtering and pagination.
    """

    model = Incident
    template_name = "dashboard/incidents/list_tailwind.html"
    context_object_name = "incidents"
    paginate_by = 20

    def get(self, request, *args, **kwargs):
        # Handle CSV export
        if request.GET.get("export") == "csv":
            return self.export_csv()
        return super().get(request, *args, **kwargs)
    
    def export_csv(self):
        import csv
        from django.http import HttpResponse
        
        queryset = self.get_queryset()
        
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="incidents.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            "ID", "Titre", "Service", "Sévérité", "Statut", 
            "Lead", "Créé", "Acquitté", "Résolu"
        ])
        
        for incident in queryset[:500]:  # Limit to 500 rows
            writer.writerow([
                incident.short_id,
                incident.title,
                incident.service.name if incident.service else "",
                incident.get_severity_display(),
                incident.get_status_display(),
                incident.lead.username if incident.lead else "",
                incident.created_at.strftime("%Y-%m-%d %H:%M") if incident.created_at else "",
                incident.acknowledged_at.strftime("%Y-%m-%d %H:%M") if incident.acknowledged_at else "",
                incident.resolved_at.strftime("%Y-%m-%d %H:%M") if incident.resolved_at else "",
            ])
        
        return response

    def get_queryset(self):
        queryset = Incident.objects.select_related(
            "service", "service__owner_team", "lead"
        ).order_by("-created_at")

        # Filter by status
        status = self.request.GET.get("status")
        if status:
            queryset = queryset.filter(status=status)

        # Filter by severity
        severity = self.request.GET.get("severity")
        if severity:
            queryset = queryset.filter(severity=severity)

        # Filter by service
        service_id = self.request.GET.get("service")
        if service_id:
            queryset = queryset.filter(service_id=service_id)

        # Search by title or ID
        search = self.request.GET.get("q")
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(id__icontains=search)
            )

        return queryset

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["services"] = Service.objects.all()
        context["statuses"] = IncidentStatus.choices
        context["severities"] = IncidentSeverity.choices
        context["current_filters"] = {
            "status": self.request.GET.get("status", ""),
            "severity": self.request.GET.get("severity", ""),
            "service": self.request.GET.get("service", ""),
            "q": self.request.GET.get("q", ""),
        }
        # Stats for status bar
        context["stats"] = {
            "triggered": Incident.objects.filter(status=IncidentStatus.TRIGGERED).count(),
            "acknowledged": Incident.objects.filter(status=IncidentStatus.ACKNOWLEDGED).count(),
            "resolved": Incident.objects.filter(status=IncidentStatus.RESOLVED).count(),
        }
        return context


class IncidentDetailView(LoginRequiredMixin, DetailView):
    """
    Detailed view of a single incident with timeline.
    """

    model = Incident
    template_name = "dashboard/incidents/detail_tailwind.html"
    context_object_name = "incident"

    def get_queryset(self):
        return Incident.objects.select_related(
            "service", "service__owner_team", "lead"
        ).prefetch_related("impacted_scopes", "events")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        incident = self.object

        # Timeline events
        context["events"] = incident.events.select_related(
            "created_by"
        ).order_by("-timestamp")

        # Forms for actions
        context["note_form"] = IncidentNoteForm()
        context["resolve_form"] = IncidentResolveForm()

        # Status checks for UI
        context["can_acknowledge"] = incident.status == IncidentStatus.TRIGGERED
        context["can_resolve"] = incident.status in [
            IncidentStatus.TRIGGERED,
            IncidentStatus.ACKNOWLEDGED,
        ]

        # KPI calculations
        if incident.detected_at and incident.created_at:
            context["mttd_seconds"] = (
                incident.created_at - incident.detected_at
            ).total_seconds()
        if incident.acknowledged_at and incident.created_at:
            context["mtta_seconds"] = (
                incident.acknowledged_at - incident.created_at
            ).total_seconds()
        if incident.resolved_at and incident.created_at:
            context["mttr_seconds"] = (
                incident.resolved_at - incident.created_at
            ).total_seconds()

        return context


class IncidentCreateView(LoginRequiredMixin, CreateView):
    """
    Create a new incident via web form.
    """

    model = Incident
    form_class = IncidentCreateForm
    template_name = "dashboard/incidents/create_tailwind.html"

    def form_valid(self, form: IncidentCreateForm) -> HttpResponse:
        # Use orchestrator to create incident
        data = {
            "title": form.cleaned_data["title"],
            "description": form.cleaned_data["description"],
            "service": form.cleaned_data["service"],
            "severity": form.cleaned_data["severity"],
            "impacted_scopes": form.cleaned_data.get("impacted_scopes", []),
        }

        incident = orchestrator.create_incident(
            data=data,
            user=self.request.user,
            trigger_orchestration=True,
        )

        messages.success(
            self.request,
            f"Incident {incident.short_id} créé. "
            "La War Room et le Document sont en cours de génération..."
        )

        return redirect("dashboard:incident_detail", pk=incident.pk)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["services"] = Service.objects.filter(is_active=True)
        return context


class IncidentAcknowledgeView(LoginRequiredMixin, View):
    """
    Acknowledge an incident.
    """

    def post(self, request: HttpRequest, pk: str) -> HttpResponse:
        incident = get_object_or_404(Incident, pk=pk)

        if incident.status != IncidentStatus.TRIGGERED:
            messages.warning(request, "Cet incident ne peut pas être acquitté.")
            return redirect("dashboard:incident_detail", pk=pk)

        orchestrator.acknowledge_incident(incident, user=request.user)
        messages.success(request, f"Incident {incident.short_id} acquitté.")

        return redirect("dashboard:incident_detail", pk=pk)


class IncidentResolveView(LoginRequiredMixin, FormView):
    """
    Resolve an incident with optional resolution note.
    """

    form_class = IncidentResolveForm
    template_name = "dashboard/incidents/resolve_tailwind.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["incident"] = get_object_or_404(Incident, pk=self.kwargs["pk"])
        return context

    def form_valid(self, form: IncidentResolveForm) -> HttpResponse:
        incident = get_object_or_404(Incident, pk=self.kwargs["pk"])

        orchestrator.resolve_incident(
            incident,
            user=self.request.user,
            resolution_note=form.cleaned_data.get("resolution_note", ""),
        )

        messages.success(self.request, f"Incident {incident.short_id} résolu.")
        return redirect("dashboard:incident_detail", pk=incident.pk)


class IncidentAddNoteView(LoginRequiredMixin, View):
    """
    Add a note/comment to an incident timeline.
    """

    def post(self, request: HttpRequest, pk: str) -> HttpResponse:
        incident = get_object_or_404(Incident, pk=pk)
        form = IncidentNoteForm(request.POST)

        if form.is_valid():
            IncidentEvent.objects.create(
                incident=incident,
                type="NOTE",
                message=form.cleaned_data["message"],
                created_by=request.user,
            )
            messages.success(request, "Note ajoutée.")
        else:
            messages.error(request, "Erreur lors de l'ajout de la note.")

        return redirect("dashboard:incident_detail", pk=pk)


class ServiceListView(LoginRequiredMixin, ListView):
    """
    List all services in the catalog.
    """

    model = Service
    template_name = "dashboard/services/list_tailwind.html"
    context_object_name = "services"

    def get_queryset(self):
        return Service.objects.select_related("owner_team").filter(is_active=True)


class TeamListView(LoginRequiredMixin, ListView):
    """
    List all teams.
    """

    model = Team
    template_name = "dashboard/teams/list_tailwind.html"
    context_object_name = "teams"
