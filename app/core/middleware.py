"""
IMAS Manager - Security Middleware

Provides audit logging and security headers for the application.
"""
from __future__ import annotations

import logging
import time
from typing import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse

logger = logging.getLogger(__name__)


class AuditLogMiddleware:
    """
    Middleware to log API requests for security auditing.
    
    Only logs:
    - API endpoints (starting with /api/)
    - Mutating requests (POST, PUT, PATCH, DELETE)
    - Authentication endpoints
    """
    
    AUDIT_PATHS = ["/api/", "/auth/", "/admin/"]
    SKIP_PATHS = ["/api/v1/health/", "/health/", "/static/", "/favicon.ico"]
    AUDIT_METHODS = ["POST", "PUT", "PATCH", "DELETE"]
    
    def __init__(self, get_response: Callable):
        self.get_response = get_response
    
    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Skip non-audit paths
        if not self._should_audit(request):
            return self.get_response(request)
        
        start_time = time.time()
        
        response = self.get_response(request)
        
        # Log after response
        duration_ms = (time.time() - start_time) * 1000
        self._log_request(request, response, duration_ms)
        
        return response
    
    def _should_audit(self, request: HttpRequest) -> bool:
        """Determine if request should be audited."""
        path = request.path
        
        # Skip certain paths
        for skip_path in self.SKIP_PATHS:
            if path.startswith(skip_path):
                return False
        
        # Only audit specific paths
        for audit_path in self.AUDIT_PATHS:
            if path.startswith(audit_path):
                # For GET requests, only log admin access
                if request.method == "GET" and not path.startswith("/admin/"):
                    return False
                return True
        
        return False
    
    def _log_request(self, request: HttpRequest, response: HttpResponse, duration_ms: float):
        """Log the request to audit log."""
        from core.models import AuditLog, AuditAction
        
        # Determine action type
        if response.status_code >= 400:
            action = AuditAction.API_ERROR
        else:
            action = AuditAction.API_REQUEST
        
        # Build description
        description = f"{request.method} {request.path} -> {response.status_code} ({duration_ms:.0f}ms)"
        
        try:
            AuditLog.log(
                action=action,
                user=request.user if hasattr(request, "user") else None,
                request=request,
                resource_type="API",
                description=description,
                success=response.status_code < 400,
                error_message=str(response.status_code) if response.status_code >= 400 else "",
            )
        except Exception as e:
            logger.warning(f"Failed to create audit log: {e}")


class SecurityHeadersMiddleware:
    """
    Middleware to add security headers to all responses.
    """
    
    def __init__(self, get_response: Callable):
        self.get_response = get_response
    
    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        
        # Security headers
        response["X-Content-Type-Options"] = "nosniff"
        response["X-Frame-Options"] = "DENY"
        response["X-XSS-Protection"] = "1; mode=block"
        response["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # HSTS (only in production)
        if not settings.DEBUG:
            response["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Content Security Policy
        if not settings.DEBUG:
            response["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' cdn.tailwindcss.com cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' cdn.tailwindcss.com cdnjs.cloudflare.com; "
                "font-src 'self' cdnjs.cloudflare.com; "
                "img-src 'self' data:; "
                "connect-src 'self'; "
                "frame-ancestors 'none';"
            )
        
        return response


class RateLimitByIPMiddleware:
    """
    Simple IP-based rate limiting middleware.
    Uses Django cache for tracking.
    """
    
    # Requests per minute for anonymous users
    RATE_LIMIT = 60
    
    def __init__(self, get_response: Callable):
        self.get_response = get_response
    
    def __call__(self, request: HttpRequest) -> HttpResponse:
        from django.core.cache import cache
        from django.http import JsonResponse
        
        # Skip for authenticated users (they have DRF throttling)
        if hasattr(request, "user") and request.user.is_authenticated:
            return self.get_response(request)
        
        # Skip for non-API paths
        if not request.path.startswith("/api/"):
            return self.get_response(request)
        
        # Get client IP
        ip = self._get_client_ip(request)
        cache_key = f"rate_limit:{ip}"
        
        # Check rate limit
        request_count = cache.get(cache_key, 0)
        
        if request_count >= self.RATE_LIMIT:
            return JsonResponse(
                {"error": "Rate limit exceeded. Please try again later."},
                status=429,
            )
        
        # Increment counter
        cache.set(cache_key, request_count + 1, 60)  # 60 second window
        
        response = self.get_response(request)
        
        # Add rate limit headers
        response["X-RateLimit-Limit"] = str(self.RATE_LIMIT)
        response["X-RateLimit-Remaining"] = str(max(0, self.RATE_LIMIT - request_count - 1))
        
        return response
    
    @staticmethod
    def _get_client_ip(request: HttpRequest) -> str:
        """Extract client IP from request."""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "")
