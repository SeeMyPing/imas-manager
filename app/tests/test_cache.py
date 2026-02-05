"""
IMAS Manager - Cache Tests

Tests for Redis caching utilities.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from core.cache import (
    CacheManager,
    cached_queryset,
    get_cache_timeout,
    make_cache_key,
)


class CacheKeyTestCase(TestCase):
    """Test cache key generation."""

    def test_make_cache_key_simple(self):
        """Test simple cache key generation."""
        key = make_cache_key("incidents", "active")
        self.assertTrue(key.startswith("imas:"))
        # Format: imas:<12 char hash>
        self.assertGreaterEqual(len(key), 17)

    def test_make_cache_key_with_prefix(self):
        """Test cache key with custom prefix."""
        key = make_cache_key("test", prefix="custom")
        self.assertTrue(key.startswith("custom:"))

    def test_make_cache_key_consistent(self):
        """Test that same inputs produce same key."""
        key1 = make_cache_key("a", "b", "c")
        key2 = make_cache_key("a", "b", "c")
        self.assertEqual(key1, key2)

    def test_make_cache_key_different_inputs(self):
        """Test that different inputs produce different keys."""
        key1 = make_cache_key("a", "b")
        key2 = make_cache_key("a", "c")
        self.assertNotEqual(key1, key2)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    },
    CACHE_TIMEOUTS={
        "dashboard_stats": 60,
        "incident_list": 30,
    }
)
class CacheTimeoutTestCase(TestCase):
    """Test cache timeout configuration."""

    def test_get_cache_timeout_known_type(self):
        """Test getting timeout for known cache type."""
        timeout = get_cache_timeout("dashboard_stats")
        self.assertEqual(timeout, 60)

    def test_get_cache_timeout_unknown_type(self):
        """Test default timeout for unknown type."""
        timeout = get_cache_timeout("unknown_type")
        self.assertEqual(timeout, 300)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
)
class CacheManagerTestCase(TestCase):
    """Test CacheManager class methods."""

    def setUp(self):
        cache.clear()

    def test_dashboard_stats_set_get(self):
        """Test setting and getting dashboard stats."""
        stats = {"triggered": 5, "acknowledged": 3}
        CacheManager.set_dashboard_stats(stats)
        
        retrieved = CacheManager.get_dashboard_stats()
        self.assertEqual(retrieved, stats)

    def test_dashboard_stats_invalidate(self):
        """Test invalidating dashboard stats."""
        CacheManager.set_dashboard_stats({"count": 10})
        CacheManager.invalidate_dashboard_stats()
        
        self.assertIsNone(CacheManager.get_dashboard_stats())

    def test_incident_count_set_get(self):
        """Test setting and getting incident counts."""
        CacheManager.set_incident_count("TRIGGERED", 42)
        
        count = CacheManager.get_incident_count("TRIGGERED")
        self.assertEqual(count, 42)

    def test_incident_counts_invalidate(self):
        """Test invalidating all incident counts."""
        CacheManager.set_incident_count("TRIGGERED", 10)
        CacheManager.set_incident_count("ACKNOWLEDGED", 5)
        CacheManager.invalidate_incident_counts()
        
        self.assertIsNone(CacheManager.get_incident_count("TRIGGERED"))
        self.assertIsNone(CacheManager.get_incident_count("ACKNOWLEDGED"))

    def test_services_list_set_get(self):
        """Test services list caching."""
        services = [{"id": 1, "name": "API"}, {"id": 2, "name": "DB"}]
        CacheManager.set_services_list(services)
        
        retrieved = CacheManager.get_services_list()
        self.assertEqual(retrieved, services)

    def test_services_invalidate(self):
        """Test invalidating services cache."""
        CacheManager.set_services_list([{"id": 1}])
        CacheManager.invalidate_services()
        
        self.assertIsNone(CacheManager.get_services_list())

    def test_teams_list_set_get(self):
        """Test teams list caching."""
        teams = [{"id": 1, "name": "SRE"}]
        CacheManager.set_teams_list(teams)
        
        retrieved = CacheManager.get_teams_list()
        self.assertEqual(retrieved, teams)

    def test_clear_all(self):
        """Test clearing all caches."""
        CacheManager.set_dashboard_stats({"count": 1})
        CacheManager.set_services_list([{"id": 1}])
        
        CacheManager.clear_all()
        
        self.assertIsNone(CacheManager.get_dashboard_stats())
        self.assertIsNone(CacheManager.get_services_list())


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
)
class CachedQuerysetDecoratorTestCase(TestCase):
    """Test @cached_queryset decorator."""

    def setUp(self):
        cache.clear()

    def test_cached_queryset_caches_result(self):
        """Test that decorated function result is cached."""
        call_count = 0
        
        @cached_queryset("test_key")
        def get_data():
            nonlocal call_count
            call_count += 1
            return ["a", "b", "c"]
        
        # First call - should execute function
        result1 = get_data()
        self.assertEqual(result1, ["a", "b", "c"])
        self.assertEqual(call_count, 1)
        
        # Second call - should return cached
        result2 = get_data()
        self.assertEqual(result2, ["a", "b", "c"])
        self.assertEqual(call_count, 1)  # Still 1

    def test_cached_queryset_with_args(self):
        """Test cached queryset with function arguments."""
        @cached_queryset("parameterized")
        def get_by_status(status):
            return [f"incident_{status}"]
        
        result_a = get_by_status("TRIGGERED")
        result_b = get_by_status("RESOLVED")
        
        # Different args = different cache keys
        self.assertEqual(result_a, ["incident_TRIGGERED"])
        self.assertEqual(result_b, ["incident_RESOLVED"])
