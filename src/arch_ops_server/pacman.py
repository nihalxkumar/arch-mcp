"""
Pacman/Official Repository interface module.
Provides package info and update checks with hybrid local/remote approach.
"""

import logging
import re
from typing import Dict, Any, List, Optional
import httpx

from .utils import (
    IS_ARCH,
    run_command,
    create_error_response,
    check_command_exists
)

logger = logging.getLogger(__name__)

# Arch Linux package API
ARCH_PACKAGES_API = "https://archlinux.org/packages/search/json/"

# HTTP client settings
DEFAULT_TIMEOUT = 10.0


async def get_official_package_info(package_name: str) -> Dict[str, Any]:
    """
    Get information about an official repository package.
    
    Uses hybrid approach:
    - If on Arch Linux: Execute `pacman -Si` for local database query
    - Otherwise: Query archlinux.org API
    
    Args:
        package_name: Package name
    
    Returns:
        Dict with package information
    """
    logger.info(f"Fetching info for official package: {package_name}")
    
    # Try local pacman first if on Arch
    if IS_ARCH and check_command_exists("pacman"):
        info = await _get_package_info_local(package_name)
        if info is not None:
            return info
        logger.warning(f"Local pacman query failed for {package_name}, trying remote API")
    
    # Fallback to remote API
    return await _get_package_info_remote(package_name)


async def _get_package_info_local(package_name: str) -> Optional[Dict[str, Any]]:
    """
    Query package info using local pacman command.
    
    Args:
        package_name: Package name
    
    Returns:
        Package info dict or None if failed
    """
    try:
        exit_code, stdout, stderr = await run_command(
            ["pacman", "-Si", package_name],
            timeout=5,
            check=False
        )
        
        if exit_code != 0:
            logger.debug(f"pacman -Si failed for {package_name}")
            return None
        
        # Parse pacman output
        info = _parse_pacman_output(stdout)
        
        if info:
            info["source"] = "local"
            logger.info(f"Successfully fetched {package_name} info locally")
            return info
        
        return None
        
    except Exception as e:
        logger.warning(f"Local pacman query failed: {e}")
        return None


async def _get_package_info_remote(package_name: str) -> Dict[str, Any]:
    """
    Query package info using archlinux.org API.
    
    Args:
        package_name: Package name
    
    Returns:
        Package info dict or error response
    """
    params = {
        "name": package_name,
        "exact": "on"  # Exact match only
    }
    
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(ARCH_PACKAGES_API, params=params)
            response.raise_for_status()
            
            data = response.json()
            results = data.get("results", [])
            
            if not results:
                return create_error_response(
                    "NotFound",
                    f"Official package '{package_name}' not found in repositories"
                )
            
            # Take first exact match (there should only be one)
            pkg = results[0]
            
            info = {
                "source": "remote",
                "name": pkg.get("pkgname"),
                "repository": pkg.get("repo"),
                "version": pkg.get("pkgver"),
                "release": pkg.get("pkgrel"),
                "epoch": pkg.get("epoch"),
                "description": pkg.get("pkgdesc"),
                "url": pkg.get("url"),
                "architecture": pkg.get("arch"),
                "maintainers": pkg.get("maintainers", []),
                "packager": pkg.get("packager"),
                "build_date": pkg.get("build_date"),
                "last_update": pkg.get("last_update"),
                "licenses": pkg.get("licenses", []),
                "groups": pkg.get("groups", []),
                "provides": pkg.get("provides", []),
                "depends": pkg.get("depends", []),
                "optdepends": pkg.get("optdepends", []),
                "conflicts": pkg.get("conflicts", []),
                "replaces": pkg.get("replaces", []),
            }
            
            logger.info(f"Successfully fetched {package_name} info remotely")
            
            return info
            
    except httpx.TimeoutException:
        logger.error(f"Remote package info fetch timed out for: {package_name}")
        return create_error_response(
            "TimeoutError",
            f"Package info fetch timed out for: {package_name}"
        )
    except httpx.HTTPStatusError as e:
        logger.error(f"Remote package info HTTP error: {e}")
        return create_error_response(
            "HTTPError",
            f"Package info fetch failed with status {e.response.status_code}",
            str(e)
        )
    except Exception as e:
        logger.error(f"Remote package info fetch failed: {e}")
        return create_error_response(
            "InfoError",
            f"Failed to get package info: {str(e)}"
        )


def _parse_pacman_output(output: str) -> Optional[Dict[str, Any]]:
    """
    Parse pacman -Si output into structured dict.
    
    Args:
        output: Raw pacman -Si output
    
    Returns:
        Parsed package info or None
    """
    if not output.strip():
        return None
    
    info = {}
    current_key = None
    
    for line in output.split('\n'):
        # Match "Key : Value" pattern
        match = re.match(r'^(\w[\w\s]*?)\s*:\s*(.*)$', line)
        if match:
            key = match.group(1).strip().lower().replace(' ', '_')
            value = match.group(2).strip()
            
            # Handle special fields
            if key in ['depends_on', 'optional_deps', 'required_by', 
                       'conflicts_with', 'replaces', 'groups', 'provides']:
                # These can be multi-line or space-separated
                if value.lower() == 'none':
                    info[key] = []
                else:
                    info[key] = [v.strip() for v in value.split() if v.strip()]
            else:
                info[key] = value
            
            current_key = key
        elif current_key and line.startswith('                '):
            # Continuation line (indented)
            continuation = line.strip()
            if continuation and current_key in info:
                if isinstance(info[current_key], list):
                    info[current_key].extend([v.strip() for v in continuation.split() if v.strip()])
                else:
                    info[current_key] += ' ' + continuation
    
    return info if info else None


async def check_updates_dry_run() -> Dict[str, Any]:
    """
    Check for available system updates without applying them.
    
    Only works on Arch Linux systems with checkupdates command.
    Requires pacman-contrib package.
    
    Returns:
        Dict with list of available updates or error response
    """
    logger.info("Checking for system updates (dry run)")
    
    # Only supported on Arch Linux
    if not IS_ARCH:
        return create_error_response(
            "NotSupported",
            "Update checking is only supported on Arch Linux systems",
            "This server is not running on Arch Linux"
        )
    
    # Check if checkupdates command exists
    if not check_command_exists("checkupdates"):
        return create_error_response(
            "CommandNotFound",
            "checkupdates command not found",
            "Install pacman-contrib package: pacman -S pacman-contrib"
        )
    
    try:
        exit_code, stdout, stderr = await run_command(
            ["checkupdates"],
            timeout=30,  # Can take longer for sync
            check=False
        )
        
        # Exit code 0: updates available
        # Exit code 2: no updates available
        # Other: error
        
        if exit_code == 2 or not stdout.strip():
            logger.info("No updates available")
            return {
                "updates_available": False,
                "count": 0,
                "packages": []
            }
        
        if exit_code != 0:
            logger.error(f"checkupdates failed with code {exit_code}: {stderr}")
            return create_error_response(
                "CommandError",
                f"checkupdates command failed: {stderr}",
                f"Exit code: {exit_code}"
            )
        
        # Parse checkupdates output
        updates = _parse_checkupdates_output(stdout)
        
        logger.info(f"Found {len(updates)} available updates")
        
        return {
            "updates_available": True,
            "count": len(updates),
            "packages": updates
        }
        
    except Exception as e:
        logger.error(f"Update check failed: {e}")
        return create_error_response(
            "UpdateCheckError",
            f"Failed to check for updates: {str(e)}"
        )


def _parse_checkupdates_output(output: str) -> List[Dict[str, str]]:
    """
    Parse checkupdates command output.
    
    Format: "package current_version -> new_version"
    
    Args:
        output: Raw checkupdates output
    
    Returns:
        List of update dicts
    """
    updates = []
    
    for line in output.strip().split('\n'):
        if not line.strip():
            continue
        
        # Match pattern: "package old_ver -> new_ver"
        match = re.match(r'^(\S+)\s+(\S+)\s+->\s+(\S+)$', line)
        if match:
            updates.append({
                "package": match.group(1),
                "current_version": match.group(2),
                "new_version": match.group(3)
            })
    
    return updates

