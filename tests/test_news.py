# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
Tests for arch_ops_server.news module.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from xml.etree import ElementTree as ET

import httpx
import pytest

from arch_ops_server.news import (
    ARCH_NEWS_URL,
    CRITICAL_KEYWORDS,
    get_latest_news,
    check_critical_news,
    get_news_since_last_update,
)


class TestNewsRetrieval:
    """Test Arch Linux news feed retrieval."""

    @pytest.fixture
    def sample_rss_feed(self):
        """Sample RSS feed XML for testing."""
        return """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
    <channel>
        <title>Arch Linux: Recent news updates</title>
        <item>
            <title>Manual intervention required for foo package</title>
            <link>https://archlinux.org/news/manual-intervention-foo/</link>
            <pubDate>Mon, 10 Nov 2025 10:00:00 +0000</pubDate>
            <description><![CDATA[<p>Action required before upgrading foo package.</p>]]></description>
        </item>
        <item>
            <title>New kernel release 6.7</title>
            <link>https://archlinux.org/news/kernel-6-7/</link>
            <pubDate>Sun, 09 Nov 2025 14:00:00 +0000</pubDate>
            <description><![CDATA[<p>The Linux kernel has been updated to version 6.7.</p>]]></description>
        </item>
        <item>
            <title>Breaking change in systemd</title>
            <link>https://archlinux.org/news/systemd-breaking/</link>
            <pubDate>Sat, 08 Nov 2025 09:00:00 +0000</pubDate>
            <description><![CDATA[<p>Important changes in systemd configuration.</p>]]></description>
        </item>
    </channel>
</rss>
"""

    @pytest.mark.asyncio
    async def test_get_latest_news_success(self, sample_rss_feed):
        """Test successful news retrieval."""
        mock_response = MagicMock()
        mock_response.content = sample_rss_feed.encode('utf-8')
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await get_latest_news(limit=10)

            assert result["count"] == 3
            assert len(result["news"]) == 3
            assert result["news"][0]["title"] == "Manual intervention required for foo package"
            assert "archlinux.org" in result["news"][0]["link"]

    @pytest.mark.asyncio
    async def test_get_latest_news_with_limit(self, sample_rss_feed):
        """Test news retrieval with limit."""
        mock_response = MagicMock()
        mock_response.content = sample_rss_feed.encode('utf-8')
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await get_latest_news(limit=2)

            assert result["count"] == 2
            assert len(result["news"]) == 2

    @pytest.mark.asyncio
    async def test_get_latest_news_http_error(self):
        """Test news retrieval with HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "HTTP 500", request=MagicMock(), response=mock_response
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await get_latest_news()

        assert "error" in result
        assert result["type"] == "HTTPError"

    @pytest.mark.asyncio
    async def test_get_latest_news_timeout(self):
        """Test news retrieval with timeout."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.TimeoutException("Request timed out")
            )

            result = await get_latest_news()

        assert "error" in result
        assert result["type"] == "Timeout"


class TestCriticalNews:
    """Test critical news detection."""

    @pytest.fixture
    def critical_rss_feed(self):
        """RSS feed with critical news items."""
        return """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
    <channel>
        <item>
            <title>Manual intervention required for glibc</title>
            <link>https://archlinux.org/news/glibc-manual/</link>
            <pubDate>Mon, 10 Nov 2025 10:00:00 +0000</pubDate>
            <description><![CDATA[<p>Action required before upgrading.</p>]]></description>
        </item>
        <item>
            <title>Regular package update</title>
            <link>https://archlinux.org/news/regular/</link>
            <pubDate>Sun, 09 Nov 2025 14:00:00 +0000</pubDate>
            <description><![CDATA[<p>Normal update information.</p>]]></description>
        </item>
    </channel>
</rss>
"""

    @pytest.mark.asyncio
    async def test_check_critical_news_found(self, critical_rss_feed):
        """Test detection of critical news."""
        mock_response = MagicMock()
        mock_response.content = critical_rss_feed.encode('utf-8')
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await check_critical_news()

            assert result["has_critical"] is True
            assert result["critical_count"] == 1
            assert len(result["critical_news"]) == 1
            assert "manual intervention" in result["critical_news"][0]["title"].lower()
            assert "matched_keywords" in result["critical_news"][0]

    @pytest.mark.asyncio
    async def test_check_critical_news_none_found(self):
        """Test when no critical news is found."""
        safe_feed = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
    <channel>
        <item>
            <title>Regular update</title>
            <link>https://archlinux.org/news/regular/</link>
            <pubDate>Mon, 10 Nov 2025 10:00:00 +0000</pubDate>
            <description><![CDATA[<p>Normal update.</p>]]></description>
        </item>
    </channel>
</rss>
"""
        mock_response = MagicMock()
        mock_response.content = safe_feed.encode('utf-8')
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await check_critical_news()

            assert result["has_critical"] is False
            assert result["critical_count"] == 0


class TestNewsSinceUpdate:
    """Test news since last update functionality."""

    @pytest.fixture
    def sample_pacman_log(self):
        """Sample pacman log content."""
        return """[2025-11-08 10:00] [PACMAN] Running 'pacman -Syu'
[2025-11-08 10:01] [ALPM] upgraded linux (6.6.1-1 -> 6.6.2-1)
[2025-11-08 10:02] [ALPM] upgraded systemd (255.1-1 -> 255.2-1)
[2025-11-08 10:03] [PACMAN] synchronizing package lists
[2025-11-09 15:30] [ALPM] installed test-package (1.0-1)
"""

    @pytest.mark.asyncio
    @patch("arch_ops_server.news.IS_ARCH", True)
    async def test_get_news_since_last_update_success(self, sample_pacman_log):
        """Test getting news since last update."""
        rss_feed = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
    <channel>
        <item>
            <title>Recent news after update</title>
            <link>https://archlinux.org/news/recent/</link>
            <pubDate>Mon, 10 Nov 2025 10:00:00 +0000</pubDate>
            <description><![CDATA[<p>New announcement.</p>]]></description>
        </item>
        <item>
            <title>Old news before update</title>
            <link>https://archlinux.org/news/old/</link>
            <pubDate>Wed, 06 Nov 2025 10:00:00 +0000</pubDate>
            <description><![CDATA[<p>Old announcement.</p>]]></description>
        </item>
    </channel>
</rss>
"""
        mock_response = MagicMock()
        mock_response.content = rss_feed.encode('utf-8')
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client, \
             patch("builtins.open", mock_open(read_data=sample_pacman_log)):
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await get_news_since_last_update()

            assert result["has_news"] is True
            assert result["news_count"] >= 0
            assert "last_update" in result

    @pytest.mark.asyncio
    @patch("arch_ops_server.news.IS_ARCH", False)
    async def test_get_news_since_last_update_not_arch(self):
        """Test on non-Arch system."""
        result = await get_news_since_last_update()

        assert "error" in result
        assert result["type"] == "NotSupported"

    @pytest.mark.asyncio
    @patch("arch_ops_server.news.IS_ARCH", True)
    async def test_get_news_since_last_update_no_log(self):
        """Test when pacman log doesn't exist."""
        with patch("pathlib.Path.exists", return_value=False):
            result = await get_news_since_last_update()

        assert "error" in result
        assert result["type"] == "NotFound"

