# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
Tests for arch_ops_server.utils module.
"""

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from arch_ops_server.utils import (
    IS_ARCH,
    add_aur_warning,
    check_command_exists,
    create_error_response,
    find_askpass,
    get_aur_helper,
    is_arch_linux,
    run_command,
)


class TestPlatformDetection:
    """Test platform detection functionality."""

    def test_is_arch_linux_with_arch_release(self, mock_arch_release):
        """Test detection via /etc/arch-release file."""
        with patch("arch_ops_server.utils.Path") as mock_path:
            mock_path.return_value.exists.return_value = True
            result = is_arch_linux()
            assert result is True

    def test_is_arch_linux_with_os_release(self, mock_os_release_arch):
        """Test detection via /etc/os-release file."""
        with (
            patch("arch_ops_server.utils.Path") as mock_path,
            patch("builtins.open", create=True) as mock_open,
        ):
            # Simulate arch-release not existing
            mock_path.return_value.exists.return_value = False

            # Mock os-release reading
            mock_open.return_value.__enter__.return_value.read.return_value = (
                mock_os_release_arch.read_text()
            )

            result = is_arch_linux()
            assert result is True

    def test_is_arch_linux_not_arch(self, mock_os_release_ubuntu):
        """Test detection on non-Arch system."""
        with (
            patch("arch_ops_server.utils.Path") as mock_path,
            patch("builtins.open", create=True) as mock_open,
        ):
            # Simulate arch-release not existing
            mock_path.return_value.exists.return_value = False

            # Mock os-release reading for Ubuntu
            mock_open.return_value.__enter__.return_value.read.return_value = (
                mock_os_release_ubuntu.read_text()
            )

            result = is_arch_linux()
            assert result is False

    def test_is_arch_linux_no_files(self):
        """Test detection when neither file exists."""
        with (
            patch("arch_ops_server.utils.Path") as mock_path,
            patch("builtins.open", side_effect=FileNotFoundError),
        ):
            mock_path.return_value.exists.return_value = False
            result = is_arch_linux()
            assert result is False


class TestCommandExecution:
    """Test async command execution."""

    @pytest.mark.asyncio
    async def test_run_command_success(self, mock_subprocess_success):
        """Test successful command execution."""
        with patch(
            "asyncio.create_subprocess_exec", new=mock_subprocess_success
        ):
            exit_code, stdout, stderr = await run_command(
                ["echo", "hello"]
            )

            assert exit_code == 0
            assert stdout == "success output"
            assert stderr == ""

    @pytest.mark.asyncio
    async def test_run_command_failure_with_check(self, mock_subprocess_failure):
        """Test command failure with check=True raises exception."""
        with patch(
            "asyncio.create_subprocess_exec", new=mock_subprocess_failure
        ):
            with pytest.raises(RuntimeError, match="Command failed with exit code 1"):
                await run_command(["false"], check=True)

    @pytest.mark.asyncio
    async def test_run_command_failure_without_check(self, mock_subprocess_failure):
        """Test command failure with check=False returns error."""
        with patch(
            "asyncio.create_subprocess_exec", new=mock_subprocess_failure
        ):
            exit_code, stdout, stderr = await run_command(
                ["false"], check=False
            )

            assert exit_code == 1
            assert stdout == ""
            assert stderr == "error output"

    @pytest.mark.asyncio
    async def test_run_command_timeout(self):
        """Test command timeout handling."""
        async def _slow_communicate():
            await asyncio.sleep(10)
            return (b"", b"")

        mock_process = MagicMock()
        mock_process.communicate = _slow_communicate

        async def _create_slow_subprocess(*args, **kwargs):
            return mock_process

        with patch("asyncio.create_subprocess_exec", new=_create_slow_subprocess):
            with pytest.raises(asyncio.TimeoutError):
                await run_command(
                    ["sleep", "10"], timeout=0.1
                )

    @pytest.mark.asyncio
    async def test_run_command_without_askpass_tries_non_interactively(
        self, mock_subprocess_success
    ):
        """
        With no askpass helper, sudo is still attempted with -n.

        A user may have a valid sudo timestamp or an authorisation rule of
        their own; refusing outright would break them. -n guarantees sudo
        never blocks waiting for a terminal we do not have.
        """
        captured = {}

        async def _create_subprocess(*args, **kwargs):
            captured["argv"] = list(args)
            return await mock_subprocess_success(*args, **kwargs)

        with patch("arch_ops_server.utils.find_askpass", return_value=None):
            with patch("asyncio.create_subprocess_exec", new=_create_subprocess):
                exit_code, _, _ = await run_command(["sudo", "pacman", "-S", "test"])

        assert exit_code == 0
        assert captured["argv"][:2] == ["sudo", "-n"]

    @pytest.mark.asyncio
    async def test_run_command_reports_when_password_needed(self):
        """When sudo cannot authenticate, explain rather than leak its error."""
        async def _create_subprocess(*args, **kwargs):
            process = MagicMock()
            process.returncode = 1

            async def _communicate():
                return (b"", b"sudo: a password is required")

            process.communicate = _communicate
            return process

        with patch("arch_ops_server.utils.find_askpass", return_value=None):
            with patch("asyncio.create_subprocess_exec", new=_create_subprocess):
                exit_code, _, stderr = await run_command(
                    ["sudo", "pacman", "-S", "test"], check=False
                )

        assert exit_code == 1
        # The command to run by hand, without the internal -n flag.
        assert "sudo pacman -S test" in stderr
        # Desktop-neutral advice, and no suggestion to weaken sudo.
        assert "seahorse" in stderr and "ksshaskpass" in stderr
        assert "Do not add a passwordless sudo rule" in stderr


class TestAskpassDiscovery:
    """Helper discovery must not assume any particular desktop."""

    def test_no_graphical_session_means_no_helper(self):
        with patch.dict(os.environ, {}, clear=True):
            assert find_askpass() is None

    def test_explicit_sudo_askpass_wins(self, tmp_path):
        helper = tmp_path / "my-askpass"
        helper.write_text("#!/bin/sh\n")
        helper.chmod(0o755)

        with patch.dict(os.environ, {"DISPLAY": ":0", "SUDO_ASKPASS": str(helper)}):
            assert find_askpass() == str(helper)

    def test_finds_helper_on_path(self):
        with patch.dict(os.environ, {"DISPLAY": ":0"}, clear=True):
            with patch("shutil.which", side_effect=lambda n: "/usr/bin/" + n
                       if n == "ssh-askpass-gnome" else None):
                assert find_askpass() == "/usr/bin/ssh-askpass-gnome"

    def test_finds_helper_installed_outside_path(self):
        """GNOME/Seahorse ships outside PATH; which() alone would miss it."""
        gnome_helper = "/usr/lib/seahorse/ssh-askpass"

        with patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}, clear=True):
            with patch("shutil.which", return_value=None):
                with patch("arch_ops_server.utils._is_executable",
                           side_effect=lambda p: p == gnome_helper):
                    assert find_askpass() == gnome_helper

    def test_honours_sudo_conf(self, tmp_path):
        configured = "/opt/custom/askpass"

        with patch.dict(os.environ, {"DISPLAY": ":0"}, clear=True):
            with patch("arch_ops_server.utils._askpass_from_sudo_conf",
                       return_value=configured):
                with patch("arch_ops_server.utils._is_executable",
                           side_effect=lambda p: p == configured):
                    assert find_askpass() == configured

    def test_helper_list_is_not_kde_only(self):
        """Regression guard: the search must cover the major desktops."""
        from arch_ops_server.utils import ASKPASS_HELPERS, ASKPASS_PATHS

        combined = " ".join(ASKPASS_HELPERS) + " " + " ".join(ASKPASS_PATHS)
        assert "ksshaskpass" in combined          # KDE
        assert "seahorse" in combined             # GNOME
        assert "gnome-ssh-askpass" in combined    # GNOME, Debian/Fedora layout
        assert "lxqt-openssh-askpass" in combined  # LXQt
        assert "x11-ssh-askpass" in combined      # plain X11

    @pytest.mark.asyncio
    async def test_run_command_sudo_uses_askpass(self, mock_subprocess_success):
        """A sudo command gets -A and SUDO_ASKPASS pointing at the helper."""
        captured = {}

        async def _create_subprocess(*args, **kwargs):
            captured["argv"] = list(args)
            captured["env"] = kwargs.get("env") or {}
            captured["stdin"] = kwargs.get("stdin")
            return await mock_subprocess_success(*args, **kwargs)

        with patch("arch_ops_server.utils.find_askpass", return_value="/usr/bin/ksshaskpass"):
            with patch("asyncio.create_subprocess_exec", new=_create_subprocess):
                exit_code, _, _ = await run_command(["sudo", "pacman", "-S", "test"])

        assert exit_code == 0
        assert captured["argv"][:2] == ["sudo", "-A"]
        assert captured["env"]["SUDO_ASKPASS"] == "/usr/bin/ksshaskpass"
        # stdin is closed: no password is ever written to the child.
        assert captured["stdin"] is asyncio.subprocess.DEVNULL

    @pytest.mark.asyncio
    async def test_run_command_non_sudo_untouched(self, mock_subprocess_success):
        """Non-privileged commands are not rewritten and need no askpass."""
        captured = {}

        async def _create_subprocess(*args, **kwargs):
            captured["argv"] = list(args)
            return await mock_subprocess_success(*args, **kwargs)

        with patch("arch_ops_server.utils.find_askpass", return_value=None):
            with patch("asyncio.create_subprocess_exec", new=_create_subprocess):
                exit_code, _, _ = await run_command(["pacman", "-Q"])

        assert exit_code == 0
        assert captured["argv"] == ["pacman", "-Q"]


class TestErrorHandling:
    """Test error response creation and formatting."""

    def test_create_error_response_basic(self):
        """Test basic error response creation."""
        response = create_error_response(
            "TestError", "Something went wrong", suggest_wiki_search=False
        )

        assert response["error"] is True
        assert response["type"] == "TestError"
        assert response["message"] == "Something went wrong"
        assert "wiki_suggestions" not in response

    def test_create_error_response_with_details(self):
        """Test error response with additional details."""
        response = create_error_response(
            "TestError",
            "Something went wrong",
            details="More information here",
            suggest_wiki_search=False,
        )

        assert response["details"] == "More information here"

    def test_create_error_response_with_wiki_suggestions(self):
        """Test error response includes Wiki suggestions."""
        response = create_error_response(
            "NotFound", "Package not found", suggest_wiki_search=True
        )

        assert "wiki_suggestions" in response
        assert isinstance(response["wiki_suggestions"], list)
        assert len(response["wiki_suggestions"]) > 0
        assert "help_text" in response

    def test_wiki_suggestions_for_network_error(self):
        """Test Wiki suggestions for network-related errors."""
        response = create_error_response(
            "NetworkError",
            "Failed to connect to mirror server",
            suggest_wiki_search=True,
        )

        suggestions = response.get("wiki_suggestions", [])
        # Should suggest network and mirror-related topics
        assert any("network" in s.lower() or "mirror" in s.lower() for s in suggestions)

    def test_wiki_suggestions_for_pacman_error(self):
        """Test Wiki suggestions for pacman-related errors."""
        response = create_error_response(
            "CommandError",
            "pacman failed to update database",
            suggest_wiki_search=True,
        )

        suggestions = response.get("wiki_suggestions", [])
        # Should suggest pacman-related topics
        assert any("pacman" in s.lower() for s in suggestions)


class TestAURWarning:
    """Test AUR warning wrapper."""

    def test_add_aur_warning(self):
        """Test AUR warning is properly added to data."""
        test_data = {"package": "test-pkg", "version": "1.0"}

        result = add_aur_warning(test_data)

        assert "warning" in result
        assert "AUR PACKAGE WARNING" in result["warning"]
        assert "USER-PRODUCED" in result["warning"]
        assert result["data"] == test_data

    def test_aur_warning_preserves_data(self):
        """Test that original data is preserved unchanged."""
        original_data = {"key1": "value1", "key2": {"nested": "value"}}

        result = add_aur_warning(original_data)

        assert result["data"] == original_data
        assert result["data"] is original_data  # Same object reference


class TestCommandExistence:
    """Test command existence checking."""

    def test_check_command_exists_found(self):
        """Test detecting an existing command."""
        with patch("shutil.which", return_value="/usr/bin/ls"):
            result = check_command_exists("ls")
            assert result is True

    def test_check_command_exists_not_found(self):
        """Test detecting a missing command."""
        with patch("shutil.which", return_value=None):
            result = check_command_exists("nonexistent_command_xyz")
            assert result is False

    def test_check_command_exists_uses_no_shell(self):
        """A command name with shell metacharacters must not be executed."""
        with patch("os.system") as mock_system:
            assert check_command_exists("x; touch /tmp/pwned") is False
            mock_system.assert_not_called()


class TestAURHelper:
    """Test AUR helper detection."""

    def test_get_aur_helper_paru(self):
        """Test detection when paru is available."""
        with patch("arch_ops_server.utils.check_command_exists") as mock_check:
            mock_check.side_effect = lambda cmd: cmd == "paru"
            result = get_aur_helper()
            assert result == "paru"

    def test_get_aur_helper_yay(self):
        """Test detection when only yay is available."""
        with patch("arch_ops_server.utils.check_command_exists") as mock_check:
            mock_check.side_effect = lambda cmd: cmd == "yay"
            result = get_aur_helper()
            assert result == "yay"

    def test_get_aur_helper_both_available(self):
        """Test priority when both helpers are available (paru wins)."""
        with patch("arch_ops_server.utils.check_command_exists", return_value=True):
            result = get_aur_helper()
            assert result == "paru"

    def test_get_aur_helper_none_available(self):
        """Test when no AUR helper is available."""
        with patch("arch_ops_server.utils.check_command_exists", return_value=False):
            result = get_aur_helper()
            assert result is None
