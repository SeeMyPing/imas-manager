"""
IMAS Manager - WebSocket Broadcasting Utilities

Helper functions to broadcast real-time updates to connected WebSocket clients.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def get_incident_serialized(incident) -> dict:
    """
    Serialize an incident for WebSocket broadcast.
    
    Returns a lightweight representation suitable for real-time updates.
    """
    return {
        "id": str(incident.id),
        "short_id": incident.short_id,
        "title": incident.title,
        "severity": incident.severity,
        "severity_display": incident.get_severity_display(),
        "status": incident.status,
        "status_display": incident.get_status_display(),
        "service": incident.service.name if incident.service else None,
        "lead": incident.lead.username if incident.lead else None,
        "created_at": incident.created_at.isoformat() if incident.created_at else None,
        "acknowledged_at": incident.acknowledged_at.isoformat() if incident.acknowledged_at else None,
        "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
        "lid_link": incident.lid_link,
        "war_room_link": incident.war_room_link,
    }


def broadcast_incident_created(incident) -> None:
    """
    Broadcast new incident creation to all connected clients.
    
    Args:
        incident: The newly created Incident instance
    """
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.warning("No channel layer available for WebSocket broadcast")
            return
        
        incident_data = get_incident_serialized(incident)
        
        # Broadcast to all incidents group
        async_to_sync(channel_layer.group_send)(
            "incidents_all",
            {
                "type": "incident_created",
                "incident": incident_data,
            }
        )
        
        # Broadcast to dashboard
        async_to_sync(channel_layer.group_send)(
            "dashboard",
            {
                "type": "stats_update",
                "stats": _get_stats(),
            }
        )
        
        # If critical, send alert
        if incident.severity in ["SEV1_CRITICAL", "SEV2_HIGH"]:
            async_to_sync(channel_layer.group_send)(
                "dashboard",
                {
                    "type": "critical_alert",
                    "incident": incident_data,
                }
            )
        
        logger.debug(f"Broadcast: incident_created {incident.short_id}")
        
    except Exception as e:
        logger.error(f"Failed to broadcast incident_created: {e}")


def broadcast_incident_updated(incident, changes: Optional[dict] = None) -> None:
    """
    Broadcast incident update to connected clients.
    
    Args:
        incident: The updated Incident instance
        changes: Optional dict of changed fields
    """
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            return
        
        incident_data = get_incident_serialized(incident)
        
        # Broadcast to specific incident group
        async_to_sync(channel_layer.group_send)(
            f"incident_{incident.id}",
            {
                "type": "incident_updated",
                "incident": incident_data,
                "changes": changes or {},
            }
        )
        
        # Broadcast to all incidents group
        async_to_sync(channel_layer.group_send)(
            "incidents_all",
            {
                "type": "incident_updated",
                "incident": incident_data,
                "changes": changes or {},
            }
        )
        
        logger.debug(f"Broadcast: incident_updated {incident.short_id}")
        
    except Exception as e:
        logger.error(f"Failed to broadcast incident_updated: {e}")


def broadcast_incident_acknowledged(incident, acknowledged_by: Optional[str] = None) -> None:
    """
    Broadcast incident acknowledgement to connected clients.
    """
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            return
        
        incident_data = get_incident_serialized(incident)
        
        # Broadcast to specific incident group
        async_to_sync(channel_layer.group_send)(
            f"incident_{incident.id}",
            {
                "type": "incident_acknowledged",
                "incident": incident_data,
                "acknowledged_by": acknowledged_by,
            }
        )
        
        # Broadcast to all incidents group
        async_to_sync(channel_layer.group_send)(
            "incidents_all",
            {
                "type": "incident_acknowledged",
                "incident": incident_data,
                "acknowledged_by": acknowledged_by,
            }
        )
        
        # Update dashboard stats
        async_to_sync(channel_layer.group_send)(
            "dashboard",
            {
                "type": "stats_update",
                "stats": _get_stats(),
            }
        )
        
        logger.debug(f"Broadcast: incident_acknowledged {incident.short_id}")
        
    except Exception as e:
        logger.error(f"Failed to broadcast incident_acknowledged: {e}")


def broadcast_incident_resolved(incident, resolved_by: Optional[str] = None) -> None:
    """
    Broadcast incident resolution to connected clients.
    """
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            return
        
        incident_data = get_incident_serialized(incident)
        
        # Broadcast to specific incident group
        async_to_sync(channel_layer.group_send)(
            f"incident_{incident.id}",
            {
                "type": "incident_resolved",
                "incident": incident_data,
                "resolved_by": resolved_by,
            }
        )
        
        # Broadcast to all incidents group
        async_to_sync(channel_layer.group_send)(
            "incidents_all",
            {
                "type": "incident_resolved",
                "incident": incident_data,
                "resolved_by": resolved_by,
            }
        )
        
        # Update dashboard stats
        async_to_sync(channel_layer.group_send)(
            "dashboard",
            {
                "type": "stats_update",
                "stats": _get_stats(),
            }
        )
        
        logger.debug(f"Broadcast: incident_resolved {incident.short_id}")
        
    except Exception as e:
        logger.error(f"Failed to broadcast incident_resolved: {e}")


def broadcast_incident_event(incident_id: str, event_data: dict) -> None:
    """
    Broadcast new timeline event to incident subscribers.
    """
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            return
        
        async_to_sync(channel_layer.group_send)(
            f"incident_{incident_id}",
            {
                "type": "incident_event_added",
                "incident_id": str(incident_id),
                "event": event_data,
            }
        )
        
        logger.debug(f"Broadcast: incident_event_added {incident_id}")
        
    except Exception as e:
        logger.error(f"Failed to broadcast incident_event: {e}")


def _get_stats() -> dict:
    """Get current incident statistics for dashboard broadcast."""
    try:
        from core.choices import IncidentStatus
        from core.models import Incident
        
        return {
            "triggered": Incident.objects.filter(
                status=IncidentStatus.TRIGGERED
            ).count(),
            "acknowledged": Incident.objects.filter(
                status=IncidentStatus.ACKNOWLEDGED
            ).count(),
        }
    except Exception:
        return {"triggered": 0, "acknowledged": 0}
