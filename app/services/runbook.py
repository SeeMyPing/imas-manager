"""
IMAS Manager - Runbook Service

Service for managing and executing runbooks.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:
    from core.models import Incident, Runbook, RunbookStep

logger = logging.getLogger(__name__)


class RunbookService:
    """
    Service for runbook operations.
    """
    
    def __init__(self, incident: "Incident"):
        self.incident = incident
    
    def find_runbook(self) -> "Runbook | None":
        """
        Find the most appropriate runbook for the incident.
        """
        from core.models import Runbook
        return Runbook.find_for_incident(self.incident)
    
    def get_runbook_steps(self, runbook: "Runbook") -> list[dict]:
        """
        Get runbook steps with context.
        
        Returns:
            List of step dictionaries with rendered content
        """
        steps = runbook.steps.all().order_by("order")
        
        context = self._build_context()
        result = []
        
        for step in steps:
            result.append({
                "id": str(step.id),
                "order": step.order,
                "title": step.title,
                "description": self._render_template(step.description, context),
                "command": step.command,
                "expected_duration_minutes": step.expected_duration_minutes,
                "is_critical": step.is_critical,
                "requires_confirmation": step.requires_confirmation,
                "rollback_instructions": step.rollback_instructions,
            })
        
        return result
    
    def execute_step(
        self, 
        step: "RunbookStep", 
        executor, 
        notes: str = None
    ) -> "RunbookExecution":
        """
        Execute a runbook step and log the execution.
        """
        from core.models import IncidentComment
        
        # Create execution log
        execution = RunbookExecution(
            incident=self.incident,
            step=step,
            executor=executor,
            started_at=timezone.now(),
        )
        
        # If has command, try to run it
        if step.command:
            try:
                result = self._run_automated_step(step)
                execution.output = result.get("output", "")
                execution.success = result.get("success", False)
            except Exception as e:
                execution.output = str(e)
                execution.success = False
        else:
            execution.success = True
        
        execution.completed_at = timezone.now()
        
        # Log as comment
        IncidentComment.objects.create(
            incident=self.incident,
            author=executor,
            comment_type="auto",
            content=f"**Runbook Step Executed**: {step.title}\n\n"
                    f"{notes or ''}\n\n"
                    f"Status: {'✅ Success' if execution.success else '❌ Failed'}",
            metadata={
                "runbook_step_id": str(step.id),
                "runbook_name": step.runbook.name,
                "execution_result": execution.success,
            }
        )
        
        return execution
    
    def get_quick_actions(self, runbook: "Runbook") -> list[dict]:
        """
        Get quick actions for a runbook.
        """
        if not runbook.quick_actions:
            return []
        
        context = self._build_context()
        actions = []
        
        for action in runbook.quick_actions:
            actions.append({
                "id": action.get("id"),
                "label": action.get("label"),
                "type": action.get("type", "link"),
                "url": self._render_template(action.get("url", ""), context),
                "command": action.get("command"),
                "confirmation_required": action.get("confirmation_required", False),
            })
        
        return actions
    
    def _build_context(self) -> dict[str, Any]:
        """Build template context from incident."""
        service = self.incident.service
        return {
            "incident_id": str(self.incident.id),
            "incident_short_id": self.incident.short_id,
            "service_name": service.name if service else "",
            "service_id": str(service.id) if service else "",
            "team_name": service.owner_team.name if service and service.owner_team else "",
            "severity": self.incident.severity,
            "alert_name": self.incident.title,
            "environment": getattr(service, "environment", "production") if service else "production",
        }
    
    def _render_template(self, template: str, context: dict) -> str:
        """Render a template string with context."""
        if not template:
            return ""
        
        try:
            # Simple placeholder replacement
            result = template
            for key, value in context.items():
                result = result.replace(f"{{{{ {key} }}}}", str(value))
                result = result.replace(f"{{{{{key}}}}}", str(value))
            return result
        except Exception as e:
            logger.warning(f"Template rendering failed: {e}")
            return template
    
    def _run_automated_step(self, step: "RunbookStep") -> dict:
        """
        Run an automated step.
        
        Note: In production, this would integrate with a job runner or 
        automation platform like Rundeck, AWX, etc.
        """
        logger.info(f"Would execute automated step: {step.title}")
        logger.info(f"Command: {step.command}")
        
        # Placeholder - in production this would call an automation API
        return {
            "success": True,
            "output": "Automated execution is configured but requires integration setup.",
        }


class RunbookExecution:
    """
    Represents a runbook step execution.
    """
    
    def __init__(
        self,
        incident: "Incident",
        step: "RunbookStep",
        executor,
        started_at=None,
    ):
        self.incident = incident
        self.step = step
        self.executor = executor
        self.started_at = started_at or timezone.now()
        self.completed_at = None
        self.success = False
        self.output = ""


# =============================================================================
# Runbook Auto-Attachment
# =============================================================================


class RunbookAutoAttacher:
    """
    Automatically attach runbooks to incidents.
    """
    
    @staticmethod
    def attach_on_incident_create(incident: "Incident") -> "Runbook | None":
        """
        Find and attach appropriate runbook when incident is created.
        
        Returns:
            The matched runbook or None
        """
        from core.models import IncidentComment, Runbook
        
        runbook = Runbook.find_for_incident(incident)
        
        if runbook:
            # Create auto-comment with runbook info
            steps = runbook.steps.all().order_by("order")
            steps_preview = "\n".join([
                f"{i+1}. {step.title}" 
                for i, step in enumerate(steps[:5])
            ])
            
            IncidentComment.objects.create(
                incident=incident,
                comment_type="auto",
                content=f"**📚 Runbook Attached: {runbook.name}**\n\n"
                        f"{runbook.description or ''}\n\n"
                        f"**Steps:**\n{steps_preview}\n\n"
                        f"{'...(more steps)' if steps.count() > 5 else ''}",
                is_pinned=True,
                metadata={
                    "runbook_id": str(runbook.id),
                    "runbook_name": runbook.name,
                    "steps_count": steps.count(),
                }
            )
            
            logger.info(f"Attached runbook '{runbook.name}' to incident {incident.id}")
        
        return runbook
    
    @staticmethod
    def suggest_runbooks(incident: "Incident") -> list["Runbook"]:
        """
        Suggest potentially relevant runbooks.
        """
        from core.models import Runbook
        
        suggestions = []
        
        # 1. Runbooks for the same service
        if incident.service:
            service_runbooks = Runbook.objects.filter(
                service=incident.service,
                is_active=True
            )
            suggestions.extend(service_runbooks)
        
        # 2. Runbooks without specific service but matching severity
        generic_runbooks = Runbook.objects.filter(
            service__isnull=True,
            is_active=True
        )
        suggestions.extend(generic_runbooks)
        
        # Remove duplicates and limit
        seen_ids = set()
        unique = []
        for rb in suggestions:
            if rb.id not in seen_ids:
                seen_ids.add(rb.id)
                unique.append(rb)
        
        return unique[:10]


# =============================================================================
# Tag Auto-Apply Service
# =============================================================================


class TagService:
    """
    Service for managing incident tags.
    """
    
    @staticmethod
    def auto_apply_tags(incident: "Incident") -> list["Tag"]:
        """
        Automatically apply tags based on patterns.
        
        Returns:
            List of applied tags
        """
        import re
        from core.models import IncidentTag, Tag
        
        applied = []
        tags = Tag.objects.filter(is_active=True).exclude(auto_apply_pattern="")
        
        # Build search text from incident
        search_text = " ".join([
            incident.title or "",
            incident.description or "",
            incident.service.name if incident.service else "",
            incident.severity or "",
        ]).lower()
        
        for tag in tags:
            if not tag.auto_apply_pattern:
                continue
            
            try:
                if re.search(tag.auto_apply_pattern, search_text, re.IGNORECASE):
                    # Apply tag if not already applied
                    _, created = IncidentTag.objects.get_or_create(
                        incident=incident,
                        tag=tag,
                        defaults={"added_by": None, "is_auto_applied": True}
                    )
                    if created:
                        applied.append(tag)
                        logger.info(f"Auto-applied tag '{tag.name}' to incident {incident.id}")
            except re.error as e:
                logger.warning(f"Invalid regex pattern for tag {tag.name}: {e}")
        
        return applied
    
    @staticmethod
    def apply_tag(incident: "Incident", tag_name: str, user=None) -> "Tag | None":
        """
        Manually apply a tag to an incident.
        """
        from core.models import IncidentTag, Tag
        
        tag = Tag.objects.filter(name__iexact=tag_name, is_active=True).first()
        if not tag:
            # Create new tag
            tag = Tag.objects.create(name=tag_name)
        
        IncidentTag.objects.get_or_create(
            incident=incident,
            tag=tag,
            defaults={"added_by": user, "is_auto_applied": False}
        )
        
        return tag
    
    @staticmethod
    def remove_tag(incident: "Incident", tag_name: str) -> bool:
        """
        Remove a tag from an incident.
        """
        from core.models import IncidentTag, Tag
        
        deleted, _ = IncidentTag.objects.filter(
            incident=incident,
            tag__name__iexact=tag_name
        ).delete()
        
        return deleted > 0
    
    @staticmethod
    def get_incident_tags(incident: "Incident") -> list[dict]:
        """
        Get all tags for an incident.
        """
        from core.models import IncidentTag
        
        incident_tags = IncidentTag.objects.filter(
            incident=incident
        ).select_related("tag", "added_by")
        
        return [
            {
                "id": str(it.tag.id),
                "name": it.tag.name,
                "color": it.tag.color,
                "description": it.tag.description,
                "added_by": it.added_by.username if it.added_by else "auto",
                "added_at": it.added_at.isoformat(),
                "is_auto_applied": it.is_auto_applied,
            }
            for it in incident_tags
        ]
