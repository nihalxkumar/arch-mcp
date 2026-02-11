# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""Tests for unified security audit functionality."""

import pytest
from arch_ops_server import audit_package_security


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
    assert "findings" in result
    assert result["action"] == "pkgbuild_analysis"


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
