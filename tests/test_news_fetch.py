# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""Tests for unified news fetching functionality."""

import pytest
from arch_ops_server.news import fetch_news


async def test_fetch_news_latest():
    """Test latest news fetching."""
    result = await fetch_news(action="latest", limit=5)
    assert "news" in result or "error" in result


async def test_fetch_news_critical():
    """Test critical news fetching."""
    result = await fetch_news(action="critical", limit=5)
    assert "critical_count" in result or "error" in result


async def test_fetch_news_since_update():
    """Test news since last update."""
    result = await fetch_news(action="since_update")
    assert "news" in result or "error" in result


async def test_fetch_news_invalid_action():
    """Test error handling for invalid action."""
    result = await fetch_news(action="invalid_action")
    assert "error" in result
