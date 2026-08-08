# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""Unified group management tool."""

from typing import Literal, Optional
from .utils import run_command, create_error_response, IS_ARCH
from .validation import ValidationError, validate_group_name


async def manage_groups(
    action: Literal["list_groups", "list_packages_in_group"],
    group_name: Optional[str] = None
) -> dict:
    """Unified group management tool."""
    if not IS_ARCH:
        return create_error_response("NotSupported", "Requires Arch Linux")

    if action == "list_groups":
        return await _list_groups()
    elif action == "list_packages_in_group":
        if not group_name:
            return create_error_response("ValidationError", "group_name required")
        try:
            group_name = validate_group_name(group_name)
        except ValidationError as e:
            return create_error_response("ValidationError", str(e))
        return await _list_packages_in_group(group_name)
    else:
        return create_error_response("ValidationError", f"Unknown action: {action}")


async def _list_groups() -> dict:
    exit_code, stdout, stderr = await run_command(["pacman", "-Sg"], timeout=10, check=False)
    if exit_code != 0:
        return create_error_response("CommandError", f"Failed to list groups: {stderr}")
    groups = [line.strip() for line in stdout.strip().split("\n") if line.strip()]
    return {"action": "list_groups", "total_groups": len(groups), "groups": sorted(groups)}


async def _list_packages_in_group(group_name: str) -> dict:
    exit_code, stdout, stderr = await run_command(
        ["pacman", "-Sg", "--", group_name], timeout=10, check=False
    )
    if exit_code != 0:
        # pacman exits non-zero for an unknown group, but also for a database it
        # cannot read. Keep stderr so the second case is not reported as the first.
        return create_error_response(
            "NotFound",
            f"Group not found: {group_name}",
            stderr.strip() or None
        )
    packages = []
    for line in stdout.strip().split("\n"):
        if line.strip():
            parts = line.split()
            if len(parts) >= 2:
                packages.append(parts[1])
    return {"action": "list_packages_in_group", "group": group_name, "total_packages": len(packages), "packages": packages}


__all__ = ["manage_groups"]
