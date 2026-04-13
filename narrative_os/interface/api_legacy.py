"""Deprecated compatibility entrypoint for the legacy API module.

This module intentionally re-exports the current FastAPI application so the
codebase maintains a single route specification while preserving import-level
compatibility for older callers.
"""

from narrative_os import __version__
from narrative_os.interface.api import app

LEGACY_API_DEPRECATED = True

__all__ = ["LEGACY_API_DEPRECATED", "__version__", "app"]