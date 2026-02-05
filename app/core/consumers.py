"""
IMAS Manager - WebSocket Consumers

Real-time updates for incidents using Django Channels.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger(__name__)


class IncidentConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer for real-time incident updates.
    
    Clients can subscribe to:
    - All incidents: /ws/incidents/
    - Specific incident: /ws/incidents/<incident_id>/
    """
    
    async def connect(self):
        """Handle WebSocket connection."""
        self.incident_id = self.scope["url_route"]["kwargs"].get("incident_id")
        self.user = self.scope.get("user")
        
        # Check authentication
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return
        
        # Join the appropriate group
        if self.incident_id:
            self.group_name = f"incident_{self.incident_id}"
        else:
            self.group_name = "incidents_all"
        
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"WebSocket connected: {self.group_name} by {self.user}")
        
        # Send initial connection confirmation
        await self.send_json({
            "type": "connection_established",
            "group": self.group_name,
            "user": str(self.user),
        })
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
            logger.info(f"WebSocket disconnected: {self.group_name}")
    
    async def receive_json(self, content: dict[str, Any]):
        """
        Handle incoming WebSocket messages.
        
        Supported message types:
        - ping: Keep-alive ping
        - subscribe: Subscribe to specific incident
        """
        message_type = content.get("type")
        
        if message_type == "ping":
            await self.send_json({"type": "pong"})
        
        elif message_type == "subscribe":
            # Subscribe to a specific incident
            incident_id = content.get("incident_id")
            if incident_id:
                new_group = f"incident_{incident_id}"
                await self.channel_layer.group_add(
                    new_group,
                    self.channel_name
                )
                await self.send_json({
                    "type": "subscribed",
                    "incident_id": incident_id,
                })
        
        elif message_type == "unsubscribe":
            incident_id = content.get("incident_id")
            if incident_id:
                old_group = f"incident_{incident_id}"
                await self.channel_layer.group_discard(
                    old_group,
                    self.channel_name
                )
                await self.send_json({
                    "type": "unsubscribed",
                    "incident_id": incident_id,
                })
    
    # Message handlers for group broadcasts
    
    async def incident_created(self, event: dict):
        """Handle new incident created."""
        await self.send_json({
            "type": "incident_created",
            "incident": event["incident"],
        })
    
    async def incident_updated(self, event: dict):
        """Handle incident update."""
        await self.send_json({
            "type": "incident_updated",
            "incident": event["incident"],
            "changes": event.get("changes", {}),
        })
    
    async def incident_acknowledged(self, event: dict):
        """Handle incident acknowledged."""
        await self.send_json({
            "type": "incident_acknowledged",
            "incident": event["incident"],
            "acknowledged_by": event.get("acknowledged_by"),
        })
    
    async def incident_resolved(self, event: dict):
        """Handle incident resolved."""
        await self.send_json({
            "type": "incident_resolved",
            "incident": event["incident"],
            "resolved_by": event.get("resolved_by"),
        })
    
    async def incident_event_added(self, event: dict):
        """Handle new event added to incident timeline."""
        await self.send_json({
            "type": "incident_event_added",
            "incident_id": event["incident_id"],
            "event": event["event"],
        })


class DashboardConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer for real-time dashboard updates.
    
    Broadcasts:
    - Incident count changes
    - Critical incident alerts
    - KPI updates
    """
    
    async def connect(self):
        """Handle WebSocket connection."""
        self.user = self.scope.get("user")
        
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return
        
        self.group_name = "dashboard"
        
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"Dashboard WebSocket connected by {self.user}")
        
        # Send current stats on connection
        stats = await self.get_dashboard_stats()
        await self.send_json({
            "type": "stats_update",
            "stats": stats,
        })
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
    
    async def receive_json(self, content: dict[str, Any]):
        """Handle incoming messages."""
        message_type = content.get("type")
        
        if message_type == "ping":
            await self.send_json({"type": "pong"})
        
        elif message_type == "refresh_stats":
            stats = await self.get_dashboard_stats()
            await self.send_json({
                "type": "stats_update",
                "stats": stats,
            })
    
    @database_sync_to_async
    def get_dashboard_stats(self) -> dict:
        """Get current dashboard statistics."""
        from core.choices import IncidentStatus
        from core.models import Incident
        
        return {
            "triggered": Incident.objects.filter(
                status=IncidentStatus.TRIGGERED
            ).count(),
            "acknowledged": Incident.objects.filter(
                status=IncidentStatus.ACKNOWLEDGED
            ).count(),
            "resolved_today": Incident.objects.filter(
                status=IncidentStatus.RESOLVED,
                resolved_at__date__gte=__import__("django.utils.timezone", fromlist=["now"]).now().date()
            ).count(),
        }
    
    # Message handlers for group broadcasts
    
    async def stats_update(self, event: dict):
        """Handle stats update broadcast."""
        await self.send_json({
            "type": "stats_update",
            "stats": event["stats"],
        })
    
    async def critical_alert(self, event: dict):
        """Handle critical incident alert."""
        await self.send_json({
            "type": "critical_alert",
            "incident": event["incident"],
        })
