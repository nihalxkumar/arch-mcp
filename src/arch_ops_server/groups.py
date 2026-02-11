# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""Unified group management tool."""

from typing import Literal, Optional
from .utils import run_command, create_error_response, IS_ARCH


async def manage_groups(
    action: Literal["list_groups", "list_packages_in_group"],
    group_name: Optional[str] = None
) -> dict:
    """Unified group management tool."""
    if not IS_ARCH:
        return create_error_response("Requires Arch Linux", error_type="platform_error")
    
    if action == "list_groups":
        return await _list_groups()
    elif action == "list_packages_in_group":
        if not group_name:
            return create_error_response("group_name required", error_type="validation_error")
        return await _list_packages_in_group(group_name)
    else:
        return create_error_response(f"Unknown action: {action}")


async def _list_groups() -> dict:
    exit_code, stdout, stderr = await run_command(["pacman", "-Sg"], timeout=10)
    if exit_code != 0:
        return create_error_response(f"Failed to list groups: {stderr}")
    groups = [line.strip() for line in stdout.strip().split("\n") if line.strip()]
    return {"action": "list_groups", "total_groups": len(groups), "groups": sorted(groups)}


async def _list_packages_in_group(group_name: str) -> dict:
    exit_code, stdout, stderr = await run_command(["pacman", "-Sg", group_name], timeout=10)
    if exit_code != 0:
        return create_error_response(f"Failed: {stderr}")
    packages = []
    for line in stdout.strip().split("\n"):
        if line.strip():
            parts = line.split()
            if len(parts) >= 2:
                packages.append(parts[1])
    return {"action": "list_packages_in_group", "group": group_name, "total_packages": len(packages), "packages": packages}


__all__ = ["manage_groups"]
