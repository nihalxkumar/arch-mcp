# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
Tests for arch_ops_server.mirrors module.
"""

from unittest.mock import AsyncMock, MagicMock, patch, mock_open

import httpx
import pytest

from arch_ops_server.mirrors import (
    MIRRORLIST_PATH,
    MIRROR_STATUS_URL,
    list_active_mirrors,
    test_mirror_speed,
    suggest_fastest_mirrors,
    check_mirrorlist_health,
)


class TestMirrorList:
    """Test mirrorlist reading and parsing."""

    @pytest.fixture
    def sample_mirrorlist(self):
        """Sample mirrorlist content."""
        return """##
## Arch Linux repository mirrorlist
##

## United States
Server = https://mirror.us1.archlinux.org/$repo/os/$arch
#Server = https://mirror.us2.archlinux.org/$repo/os/$arch

## Germany
Server = https://mirror.de1.archlinux.org/$repo/os/$arch
#Server = https://mirror.de2.archlinux.org/$repo/os/$arch

## Comments and empty lines
# This is a comment
"""

    @pytest.mark.asyncio
    @patch("arch_ops_server.mirrors.IS_ARCH", True)
    async def test_list_active_mirrors_success(self, sample_mirrorlist):
        """Test listing active mirrors."""
        with patch("builtins.open", mock_open(read_data=sample_mirrorlist)):
            result = await list_active_mirrors()
            
            assert result["active_count"] == 2
            assert result["commented_count"] == 2
            assert len(result["active_mirrors"]) == 2
            
            # Check that active mirrors are marked correctly
            for mirror in result["active_mirrors"]:
                assert mirror["active"] is True
                assert "https://" in mirror["url"]

    @pytest.mark.asyncio
    @patch("arch_ops_server.mirrors.IS_ARCH", True)
    async def test_list_active_mirrors_commented(self, sample_mirrorlist):
        """Test that commented mirrors are detected."""
        with patch("builtins.open", mock_open(read_data=sample_mirrorlist)):
            result = await list_active_mirrors()
            
            commented = result["commented_mirrors"]
            assert len(commented) == 2
            
            # Check that commented mirrors are marked correctly
            for mirror in commented:
                assert mirror["active"] is False

    @pytest.mark.asyncio
    @patch("arch_ops_server.mirrors.IS_ARCH", False)
    async def test_list_active_mirrors_not_arch(self):
        """Test on non-Arch system."""
        result = await list_active_mirrors()
        
        assert "error" in result
        assert result["error"] == "NotSupported"

    @pytest.mark.asyncio
    @patch("arch_ops_server.mirrors.IS_ARCH", True)
    async def test_list_active_mirrors_file_not_found(self):
        """Test when mirrorlist file doesn't exist."""
        with patch("pathlib.Path.exists", return_value=False):
            result = await list_active_mirrors()
            
            assert "error" in result
            assert result["error"] == "NotFound"


class TestMirrorSpeed:
    """Test mirror speed testing functionality."""

    @pytest.mark.asyncio
    @patch("arch_ops_server.mirrors.IS_ARCH", True)
    async def test_mirror_speed_single_success(self):
        """Test testing a single mirror."""
        mirror_url = "https://mirror.example.com/$repo/os/$arch"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        with patch("httpx.AsyncClient") as mock_client, \
             patch("time.time", side_effect=[0.0, 0.05]):  # 50ms latency
            mock_client.return_value.__aenter__.return_value.head = AsyncMock(
                return_value=mock_response
            )
            
            result = await test_mirror_speed(mirror_url=mirror_url)
            
            assert result["tested_count"] == 1
            assert len(result["results"]) == 1
            assert result["results"][0]["success"] is True
            assert result["results"][0]["latency_ms"] > 0

    @pytest.mark.asyncio
    @patch("arch_ops_server.mirrors.IS_ARCH", True)
    async def test_mirror_speed_timeout(self):
        """Test mirror speed with timeout."""
        mirror_url = "https://slow-mirror.example.com/$repo/os/$arch"
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.head = AsyncMock(
                side_effect=httpx.TimeoutException("Timeout")
            )
            
            result = await test_mirror_speed(mirror_url=mirror_url)
            
            assert result["tested_count"] == 1
            assert result["results"][0]["success"] is False
            assert result["results"][0]["error"] == "timeout"

    @pytest.mark.asyncio
    @patch("arch_ops_server.mirrors.IS_ARCH", True)
    async def test_mirror_speed_all_mirrors(self):
        """Test testing all active mirrors."""
        mirrorlist = """Server = https://mirror1.example.com/$repo/os/$arch
Server = https://mirror2.example.com/$repo/os/$arch
"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        with patch("builtins.open", mock_open(read_data=mirrorlist)), \
             patch("httpx.AsyncClient") as mock_client, \
             patch("time.time", side_effect=[0.0, 0.05, 0.1, 0.15]):
            mock_client.return_value.__aenter__.return_value.head = AsyncMock(
                return_value=mock_response
            )
            
            result = await test_mirror_speed()  # No mirror_url = test all
            
            assert result["tested_count"] == 2
            assert len(result["results"]) == 2

    @pytest.mark.asyncio
    @patch("arch_ops_server.mirrors.IS_ARCH", False)
    async def test_mirror_speed_not_arch(self):
        """Test on non-Arch system."""
        result = await test_mirror_speed()
        
        assert "error" in result
        assert result["error"] == "NotSupported"


class TestMirrorSuggestions:
    """Test mirror suggestion functionality."""

    @pytest.fixture
    def sample_mirror_status(self):
        """Sample mirror status API response."""
        return {
            "urls": [
                {
                    "url": "https://mirror.us1.archlinux.org/$repo/os/$arch",
                    "country": "United States",
                    "country_code": "US",
                    "protocol": "https",
                    "active": True,
                    "completion_pct": 100.0,
                    "delay": 0.5,
                    "duration_avg": 0.3,
                    "duration_stddev": 0.1,
                    "last_sync": "2025-11-10T10:00:00Z"
                },
                {
                    "url": "https://mirror.de1.archlinux.org/$repo/os/$arch",
                    "country": "Germany",
                    "country_code": "DE",
                    "protocol": "https",
                    "active": True,
                    "completion_pct": 100.0,
                    "delay": 0.2,
                    "duration_avg": 0.25,
                    "duration_stddev": 0.05,
                    "last_sync": "2025-11-10T10:05:00Z"
                },
                {
                    "url": "https://mirror.inactive.com/$repo/os/$arch",
                    "country": "Unknown",
                    "country_code": "XX",
                    "protocol": "https",
                    "active": False,
                    "completion_pct": 50.0,
                    "delay": 10.0,
                    "duration_avg": 5.0,
                    "duration_stddev": 2.0,
                    "last_sync": None
                }
            ]
        }

    @pytest.mark.asyncio
    async def test_suggest_fastest_mirrors_success(self, sample_mirror_status):
        """Test suggesting fastest mirrors."""
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value=sample_mirror_status)
        mock_response.raise_for_status = MagicMock()
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            result = await suggest_fastest_mirrors(limit=10)
            
            assert result["suggested_count"] >= 1
            assert "mirrors" in result
            
            # Should only include active, complete mirrors
            for mirror in result["mirrors"]:
                assert mirror["completion_pct"] == 100.0
                assert "score" in mirror

    @pytest.mark.asyncio
    async def test_suggest_fastest_mirrors_with_country(self, sample_mirror_status):
        """Test suggesting mirrors filtered by country."""
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value=sample_mirror_status)
        mock_response.raise_for_status = MagicMock()
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            result = await suggest_fastest_mirrors(country="DE", limit=10)
            
            assert result["country_filter"] == "DE"
            # All returned mirrors should be from Germany
            for mirror in result["mirrors"]:
                assert mirror["country_code"] == "DE"

    @pytest.mark.asyncio
    async def test_suggest_fastest_mirrors_sorted_by_score(self, sample_mirror_status):
        """Test that mirrors are sorted by score."""
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value=sample_mirror_status)
        mock_response.raise_for_status = MagicMock()
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            result = await suggest_fastest_mirrors(limit=10)
            
            # Check that mirrors are sorted by score (lower is better)
            scores = [m["score"] for m in result["mirrors"]]
            assert scores == sorted(scores)

    @pytest.mark.asyncio
    async def test_suggest_fastest_mirrors_http_error(self):
        """Test mirror suggestion with HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "HTTP 500", request=MagicMock(), response=mock_response
        )
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            result = await suggest_fastest_mirrors()
            
            assert "error" in result
            assert result["error"] == "HTTPError"


class TestMirrorlistHealth:
    """Test mirrorlist health checking."""

    @pytest.mark.asyncio
    @patch("arch_ops_server.mirrors.IS_ARCH", True)
    async def test_mirrorlist_health_good(self):
        """Test healthy mirrorlist."""
        mirrorlist = """Server = https://mirror1.example.com/$repo/os/$arch
Server = https://mirror2.example.com/$repo/os/$arch
Server = https://mirror3.example.com/$repo/os/$arch
"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        with patch("builtins.open", mock_open(read_data=mirrorlist)), \
             patch("httpx.AsyncClient") as mock_client, \
             patch("time.time", side_effect=[0.0, 0.05] * 3):
            mock_client.return_value.__aenter__.return_value.head = AsyncMock(
                return_value=mock_response
            )
            
            result = await check_mirrorlist_health()
            
            assert result["health_status"] == "healthy"
            assert result["health_score"] >= 70
            assert len(result["issues"]) == 0

    @pytest.mark.asyncio
    @patch("arch_ops_server.mirrors.IS_ARCH", True)
    async def test_mirrorlist_health_no_mirrors(self):
        """Test health check with no active mirrors."""
        mirrorlist = """# All mirrors are commented out
#Server = https://mirror1.example.com/$repo/os/$arch
#Server = https://mirror2.example.com/$repo/os/$arch
"""
        
        with patch("builtins.open", mock_open(read_data=mirrorlist)):
            result = await check_mirrorlist_health()
            
            assert result["health_status"] == "critical"
            assert len(result["issues"]) > 0
            assert any("no active mirrors" in issue.lower() for issue in result["issues"])

    @pytest.mark.asyncio
    @patch("arch_ops_server.mirrors.IS_ARCH", True)
    async def test_mirrorlist_health_high_latency(self):
        """Test health check with high latency mirrors."""
        mirrorlist = """Server = https://slow-mirror.example.com/$repo/os/$arch
"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        with patch("builtins.open", mock_open(read_data=mirrorlist)), \
             patch("httpx.AsyncClient") as mock_client, \
             patch("time.time", side_effect=[0.0, 2.0]):  # 2 second latency
            mock_client.return_value.__aenter__.return_value.head = AsyncMock(
                return_value=mock_response
            )
            
            result = await check_mirrorlist_health()
            
            assert len(result["warnings"]) > 0 or len(result["issues"]) > 0

    @pytest.mark.asyncio
    @patch("arch_ops_server.mirrors.IS_ARCH", False)
    async def test_mirrorlist_health_not_arch(self):
        """Test on non-Arch system."""
        result = await check_mirrorlist_health()
        
        assert "error" in result
        assert result["error"] == "NotSupported"

