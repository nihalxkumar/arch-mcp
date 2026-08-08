# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""Tests for unified security audit functionality."""

import pytest
from arch_ops_server import audit_package_security
from arch_ops_server.aur import BINARY_EXTENSIONS


async def test_audit_package_security_pkgbuild_analysis():
    """Test PKGBUILD safety analysis."""
    pkgbuild = """pkgname=test
pkgver=1.0
pkgrel=1
arch=('x86_64')
"""
    result = await audit_package_security(
        action="pkgbuild_analysis",
        pkgbuild_content=pkgbuild
    )
    assert "risk_score" in result
    # Findings are reported in three severity buckets; there is no combined
    # "findings" key and no boolean verdict -- the scan does not certify a
    # package, so nothing may install on the strength of it.
    assert "red_flags" in result
    assert "warnings" in result
    assert "info" in result
    assert "limitations" in result
    assert "safe" not in result
    assert result["action"] == "pkgbuild_analysis"


def _warning_text(result: dict) -> str:
    """Join every warning message so a test can assert on what was reported."""
    return " ".join(warning["issue"] for warning in result["warnings"])


async def test_pkgbuild_analysis_flags_md5_checksums():
    """A real md5 digest is a finding: md5 collisions are constructible."""
    result = await audit_package_security(
        action="pkgbuild_analysis",
        pkgbuild_content="md5sums=('a8f84171ee1796fc4899579d92df0e24')\n"
    )
    assert "md5" in _warning_text(result)
    assert "collision-broken" in _warning_text(result)


async def test_pkgbuild_analysis_flags_sha1_checksums():
    """sha1 is broken in the same way and reported the same way."""
    result = await audit_package_security(
        action="pkgbuild_analysis",
        pkgbuild_content="sha1sums=('da39a3ee5e6b4b0d3255bfef95601890afd80709')\n"
    )
    assert "sha1" in _warning_text(result)
    assert "collision-broken" in _warning_text(result)


@pytest.mark.parametrize("algorithm", ["sha256", "sha384", "sha512", "b2"])
async def test_pkgbuild_analysis_accepts_strong_checksums(algorithm):
    """Algorithms that still resist collisions produce no integrity finding."""
    result = await audit_package_security(
        action="pkgbuild_analysis",
        pkgbuild_content=f"{algorithm}sums=('abc123')\n"
    )
    assert "collision-broken" not in _warning_text(result)


async def test_pkgbuild_analysis_reports_skip_without_the_algorithm():
    """
    SKIP verifies nothing at all, so the algorithm named alongside it is moot.

    Reporting both would suggest the fix is a stronger hash, when the source is
    simply unverified.
    """
    result = await audit_package_security(
        action="pkgbuild_analysis",
        pkgbuild_content="md5sums=('SKIP')\n"
    )
    assert "SKIP" in _warning_text(result)
    assert "collision-broken" not in _warning_text(result)


async def test_pkgbuild_analysis_flags_multi_line_md5_array():
    """The algorithm sits on the declaration line, so a split array still matches."""
    result = await audit_package_security(
        action="pkgbuild_analysis",
        pkgbuild_content=(
            "md5sums=(\n"
            "  'a8f84171ee1796fc4899579d92df0e24'\n"
            ")\n"
        )
    )
    assert "collision-broken" in _warning_text(result)


async def test_pkgbuild_analysis_flags_appimage_sources():
    """
    A prebuilt AppImage is the archetypal opaque binary in an AUR recipe.

    It went undetected for as long as the extension list was compared with the
    wrong case, so it gets a test of its own and not only the sweep below.
    """
    result = await audit_package_security(
        action="pkgbuild_analysis",
        pkgbuild_content='source=("https://example.com/app-1.0.AppImage")\n'
    )
    assert "Binary file type detected: .AppImage" in _warning_text(result)


@pytest.mark.parametrize("extension", BINARY_EXTENSIONS)
async def test_every_binary_extension_is_detectable(extension):
    """
    Parametrised over the real list so a new entry is covered automatically.

    This guards the class of bug rather than the instance: an entry carrying
    capitals cannot silently stop matching again.
    """
    result = await audit_package_security(
        action="pkgbuild_analysis",
        pkgbuild_content=f'source=("https://example.com/app-1.0{extension}")\n'
    )
    assert f"Binary file type detected: {extension}" in _warning_text(result)


async def test_audit_package_security_missing_pkgbuild():
    """Test error when pkgbuild_content is missing."""
    result = await audit_package_security(action="pkgbuild_analysis")
    assert "error" in result


async def test_audit_package_security_metadata_risk_with_name():
    """Test metadata risk analysis with package name."""
    result = await audit_package_security(
        action="metadata_risk",
        package_name="yay"
    )
    # Result depends on AUR API response
    assert "action" in result
    # Should either have trust_score or error
    assert "trust_score" in result or "error" in result


async def test_audit_package_security_metadata_risk_with_info():
    """Test metadata risk analysis with pre-fetched info."""
    package_info = {
        "Name": "test-package",
        "NumVotes": 100,
        "OutOfDate": None,
        "Maintainer": "testuser",
        "FirstSubmitted": 1609459200,
        "LastModified": 1609459200
    }
    result = await audit_package_security(
        action="metadata_risk",
        package_info=package_info
    )
    assert "trust_score" in result
    assert result["action"] == "metadata_risk"


async def test_audit_package_security_missing_params():
    """Test error when neither package_name nor package_info provided."""
    result = await audit_package_security(action="metadata_risk")
    assert "error" in result


async def test_audit_package_security_invalid_action():
    """Test error for invalid action."""
    result = await audit_package_security(action="invalid_action")
    assert "error" in result
