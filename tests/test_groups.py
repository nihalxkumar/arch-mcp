# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""Tests for group management functionality."""

import pytest
from arch_ops_server.groups import manage_groups
from arch_ops_server.utils import IS_ARCH


@pytest.mark.skipif(not IS_ARCH, reason="Arch Linux only")
async def test_manage_groups_list_groups():
    """Test listing all package groups."""
    result = await manage_groups(action="list_groups")
    assert "groups" in result
    assert "total_groups" in result
    assert isinstance(result["groups"], list)
    # Should have common groups
    assert len(result["groups"]) > 0


@pytest.mark.skipif(not IS_ARCH, reason="Arch Linux only")
async def test_manage_groups_list_packages_in_group():
    """Test listing packages in a specific group."""
    result = await manage_groups(action="list_packages_in_group", group_name="base-devel")
    assert "packages" in result
    assert result["group"] == "base-devel"
    assert "total_packages" in result
    assert isinstance(result["packages"], list)


async def test_manage_groups_invalid_action():
    """Test error handling for invalid action."""
    result = await manage_groups(action="invalid_action")
    assert "error" in result


async def test_manage_groups_missing_group_name():
    """Test error when group_name is missing for list_packages_in_group."""
    result = await manage_groups(action="list_packages_in_group")
    assert "error" in result


@pytest.mark.skipif(not IS_ARCH, reason="Arch Linux only")
async def test_manage_groups_nonexistent_group():
    """Test error handling for non-existent group."""
    result = await manage_groups(action="list_packages_in_group", group_name="definitely_not_real_12345")
    assert "error" in result
