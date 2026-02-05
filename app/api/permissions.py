"""
IMAS Manager - Custom Permissions (RBAC)

Role-Based Access Control for incident management:
- Viewer: Read-only access to incidents and services
- Operator: Can acknowledge and add notes to incidents
- Responder: Can create, acknowledge, and resolve incidents
- Manager: Full access including team management
- Admin: Superuser access
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission, SAFE_METHODS
from rest_framework.request import Request
from rest_framework.views import APIView


class IsViewer(BasePermission):
    """
    Read-only access to incidents and services.
    Any authenticated user has viewer access.
    """
    message = "Viewer access required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        return request.method in SAFE_METHODS


class IsOperator(BasePermission):
    """
    Can acknowledge incidents and add notes.
    Users in groups: 'operators', 'responders', 'managers', or staff.
    """
    message = "Operator access required."

    ALLOWED_GROUPS = {"operators", "responders", "managers", "admins"}

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        
        if request.user.is_staff or request.user.is_superuser:
            return True
        
        user_groups = set(request.user.groups.values_list("name", flat=True))
        return bool(user_groups & self.ALLOWED_GROUPS)


class IsResponder(BasePermission):
    """
    Can create, acknowledge, and resolve incidents.
    Users in groups: 'responders', 'managers', or staff.
    """
    message = "Responder access required to perform this action."

    ALLOWED_GROUPS = {"responders", "managers", "admins"}

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        
        if request.user.is_staff or request.user.is_superuser:
            return True
        
        user_groups = set(request.user.groups.values_list("name", flat=True))
        return bool(user_groups & self.ALLOWED_GROUPS)


class IsManager(BasePermission):
    """
    Full access to incidents, teams, and services.
    Users in groups: 'managers' or superuser.
    """
    message = "Manager access required."

    ALLOWED_GROUPS = {"managers", "admins"}

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        
        if request.user.is_superuser:
            return True
        
        user_groups = set(request.user.groups.values_list("name", flat=True))
        return bool(user_groups & self.ALLOWED_GROUPS)


class IsIncidentLead(BasePermission):
    """
    Object-level permission: Only the incident lead or staff can modify.
    """
    message = "You must be the incident lead to perform this action."

    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        if request.method in SAFE_METHODS:
            return True
        
        if request.user.is_staff or request.user.is_superuser:
            return True
        
        # Check if user is the incident lead
        if hasattr(obj, "lead"):
            return obj.lead == request.user
        
        return False


class IsTeamMember(BasePermission):
    """
    Object-level permission: Only team members can modify their team's resources.
    """
    message = "You must be a team member to perform this action."

    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        if request.method in SAFE_METHODS:
            return True
        
        if request.user.is_staff or request.user.is_superuser:
            return True
        
        # Check service ownership via team on-call
        if hasattr(obj, "service") and obj.service and obj.service.owner_team:
            team = obj.service.owner_team
            if team.current_on_call == request.user:
                return True
            # Could extend to check team members if we add that field
        
        return False


class CanAcknowledgeIncident(BasePermission):
    """
    Permission to acknowledge an incident.
    Requires operator role or being the incident lead.
    """
    message = "You don't have permission to acknowledge this incident."

    ALLOWED_GROUPS = {"operators", "responders", "managers", "admins"}

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        
        if request.user.is_staff or request.user.is_superuser:
            return True
        
        user_groups = set(request.user.groups.values_list("name", flat=True))
        return bool(user_groups & self.ALLOWED_GROUPS)

    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        if request.user.is_staff or request.user.is_superuser:
            return True
        
        # Lead can always acknowledge
        if hasattr(obj, "lead") and obj.lead == request.user:
            return True
        
        # Team on-call can acknowledge
        if hasattr(obj, "service") and obj.service and obj.service.owner_team:
            if obj.service.owner_team.current_on_call == request.user:
                return True
        
        user_groups = set(request.user.groups.values_list("name", flat=True))
        return bool(user_groups & self.ALLOWED_GROUPS)


class CanResolveIncident(BasePermission):
    """
    Permission to resolve an incident.
    Requires responder role or being the incident lead.
    """
    message = "You don't have permission to resolve this incident."

    ALLOWED_GROUPS = {"responders", "managers", "admins"}

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        
        if request.user.is_staff or request.user.is_superuser:
            return True
        
        user_groups = set(request.user.groups.values_list("name", flat=True))
        return bool(user_groups & self.ALLOWED_GROUPS)

    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        if request.user.is_staff or request.user.is_superuser:
            return True
        
        # Lead can always resolve
        if hasattr(obj, "lead") and obj.lead == request.user:
            return True
        
        user_groups = set(request.user.groups.values_list("name", flat=True))
        return bool(user_groups & self.ALLOWED_GROUPS)


class IsAPIKeyAuthenticated(BasePermission):
    """
    Permission for service-to-service API calls using API keys.
    Checks for X-API-Key header.
    """
    message = "Valid API key required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        from django.conf import settings
        
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return False
        
        # Check against configured API keys
        valid_keys = getattr(settings, "API_KEYS", [])
        return api_key in valid_keys


class ReadOnlyOrAuthenticated(BasePermission):
    """
    Read-only for anonymous users, full access for authenticated.
    """
    def has_permission(self, request: Request, view: APIView) -> bool:
        if request.method in SAFE_METHODS:
            return True
        return request.user and request.user.is_authenticated
