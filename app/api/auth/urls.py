"""
IMAS Manager - API Auth URL Configuration

Endpoints for token management.
"""
from __future__ import annotations

from django.urls import path

from api.auth import views

app_name = "api_auth"

urlpatterns = [
    # Obtain token (login)
    path("obtain/", views.ObtainTokenView.as_view(), name="obtain_token"),
    
    # Verify token validity
    path("verify/", views.VerifyTokenView.as_view(), name="verify_token"),
    
    # Revoke token (logout)
    path("revoke/", views.RevokeTokenView.as_view(), name="revoke_token"),
    
    # Regenerate token
    path("regenerate/", views.RegenerateTokenView.as_view(), name="regenerate_token"),
]
