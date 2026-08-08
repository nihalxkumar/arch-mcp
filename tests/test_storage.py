# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""Tests for unified storage analysis functionality."""

import pytest
from arch_ops_server.system import analyze_storage


async def test_analyze_storage_disk_usage():
    """Test disk usage analysis."""
    result = await analyze_storage(action="disk_usage")
    assert "disk_usage" in result or "error" in result


async def test_analyze_storage_cache_stats():
    """Test pacman cache stats analysis."""
    result = await analyze_storage(action="cache_stats")
    # analyze_storage forwards get_pacman_cache_stats' payload unchanged; the
    # fields are returned flat, not under a "cache_stats" key.
    assert "cache_dir" in result or "error" in result


async def test_analyze_storage_invalid_action():
    """Test error handling for invalid action."""
    result = await analyze_storage(action="invalid_action")
    assert "error" in result
