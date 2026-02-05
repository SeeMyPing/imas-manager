"""
IMAS Manager - Cache Utilities

Redis-based caching for performance optimization.
"""
from __future__ import annotations

import hashlib
import json
import logging
from functools import wraps
from typing import Any, Callable, Optional

from django.conf import settings
from django.core.cache import cache
from django.db.models import QuerySet

logger = logging.getLogger(__name__)


def get_cache_timeout(cache_type: str) -> int:
    """Get cache timeout for a specific data type."""
    timeouts = getattr(settings, "CACHE_TIMEOUTS", {})
    return timeouts.get(cache_type, 300)  # Default 5 minutes


def make_cache_key(*args, prefix: str = "imas") -> str:
    """
    Generate a consistent cache key from arguments.
    
    Args:
        *args: Values to include in the key
        prefix: Key prefix for namespacing
    
    Returns:
        A unique cache key string
    """
    key_data = ":".join(str(arg) for arg in args)
    key_hash = hashlib.md5(key_data.encode()).hexdigest()[:12]
    return f"{prefix}:{key_hash}"


def cached_queryset(
    cache_key: str,
    timeout: Optional[int] = None,
    cache_type: str = "default",
) -> Callable:
    """
    Decorator to cache QuerySet results.
    
    Usage:
        @cached_queryset("active_incidents", cache_type="incident_list")
        def get_active_incidents():
            return Incident.objects.filter(status="TRIGGERED")
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Generate unique key based on function args
            key_parts = [cache_key] + [str(a) for a in args]
            key_parts += [f"{k}={v}" for k, v in sorted(kwargs.items())]
            full_key = make_cache_key(*key_parts)
            
            # Try to get from cache
            cached = cache.get(full_key)
            if cached is not None:
                logger.debug(f"Cache hit: {full_key}")
                return cached
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            
            # Handle QuerySets by converting to list
            if isinstance(result, QuerySet):
                result = list(result)
            
            effective_timeout = timeout or get_cache_timeout(cache_type)
            cache.set(full_key, result, timeout=effective_timeout)
            logger.debug(f"Cache set: {full_key} (TTL: {effective_timeout}s)")
            
            return result
        return wrapper
    return decorator


def cached_property_with_ttl(timeout: int = 300) -> Callable:
    """
    Decorator for caching expensive model property calculations.
    
    Usage:
        class Incident(Model):
            @cached_property_with_ttl(timeout=60)
            def mttr_seconds(self):
                # Expensive calculation
                ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self) -> Any:
            cache_key = f"prop:{self.__class__.__name__}:{self.pk}:{func.__name__}"
            
            cached = cache.get(cache_key)
            if cached is not None:
                return cached
            
            result = func(self)
            cache.set(cache_key, result, timeout=timeout)
            return result
        return wrapper
    return decorator


class CacheManager:
    """
    Centralized cache management for IMAS.
    
    Provides methods for caching common data patterns.
    """
    
    @staticmethod
    def get_dashboard_stats() -> Optional[dict]:
        """Get cached dashboard statistics."""
        return cache.get("imas:dashboard:stats")
    
    @staticmethod
    def set_dashboard_stats(stats: dict) -> None:
        """Cache dashboard statistics."""
        timeout = get_cache_timeout("dashboard_stats")
        cache.set("imas:dashboard:stats", stats, timeout=timeout)
    
    @staticmethod
    def invalidate_dashboard_stats() -> None:
        """Invalidate dashboard stats cache."""
        cache.delete("imas:dashboard:stats")
    
    @staticmethod
    def get_incident_count(status: str) -> Optional[int]:
        """Get cached incident count for a status."""
        return cache.get(f"imas:incident:count:{status}")
    
    @staticmethod
    def set_incident_count(status: str, count: int) -> None:
        """Cache incident count for a status."""
        timeout = get_cache_timeout("incident_list")
        cache.set(f"imas:incident:count:{status}", count, timeout=timeout)
    
    @staticmethod
    def invalidate_incident_counts() -> None:
        """Invalidate all incident count caches."""
        statuses = ["TRIGGERED", "ACKNOWLEDGED", "RESOLVED", "ARCHIVED"]
        for status in statuses:
            cache.delete(f"imas:incident:count:{status}")
        cache.delete("imas:dashboard:stats")
    
    @staticmethod
    def get_services_list() -> Optional[list]:
        """Get cached services list."""
        return cache.get("imas:services:list")
    
    @staticmethod
    def set_services_list(services: list) -> None:
        """Cache services list."""
        timeout = get_cache_timeout("service_list")
        cache.set("imas:services:list", services, timeout=timeout)
    
    @staticmethod
    def invalidate_services() -> None:
        """Invalidate services cache."""
        cache.delete("imas:services:list")
    
    @staticmethod
    def get_teams_list() -> Optional[list]:
        """Get cached teams list."""
        return cache.get("imas:teams:list")
    
    @staticmethod
    def set_teams_list(teams: list) -> None:
        """Cache teams list."""
        timeout = get_cache_timeout("team_list")
        cache.set("imas:teams:list", teams, timeout=timeout)
    
    @staticmethod
    def invalidate_teams() -> None:
        """Invalidate teams cache."""
        cache.delete("imas:teams:list")
    
    @staticmethod
    def clear_all() -> None:
        """Clear all IMAS caches."""
        # Note: This clears all keys with the imas prefix
        # In production, you might want a more targeted approach
        try:
            cache.clear()
            logger.info("All caches cleared")
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")


def invalidate_on_save(cache_types: list[str]):
    """
    Signal handler decorator to invalidate cache on model save.
    
    Usage:
        @receiver(post_save, sender=Incident)
        @invalidate_on_save(["incident_list", "dashboard_stats"])
        def invalidate_incident_cache(sender, **kwargs):
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            
            for cache_type in cache_types:
                if cache_type == "incident_list":
                    CacheManager.invalidate_incident_counts()
                elif cache_type == "dashboard_stats":
                    CacheManager.invalidate_dashboard_stats()
                elif cache_type == "service_list":
                    CacheManager.invalidate_services()
                elif cache_type == "team_list":
                    CacheManager.invalidate_teams()
            
            return result
        return wrapper
    return decorator
