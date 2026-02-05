"""
IMAS Manager - Django Admin Configuration

Provides a comprehensive admin interface for managing incidents, services, and teams.
Includes custom actions, filters, and dashboard statistics.
"""
from __future__ import annotations

import csv
from datetime import timedelta
from io import StringIO
from typing import Any

from django.contrib import admin, messages
from django.contrib.admin import SimpleListFilter
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.db.models import Avg, Count, Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.template.response import TemplateResponse
from django.urls import path
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from core.choices import IncidentSeverity, IncidentStatus
from core.models import (
    AlertFingerprint,
    AlertRule,
    AuditLog,
    EscalationPolicy,
    EscalationStep,
    ImpactScope,
    Incident,
    IncidentComment,
    IncidentEscalation,
    IncidentEvent,
    IncidentTag,
    NotificationProvider,
    OnCallSchedule,
    Runbook,
    RunbookStep,
    Service,
    Tag,
    Team,
)


# =============================================================================
# Custom Admin Site with Dashboard
# =============================================================================


class IMASAdminSite(admin.AdminSite):
    """Custom admin site with IMAS branding and dashboard."""
    
    site_header = "🚨 IMAS Manager"
    site_title = "IMAS Admin"
    index_title = "Incident Management Dashboard"
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("dashboard/", self.admin_view(self.dashboard_view), name="imas_dashboard"),
        ]
        return custom_urls + urls
    
    def dashboard_view(self, request: HttpRequest) -> TemplateResponse:
        """Admin dashboard with key metrics and statistics."""
        now = timezone.now()
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)
        last_30d = now - timedelta(days=30)
        
        # Active incidents
        active_incidents = Incident.objects.filter(
            status__in=[IncidentStatus.TRIGGERED, IncidentStatus.ACKNOWLEDGED, IncidentStatus.MITIGATED]
        )
        
        # Incident counts
        total_incidents_24h = Incident.objects.filter(created_at__gte=last_24h).count()
        total_incidents_7d = Incident.objects.filter(created_at__gte=last_7d).count()
        total_incidents_30d = Incident.objects.filter(created_at__gte=last_30d).count()
        
        # Severity breakdown (last 7 days)
        severity_breakdown = Incident.objects.filter(
            created_at__gte=last_7d
        ).values("severity").annotate(count=Count("id")).order_by("-count")
        
        # Top impacted services (last 30 days)
        top_services = Incident.objects.filter(
            created_at__gte=last_30d
        ).values("service__name").annotate(
            count=Count("id")
        ).order_by("-count")[:10]
        
        # MTTR average (resolved incidents last 30 days)
        resolved_incidents = Incident.objects.filter(
            status=IncidentStatus.RESOLVED,
            resolved_at__isnull=False,
            created_at__gte=last_30d,
        )
        
        mttr_values = [inc.mttr for inc in resolved_incidents if inc.mttr]
        avg_mttr = None
        if mttr_values:
            total_seconds = sum(m.total_seconds() for m in mttr_values)
            avg_mttr = timedelta(seconds=total_seconds / len(mttr_values))
        
        # Recent critical incidents
        recent_critical = Incident.objects.filter(
            severity=IncidentSeverity.SEV1_CRITICAL,
            created_at__gte=last_7d,
        ).order_by("-created_at")[:5]
        
        context = {
            **self.each_context(request),
            "title": "IMAS Dashboard",
            "active_incidents": active_incidents,
            "active_count": active_incidents.count(),
            "total_incidents_24h": total_incidents_24h,
            "total_incidents_7d": total_incidents_7d,
            "total_incidents_30d": total_incidents_30d,
            "severity_breakdown": severity_breakdown,
            "top_services": top_services,
            "avg_mttr": avg_mttr,
            "recent_critical": recent_critical,
        }
        
        return TemplateResponse(request, "admin/imas_dashboard.html", context)


# Create custom admin site instance
imas_admin_site = IMASAdminSite(name="imas_admin")


# =============================================================================
# Custom Filters
# =============================================================================


class ActiveIncidentFilter(SimpleListFilter):
    """Filter to show only active (non-resolved) incidents."""
    
    title = "Active Status"
    parameter_name = "active"
    
    def lookups(self, request: HttpRequest, model_admin) -> list[tuple[str, str]]:
        return [
            ("yes", "Active Only"),
            ("no", "Resolved Only"),
        ]
    
    def queryset(self, request: HttpRequest, queryset: QuerySet) -> QuerySet:
        if self.value() == "yes":
            return queryset.exclude(status=IncidentStatus.RESOLVED)
        if self.value() == "no":
            return queryset.filter(status=IncidentStatus.RESOLVED)
        return queryset


class SeverityCriticalFilter(SimpleListFilter):
    """Filter for critical/high severity incidents."""
    
    title = "Critical Priority"
    parameter_name = "critical"
    
    def lookups(self, request: HttpRequest, model_admin) -> list[tuple[str, str]]:
        return [
            ("sev1", "SEV1 - Critical"),
            ("sev1_sev2", "SEV1 + SEV2"),
        ]
    
    def queryset(self, request: HttpRequest, queryset: QuerySet) -> QuerySet:
        if self.value() == "sev1":
            return queryset.filter(severity=IncidentSeverity.SEV1_CRITICAL)
        if self.value() == "sev1_sev2":
            return queryset.filter(
                severity__in=[IncidentSeverity.SEV1_CRITICAL, IncidentSeverity.SEV2_HIGH]
            )
        return queryset


class RecentlyCreatedFilter(SimpleListFilter):
    """Filter for recently created incidents."""
    
    title = "Created"
    parameter_name = "created"
    
    def lookups(self, request: HttpRequest, model_admin) -> list[tuple[str, str]]:
        return [
            ("1h", "Last Hour"),
            ("24h", "Last 24 Hours"),
            ("7d", "Last 7 Days"),
            ("30d", "Last 30 Days"),
        ]
    
    def queryset(self, request: HttpRequest, queryset: QuerySet) -> QuerySet:
        now = timezone.now()
        if self.value() == "1h":
            return queryset.filter(created_at__gte=now - timedelta(hours=1))
        if self.value() == "24h":
            return queryset.filter(created_at__gte=now - timedelta(hours=24))
        if self.value() == "7d":
            return queryset.filter(created_at__gte=now - timedelta(days=7))
        if self.value() == "30d":
            return queryset.filter(created_at__gte=now - timedelta(days=30))
        return queryset


class HasWarRoomFilter(SimpleListFilter):
    """Filter for incidents with/without war room."""
    
    title = "War Room"
    parameter_name = "war_room"
    
    def lookups(self, request: HttpRequest, model_admin) -> list[tuple[str, str]]:
        return [
            ("yes", "Has War Room"),
            ("no", "No War Room"),
        ]
    
    def queryset(self, request: HttpRequest, queryset: QuerySet) -> QuerySet:
        if self.value() == "yes":
            return queryset.exclude(war_room_link="").exclude(war_room_link__isnull=True)
        if self.value() == "no":
            return queryset.filter(Q(war_room_link="") | Q(war_room_link__isnull=True))
        return queryset


class OnCallActiveFilter(SimpleListFilter):
    """Filter for currently active on-call schedules."""
    
    title = "Schedule Status"
    parameter_name = "schedule_active"
    
    def lookups(self, request: HttpRequest, model_admin) -> list[tuple[str, str]]:
        return [
            ("active", "Currently Active"),
            ("upcoming", "Upcoming (next 24h)"),
            ("past", "Past"),
        ]
    
    def queryset(self, request: HttpRequest, queryset: QuerySet) -> QuerySet:
        now = timezone.now()
        if self.value() == "active":
            return queryset.filter(start_time__lte=now, end_time__gte=now)
        if self.value() == "upcoming":
            return queryset.filter(
                start_time__gt=now,
                start_time__lte=now + timedelta(hours=24)
            )
        if self.value() == "past":
            return queryset.filter(end_time__lt=now)
        return queryset


# =============================================================================
# Inline Admin Classes
# =============================================================================


class IncidentEventInline(admin.TabularInline):
    """Inline display of incident events (audit log)."""
    
    model = IncidentEvent
    extra = 0
    readonly_fields = ("id", "type", "message", "timestamp", "created_by")
    ordering = ("-timestamp",)
    can_delete = False
    
    def has_add_permission(self, request: HttpRequest, obj=None) -> bool:
        return False


class ServiceInline(admin.TabularInline):
    """Inline display of services owned by a team."""
    
    model = Service
    extra = 0
    fields = ("name", "criticality", "runbook_url")
    readonly_fields = ("name",)
    show_change_link = True


class OnCallScheduleInline(admin.TabularInline):
    """Inline display of on-call schedules for a team."""
    
    model = OnCallSchedule
    extra = 1
    fields = ("user", "start_time", "end_time", "escalation_level", "notes")
    autocomplete_fields = ("user",)
    ordering = ("start_time", "escalation_level")


class LeadIncidentsInline(admin.TabularInline):
    """Inline display of incidents where user is lead."""
    
    model = Incident
    fk_name = "lead"
    extra = 0
    fields = ("short_id", "title", "severity", "status", "created_at")
    readonly_fields = ("short_id", "title", "severity", "status", "created_at")
    ordering = ("-created_at",)
    can_delete = False
    max_num = 10
    verbose_name = "Lead Incident"
    verbose_name_plural = "Lead Incidents (last 10)"
    
    def has_add_permission(self, request: HttpRequest, obj=None) -> bool:
        return False


# =============================================================================
# User Admin (Enhanced)
# =============================================================================


User = get_user_model()


class IMASUserAdmin(BaseUserAdmin):
    """Enhanced User admin with IMAS-specific information."""
    
    list_display = (
        "username", "email", "full_name", "is_active", "is_staff",
        "incident_lead_count", "on_call_teams_display", "last_login"
    )
    list_filter = BaseUserAdmin.list_filter + ("on_call_teams",)
    search_fields = ("username", "email", "first_name", "last_name")
    inlines = [LeadIncidentsInline]
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ("IMAS Information", {
            "fields": ("incident_stats_display",),
            "classes": ("collapse",),
        }),
    )
    readonly_fields = BaseUserAdmin.readonly_fields + ("incident_stats_display",)
    
    @admin.display(description="Name")
    def full_name(self, obj: User) -> str:
        name = obj.get_full_name()
        return name if name else obj.username
    
    @admin.display(description="Lead Incidents")
    def incident_lead_count(self, obj: User) -> int:
        return Incident.objects.filter(lead=obj).count()
    
    @admin.display(description="On-Call Teams")
    def on_call_teams_display(self, obj: User) -> str:
        teams = obj.on_call_teams.all()[:3]
        if teams:
            names = ", ".join(t.name for t in teams)
            if obj.on_call_teams.count() > 3:
                names += "..."
            return names
        return "-"
    
    @admin.display(description="Incident Statistics")
    def incident_stats_display(self, obj: User) -> str:
        total = Incident.objects.filter(lead=obj).count()
        active = Incident.objects.filter(
            lead=obj
        ).exclude(status=IncidentStatus.RESOLVED).count()
        resolved = total - active
        
        return format_html(
            '<div style="padding: 10px; background: #f8f9fa; border-radius: 4px;">'
            '<strong>Total Incidents Led:</strong> {}<br>'
            '<strong>Currently Active:</strong> <span style="color: #dc3545;">{}</span><br>'
            '<strong>Resolved:</strong> <span style="color: #28a745;">{}</span>'
            '</div>',
            total, active, resolved
        )


# Unregister default UserAdmin and register our custom one
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass
admin.site.register(User, IMASUserAdmin)


# =============================================================================
# Team Admin
# =============================================================================


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    """Admin interface for Team model."""
    
    list_display = (
        "name", "slug", "current_on_call_display", "email", 
        "slack_channel", "service_count", "created_at"
    )
    list_filter = ("created_at",)
    search_fields = ("name", "slug", "slack_channel", "email")
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ("current_on_call",)
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ServiceInline, OnCallScheduleInline]
    
    fieldsets = (
        (None, {
            "fields": ("id", "name", "slug", "description"),
        }),
        ("Contact", {
            "fields": ("email", "slack_channel", "slack_channel_id"),
        }),
        ("On-Call Configuration", {
            "fields": ("current_on_call", "escalation_timeout_minutes"),
            "description": "Configure on-call rotation. Use the schedule below for time-based rotation.",
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Services")
    def service_count(self, obj: Team) -> int:
        return obj.services.count()

    @admin.display(description="On-Call")
    def current_on_call_display(self, obj: Team) -> str:
        on_call = obj.get_current_on_call()
        if on_call:
            return on_call.username
        return "-"


# =============================================================================
# Service Admin
# =============================================================================


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    """Admin interface for Service model."""
    
    list_display = (
        "name", "owner_team", "criticality", "is_active",
        "has_runbook", "has_monitoring", "incident_count", "created_at"
    )
    list_filter = ("criticality", "is_active", "owner_team", "created_at")
    search_fields = ("name", "owner_team__name", "description")
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ("owner_team",)
    list_select_related = ("owner_team",)
    list_editable = ("is_active",)
    
    fieldsets = (
        (None, {
            "fields": ("id", "name", "description", "criticality", "is_active"),
        }),
        ("Ownership", {
            "fields": ("owner_team",),
        }),
        ("Documentation & Monitoring", {
            "fields": ("runbook_url", "repository_url", "monitoring_url"),
            "description": "Links to relevant resources for incident response.",
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Runbook", boolean=True)
    def has_runbook(self, obj: Service) -> bool:
        return bool(obj.runbook_url)

    @admin.display(description="Monitoring", boolean=True)
    def has_monitoring(self, obj: Service) -> bool:
        return bool(obj.monitoring_url)

    @admin.display(description="Incidents")
    def incident_count(self, obj: Service) -> int:
        return obj.incidents.count()


# =============================================================================
# ImpactScope Admin
# =============================================================================


@admin.register(ImpactScope)
class ImpactScopeAdmin(admin.ModelAdmin):
    """Admin interface for ImpactScope model."""
    
    list_display = ("name", "mandatory_notify_email", "is_active", "incident_count", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "description", "mandatory_notify_email")
    readonly_fields = ("id", "created_at", "updated_at")
    list_editable = ("is_active",)
    
    fieldsets = (
        (None, {
            "fields": ("id", "name", "is_active"),
        }),
        ("Details", {
            "fields": ("description", "mandatory_notify_email"),
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Incidents")
    def incident_count(self, obj: ImpactScope) -> int:
        return obj.incidents.count()


# =============================================================================
# Incident Admin
# =============================================================================


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    """Admin interface for Incident model with advanced actions and filters."""
    
    list_display = (
        "short_id_display",
        "title_truncated",
        "service",
        "severity_badge",
        "status_badge",
        "lead",
        "has_war_room",
        "has_lid",
        "age_display",
        "created_at",
    )
    list_filter = (
        ActiveIncidentFilter,
        SeverityCriticalFilter,
        RecentlyCreatedFilter,
        HasWarRoomFilter,
        "status",
        "severity",
        "service",
        "impacted_scopes",
    )
    search_fields = ("id", "title", "description", "service__name", "lead__username")
    readonly_fields = (
        "id",
        "short_id",
        "created_at",
        "acknowledged_at",
        "resolved_at",
        "mttd_display",
        "mtta_display",
        "mttr_display",
        "links_display",
    )
    autocomplete_fields = ("service", "lead")
    filter_horizontal = ("impacted_scopes",)
    list_select_related = ("service", "lead")
    date_hierarchy = "created_at"
    inlines = [IncidentEventInline]
    list_per_page = 25
    save_on_top = True
    
    fieldsets = (
        ("Incident", {
            "fields": ("id", "title", "description"),
        }),
        ("Classification", {
            "fields": ("service", "severity", "status", "impacted_scopes"),
        }),
        ("Assignment", {
            "fields": ("lead",),
        }),
        ("Automation", {
            "fields": ("links_display", "lid_link", "war_room_link", "war_room_id"),
        }),
        ("Timestamps & KPIs", {
            "fields": (
                "detected_at",
                "created_at",
                "acknowledged_at",
                "resolved_at",
                "mttd_display",
                "mtta_display",
                "mttr_display",
            ),
            "classes": ("collapse",),
        }),
    )
    
    actions = [
        "mark_as_acknowledged",
        "mark_as_resolved",
        "mark_as_mitigated",
        "rerun_orchestration",
        "export_as_csv",
        "assign_to_me",
    ]

    @admin.display(description="ID")
    def short_id_display(self, obj: Incident) -> str:
        return format_html(
            '<a href="/admin/core/incident/{}/change/" style="font-weight: bold;">INC-{}</a>',
            obj.id, obj.short_id
        )

    @admin.display(description="Title")
    def title_truncated(self, obj: Incident) -> str:
        return obj.title[:50] + "..." if len(obj.title) > 50 else obj.title

    @admin.display(description="Severity")
    def severity_badge(self, obj: Incident) -> str:
        colors = {
            "SEV1_CRITICAL": "#dc3545",
            "SEV2_HIGH": "#fd7e14",
            "SEV3_MEDIUM": "#ffc107",
            "SEV4_LOW": "#28a745",
        }
        color = colors.get(obj.severity, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.get_severity_display(),
        )

    @admin.display(description="Status")
    def status_badge(self, obj: Incident) -> str:
        colors = {
            "TRIGGERED": "#dc3545",
            "ACKNOWLEDGED": "#17a2b8",
            "MITIGATED": "#ffc107",
            "RESOLVED": "#28a745",
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="War Room", boolean=True)
    def has_war_room(self, obj: Incident) -> bool:
        return bool(obj.war_room_link)

    @admin.display(description="LID", boolean=True)
    def has_lid(self, obj: Incident) -> bool:
        return bool(obj.lid_link)

    @admin.display(description="Age")
    def age_display(self, obj: Incident) -> str:
        """Display incident age in human-readable format."""
        if obj.status == IncidentStatus.RESOLVED and obj.resolved_at:
            delta = obj.resolved_at - obj.created_at
        else:
            delta = timezone.now() - obj.created_at
        
        hours = delta.total_seconds() / 3600
        if hours < 1:
            return f"{int(delta.total_seconds() / 60)}m"
        elif hours < 24:
            return f"{int(hours)}h"
        else:
            return f"{int(hours / 24)}d"

    @admin.display(description="Links")
    def links_display(self, obj: Incident) -> str:
        """Display clickable links for LID and War Room."""
        links = []
        if obj.lid_link:
            links.append(format_html(
                '<a href="{}" target="_blank" style="margin-right: 10px;">📄 LID Document</a>',
                obj.lid_link
            ))
        if obj.war_room_link:
            links.append(format_html(
                '<a href="{}" target="_blank">💬 War Room</a>',
                obj.war_room_link
            ))
        if links:
            return mark_safe(" | ".join(str(l) for l in links))
        return "-"

    @admin.display(description="MTTD")
    def mttd_display(self, obj: Incident) -> str:
        return str(obj.mttd) if obj.mttd else "-"

    @admin.display(description="MTTA")
    def mtta_display(self, obj: Incident) -> str:
        return str(obj.mtta) if obj.mtta else "-"

    @admin.display(description="MTTR")
    def mttr_display(self, obj: Incident) -> str:
        return str(obj.mttr) if obj.mttr else "-"

    # -------------------------------------------------------------------------
    # Admin Actions
    # -------------------------------------------------------------------------

    @admin.action(description="✅ Mark as Acknowledged")
    def mark_as_acknowledged(self, request: HttpRequest, queryset: QuerySet[Incident]) -> None:
        updated = queryset.filter(status=IncidentStatus.TRIGGERED).update(
            status=IncidentStatus.ACKNOWLEDGED,
            acknowledged_at=timezone.now()
        )
        self.message_user(request, f"{updated} incident(s) marked as acknowledged.", messages.SUCCESS)

    @admin.action(description="🔧 Mark as Mitigated")
    def mark_as_mitigated(self, request: HttpRequest, queryset: QuerySet[Incident]) -> None:
        updated = queryset.filter(
            status__in=[IncidentStatus.TRIGGERED, IncidentStatus.ACKNOWLEDGED]
        ).update(status=IncidentStatus.MITIGATED)
        self.message_user(request, f"{updated} incident(s) marked as mitigated.", messages.SUCCESS)

    @admin.action(description="✔️ Mark as Resolved")
    def mark_as_resolved(self, request: HttpRequest, queryset: QuerySet[Incident]) -> None:
        updated = queryset.exclude(status=IncidentStatus.RESOLVED).update(
            status=IncidentStatus.RESOLVED,
            resolved_at=timezone.now()
        )
        self.message_user(request, f"{updated} incident(s) marked as resolved.", messages.SUCCESS)

    @admin.action(description="🔄 Re-run Orchestration")
    def rerun_orchestration(self, request: HttpRequest, queryset: QuerySet[Incident]) -> None:
        """Trigger orchestration task again for selected incidents."""
        try:
            from services.tasks import orchestrate_incident_task
            count = 0
            for incident in queryset:
                orchestrate_incident_task.delay(str(incident.id))
                count += 1
            self.message_user(
                request, 
                f"Orchestration queued for {count} incident(s).", 
                messages.SUCCESS
            )
        except ImportError:
            self.message_user(
                request,
                "Celery tasks not available. Cannot re-run orchestration.",
                messages.ERROR
            )

    @admin.action(description="👤 Assign to Me")
    def assign_to_me(self, request: HttpRequest, queryset: QuerySet[Incident]) -> None:
        """Assign selected incidents to current user."""
        updated = queryset.update(lead=request.user)
        self.message_user(
            request, 
            f"{updated} incident(s) assigned to {request.user.username}.", 
            messages.SUCCESS
        )

    @admin.action(description="📥 Export as CSV")
    def export_as_csv(self, request: HttpRequest, queryset: QuerySet[Incident]) -> HttpResponse:
        """Export selected incidents to CSV file."""
        output = StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            "ID", "Short ID", "Title", "Service", "Severity", "Status",
            "Lead", "Created At", "Acknowledged At", "Resolved At",
            "MTTD", "MTTA", "MTTR", "War Room", "LID"
        ])
        
        # Data rows
        for inc in queryset.select_related("service", "lead"):
            writer.writerow([
                str(inc.id),
                inc.short_id,
                inc.title,
                inc.service.name if inc.service else "",
                inc.get_severity_display(),
                inc.get_status_display(),
                inc.lead.username if inc.lead else "",
                inc.created_at.isoformat() if inc.created_at else "",
                inc.acknowledged_at.isoformat() if inc.acknowledged_at else "",
                inc.resolved_at.isoformat() if inc.resolved_at else "",
                str(inc.mttd) if inc.mttd else "",
                str(inc.mtta) if inc.mtta else "",
                str(inc.mttr) if inc.mttr else "",
                inc.war_room_link or "",
                inc.lid_link or "",
            ])
        
        response = HttpResponse(output.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="incidents_export.csv"'
        return response


# =============================================================================
# IncidentEvent Admin
# =============================================================================


@admin.register(IncidentEvent)
class IncidentEventAdmin(admin.ModelAdmin):
    """Admin interface for IncidentEvent model (read-only audit log)."""
    
    list_display = ("incident", "type", "message_truncated", "created_by", "timestamp")
    list_filter = ("type", "timestamp")
    search_fields = ("incident__title", "message")
    readonly_fields = ("id", "incident", "type", "message", "timestamp", "created_by")
    list_select_related = ("incident", "created_by")
    date_hierarchy = "timestamp"
    
    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    @admin.display(description="Message")
    def message_truncated(self, obj: IncidentEvent) -> str:
        return obj.message[:100] + "..." if len(obj.message) > 100 else obj.message


# =============================================================================
# NotificationProvider Admin
# =============================================================================


@admin.register(NotificationProvider)
class NotificationProviderAdmin(admin.ModelAdmin):
    """Admin interface for NotificationProvider model."""
    
    list_display = ("name", "type", "is_active", "config_keys", "created_at")
    list_filter = ("type", "is_active", "created_at")
    search_fields = ("name",)
    readonly_fields = ("id", "created_at", "updated_at")
    list_editable = ("is_active",)
    
    fieldsets = (
        (None, {
            "fields": ("id", "name", "type", "is_active"),
        }),
        ("Configuration", {
            "fields": ("config",),
            "description": "Store provider-specific configuration as JSON.",
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Config Keys")
    def config_keys(self, obj: NotificationProvider) -> str:
        if obj.config:
            keys = ", ".join(obj.config.keys())
            return keys[:50] + "..." if len(keys) > 50 else keys
        return "-"


# =============================================================================
# OnCallSchedule Admin
# =============================================================================


@admin.register(OnCallSchedule)
class OnCallScheduleAdmin(admin.ModelAdmin):
    """Admin interface for OnCallSchedule model."""
    
    list_display = (
        "user", "team", "start_time", "end_time", 
        "escalation_level", "is_active_display", "duration_display"
    )
    list_filter = (OnCallActiveFilter, "team", "escalation_level", "start_time")
    search_fields = ("user__username", "team__name", "notes")
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ("user", "team")
    list_select_related = ("user", "team")
    date_hierarchy = "start_time"
    ordering = ("-start_time", "escalation_level")
    actions = ["duplicate_schedule"]
    
    fieldsets = (
        (None, {
            "fields": ("id", "team", "user"),
        }),
        ("Schedule", {
            "fields": ("start_time", "end_time", "escalation_level"),
        }),
        ("Notes", {
            "fields": ("notes",),
            "classes": ("collapse",),
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Active", boolean=True)
    def is_active_display(self, obj: OnCallSchedule) -> bool:
        return obj.is_active

    @admin.display(description="Duration")
    def duration_display(self, obj: OnCallSchedule) -> str:
        hours = obj.duration_hours
        if hours >= 24:
            days = hours / 24
            return f"{days:.1f} days"
        return f"{hours:.1f} hours"

    @admin.action(description="📋 Duplicate for Next Week")
    def duplicate_schedule(self, request: HttpRequest, queryset: QuerySet[OnCallSchedule]) -> None:
        """Duplicate selected schedules shifted by 7 days."""
        count = 0
        for schedule in queryset:
            OnCallSchedule.objects.create(
                team=schedule.team,
                user=schedule.user,
                start_time=schedule.start_time + timedelta(days=7),
                end_time=schedule.end_time + timedelta(days=7),
                escalation_level=schedule.escalation_level,
                notes=f"(Duplicated) {schedule.notes}" if schedule.notes else "(Duplicated)",
            )
            count += 1
        self.message_user(
            request, 
            f"Created {count} schedule(s) for next week.", 
            messages.SUCCESS
        )


# =============================================================================
# Alerting Admin
# =============================================================================


@admin.register(AlertFingerprint)
class AlertFingerprintAdmin(admin.ModelAdmin):
    """Admin interface for AlertFingerprint model."""
    
    list_display = (
        "alert_name",
        "source",
        "status",
        "fire_count",
        "incident_link",
        "first_fired_at",
        "last_fired_at",
    )
    list_filter = ("source", "status", "first_fired_at")
    search_fields = ("alert_name", "fingerprint", "labels")
    readonly_fields = (
        "id", "fingerprint", "first_fired_at", "last_fired_at", 
        "resolved_at", "fire_count"
    )
    raw_id_fields = ("incident",)
    date_hierarchy = "last_fired_at"
    ordering = ("-last_fired_at",)
    
    fieldsets = (
        (None, {
            "fields": ("id", "fingerprint", "source", "alert_name", "status"),
        }),
        ("Details", {
            "fields": ("labels", "annotations"),
            "classes": ("collapse",),
        }),
        ("Incident", {
            "fields": ("incident", "auto_create_incident"),
        }),
        ("Timestamps", {
            "fields": ("fire_count", "first_fired_at", "last_fired_at", "resolved_at"),
        }),
    )

    @admin.display(description="Incident")
    def incident_link(self, obj: AlertFingerprint) -> str:
        if obj.incident:
            return format_html(
                '<a href="/admin/core/incident/{}/change/">{}</a>',
                obj.incident.id,
                obj.incident.short_id,
            )
        return "-"


@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    """Admin interface for AlertRule model."""
    
    list_display = (
        "name",
        "source",
        "alert_name_pattern",
        "target_service",
        "default_severity",
        "auto_create",
        "is_active",
    )
    list_filter = ("source", "is_active", "auto_create", "auto_resolve")
    search_fields = ("name", "description", "alert_name_pattern")
    readonly_fields = ("id", "created_at", "updated_at")
    raw_id_fields = ("target_service",)
    list_editable = ("is_active",)
    ordering = ("-created_at",)
    
    fieldsets = (
        (None, {
            "fields": ("id", "name", "description", "is_active"),
        }),
        ("Matching Criteria", {
            "fields": ("source", "alert_name_pattern", "label_matchers"),
        }),
        ("Incident Settings", {
            "fields": (
                "target_service", "severity_mapping", "default_severity",
                "auto_create", "auto_resolve", "suppress_duplicates_minutes"
            ),
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


# =============================================================================
# Audit Log Admin
# =============================================================================


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Admin for viewing audit logs (read-only)."""
    
    list_display = (
        "timestamp",
        "username",
        "action",
        "resource_type",
        "resource_id",
        "ip_address",
        "success_badge",
    )
    list_filter = ("action", "success", "resource_type", "timestamp")
    search_fields = ("username", "resource_id", "description", "ip_address")
    readonly_fields = (
        "id", "timestamp", "user", "username", "action",
        "resource_type", "resource_id", "description", "changes",
        "ip_address", "user_agent", "request_method", "request_path",
        "success", "error_message",
    )
    date_hierarchy = "timestamp"
    ordering = ("-timestamp",)
    
    def has_add_permission(self, request: HttpRequest) -> bool:
        """Audit logs are created automatically, not manually."""
        return False
    
    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        """Audit logs are immutable."""
        return False
    
    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        """Only superusers can delete audit logs."""
        return request.user.is_superuser
    
    @admin.display(description="Status")
    def success_badge(self, obj: AuditLog) -> str:
        if obj.success:
            return format_html(
                '<span style="color: #22c55e; font-weight: bold;">✓</span>'
            )
        return format_html(
            '<span style="color: #ef4444; font-weight: bold;">✗</span>'
        )


# =============================================================================
# Runbook Admin
# =============================================================================


class RunbookStepInline(admin.TabularInline):
    """Inline admin for runbook steps."""
    
    model = RunbookStep
    extra = 1
    fields = ("order", "title", "description", "is_critical", "expected_duration_minutes")
    ordering = ("order",)


@admin.register(Runbook)
class RunbookAdmin(admin.ModelAdmin):
    """Admin for managing runbooks."""
    
    list_display = (
        "name",
        "service",
        "steps_count",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "service", "service__owner_team")
    search_fields = ("name", "description", "alert_pattern")
    readonly_fields = ("id", "created_at", "updated_at", "usage_count", "last_used_at")
    raw_id_fields = ("service", "author")
    list_editable = ("is_active",)
    inlines = [RunbookStepInline]
    ordering = ("-created_at",)
    
    fieldsets = (
        (None, {
            "fields": ("id", "name", "slug", "description", "is_active"),
        }),
        ("Targeting", {
            "fields": ("service", "alert_pattern", "severity_filter"),
            "description": "Match runbook to services and alert patterns",
        }),
        ("Actions", {
            "fields": ("quick_actions", "external_docs"),
            "classes": ("collapse",),
        }),
        ("Metadata", {
            "fields": ("author", "version", "usage_count", "last_used_at", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )
    
    @admin.display(description="Steps")
    def steps_count(self, obj: Runbook) -> int:
        return obj.steps.count()


@admin.register(RunbookStep)
class RunbookStepAdmin(admin.ModelAdmin):
    """Admin for runbook steps."""
    
    list_display = ("title", "runbook", "order", "is_critical", "expected_duration_minutes")
    list_filter = ("is_critical", "runbook")
    search_fields = ("title", "description", "command")
    readonly_fields = ("id",)
    raw_id_fields = ("runbook",)
    ordering = ("runbook", "order")


# =============================================================================
# Tag Admin
# =============================================================================


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    """Admin for managing tags."""
    
    list_display = (
        "name",
        "color_preview",
        "usage_count",
        "auto_apply_pattern",
        "is_active",
    )
    list_filter = ("is_active",)
    search_fields = ("name", "description", "auto_apply_pattern")
    readonly_fields = ("id", "created_at")
    list_editable = ("is_active",)
    ordering = ("name",)
    
    fieldsets = (
        (None, {
            "fields": ("id", "name", "description", "color", "is_active"),
        }),
        ("Auto-Apply", {
            "fields": ("auto_apply_pattern",),
            "description": "Regex pattern to auto-apply this tag to matching incidents",
        }),
        ("Metadata", {
            "fields": ("created_at",),
            "classes": ("collapse",),
        }),
    )
    
    @admin.display(description="Color")
    def color_preview(self, obj: Tag) -> str:
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 4px;">{}</span>',
            obj.color,
            obj.color
        )
    
    @admin.display(description="Usage")
    def usage_count(self, obj: Tag) -> int:
        return obj.incident_tags.count()


# =============================================================================
# Incident Comment Admin
# =============================================================================


@admin.register(IncidentComment)
class IncidentCommentAdmin(admin.ModelAdmin):
    """Admin for incident comments."""
    
    list_display = (
        "short_content",
        "incident",
        "author",
        "comment_type",
        "is_pinned",
        "created_at",
    )
    list_filter = ("comment_type", "is_pinned", "created_at")
    search_fields = ("content", "incident__title", "author__username")
    readonly_fields = ("id", "created_at", "updated_at")
    raw_id_fields = ("incident", "author")
    ordering = ("-created_at",)
    
    @admin.display(description="Content")
    def short_content(self, obj: IncidentComment) -> str:
        return obj.content[:80] + "..." if len(obj.content) > 80 else obj.content


# =============================================================================
# Escalation Policy Admin
# =============================================================================


class EscalationStepInline(admin.TabularInline):
    """Inline admin for escalation steps."""
    
    model = EscalationStep
    extra = 1
    fields = ("order", "delay_minutes", "notify_type", "notify_user", "notification_channels")
    raw_id_fields = ("notify_user",)
    ordering = ("order",)


@admin.register(EscalationPolicy)
class EscalationPolicyAdmin(admin.ModelAdmin):
    """Admin for escalation policies."""
    
    list_display = (
        "name",
        "team",
        "initial_delay_minutes",
        "steps_count",
        "is_active",
    )
    list_filter = ("is_active", "team", "severity_filter")
    search_fields = ("name", "description", "team__name")
    readonly_fields = ("id", "created_at", "updated_at")
    raw_id_fields = ("team",)
    list_editable = ("is_active",)
    inlines = [EscalationStepInline]
    ordering = ("team", "name")
    
    fieldsets = (
        (None, {
            "fields": ("id", "name", "description", "team", "is_active"),
        }),
        ("Targeting", {
            "fields": ("severity_filter",),
            "description": "Optionally limit this policy to specific severity",
        }),
        ("Timing", {
            "fields": ("initial_delay_minutes", "repeat_interval_minutes", "max_escalations"),
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )
    
    @admin.display(description="Steps")
    def steps_count(self, obj: EscalationPolicy) -> int:
        return obj.steps.count()


@admin.register(EscalationStep)
class EscalationStepAdmin(admin.ModelAdmin):
    """Admin for escalation steps."""
    
    list_display = ("policy", "order", "notify_type", "delay_minutes", "target_display")
    list_filter = ("notify_type", "policy")
    search_fields = ("policy__name",)
    readonly_fields = ("id",)
    raw_id_fields = ("policy", "notify_user")
    ordering = ("policy", "order")
    
    @admin.display(description="Target")
    def target_display(self, obj: EscalationStep) -> str:
        if obj.notify_type == "user" and obj.notify_user:
            return f"User: {obj.notify_user.username}"
        elif obj.notify_type == "oncall":
            return "On-Call"
        elif obj.notify_type == "manager":
            return "Manager"
        elif obj.notify_type == "team":
            return "Entire Team"
        return "-"


# =============================================================================
# Incident Escalation Admin
# =============================================================================


@admin.register(IncidentEscalation)
class IncidentEscalationAdmin(admin.ModelAdmin):
    """Admin for viewing incident escalations."""
    
    list_display = (
        "incident",
        "policy",
        "escalation_number",
        "status",
        "executed_at",
        "acknowledged_at",
    )
    list_filter = ("status", "policy", "escalation_number")
    search_fields = ("incident__title", "policy__name")
    readonly_fields = (
        "id", "incident", "policy", "step", "escalation_number",
        "status", "notified_user", "channels_used", "executed_at", 
        "acknowledged_at", "error_message", "scheduled_at",
    )
    raw_id_fields = ("incident", "policy", "step", "notified_user")
    ordering = ("-scheduled_at",)
    
    def has_add_permission(self, request: HttpRequest) -> bool:
        """Escalations are created automatically."""
        return False
    
    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        """Escalations are immutable."""
        return False


# =============================================================================
# Incident Tag Admin
# =============================================================================


@admin.register(IncidentTag)
class IncidentTagAdmin(admin.ModelAdmin):
    """Admin for incident tags."""
    
    list_display = ("incident", "tag", "added_by", "added_at", "is_auto_applied")
    list_filter = ("tag", "is_auto_applied", "added_at")
    search_fields = ("incident__title", "tag__name")
    readonly_fields = ("id", "added_at")
    raw_id_fields = ("incident", "tag", "added_by")
    ordering = ("-added_at",)
