"""Shared pytest fixtures for the bare-pytest suites.

Deliberately tiny — the suites run on plain ``pytest`` (no pytest-asyncio) by
design (see CLAUDE.md), so this only wires up cross-test isolation that every
suite needs.
"""
from __future__ import annotations

import asyncio

import pytest


@pytest.fixture(autouse=True)
def _clear_inmemory_cache():
    """Reset the process-global in-memory data cache between tests.

    ``utils.cache.cache`` holds the orchestrator's per-match snapshot
    (``orch:<match_id>`` — which now also carries ``live_odds``) plus every
    connector's per-call payload. Because it is a module-global singleton, two
    tests that predict the *same* match id would otherwise share a snapshot:
    the second test gets a cache hit and silently bypasses any monkeypatched
    connector. Clearing before each test keeps them independent (and matches
    the fresh-process assumption the CI list already relies on).
    """
    from utils.cache import cache

    asyncio.run(cache.invalidate())
    yield
    asyncio.run(cache.invalidate())
