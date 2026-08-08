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


def build_rss_feed(*items):
    """Build an RSS feed body from (title, pubDate) pairs."""
    entries = "\n".join(
        f"""        <item>
            <title>{title}</title>
            <link>https://archlinux.org/news/{index}/</link>
            <pubDate>{pub_date}</pubDate>
            <description><![CDATA[<p>Announcement {index}.</p>]]></description>
        </item>"""
        for index, (title, pub_date) in enumerate(items)
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
    <channel>
{entries}
    </channel>
</rss>
""".encode('utf-8')


async def news_since_update(pacman_log, feed):
    """Run get_news_since_last_update against a fake pacman log and feed."""
    mock_response = MagicMock()
    mock_response.content = feed
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client, \
         patch("pathlib.Path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=pacman_log)):
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )

        return await get_news_since_last_update()


class TestNewsSinceUpdate:
    """Test news since last update functionality."""

    @pytest.fixture
    def sample_pacman_log(self):
        """Pacman log in the ISO-8601 format pacman has written since 5.2."""
        return """[2026-08-06T09:12:03+0200] [PACMAN] starting full system upgrade
[2026-08-06T09:12:40+0200] [ALPM] upgraded linux (6.6.1-1 -> 6.6.2-1)
[2026-08-08T10:00:00+0200] [PACMAN] starting full system upgrade
[2026-08-08T10:00:31+0200] [ALPM] upgraded systemd (255.1-1 -> 255.2-1)
[2026-08-08T18:30:00+0200] [ALPM] installed test-package (1.0-1)
"""

    @pytest.mark.asyncio
    @patch("arch_ops_server.news.IS_ARCH", True)
    async def test_get_news_since_last_update_success(self, sample_pacman_log):
        """The boundary is the last full upgrade, and only later news is returned."""
        feed = build_rss_feed(
            ("Announced after the upgrade", "Sat, 08 Aug 2026 12:00:00 +0000"),
            ("Announced before the upgrade", "Thu, 06 Aug 2026 06:00:00 +0000"),
        )

        result = await news_since_update(sample_pacman_log, feed)

        assert result["last_update"] == "2026-08-08T10:00:00+02:00"
        assert result["boundary_known"] is True
        assert result["has_news"] is True
        assert result["news_count"] == 1
        assert [item["title"] for item in result["news"]] == [
            "Announced after the upgrade"
        ]

    @pytest.mark.asyncio
    @patch("arch_ops_server.news.IS_ARCH", True)
    async def test_get_news_since_last_update_honours_timezone(self):
        """The log's own offset is used, not a hardcoded UTC one."""
        # 10:00+0200 is 08:00 UTC. An item published at 09:00 UTC comes after
        # the upgrade; reading the stamp as if it were UTC would hide it.
        pacman_log = "[2026-08-08T10:00:00+0200] [PACMAN] starting full system upgrade\n"
        feed = build_rss_feed(
            ("Published in the offset window", "Sat, 08 Aug 2026 09:00:00 +0000"),
        )

        result = await news_since_update(pacman_log, feed)

        assert result["last_update"] == "2026-08-08T10:00:00+02:00"
        assert result["news_count"] == 1
        assert result["news"][0]["title"] == "Published in the offset window"

    @pytest.mark.asyncio
    @patch("arch_ops_server.news.IS_ARCH", True)
    async def test_get_news_since_last_update_ignores_package_install(
        self, sample_pacman_log
    ):
        """A later single-package install must not move the boundary forward."""
        # The log ends with an install at 18:30+0200 (16:30 UTC), hours after
        # the last full upgrade at 10:00+0200 (08:00 UTC).
        feed = build_rss_feed(
            ("Published between upgrade and install", "Sat, 08 Aug 2026 14:00:00 +0000"),
        )

        result = await news_since_update(sample_pacman_log, feed)

        assert result["last_update"] == "2026-08-08T10:00:00+02:00"
        assert result["news_count"] == 1
        assert result["news"][0]["title"] == "Published between upgrade and install"

    @pytest.mark.asyncio
    @patch("arch_ops_server.news.IS_ARCH", True)
    async def test_get_news_since_last_update_legacy_log_format(self):
        """Pre-5.2 space-separated stamps still parse, and land timezone-aware."""
        pacman_log = """[2025-11-08 10:00] [PACMAN] starting full system upgrade
[2025-11-08 10:01] [ALPM] upgraded linux (6.6.1-1 -> 6.6.2-1)
"""
        # A naive stamp is read as local time, so the expectation has to be too.
        # The feed dates sit days either side, well clear of any host offset.
        expected = datetime.fromisoformat("2025-11-08 10:00").astimezone()
        feed = build_rss_feed(
            ("Announced after the upgrade", "Wed, 12 Nov 2025 10:00:00 +0000"),
            ("Announced before the upgrade", "Tue, 04 Nov 2025 10:00:00 +0000"),
        )

        result = await news_since_update(pacman_log, feed)

        assert result["last_update"] == expected.isoformat()
        assert [item["title"] for item in result["news"]] == [
            "Announced after the upgrade"
        ]

    @pytest.mark.asyncio
    @patch("arch_ops_server.news.IS_ARCH", True)
    async def test_get_news_since_last_update_no_full_upgrade(self):
        """With no upgrade to anchor on, report all the news rather than none."""
        pacman_log = """[2026-08-08T10:00:31+0200] [ALPM] installed test-package (1.0-1)
[2026-08-08T18:30:00+0200] [ALPM] upgraded linux (6.6.1-1 -> 6.6.2-1)
"""
        feed = build_rss_feed(
            ("First announcement", "Sat, 08 Aug 2026 12:00:00 +0000"),
            ("Second announcement", "Thu, 06 Aug 2026 06:00:00 +0000"),
        )

        result = await news_since_update(pacman_log, feed)

        assert "error" not in result
        assert result["last_update"] is None
        assert result["boundary_known"] is False
        assert "rotated" in result["note"]
        assert result["has_news"] is True
        assert result["news_count"] == 2

    @pytest.mark.asyncio
    @patch("arch_ops_server.news.IS_ARCH", True)
    async def test_get_news_since_last_update_unreadable_log(self):
        """An unreadable log is reported as such, not as a generic news error."""
        with patch("pathlib.Path.exists", return_value=True), \
             patch("builtins.open", side_effect=PermissionError("Permission denied")):
            result = await get_news_since_last_update()

        assert "error" in result
        assert result["type"] == "ReadError"
        assert "Permission denied" in result["message"]

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

