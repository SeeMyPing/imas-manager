"""
IMAS Manager - API Auth Views

Token management views for API authentication.
"""
from __future__ import annotations

from django.contrib.auth import authenticate
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.auth.serializers import (
    ObtainTokenSerializer,
    TokenResponseSerializer,
)


@extend_schema(
    tags=["auth"],
    summary="Obtain API token",
    description="""
Authenticate with username and password to obtain an API token.

The token should be included in the `Authorization` header for subsequent requests:
```
Authorization: Token <your-token>
```

**Token lifespan:** Tokens do not expire automatically. Use the revoke endpoint to invalidate a token.
    """,
    request=ObtainTokenSerializer,
    responses={
        200: OpenApiResponse(
            response=TokenResponseSerializer,
            description="Authentication successful",
            examples=[
                OpenApiExample(
                    "Success",
                    value={
                        "token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b",
                        "user_id": 1,
                        "username": "admin",
                        "created": True,
                    },
                )
            ],
        ),
        401: OpenApiResponse(
            description="Authentication failed",
            examples=[
                OpenApiExample(
                    "Invalid Credentials",
                    value={"error": "Invalid credentials"},
                ),
                OpenApiExample(
                    "Disabled Account",
                    value={"error": "User account is disabled"},
                ),
            ],
        ),
    },
    examples=[
        OpenApiExample(
            "Login Request",
            value={"username": "admin", "password": "password123"},
            request_only=True,
        ),
    ],
)
class ObtainTokenView(APIView):
    """
    Obtain an API token by providing username and password.
    
    Used by monitoring tools and external services to authenticate.
    """
    
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = ObtainTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = authenticate(
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        
        if not user:
            return Response(
                {"error": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        
        if not user.is_active:
            return Response(
                {"error": "User account is disabled"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        
        # Get or create token
        token, created = Token.objects.get_or_create(user=user)
        
        return Response(
            TokenResponseSerializer({
                "token": token.key,
                "user_id": user.id,
                "username": user.username,
                "created": created,
            }).data,
            status=status.HTTP_200_OK,
        )


@extend_schema(
    tags=["auth"],
    summary="Verify token",
    description="Verify that the current authentication token is valid and return user information.",
    responses={
        200: OpenApiResponse(
            description="Token is valid",
            examples=[
                OpenApiExample(
                    "Valid Token",
                    value={
                        "valid": True,
                        "user_id": 1,
                        "username": "admin",
                        "email": "admin@example.com",
                    },
                )
            ],
        ),
        401: OpenApiResponse(description="Invalid or missing token"),
    },
)
class VerifyTokenView(APIView):
    """
    Verify that the current token is valid.
    
    GET /api/token/verify/
    Headers: Authorization: Token abc123...
    
    Returns user information if token is valid.
    """
    
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response({
            "valid": True,
            "user_id": request.user.id,
            "username": request.user.username,
            "email": request.user.email,
        })


@extend_schema(
    tags=["auth"],
    summary="Revoke token",
    description="""
Revoke (delete) the current user's authentication token.

After calling this endpoint, the token will no longer be valid.
Use this for logout functionality or when a token might be compromised.
    """,
    request=None,
    responses={
        200: OpenApiResponse(
            description="Token revoked successfully",
            examples=[
                OpenApiExample(
                    "Success",
                    value={"message": "Token revoked successfully"},
                )
            ],
        ),
        401: OpenApiResponse(description="Invalid or missing token"),
    },
)
class RevokeTokenView(APIView):
    """
    Revoke (delete) the current user's token.
    """
    
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        try:
            request.user.auth_token.delete()
        except Token.DoesNotExist:
            pass
        
        return Response(
            {"message": "Token revoked successfully"},
            status=status.HTTP_200_OK,
        )


@extend_schema(
    tags=["auth"],
    summary="Regenerate token",
    description="""
Regenerate (rotate) the current user's authentication token.

This deletes the old token and creates a new one.
Useful for:
- Regular security rotation
- If the current token might be compromised
- Forcing re-authentication of other sessions
    """,
    request=None,
    responses={
        200: OpenApiResponse(
            response=TokenResponseSerializer,
            description="New token generated",
        ),
        401: OpenApiResponse(description="Invalid or missing token"),
    },
)
class RegenerateTokenView(APIView):
    """
    Regenerate (rotate) the current user's token.
    """
    
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        # Delete existing token
        try:
            request.user.auth_token.delete()
        except Token.DoesNotExist:
            pass
        
        # Create new token
        token = Token.objects.create(user=request.user)
        
        return Response(
            TokenResponseSerializer({
                "token": token.key,
                "user_id": request.user.id,
                "username": request.user.username,
                "created": True,
            }).data,
            status=status.HTTP_200_OK,
        )
