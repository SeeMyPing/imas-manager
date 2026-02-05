"""
IMAS Manager - Incident Orchestrator

Main service for incident creation and orchestration workflow.
This is the central point for incident lifecycle management.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.contrib.auth import get_user_model
from django.db import transaction

from core.choices import IncidentStatus
from core.models import Incident, IncidentEvent, Service

if TYPE_CHECKING:
    from django.contrib.auth.models import User

logger = logging.getLogger(__name__)
User = get_user_model()


class IncidentOrchestrator:
    """
    Orchestrates incident creation and lifecycle management.
    
    This service is responsible for:
    - Creating incidents (from web or API)
    - Triggering async orchestration tasks
    - Handling deduplication logic
    """

    def create_incident(
        self,
        data: dict[str, Any],
        user: "User | None" = None,
        trigger_orchestration: bool = True,
    ) -> Incident:
        """
        Create a new incident and optionally trigger orchestration.
        
        Args:
            data: Incident data including title, description, service, severity, etc.
            user: The user creating the incident (will be assigned as lead).
            trigger_orchestration: Whether to trigger async setup task.
            
        Returns:
            The created Incident instance.
            
        Raises:
            ValueError: If required fields are missing or invalid.
        """
        with transaction.atomic():
            # Extract and validate required fields
            service = self._resolve_service(data.get("service"))
            
            incident = Incident.objects.create(
                title=data["title"],
                description=data.get("description", ""),
                service=service,
                severity=data.get("severity", "SEV3_MEDIUM"),
                status=IncidentStatus.TRIGGERED,
                lead=user,
                detected_at=data.get("detected_at"),
            )
            
            # Add impact scopes if provided
            if scope_ids := data.get("impacted_scopes"):
                incident.impacted_scopes.set(scope_ids)
            
            logger.info(f"Created incident {incident.short_id}: {incident.title}")
        
        # Trigger async orchestration
        if trigger_orchestration:
            self._trigger_orchestration(incident)
        
        return incident

    def deduplicate_check(
        self,
        service: Service,
        severity: str | None = None,
    ) -> Incident | None:
        """
        Check if an open incident already exists for this service.
        
        Used by API to prevent duplicate incidents from monitoring tools.
        
        Args:
            service: The service to check.
            severity: Optional severity to match.
            
        Returns:
            Existing open incident if found, None otherwise.
        """
        queryset = Incident.objects.filter(
            service=service,
            status__in=[IncidentStatus.TRIGGERED, IncidentStatus.ACKNOWLEDGED],
        )
        
        if severity:
            queryset = queryset.filter(severity=severity)
        
        return queryset.first()

    def acknowledge_incident(
        self,
        incident: Incident,
        user: "User | None" = None,
    ) -> Incident:
        """
        Acknowledge an incident.
        
        Args:
            incident: The incident to acknowledge.
            user: The user acknowledging.
            
        Returns:
            Updated incident.
        """
        if incident.status != IncidentStatus.TRIGGERED:
            logger.warning(f"Incident {incident.short_id} is not in TRIGGERED status")
            return incident
        
        incident.status = IncidentStatus.ACKNOWLEDGED
        if user and not incident.lead:
            incident.lead = user
        incident.save()
        
        # Create event
        IncidentEvent.objects.create(
            incident=incident,
            type="STATUS_CHANGE",
            message=f"Incident acknowledged by {user.username if user else 'system'}",
            created_by=user,
        )
        
        logger.info(f"Incident {incident.short_id} acknowledged by {user}")
        return incident

    def resolve_incident(
        self,
        incident: Incident,
        user: "User | None" = None,
        resolution_note: str = "",
    ) -> Incident:
        """
        Resolve an incident.
        
        Args:
            incident: The incident to resolve.
            user: The user resolving.
            resolution_note: Optional resolution note.
            
        Returns:
            Updated incident.
        """
        incident.status = IncidentStatus.RESOLVED
        incident.save()
        
        message = f"Incident resolved by {user.username if user else 'system'}"
        if resolution_note:
            message += f": {resolution_note}"
        
        IncidentEvent.objects.create(
            incident=incident,
            type="STATUS_CHANGE",
            message=message,
            created_by=user,
        )
        
        # Schedule War Room archival (async)
        if incident.war_room_id:
            self._schedule_war_room_archive(incident)
        
        logger.info(f"Incident {incident.short_id} resolved")
        return incident

    def _schedule_war_room_archive(self, incident: Incident) -> None:
        """Schedule async War Room archival task."""
        from tasks.incident_tasks import archive_war_room_task
        
        try:
            # Archive war room after a delay (30 minutes)
            # This gives time for post-incident discussion
            archive_war_room_task.apply_async(
                args=[str(incident.id)],
                countdown=30 * 60,  # 30 minutes
            )
            logger.info(f"Scheduled War Room archive for {incident.short_id} in 30 minutes")
        except Exception as e:
            logger.warning(f"Failed to schedule War Room archive: {e}")

    def _resolve_service(self, service_input: Any) -> Service:
        """
        Resolve service from ID, name, or instance.
        
        Args:
            service_input: Service ID (UUID), name (str), or Service instance.
            
        Returns:
            Service instance.
            
        Raises:
            ValueError: If service cannot be resolved.
        """
        if isinstance(service_input, Service):
            return service_input
        
        if isinstance(service_input, str):
            # Try by name first (for API), then by ID
            try:
                return Service.objects.get(name=service_input)
            except Service.DoesNotExist:
                try:
                    return Service.objects.get(pk=service_input)
                except (Service.DoesNotExist, ValueError):
                    raise ValueError(f"Service not found: {service_input}")
        
        raise ValueError(f"Invalid service input: {service_input}")

    def _trigger_orchestration(self, incident: Incident) -> None:
        """
        Trigger async orchestration task.
        
        Launches the Celery task that will:
        1. Create the LID document
        2. Create the War Room (if critical)
        3. Send notifications
        """
        from tasks.incident_tasks import orchestrate_incident_task
        
        try:
            orchestrate_incident_task.delay(str(incident.id))
            logger.info(f"Orchestration task queued for incident {incident.short_id}")
        except Exception as e:
            # If Celery is not available, log but don't fail
            logger.warning(
                f"Failed to queue orchestration task for {incident.short_id}: {e}. "
                "Celery may not be running."
            )


# Singleton instance for convenience
orchestrator = IncidentOrchestrator()
