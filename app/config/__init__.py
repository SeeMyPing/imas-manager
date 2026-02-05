"""
IMAS Manager - Django Configuration Package

This package contains the core Django settings and configuration.
"""
from __future__ import annotations

from .celery import app as celery_app

__all__ = ("celery_app",)
