# SPDX-License-Identifier: GPL-3.0-only OR MIT
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


async def remove_package(
    package_name: str,
    remove_dependencies: bool = False,
    force: bool = False
) -> Dict[str, Any]:
    """
    Remove a single package from the system.

    Args:
        package_name: Name of package to remove
        remove_dependencies: If True, remove unneeded dependencies (pacman -Rs)
        force: If True, force removal ignoring dependencies (pacman -Rdd)

    Returns:
        Dict with removal status and information
    """
    if not IS_ARCH:
        return create_error_response(
            "NotSupported",
            "Package removal is only available on Arch Linux"
        )

    if not check_command_exists("pacman"):
        return create_error_response(
            "CommandNotFound",
            "pacman command not found"
        )

    logger.info(f"Removing package: {package_name} (deps={remove_dependencies}, force={force})")

    # Build command based on options
    cmd = ["sudo", "pacman"]

    if force:
        cmd.extend(["-Rdd"])  # Force remove, skip dependency checks
    elif remove_dependencies:
        cmd.extend(["-Rs"])  # Remove with unused dependencies
    else:
        cmd.extend(["-R"])  # Basic removal

    cmd.extend(["--noconfirm", package_name])

    try:
        exit_code, stdout, stderr = await run_command(
            cmd,
            timeout=60,  # Longer timeout for removal
            check=False,
            skip_sudo_check=True  # We're using sudo in the command
        )

        if exit_code != 0:
            logger.error(f"Package removal failed: {stderr}")
            return create_error_response(
                "RemovalError",
                f"Failed to remove {package_name}: {stderr}",
                f"Exit code: {exit_code}"
            )

        logger.info(f"Successfully removed {package_name}")

        return {
            "success": True,
            "package": package_name,
            "removed_dependencies": remove_dependencies,
            "output": stdout
        }

    except Exception as e:
        logger.error(f"Package removal failed with exception: {e}")
        return create_error_response(
            "RemovalError",
            f"Failed to remove {package_name}: {str(e)}"
        )


async def remove_packages_batch(
    package_names: List[str],
    remove_dependencies: bool = False
) -> Dict[str, Any]:
    """
    Remove multiple packages in a single transaction.

    Args:
        package_names: List of package names to remove
        remove_dependencies: If True, remove unneeded dependencies

    Returns:
        Dict with removal status
    """
    if not IS_ARCH:
        return create_error_response(
            "NotSupported",
            "Package removal is only available on Arch Linux"
        )

    if not check_command_exists("pacman"):
        return create_error_response(
            "CommandNotFound",
            "pacman command not found"
        )

    if not package_names:
        return create_error_response(
            "ValidationError",
            "No packages specified for removal"
        )

    logger.info(f"Batch removing {len(package_names)} packages (deps={remove_dependencies})")

    # Build command
    cmd = ["sudo", "pacman"]

    if remove_dependencies:
        cmd.extend(["-Rs"])
    else:
        cmd.extend(["-R"])

    cmd.extend(["--noconfirm"] + package_names)

    try:
        exit_code, stdout, stderr = await run_command(
            cmd,
            timeout=120,  # Longer timeout for batch removal
            check=False,
            skip_sudo_check=True
        )

        if exit_code != 0:
            logger.error(f"Batch removal failed: {stderr}")
            return create_error_response(
                "RemovalError",
                f"Failed to remove packages: {stderr}",
                f"Exit code: {exit_code}"
            )

        logger.info(f"Successfully removed {len(package_names)} packages")

        return {
            "success": True,
            "package_count": len(package_names),
            "packages": package_names,
            "removed_dependencies": remove_dependencies,
            "output": stdout
        }

    except Exception as e:
        logger.error(f"Batch removal failed with exception: {e}")
        return create_error_response(
            "RemovalError",
            f"Failed to remove packages: {str(e)}"
        )


async def list_orphan_packages() -> Dict[str, Any]:
    """
    List all orphaned packages (dependencies no longer required).

    Returns:
        Dict with list of orphan packages
    """
    if not IS_ARCH:
        return create_error_response(
            "NotSupported",
            "Orphan package detection is only available on Arch Linux"
        )

    if not check_command_exists("pacman"):
        return create_error_response(
            "CommandNotFound",
            "pacman command not found"
        )

    logger.info("Listing orphan packages")

    try:
        exit_code, stdout, stderr = await run_command(
            ["pacman", "-Qtdq"],
            timeout=10,
            check=False
        )

        # Exit code 1 with no output means no orphans
        if exit_code == 1 and not stdout.strip():
            logger.info("No orphan packages found")
            return {
                "orphan_count": 0,
                "orphans": []
            }

        if exit_code != 0:
            logger.error(f"Failed to list orphans: {stderr}")
            return create_error_response(
                "CommandError",
                f"Failed to list orphan packages: {stderr}",
                f"Exit code: {exit_code}"
            )

        # Parse output - one package per line
        orphans = [pkg.strip() for pkg in stdout.strip().split('\n') if pkg.strip()]

        logger.info(f"Found {len(orphans)} orphan packages")

        return {
            "orphan_count": len(orphans),
            "orphans": orphans
        }

    except Exception as e:
        logger.error(f"Orphan listing failed with exception: {e}")
        return create_error_response(
            "CommandError",
            f"Failed to list orphan packages: {str(e)}"
        )


async def remove_orphans(dry_run: bool = True, exclude: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Remove all orphaned packages.

    Args:
        dry_run: If True, show what would be removed without actually removing
        exclude: List of packages to exclude from removal

    Returns:
        Dict with removal status
    """
    if not IS_ARCH:
        return create_error_response(
            "NotSupported",
            "Orphan removal is only available on Arch Linux"
        )

    if not check_command_exists("pacman"):
        return create_error_response(
            "CommandNotFound",
            "pacman command not found"
        )

    # First, get list of orphans
    orphans_result = await list_orphan_packages()

    if orphans_result.get("error"):
        return orphans_result

    orphans = orphans_result.get("orphans", [])

    if not orphans:
        return {
            "removed_count": 0,
            "packages": [],
            "message": "No orphan packages to remove"
        }

    # Apply exclusions if provided
    if exclude:
        orphans = [pkg for pkg in orphans if pkg not in exclude]
        if not orphans:
            return {
                "removed_count": 0,
                "packages": [],
                "message": "All orphan packages are in exclusion list"
            }

    logger.info(f"Removing {len(orphans)} orphan packages (dry_run={dry_run})")

    if dry_run:
        return {
            "dry_run": True,
            "would_remove_count": len(orphans),
            "packages": orphans,
            "message": "This is a dry run. No packages were removed."
        }

    try:
        # Remove orphans using pacman -Rns
        cmd = ["sudo", "pacman", "-Rns", "--noconfirm"] + orphans

        exit_code, stdout, stderr = await run_command(
            cmd,
            timeout=120,
            check=False,
            skip_sudo_check=True
        )

        if exit_code != 0:
            logger.error(f"Orphan removal failed: {stderr}")
            return create_error_response(
                "RemovalError",
                f"Failed to remove orphan packages: {stderr}",
                f"Exit code: {exit_code}"
            )

        logger.info(f"Successfully removed {len(orphans)} orphan packages")

        return {
            "success": True,
            "removed_count": len(orphans),
            "packages": orphans,
            "output": stdout
        }

    except Exception as e:
        logger.error(f"Orphan removal failed with exception: {e}")
        return create_error_response(
            "RemovalError",
            f"Failed to remove orphan packages: {str(e)}"
        )


async def find_package_owner(file_path: str) -> Dict[str, Any]:
    """
    Find which package owns a specific file.

    Args:
        file_path: Absolute path to file

    Returns:
        Dict with package owner information
    """
    if not IS_ARCH:
        return create_error_response(
            "NotSupported",
            "Package ownership queries are only available on Arch Linux"
        )

    if not check_command_exists("pacman"):
        return create_error_response(
            "CommandNotFound",
            "pacman command not found"
        )

    logger.info(f"Finding owner of file: {file_path}")

    try:
        exit_code, stdout, stderr = await run_command(
            ["pacman", "-Qo", file_path],
            timeout=5,
            check=False
        )

        if exit_code != 0:
            logger.info(f"No package owns {file_path}")
            return create_error_response(
                "NotFound",
                f"No package owns this file: {file_path}",
                stderr
            )

        # Parse output: "/path/to/file is owned by package 1.0-1"
        match = re.search(r'is owned by (\S+)\s+(\S+)', stdout)
        if match:
            package_name = match.group(1)
            version = match.group(2)

            logger.info(f"File {file_path} is owned by {package_name} {version}")

            return {
                "file": file_path,
                "package": package_name,
                "version": version
            }

        return create_error_response(
            "ParseError",
            f"Could not parse pacman output: {stdout}"
        )

    except Exception as e:
        logger.error(f"Package ownership query failed: {e}")
        return create_error_response(
            "CommandError",
            f"Failed to find package owner: {str(e)}"
        )


async def list_package_files(package_name: str, filter_pattern: Optional[str] = None) -> Dict[str, Any]:
    """
    List all files owned by a package.

    Args:
        package_name: Name of package
        filter_pattern: Optional regex pattern to filter files

    Returns:
        Dict with list of files
    """
    if not IS_ARCH:
        return create_error_response(
            "NotSupported",
            "Package file listing is only available on Arch Linux"
        )

    if not check_command_exists("pacman"):
        return create_error_response(
            "CommandNotFound",
            "pacman command not found"
        )

    logger.info(f"Listing files for package: {package_name}")

    try:
        exit_code, stdout, stderr = await run_command(
            ["pacman", "-Ql", package_name],
            timeout=10,
            check=False
        )

        if exit_code != 0:
            logger.error(f"Failed to list files for {package_name}: {stderr}")
            return create_error_response(
                "NotFound",
                f"Package not found or no files: {package_name}",
                stderr
            )

        # Parse output: "package /path/to/file"
        files = []
        for line in stdout.strip().split('\n'):
            if not line.strip():
                continue

            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                file_path = parts[1]

                # Apply filter if provided
                if filter_pattern:
                    if re.search(filter_pattern, file_path):
                        files.append(file_path)
                else:
                    files.append(file_path)

        logger.info(f"Found {len(files)} files for {package_name}")

        return {
            "package": package_name,
            "file_count": len(files),
            "files": files,
            "filter_applied": filter_pattern is not None
        }

    except Exception as e:
        logger.error(f"File listing failed: {e}")
        return create_error_response(
            "CommandError",
            f"Failed to list package files: {str(e)}"
        )


async def search_package_files(filename_pattern: str) -> Dict[str, Any]:
    """
    Search for files across all packages.

    Args:
        filename_pattern: Filename pattern to search for

    Returns:
        Dict with matching files and packages
    """
    if not IS_ARCH:
        return create_error_response(
            "NotSupported",
            "Package file search is only available on Arch Linux"
        )

    if not check_command_exists("pacman"):
        return create_error_response(
            "CommandNotFound",
            "pacman command not found"
        )

    logger.info(f"Searching for files matching: {filename_pattern}")

    try:
        # First check if file database is synced
        exit_code, stdout, stderr = await run_command(
            ["pacman", "-F", filename_pattern],
            timeout=30,
            check=False
        )

        if exit_code == 1 and "database" in stderr.lower():
            return create_error_response(
                "DatabaseNotSynced",
                "Package file database not synced. Run 'sudo pacman -Fy' first.",
                "File database needs to be synchronized before searching"
            )

        if exit_code != 0 and not stdout.strip():
            logger.info(f"No files found matching {filename_pattern}")
            return {
                "pattern": filename_pattern,
                "match_count": 0,
                "matches": []
            }

        # Parse output: "repository/package version\n    path/to/file"
        matches = []
        current_package = None

        for line in stdout.strip().split('\n'):
            if not line.strip():
                continue

            if line.startswith(' '):
                # This is a file path
                if current_package:
                    file_path = line.strip()
                    matches.append({
                        "package": current_package["package"],
                        "repository": current_package["repository"],
                        "version": current_package["version"],
                        "file": file_path
                    })
            else:
                # This is a package line: "repository/package version"
                parts = line.split()
                if len(parts) >= 2:
                    repo_pkg = parts[0].split('/')
                    if len(repo_pkg) == 2:
                        current_package = {
                            "repository": repo_pkg[0],
                            "package": repo_pkg[1],
                            "version": parts[1]
                        }

        logger.info(f"Found {len(matches)} files matching {filename_pattern}")

        return {
            "pattern": filename_pattern,
            "match_count": len(matches),
            "matches": matches
        }

    except Exception as e:
        logger.error(f"File search failed: {e}")
        return create_error_response(
            "CommandError",
            f"Failed to search package files: {str(e)}"
        )

