"""
IMAS Manager - Dashboard URL Configuration
"""
from django.urls import path

from . import views
from .views_analytics import (
    AnalyticsDashboardView,
    AnalyticsMTTAView,
    AnalyticsMTTRView,
)

app_name = "dashboard"

urlpatterns = [
    # Home / Dashboard
    path("", views.DashboardHomeView.as_view(), name="home"),
    
    # Incidents
    path("incidents/", views.IncidentListView.as_view(), name="incident_list"),
    path("incidents/create/", views.IncidentCreateView.as_view(), name="incident_create"),
    path("incidents/<uuid:pk>/", views.IncidentDetailView.as_view(), name="incident_detail"),
    path("incidents/<uuid:pk>/acknowledge/", views.IncidentAcknowledgeView.as_view(), name="incident_acknowledge"),
    path("incidents/<uuid:pk>/resolve/", views.IncidentResolveView.as_view(), name="incident_resolve"),
    path("incidents/<uuid:pk>/add-note/", views.IncidentAddNoteView.as_view(), name="incident_add_note"),
    
    # Services
    path("services/", views.ServiceListView.as_view(), name="service_list"),
    
    # Teams
    path("teams/", views.TeamListView.as_view(), name="team_list"),
    
    # Analytics
    path("analytics/", AnalyticsDashboardView.as_view(), name="analytics"),
    path("analytics/mtta/", AnalyticsMTTAView.as_view(), name="analytics_mtta"),
    path("analytics/mttr/", AnalyticsMTTRView.as_view(), name="analytics_mttr"),
]
