"""
IMAS Manager - API Auth Serializers

Serializers for token authentication.
"""
from __future__ import annotations

from rest_framework import serializers


class ObtainTokenSerializer(serializers.Serializer):
    """Serializer for token obtain request."""
    
    username = serializers.CharField(
        max_length=150,
        help_text="Username for authentication.",
    )
    password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
        help_text="Password for authentication.",
    )


class TokenResponseSerializer(serializers.Serializer):
    """Serializer for token response."""
    
    token = serializers.CharField(
        read_only=True,
        help_text="API token for authentication. Use in header: 'Authorization: Token <token>'",
    )
    user_id = serializers.IntegerField(
        read_only=True,
        help_text="User ID associated with the token.",
    )
    username = serializers.CharField(
        read_only=True,
        help_text="Username associated with the token.",
    )
    created = serializers.BooleanField(
        read_only=True,
        required=False,
        help_text="Whether a new token was created.",
    )
