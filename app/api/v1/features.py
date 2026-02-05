"""
IMAS Manager - API v1 Features Views

ViewSets for enhanced features: Comments, Tags, Runbooks, Escalation Policies.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.models import (
    EscalationPolicy,
    Incident,
    IncidentComment,
    IncidentTag,
    Runbook,
    Tag,
)
from services.runbook import RunbookService, TagService

from .serializers import (
    ApplyTagSerializer,
    EscalationPolicyListSerializer,
    EscalationPolicySerializer,
    IncidentCommentCreateSerializer,
    IncidentCommentSerializer,
    IncidentTagSerializer,
    RunbookListSerializer,
    RunbookSerializer,
    TagSerializer,
)


# =============================================================================
# Comment ViewSet
# =============================================================================


@extend_schema_view(
    list=extend_schema(
        summary="List incident comments",
        description="Get all comments for an incident",
        tags=["Comments"],
    ),
    create=extend_schema(
        summary="Add comment to incident",
        description="Add a new comment to an incident timeline",
        tags=["Comments"],
    ),
    retrieve=extend_schema(
        summary="Get comment details",
        description="Get a specific comment by ID",
        tags=["Comments"],
    ),
    update=extend_schema(
        summary="Update comment",
        description="Update an existing comment (author only)",
        tags=["Comments"],
    ),
    partial_update=extend_schema(
        summary="Partially update comment",
        description="Partially update an existing comment",
        tags=["Comments"],
    ),
    destroy=extend_schema(
        summary="Delete comment",
        description="Delete a comment (author or admin only)",
        tags=["Comments"],
    ),
)
class IncidentCommentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing incident comments.
    
    Comments support Markdown and can be pinned for important updates.
    """
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        incident_id = self.kwargs.get("incident_id")
        return IncidentComment.objects.filter(
            incident_id=incident_id
        ).select_related(
            "author", "incident"
        ).order_by("-created_at")
    
    def get_serializer_class(self):
        if self.action == "create":
            return IncidentCommentCreateSerializer
        return IncidentCommentSerializer
    
    def perform_create(self, serializer):
        incident = get_object_or_404(Incident, pk=self.kwargs["incident_id"])
        serializer.save(
            incident=incident,
            author=self.request.user,
        )
    
    @extend_schema(
        summary="Toggle pin status",
        description="Pin or unpin a comment",
        tags=["Comments"],
    )
    @action(detail=True, methods=["post"])
    def toggle_pin(self, request, **kwargs):
        """Toggle the pinned status of a comment."""
        comment = self.get_object()
        comment.is_pinned = not comment.is_pinned
        comment.save(update_fields=["is_pinned"])
        
        return Response({
            "id": str(comment.id),
            "is_pinned": comment.is_pinned,
        })
    
    @extend_schema(
        summary="Get pinned comments",
        description="Get all pinned comments for the incident",
        tags=["Comments"],
    )
    @action(detail=False, methods=["get"])
    def pinned(self, request, **kwargs):
        """Get pinned comments only."""
        queryset = self.get_queryset().filter(is_pinned=True)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


# =============================================================================
# Tag ViewSet
# =============================================================================


@extend_schema_view(
    list=extend_schema(
        summary="List all tags",
        description="Get all available tags",
        tags=["Tags"],
    ),
    create=extend_schema(
        summary="Create tag",
        description="Create a new tag",
        tags=["Tags"],
    ),
    retrieve=extend_schema(
        summary="Get tag details",
        description="Get a specific tag by ID",
        tags=["Tags"],
    ),
    update=extend_schema(
        summary="Update tag",
        description="Update an existing tag",
        tags=["Tags"],
    ),
    destroy=extend_schema(
        summary="Delete tag",
        description="Delete a tag",
        tags=["Tags"],
    ),
)
class TagViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing tags.
    
    Tags can be applied to incidents manually or automatically via patterns.
    """
    
    queryset = Tag.objects.filter(is_active=True).order_by("name")
    serializer_class = TagSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    @extend_schema(
        summary="Get popular tags",
        description="Get the most used tags",
        tags=["Tags"],
    )
    @action(detail=False, methods=["get"])
    def popular(self, request):
        """Get popular tags by usage count."""
        from django.db.models import Count
        
        tags = Tag.objects.annotate(
            usage_count=Count("incident_tags")
        ).filter(
            is_active=True
        ).order_by("-usage_count")[:20]
        
        serializer = self.get_serializer(tags, many=True)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(
        summary="List incident tags",
        description="Get all tags for an incident",
        tags=["Tags"],
    ),
    create=extend_schema(
        summary="Apply tag to incident",
        description="Apply a tag to an incident",
        tags=["Tags"],
    ),
    destroy=extend_schema(
        summary="Remove tag from incident",
        description="Remove a tag from an incident",
        tags=["Tags"],
    ),
)
class IncidentTagViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing tags on a specific incident.
    """
    
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "delete"]
    
    def get_queryset(self):
        incident_id = self.kwargs.get("incident_id")
        return IncidentTag.objects.filter(
            incident_id=incident_id
        ).select_related("tag", "applied_by")
    
    def get_serializer_class(self):
        if self.action == "create":
            return ApplyTagSerializer
        return IncidentTagSerializer
    
    def create(self, request, incident_id=None, **kwargs):
        """Apply a tag to the incident."""
        serializer = ApplyTagSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        incident = get_object_or_404(Incident, pk=incident_id)
        tag = TagService.apply_tag(
            incident=incident,
            tag_name=serializer.validated_data["tag_name"],
            user=request.user
        )
        
        return Response({
            "tag_id": str(tag.id),
            "tag_name": tag.name,
            "applied": True,
        }, status=status.HTTP_201_CREATED)
    
    def destroy(self, request, incident_id=None, pk=None, **kwargs):
        """Remove a tag from the incident."""
        incident = get_object_or_404(Incident, pk=incident_id)
        tag = get_object_or_404(Tag, pk=pk)
        
        removed = TagService.remove_tag(incident, tag.name)
        
        if removed:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(
            {"error": "Tag not found on incident"},
            status=status.HTTP_404_NOT_FOUND
        )


# =============================================================================
# Runbook ViewSet
# =============================================================================


@extend_schema_view(
    list=extend_schema(
        summary="List runbooks",
        description="Get all runbooks",
        tags=["Runbooks"],
    ),
    create=extend_schema(
        summary="Create runbook",
        description="Create a new runbook",
        tags=["Runbooks"],
    ),
    retrieve=extend_schema(
        summary="Get runbook details",
        description="Get a specific runbook with all steps",
        tags=["Runbooks"],
    ),
    update=extend_schema(
        summary="Update runbook",
        description="Update an existing runbook",
        tags=["Runbooks"],
    ),
    destroy=extend_schema(
        summary="Delete runbook",
        description="Delete a runbook",
        tags=["Runbooks"],
    ),
)
class RunbookViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing runbooks.
    
    Runbooks contain step-by-step instructions for incident response.
    """
    
    queryset = Runbook.objects.filter(
        is_active=True
    ).select_related(
        "service", "author"
    ).prefetch_related("steps")
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == "list":
            return RunbookListSerializer
        return RunbookSerializer
    
    def perform_create(self, serializer):
        serializer.save(author=self.request.user)
    
    @extend_schema(
        summary="Find runbook for incident",
        description="Find the most appropriate runbook for a given incident",
        tags=["Runbooks"],
        parameters=[
            OpenApiParameter(
                name="incident_id",
                type=str,
                description="Incident ID to match runbook for",
                required=True,
            )
        ],
    )
    @action(detail=False, methods=["get"])
    def find_for_incident(self, request):
        """Find appropriate runbook for an incident."""
        incident_id = request.query_params.get("incident_id")
        if not incident_id:
            return Response(
                {"error": "incident_id parameter required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        incident = get_object_or_404(Incident, pk=incident_id)
        runbook_service = RunbookService(incident)
        runbook = runbook_service.find_runbook()
        
        if runbook:
            serializer = RunbookSerializer(runbook)
            return Response(serializer.data)
        
        return Response(
            {"detail": "No matching runbook found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    @extend_schema(
        summary="Get runbooks for service",
        description="Get all runbooks for a specific service",
        tags=["Runbooks"],
    )
    @action(detail=False, methods=["get"], url_path="by-service/(?P<service_id>[^/.]+)")
    def by_service(self, request, service_id=None):
        """Get runbooks for a specific service."""
        runbooks = self.queryset.filter(service_id=service_id)
        serializer = RunbookListSerializer(runbooks, many=True)
        return Response(serializer.data)


# =============================================================================
# Escalation Policy ViewSet
# =============================================================================


@extend_schema_view(
    list=extend_schema(
        summary="List escalation policies",
        description="Get all escalation policies",
        tags=["Escalation"],
    ),
    create=extend_schema(
        summary="Create escalation policy",
        description="Create a new escalation policy",
        tags=["Escalation"],
    ),
    retrieve=extend_schema(
        summary="Get escalation policy details",
        description="Get a specific escalation policy with steps",
        tags=["Escalation"],
    ),
    update=extend_schema(
        summary="Update escalation policy",
        description="Update an existing escalation policy",
        tags=["Escalation"],
    ),
    destroy=extend_schema(
        summary="Delete escalation policy",
        description="Delete an escalation policy",
        tags=["Escalation"],
    ),
)
class EscalationPolicyViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing escalation policies.
    
    Escalation policies define how and when to escalate unacknowledged incidents.
    """
    
    queryset = EscalationPolicy.objects.filter(
        is_active=True
    ).select_related("team").prefetch_related("steps")
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == "list":
            return EscalationPolicyListSerializer
        return EscalationPolicySerializer
    
    @extend_schema(
        summary="Get policies for team",
        description="Get all escalation policies for a specific team",
        tags=["Escalation"],
    )
    @action(detail=False, methods=["get"], url_path="by-team/(?P<team_id>[^/.]+)")
    def by_team(self, request, team_id=None):
        """Get escalation policies for a specific team."""
        policies = self.queryset.filter(team_id=team_id)
        serializer = EscalationPolicyListSerializer(policies, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        summary="Test escalation policy",
        description="Test an escalation policy without triggering notifications",
        tags=["Escalation"],
    )
    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """Test the escalation policy (dry run)."""
        policy = self.get_object()
        steps = policy.steps.filter(is_active=True).order_by("step_order")
        
        test_result = {
            "policy_name": policy.name,
            "initial_delay_minutes": policy.initial_delay_minutes,
            "steps": []
        }
        
        cumulative_time = policy.initial_delay_minutes
        for step in steps:
            test_result["steps"].append({
                "order": step.step_order,
                "notify_type": step.notify_type,
                "delay_minutes": step.delay_minutes,
                "cumulative_time_minutes": cumulative_time,
                "target": (
                    step.target_user.username if step.target_user
                    else step.target_team.name if step.target_team
                    else step.notify_type
                ),
            })
            cumulative_time += step.delay_minutes
        
        return Response(test_result)
