# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
Tests for arch_ops_server.pacman module.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from arch_ops_server.pacman import (
    ARCH_PACKAGES_API,
    _parse_checkupdates_output,
    _parse_pacman_output,
    check_updates_dry_run,
    get_official_package_info,
)


class TestGetOfficialPackageInfo:
    """Test hybrid local/remote package info retrieval."""

    @pytest.mark.asyncio
    async def test_get_package_info_local_on_arch(
        self, sample_pacman_info, mock_subprocess_success
    ):
        """Test local pacman query on Arch Linux."""
        # Mock being on Arch
        with (
            patch("arch_ops_server.pacman.IS_ARCH", True),
            patch("arch_ops_server.pacman.check_command_exists", return_value=True),
            patch("arch_ops_server.pacman.run_command") as mock_run,
        ):
            # Mock successful pacman command
            mock_run.return_value = (0, sample_pacman_info, "")

            result = await get_official_package_info("vim")

            assert result["source"] == "local"
            assert result["name"] == "vim"
            assert result["version"] == "9.0.1000-1"
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_package_info_remote_not_on_arch(self, mock_httpx_response):
        """Test remote API query when not on Arch."""
        mock_response = mock_httpx_response(
            status_code=200,
            json_data={
                "results": [
                    {
                        "pkgname": "vim",
                        "pkgver": "9.0.1000",
                        "pkgrel": "1",
                        "pkgdesc": "Vi Improved",
                        "url": "https://www.vim.org",
                        "repo": "extra",
                        "arch": "x86_64",
                    }
                ]
            },
        )

        with (
            patch("arch_ops_server.pacman.IS_ARCH", False),
            patch("httpx.AsyncClient") as mock_client,
        ):
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await get_official_package_info("vim")

            assert result["source"] == "remote"
            assert result["name"] == "vim"

    @pytest.mark.asyncio
    async def test_get_package_info_fallback_to_remote(self, mock_httpx_response):
        """Test fallback to remote API when local query fails."""
        mock_response = mock_httpx_response(
            status_code=200,
            json_data={
                "results": [
                    {
                        "pkgname": "test-pkg",
                        "pkgver": "1.0",
                        "pkgrel": "1",
                        "pkgdesc": "Test package",
                        "url": "https://example.com",
                        "repo": "extra",
                        "arch": "x86_64",
                    }
                ]
            },
        )

        with (
            patch("arch_ops_server.pacman.IS_ARCH", True),
            patch("arch_ops_server.pacman.check_command_exists", return_value=True),
            patch("arch_ops_server.pacman.run_command") as mock_run,
            patch("httpx.AsyncClient") as mock_client,
        ):
            # Local query fails
            mock_run.return_value = (1, "", "error: package not found")

            # Remote query succeeds
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await get_official_package_info("test-pkg")

            assert result["source"] == "remote"
            assert result["name"] == "test-pkg"

    @pytest.mark.asyncio
    async def test_get_package_info_remote_not_found(self, mock_httpx_response):
        """Test remote API when package doesn't exist."""
        mock_response = mock_httpx_response(
            status_code=200, json_data={"results": []}
        )

        with (
            patch("arch_ops_server.pacman.IS_ARCH", False),
            patch("httpx.AsyncClient") as mock_client,
        ):
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await get_official_package_info("nonexistent-pkg")

            assert result["error"] is True
            assert result["type"] == "NotFound"

    @pytest.mark.asyncio
    async def test_get_package_info_remote_timeout(self):
        """Test remote API timeout handling."""
        with (
            patch("arch_ops_server.pacman.IS_ARCH", False),
            patch("httpx.AsyncClient") as mock_client,
        ):
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.TimeoutException("Request timed out")
            )

            result = await get_official_package_info("vim")

            assert result["error"] is True
            assert result["type"] == "TimeoutError"


class TestParsePacmanOutput:
    """Test pacman output parsing."""

    def test_parse_pacman_output_success(self, sample_pacman_info):
        """Test successful parsing of pacman -Si output."""
        result = _parse_pacman_output(sample_pacman_info)

        assert result is not None
        assert result["name"] == "vim"
        assert result["version"] == "9.0.1000-1"
        assert result["description"] == "Vi Improved, a highly configurable, improved version of the vi text editor"
        assert result["architecture"] == "x86_64"
        assert result["url"] == "https://www.vim.org"
        # The parser uses 'depends_on' not 'depends'
        assert "vim-runtime=9.0.1000-1" in result["depends_on"]

    def test_parse_pacman_output_multiline_depends(self):
        """Test parsing dependencies that span multiple lines."""
        output = """Name            : test-pkg
Version         : 1.0-1
Description     : Test package
Architecture    : x86_64
URL             : https://example.com
Licenses        : MIT
Depends On      : dep1  dep2
                  dep3  dep4
"""
        result = _parse_pacman_output(output)

        assert result is not None
        # Parser uses 'depends_on' and splits by whitespace
        assert "dep1" in result["depends_on"]
        assert "dep2" in result["depends_on"]
        assert "dep3" in result["depends_on"]
        assert "dep4" in result["depends_on"]

    def test_parse_pacman_output_optional_deps(self):
        """Test parsing optional dependencies with descriptions."""
        output = """Name            : vim
Version         : 9.0-1
Description     : Vi Improved
Architecture    : x86_64
URL             : https://www.vim.org
Licenses        : custom:vim
Optional Deps   : python: Python language support
                  ruby: Ruby language support
"""
        result = _parse_pacman_output(output)

        assert result is not None
        # Parser splits by whitespace, so each word becomes a separate item
        assert len(result["optional_deps"]) > 0
        # Check that python and ruby are in the list
        assert "python:" in result["optional_deps"]
        assert "ruby:" in result["optional_deps"]

    def test_parse_pacman_output_empty(self):
        """Test parsing empty output."""
        result = _parse_pacman_output("")

        assert result is None

    def test_parse_pacman_output_malformed(self):
        """Test parsing malformed output."""
        result = _parse_pacman_output("Random text\nNo valid format\n")

        assert result is None


class TestCheckUpdatesDryRun:
    """Test update checking functionality."""

    @pytest.mark.asyncio
    async def test_check_updates_success(self):
        """Test successful update check with available updates."""
        checkupdates_output = """vim 9.0.1000-1 -> 9.0.2000-1
python 3.11.0-1 -> 3.11.5-1
gcc 12.2.0-1 -> 13.1.0-1
"""

        with (
            patch("arch_ops_server.pacman.IS_ARCH", True),
            patch("arch_ops_server.pacman.check_command_exists", return_value=True),
            patch("arch_ops_server.pacman.run_command") as mock_run,
        ):
            mock_run.return_value = (0, checkupdates_output, "")

            result = await check_updates_dry_run()

            # Returns: updates_available (bool), count, packages
            assert result["updates_available"] is True
            assert result["count"] == 3
            assert len(result["packages"]) == 3
            assert result["packages"][0]["package"] == "vim"
            assert result["packages"][0]["current_version"] == "9.0.1000-1"
            assert result["packages"][0]["new_version"] == "9.0.2000-1"

    @pytest.mark.asyncio
    async def test_check_updates_no_updates(self):
        """Test update check when system is up to date."""
        with (
            patch("arch_ops_server.pacman.IS_ARCH", True),
            patch("arch_ops_server.pacman.check_command_exists", return_value=True),
            patch("arch_ops_server.pacman.run_command") as mock_run,
        ):
            # Exit code 2 means no updates
            mock_run.return_value = (2, "", "")

            result = await check_updates_dry_run()

            # Returns: updates_available (bool), count, packages
            assert result["updates_available"] is False
            assert result["count"] == 0
            assert result["packages"] == []

    @pytest.mark.asyncio
    async def test_check_updates_not_on_arch(self):
        """Test update check fails gracefully when not on Arch."""
        with patch("arch_ops_server.pacman.IS_ARCH", False):
            result = await check_updates_dry_run()

            assert result["error"] is True
            assert result["type"] == "NotSupported"
            assert "Arch Linux" in result["message"]

    @pytest.mark.asyncio
    async def test_check_updates_checkupdates_not_installed(self):
        """Test when checkupdates command is not available."""
        with (
            patch("arch_ops_server.pacman.IS_ARCH", True),
            patch("arch_ops_server.pacman.check_command_exists", return_value=False),
        ):
            result = await check_updates_dry_run()

            assert result["error"] is True
            assert result["type"] == "CommandNotFound"
            assert "checkupdates" in result["message"]

    @pytest.mark.asyncio
    async def test_check_updates_timeout(self):
        """Test update check timeout handling."""
        import asyncio

        with (
            patch("arch_ops_server.pacman.IS_ARCH", True),
            patch("arch_ops_server.pacman.check_command_exists", return_value=True),
            patch("arch_ops_server.pacman.run_command") as mock_run,
        ):
            mock_run.side_effect = asyncio.TimeoutError("Command timed out")

            result = await check_updates_dry_run()

            assert result["error"] is True
            # Generic exception handler returns UpdateCheckError
            assert result["type"] == "UpdateCheckError"

    @pytest.mark.asyncio
    async def test_check_updates_command_error(self):
        """Test update check when checkupdates fails."""
        with (
            patch("arch_ops_server.pacman.IS_ARCH", True),
            patch("arch_ops_server.pacman.check_command_exists", return_value=True),
            patch("arch_ops_server.pacman.run_command") as mock_run,
        ):
            # Exit code 1 with some output triggers CommandError
            # (empty stdout would be treated as no updates)
            mock_run.return_value = (1, "some output", "error: failed to synchronize databases")

            result = await check_updates_dry_run()

            # Exit code 1 with output triggers CommandError
            assert result["error"] is True
            assert result["type"] == "CommandError"


class TestParseCheckupdatesOutput:
    """Test checkupdates output parsing."""

    def test_parse_checkupdates_output_success(self):
        """Test successful parsing of checkupdates output."""
        output = """vim 9.0.1000-1 -> 9.0.2000-1
python 3.11.0-1 -> 3.11.5-1
gcc 12.2.0-1 -> 13.1.0-1
"""
        result = _parse_checkupdates_output(output)

        assert len(result) == 3
        assert result[0]["package"] == "vim"
        assert result[0]["current_version"] == "9.0.1000-1"
        assert result[0]["new_version"] == "9.0.2000-1"
        assert result[1]["package"] == "python"
        assert result[2]["package"] == "gcc"

    def test_parse_checkupdates_output_single_update(self):
        """Test parsing single update."""
        output = "linux 6.1.0-1 -> 6.2.0-1\n"
        result = _parse_checkupdates_output(output)

        assert len(result) == 1
        assert result[0]["package"] == "linux"

    def test_parse_checkupdates_output_empty(self):
        """Test parsing empty output."""
        result = _parse_checkupdates_output("")

        assert result == []

    def test_parse_checkupdates_output_malformed_lines(self):
        """Test parsing with some malformed lines."""
        output = """vim 9.0.1000-1 -> 9.0.2000-1
malformed line without arrow
python 3.11.0-1 -> 3.11.5-1
another bad line
gcc 12.2.0-1 -> 13.1.0-1
"""
        result = _parse_checkupdates_output(output)

        # Should only parse valid lines
        assert len(result) == 3
        assert result[0]["package"] == "vim"
        assert result[1]["package"] == "python"
        assert result[2]["package"] == "gcc"

    def test_parse_checkupdates_output_with_whitespace(self):
        """Test parsing with extra whitespace."""
        # The regex is: ^\S+\s+\S+\s+->\s+\S+$ which requires no leading whitespace
        # Lines with leading whitespace will be skipped
        output = """vim   9.0.1000-1   ->   9.0.2000-1
   python  3.11.0-1  ->  3.11.5-1
"""
        result = _parse_checkupdates_output(output)

        # Only the first line matches (no leading whitespace)
        assert len(result) == 1
        assert result[0]["package"] == "vim"
        assert result[0]["current_version"] == "9.0.1000-1"
