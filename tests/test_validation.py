# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
Regression tests for the argv-safety layer.

Commands run via create_subprocess_exec with an argv list, so there is no shell
to inject into. What these tests protect against is pacman's own option
parsing: a "package name" that begins with '-' is a flag, not a target.
"""

import asyncio
import json
from unittest.mock import patch

import pytest

from arch_ops_server.validation import (
    MAX_PACKAGES,
    ValidationError,
    validate_file_path,
    validate_glob_pattern,
    validate_group_name,
    validate_package_name,
    validate_package_names,
    validate_public_url,
)


class TestPackageNameValidation:
    """Names that pacman would parse as options must be rejected."""

    @pytest.mark.parametrize("name", [
        "-Rdd",
        "--dbpath=/tmp/evil",
        "--root=/",
        "--config=/tmp/evil.conf",
        "-Syu",
        "--overwrite=*",
        "-",
    ])
    def test_rejects_option_like_names(self, name):
        with pytest.raises(ValidationError):
            validate_package_name(name)

    @pytest.mark.parametrize("name", [
        "",
        "../etc/passwd",
        "pkg;rm -rf /",
        "pkg name",
        "pkg\nname",
        "pkg\x00name",
        "pkg$(id)",
        "pkg`id`",
        "pkg|tee",
        "a" * 300,
    ])
    def test_rejects_malformed_names(self, name):
        with pytest.raises(ValidationError):
            validate_package_name(name)

    @pytest.mark.parametrize("name", [
        "firefox",
        "python-pip",
        "lib32-gcc-libs",
        "gtk+",
        "core/linux",
        "extra/firefox",
        "nodejs-lts-hydrogen",
        "a",
        "7zip",
        "ca-certificates-utils",
    ])
    def test_accepts_real_package_names(self, name):
        assert validate_package_name(name) == name

    def test_rejects_non_string(self):
        with pytest.raises(ValidationError):
            validate_package_name(None)

    def test_batch_rejects_any_bad_entry(self):
        with pytest.raises(ValidationError):
            validate_package_names(["firefox", "--dbpath=/tmp", "vim"])

    def test_batch_rejects_empty(self):
        with pytest.raises(ValidationError):
            validate_package_names([])

    def test_batch_is_bounded(self):
        with pytest.raises(ValidationError):
            validate_package_names([f"pkg{i}" for i in range(MAX_PACKAGES + 1)])


class TestOtherValidators:
    def test_group_name_rejects_flags(self):
        with pytest.raises(ValidationError):
            validate_group_name("--root=/")

    def test_group_name_accepts_real_group(self):
        assert validate_group_name("base-devel") == "base-devel"

    def test_file_path_allows_paths_but_not_control_characters(self):
        assert validate_file_path("/usr/bin/python") == "/usr/bin/python"
        with pytest.raises(ValidationError):
            validate_file_path("/usr/bin/\x00")

    def test_glob_pattern_allows_metacharacters(self):
        assert validate_glob_pattern("*.service") == "*.service"
        with pytest.raises(ValidationError):
            validate_glob_pattern("")

    @pytest.mark.parametrize("url", [
        "http://127.0.0.1:8080/",
        "http://localhost/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://[::1]/",
        "file:///etc/passwd",
        "ftp://example.com/",
    ])
    def test_public_url_blocks_internal_targets(self, url):
        with pytest.raises(ValidationError):
            validate_public_url(url)

    def test_public_url_allows_a_real_mirror(self):
        url = "https://archlinux.org/"
        assert validate_public_url(url) == url


class TestArgvConstruction:
    """Every user-supplied value must sit after a '--' end-of-options marker."""

    @pytest.mark.asyncio
    async def test_removal_argv_separates_options_from_targets(self):
        from arch_ops_server.pacman import remove_packages

        result = await remove_packages(["firefox", "vim"], remove_dependencies=True)

        argv = result["command"].split()
        assert "--" in argv
        # Nothing after '--' is treated as an option by pacman.
        assert argv[argv.index("--") + 1:] == ["firefox", "vim"]

    @pytest.mark.asyncio
    async def test_dispatcher_rejects_option_like_package(self):
        import importlib

        server = importlib.import_module("arch_ops_server.server")
        error = server._validate_tool_arguments({"package_name": "-Rdd"})

        assert error is not None
        assert error["type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_dispatcher_allows_ordinary_package(self):
        import importlib

        server = importlib.import_module("arch_ops_server.server")
        assert server._validate_tool_arguments({"package_name": "firefox"}) is None


class TestConfirmationGates:
    """Mutating tools must not touch the system without explicit confirmation."""

    @pytest.mark.asyncio
    async def test_remove_packages_dry_run_spawns_nothing(self):
        from arch_ops_server.pacman import remove_packages

        async def fail(*args, **kwargs):
            raise AssertionError(f"must not spawn a subprocess: {args}")

        with patch("asyncio.create_subprocess_exec", new=fail):
            result = await remove_packages("firefox")

        assert result["removed"] is False
        assert "firefox" in result["command"]

    @pytest.mark.asyncio
    async def test_orphan_removal_needs_dry_run_off_and_confirm(self):
        from arch_ops_server.pacman import remove_orphans

        async def fail(*args, **kwargs):
            raise AssertionError(f"must not spawn a subprocess: {args}")

        with patch("arch_ops_server.pacman.list_orphan_packages") as listing:
            async def orphans():
                return {"orphans": ["leftover-lib"]}
            listing.side_effect = orphans

            with patch("asyncio.create_subprocess_exec", new=fail):
                # Default dry run.
                assert (await remove_orphans())["removed"] is False
                # dry_run off alone is still not enough.
                assert (await remove_orphans(dry_run=False))["removed"] is False

    @pytest.mark.asyncio
    async def test_aur_install_never_runs_a_helper(self):
        """AUR packages are reported, never installed, even with confirm=True."""
        from arch_ops_server import aur

        async def fail(*args, **kwargs):
            raise AssertionError(f"must not spawn a subprocess: {args}")

        async def not_official(_name):
            return {"error": True, "type": "NotFound"}

        async def aur_info(_name):
            return {"data": {"name": "demo", "version": "1.0", "NumVotes": 5}}

        async def pkgbuild(_name):
            return "pkgname=demo\npkgver=1.0\n"

        async def missing_file(*_args, **_kwargs):
            raise ValueError("no .install file")

        with patch("arch_ops_server.pacman.get_official_package_info", new=not_official), \
             patch.object(aur, "get_aur_info", new=aur_info), \
             patch.object(aur, "get_pkgbuild", new=pkgbuild), \
             patch.object(aur, "get_aur_file", new=missing_file), \
             patch("arch_ops_server.utils.find_askpass", return_value="/usr/bin/ksshaskpass"), \
             patch("asyncio.create_subprocess_exec", new=fail):
            result = await aur.install_package_secure("demo", confirm=True)

        assert result["installed"] is False
        assert result["security_checks"]["decision"] == "MANUAL_INSTALL_REQUIRED"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("confirm", ["false", "no", "0", []])
    async def test_dispatch_rejects_a_non_boolean_confirm(self, confirm):
        """
        A confirm that is not a JSON boolean must be refused, not believed.

        The handlers gate on truthiness, so the string "false" would read as
        True and remove the packages. The SDK validates arguments on its own
        request path, but the HTTP transport imports this function directly,
        so the check has to live here to cover both.
        """
        from arch_ops_server.server import call_tool

        async def fail(*args, **kwargs):
            raise AssertionError(f"must not spawn a subprocess: {args}")

        with patch("asyncio.create_subprocess_exec", new=fail):
            content = await call_tool(
                "remove_packages", {"packages": "firefox", "confirm": confirm}
            )

        result = json.loads(content[0].text)
        assert result["error"] is True
        assert result["type"] == "ValidationError"
        assert "confirm" in result["message"]

    @pytest.mark.asyncio
    async def test_dispatch_still_accepts_a_real_boolean(self):
        """The type check must not break the ordinary dry-run call."""
        from arch_ops_server.server import call_tool

        async def fail(*args, **kwargs):
            raise AssertionError(f"must not spawn a subprocess: {args}")

        with patch("asyncio.create_subprocess_exec", new=fail):
            content = await call_tool(
                "remove_packages", {"packages": "firefox", "confirm": False}
            )

        result = json.loads(content[0].text)
        assert result["removed"] is False
        assert "firefox" in result["command"]

    @pytest.mark.asyncio
    async def test_install_still_attempted_without_a_graphical_prompt(self):
        """
        No askpass helper is a warning, not a refusal.

        On a headless or SSH session find_askpass() always returns None. run_command
        falls back to `sudo -n`, which still works for a user with a valid sudo
        timestamp, so this path must reach the command rather than bail out early.
        """
        from arch_ops_server import aur

        spawned = {}

        async def official(_name):
            return {"found": True, "repository": "extra"}

        async def fake_run(cmd, **_kwargs):
            spawned["cmd"] = cmd
            return 0, "installed", ""

        with patch("arch_ops_server.pacman.get_official_package_info", new=official), \
             patch.object(aur, "find_askpass", return_value=None), \
             patch.object(aur, "run_command", new=fake_run):
            result = await aur.install_package_secure("firefox", confirm=True)

        assert result["installed"] is True
        assert spawned["cmd"][:2] == ["sudo", "pacman"]
        # The advice is still given, just not as a refusal.
        assert any("askpass" in m for m in result["messages"])


class TestScanIsNotAVerdict:
    """The PKGBUILD scan reports findings; it must not certify a package."""

    def test_no_safe_boolean(self):
        from arch_ops_server.aur import analyze_pkgbuild_safety

        result = analyze_pkgbuild_safety("pkgname=demo\npkgver=1.0\n")

        assert "safe" not in result
        assert result["has_critical_findings"] is False
        # A clean scan must say what it did not check.
        assert "limitations" in result
        assert "not evidence that the package is safe" in result["recommendation"]

    def test_flags_unverified_and_unpinned_sources(self):
        from arch_ops_server.aur import analyze_pkgbuild_safety

        pkgbuild = (
            'pkgname=demo\n'
            'url="https://github.com/upstream/demo"\n'
            'source=("git+https://elsewhere.example.com/demo.git")\n'
            'sha256sums=("SKIP")\n'
        )
        issues = " ".join(w["issue"] for w in analyze_pkgbuild_safety(pkgbuild)["warnings"])

        assert "SKIP" in issues
        assert "not pinned" in issues
