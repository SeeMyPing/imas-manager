"""
IMAS Manager - WebSocket URL Routing
"""
from django.urls import re_path

from core import consumers

websocket_urlpatterns = [
    # Dashboard real-time updates
    re_path(r"ws/dashboard/$", consumers.DashboardConsumer.as_asgi()),
    
    # All incidents updates
    re_path(r"ws/incidents/$", consumers.IncidentConsumer.as_asgi()),
    
    # Specific incident updates
    re_path(
        r"ws/incidents/(?P<incident_id>[0-9a-f-]+)/$",
        consumers.IncidentConsumer.as_asgi()
    ),
]
