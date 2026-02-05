"""
IMAS Manager - API v1 Views

Provides RESTful endpoints for incident management, services, and teams.
"""
from __future__ import annotations

from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import (
    CanAcknowledgeIncident,
    CanResolveIncident,
    IsResponder,
)
from api.v1.serializers import (
    ErrorSerializer,
    IncidentAcknowledgeResponseSerializer,
    IncidentCreateSerializer,
    IncidentDetailSerializer,
    IncidentResolveRequestSerializer,
    IncidentSerializer,
    ServiceSerializer,
    TeamSerializer,
)
from core.choices import IncidentStatus
from core.models import AuditAction, AuditLog, Incident, Service, Team
from services.orchestrator import orchestrator


@extend_schema(
    tags=["health"],
    summary="API Health Check",
    description="Quick health check endpoint for load balancers and monitoring systems.",
    responses={
        200: OpenApiResponse(
            description="Service is healthy",
            examples=[
                OpenApiExample(
                    "Healthy Response",
                    value={"status": "healthy", "service": "imas-manager", "version": "1.0.0"},
                )
            ],
        ),
    },
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request: Request) -> Response:
    """
    Health check endpoint for load balancers and monitoring.
    
    Returns:
        200 OK with status information.
    """
    return Response({
        "status": "healthy",
        "service": "imas-manager",
        "version": "1.0.0",
    })


@extend_schema_view(
    get=extend_schema(
        tags=["incidents"],
        summary="List all incidents",
        description="""
Retrieve a paginated list of all incidents with optional filtering.

**Filtering options:**
- `status`: Filter by incident status (triggered, acknowledged, resolved)
- `severity`: Filter by severity level (SEV1, SEV2, SEV3, SEV4)
- `service`: Filter by service UUID

**Search:** Use `search` parameter to search in title and description.

**Ordering:** Use `ordering` parameter with fields: created_at, severity, status.
        """,
        parameters=[
            OpenApiParameter(
                name="status",
                description="Filter by incident status",
                required=False,
                type=str,
                enum=["triggered", "acknowledged", "resolved"],
            ),
            OpenApiParameter(
                name="severity",
                description="Filter by severity level",
                required=False,
                type=str,
                enum=["SEV1", "SEV2", "SEV3", "SEV4"],
            ),
            OpenApiParameter(
                name="service",
                description="Filter by service UUID",
                required=False,
                type=str,
            ),
            OpenApiParameter(
                name="search",
                description="Search in title and description",
                required=False,
                type=str,
            ),
            OpenApiParameter(
                name="ordering",
                description="Order results by field (prefix with - for descending)",
                required=False,
                type=str,
                enum=["created_at", "-created_at", "severity", "-severity"],
            ),
        ],
    ),
    post=extend_schema(
        tags=["incidents"],
        summary="Create a new incident",
        description="""
Create a new incident and trigger the orchestration workflow.

**Orchestration actions (based on severity):**
- **SEV1/SEV2**: Creates War Room (Slack channel) + LID document + Notifications
- **SEV3/SEV4**: Creates LID document + Slack notifications

**Deduplication:** If an open incident already exists for the same service,
the existing incident is returned with HTTP 200 instead of creating a duplicate.
        """,
        responses={
            201: OpenApiResponse(
                response=IncidentSerializer,
                description="Incident created successfully",
            ),
            200: OpenApiResponse(
                response=IncidentSerializer,
                description="Existing open incident returned (deduplication)",
            ),
            400: OpenApiResponse(
                response=ErrorSerializer,
                description="Validation error",
            ),
            403: OpenApiResponse(
                response=ErrorSerializer,
                description="Permission denied - requires Responder role",
            ),
        },
        examples=[
            OpenApiExample(
                "Create SEV1 Incident",
                value={
                    "title": "Production database outage",
                    "description": "Primary PostgreSQL cluster is unreachable",
                    "service": "550e8400-e29b-41d4-a716-446655440000",
                    "severity": "SEV1",
                    "impacted_scopes": ["550e8400-e29b-41d4-a716-446655440001"],
                },
                request_only=True,
            ),
        ],
    ),
)
class IncidentListCreateView(generics.ListCreateAPIView):
    """
    List all incidents or create a new incident.
    
    GET: List incidents with filtering and pagination.
    POST: Create a new incident (triggers orchestration).
    """
    
    queryset = Incident.objects.select_related("service", "lead").prefetch_related("impacted_scopes")
    filterset_fields = ["status", "severity", "service"]
    search_fields = ["title", "description"]
    ordering_fields = ["created_at", "severity", "status"]
    ordering = ["-created_at"]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsResponder()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return IncidentCreateSerializer
        return IncidentSerializer

    def create(self, request: Request, *args, **kwargs) -> Response:
        """Create incident with deduplication check."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        service = serializer.validated_data["service"]
        
        # Check for existing open incident (deduplication)
        existing = orchestrator.deduplicate_check(
            service=service,
            severity=serializer.validated_data.get("severity"),
        )
        
        if existing:
            # Return existing incident (idempotent)
            return Response(
                IncidentSerializer(existing).data,
                status=status.HTTP_200_OK,
            )
        
        # Create new incident
        incident = orchestrator.create_incident(
            data=serializer.validated_data,
            user=request.user if request.user.is_authenticated else None,
        )
        
        # Audit log
        AuditLog.log(
            action=AuditAction.INCIDENT_CREATED,
            user=request.user,
            request=request,
            resource_type="Incident",
            resource_id=str(incident.id),
            description=f"Created incident: {incident.title}",
        )
        
        return Response(
            IncidentSerializer(incident).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema_view(
    get=extend_schema(
        tags=["incidents"],
        summary="Get incident details",
        description="Retrieve full details of an incident including events timeline.",
    ),
    put=extend_schema(
        tags=["incidents"],
        summary="Update incident",
        description="Update incident fields (title, description, severity, lead, etc.)",
    ),
    patch=extend_schema(
        tags=["incidents"],
        summary="Partial update incident",
        description="Partially update specific incident fields.",
    ),
)
class IncidentDetailView(generics.RetrieveUpdateAPIView):
    """
    Retrieve or update a specific incident.
    """
    
    queryset = Incident.objects.select_related("service", "lead").prefetch_related(
        "impacted_scopes", "events"
    )
    serializer_class = IncidentDetailSerializer
    permission_classes = [IsAuthenticated]


@extend_schema(
    tags=["incidents"],
    summary="Acknowledge incident",
    description="""
Transition an incident from TRIGGERED to ACKNOWLEDGED status.

**Requirements:**
- Incident must be in TRIGGERED status
- User must have acknowledge permission (Responder or Incident Lead)

**Side effects:**
- Records acknowledged_at timestamp
- Creates audit log entry
- Sends notification to War Room (if exists)
    """,
    request=None,
    responses={
        200: OpenApiResponse(
            response=IncidentSerializer,
            description="Incident acknowledged successfully",
        ),
        400: OpenApiResponse(
            response=ErrorSerializer,
            description="Invalid status transition",
            examples=[
                OpenApiExample(
                    "Already Acknowledged",
                    value={"error": "Cannot acknowledge incident in 'acknowledged' status"},
                )
            ],
        ),
        404: OpenApiResponse(
            response=ErrorSerializer,
            description="Incident not found",
        ),
    },
)
class IncidentAcknowledgeView(APIView):
    """
    Acknowledge an incident.
    
    POST: Transition incident from TRIGGERED to ACKNOWLEDGED.
    """
    
    permission_classes = [CanAcknowledgeIncident]

    def post(self, request: Request, pk: str) -> Response:
        try:
            incident = Incident.objects.get(pk=pk)
        except Incident.DoesNotExist:
            return Response(
                {"error": "Incident not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        # Check object-level permission
        self.check_object_permissions(request, incident)
        
        if incident.status != IncidentStatus.TRIGGERED:
            return Response(
                {"error": f"Cannot acknowledge incident in '{incident.status}' status"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        incident = orchestrator.acknowledge_incident(
            incident=incident,
            user=request.user,
        )
        
        # Audit log
        AuditLog.log(
            action=AuditAction.INCIDENT_ACKNOWLEDGED,
            user=request.user,
            request=request,
            resource_type="Incident",
            resource_id=str(incident.id),
            description=f"Acknowledged incident: {incident.short_id}",
        )
        
        return Response(IncidentSerializer(incident).data)


@extend_schema(
    tags=["incidents"],
    summary="Resolve incident",
    description="""
Transition an incident to RESOLVED status.

**Requirements:**
- Incident must not already be resolved
- User must have resolve permission (Responder, Incident Lead, or Manager)

**Side effects:**
- Records resolved_at timestamp
- Calculates MTTR (Mean Time To Resolve)
- Creates audit log entry
- Sends resolution notification
- Archives War Room channel (optional)
    """,
    request=IncidentResolveRequestSerializer,
    responses={
        200: OpenApiResponse(
            response=IncidentSerializer,
            description="Incident resolved successfully",
        ),
        400: OpenApiResponse(
            response=ErrorSerializer,
            description="Already resolved",
        ),
        404: OpenApiResponse(
            response=ErrorSerializer,
            description="Incident not found",
        ),
    },
    examples=[
        OpenApiExample(
            "Resolve with note",
            value={"note": "Root cause identified: Memory leak in auth service. Fix deployed."},
            request_only=True,
        ),
    ],
)
class IncidentResolveView(APIView):
    """
    Resolve an incident.
    
    POST: Transition incident to RESOLVED status.
    """
    
    permission_classes = [CanResolveIncident]

    def post(self, request: Request, pk: str) -> Response:
        try:
            incident = Incident.objects.get(pk=pk)
        except Incident.DoesNotExist:
            return Response(
                {"error": "Incident not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        # Check object-level permission
        self.check_object_permissions(request, incident)
        
        if incident.status == IncidentStatus.RESOLVED:
            return Response(
                {"error": "Incident is already resolved"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        resolution_note = request.data.get("note", "")
        incident = orchestrator.resolve_incident(
            incident=incident,
            user=request.user,
            resolution_note=resolution_note,
        )
        
        # Audit log
        AuditLog.log(
            action=AuditAction.INCIDENT_RESOLVED,
            user=request.user,
            request=request,
            resource_type="Incident",
            resource_id=str(incident.id),
            description=f"Resolved incident: {incident.short_id}",
        )
        
        return Response(IncidentSerializer(incident).data)


@extend_schema(
    tags=["services"],
    summary="List all services",
    description="""
Retrieve a list of all services in the catalog.

Services are ordered by criticality (most critical first) then by name.
    """,
    parameters=[
        OpenApiParameter(
            name="search",
            description="Search by service name",
            required=False,
            type=str,
        ),
    ],
)
class ServiceListView(generics.ListAPIView):
    """
    List all services.
    """
    
    queryset = Service.objects.select_related("owner_team")
    serializer_class = ServiceSerializer
    permission_classes = [IsAuthenticated]
    search_fields = ["name"]
    ordering = ["criticality", "name"]


@extend_schema(
    tags=["teams"],
    summary="List all teams",
    description="""
Retrieve a list of all teams with their on-call information.

Each team includes the current on-call user if configured.
    """,
    parameters=[
        OpenApiParameter(
            name="search",
            description="Search by team name",
            required=False,
            type=str,
        ),
    ],
)
class TeamListView(generics.ListAPIView):
    """
    List all teams.
    """
    
    queryset = Team.objects.select_related("current_on_call")
    serializer_class = TeamSerializer
    permission_classes = [IsAuthenticated]
    search_fields = ["name"]
    ordering = ["name"]
