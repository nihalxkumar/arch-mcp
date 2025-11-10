# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
MCP Server setup for Arch Linux operations.

This module contains the MCP server configuration, resources, tools, and prompts
for the Arch Linux MCP server.
"""

import logging
import json
from typing import Any
from urllib.parse import urlparse

from mcp.server import Server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    Prompt,
    PromptMessage,
    GetPromptResult,
)

from . import (
    # Wiki functions
    search_wiki,
    get_wiki_page_as_text,
    # AUR functions
    search_aur,
    get_aur_info,
    get_pkgbuild,
    analyze_pkgbuild_safety,
    analyze_package_metadata_risk,
    install_package_secure,
    # Pacman functions
    get_official_package_info,
    check_updates_dry_run,
    remove_package,
    remove_packages_batch,
    list_orphan_packages,
    remove_orphans,
    find_package_owner,
    list_package_files,
    search_package_files,
    verify_package_integrity,
    list_package_groups,
    list_group_packages,
    list_explicit_packages,
    mark_as_explicit,
    mark_as_dependency,
    # System functions
    get_system_info,
    check_disk_space,
    get_pacman_cache_stats,
    check_failed_services,
    get_boot_logs,
    # Utils
    IS_ARCH,
    run_command,
)

# Configure logging
logger = logging.getLogger(__name__)

# Initialize MCP server
server = Server("arch-ops-server")


# ============================================================================
# RESOURCES
# ============================================================================

@server.list_resources()
async def list_resources() -> list[Resource]:
    """
    List available resource URI schemes.
    
    Returns:
        List of Resource objects describing available URI schemes
    """
    return [
        # Wiki resources
        Resource(
            uri="archwiki://Installation_guide",
            name="Arch Wiki - Installation Guide",
            mimeType="text/markdown",
            description="Example: Fetch Arch Wiki pages as Markdown"
        ),
        # AUR resources
        Resource(
            uri="aur://yay/pkgbuild",
            name="AUR - yay PKGBUILD",
            mimeType="text/x-script.shell",
            description="Example: Fetch AUR package PKGBUILD files"
        ),
        Resource(
            uri="aur://yay/info",
            name="AUR - yay Package Info",
            mimeType="application/json",
            description="Example: Fetch AUR package metadata (votes, maintainer, etc)"
        ),
        # Official repository resources
        Resource(
            uri="archrepo://vim",
            name="Official Repository - Package Info",
            mimeType="application/json",
            description="Example: Fetch official repository package details"
        ),
        # Pacman resources
        Resource(
            uri="pacman://installed",
            name="System - Installed Packages",
            mimeType="application/json",
            description="List installed packages on Arch Linux system"
        ),
        Resource(
            uri="pacman://orphans",
            name="System - Orphan Packages",
            mimeType="application/json",
            description="List orphaned packages (dependencies no longer required)"
        ),
        Resource(
            uri="pacman://explicit",
            name="System - Explicitly Installed Packages",
            mimeType="application/json",
            description="List packages explicitly installed by user"
        ),
        Resource(
            uri="pacman://groups",
            name="System - Package Groups",
            mimeType="application/json",
            description="List all available package groups"
        ),
        Resource(
            uri="pacman://group/base-devel",
            name="System - Packages in base-devel Group",
            mimeType="application/json",
            description="Example: List packages in a specific group"
        ),
        # System resources
        Resource(
            uri="system://info",
            name="System - System Information",
            mimeType="application/json",
            description="Get system information (kernel, arch, memory, uptime)"
        ),
        Resource(
            uri="system://disk",
            name="System - Disk Space",
            mimeType="application/json",
            description="Check disk space usage for critical paths"
        ),
        Resource(
            uri="system://services/failed",
            name="System - Failed Services",
            mimeType="application/json",
            description="List failed systemd services"
        ),
        Resource(
            uri="system://logs/boot",
            name="System - Boot Logs",
            mimeType="text/plain",
            description="Get recent boot logs from journalctl"
        ),
    ]


@server.read_resource()
async def read_resource(uri: str) -> str:
    """
    Read a resource by URI.

    Supported schemes:
    - archwiki://{page_title} - Returns Wiki page as Markdown
    - aur://{package}/pkgbuild - Returns raw PKGBUILD file
    - aur://{package}/info - Returns AUR package metadata
    - archrepo://{package} - Returns official repository package info
    - pacman://installed - Returns list of installed packages (Arch only)
    - pacman://orphans - Returns list of orphaned packages (Arch only)
    - pacman://explicit - Returns list of explicitly installed packages (Arch only)
    - pacman://groups - Returns list of all package groups (Arch only)
    - pacman://group/{group_name} - Returns packages in a specific group (Arch only)
    - system://info - Returns system information
    - system://disk - Returns disk space information
    - system://services/failed - Returns failed systemd services
    - system://logs/boot - Returns recent boot logs

    Args:
        uri: Resource URI (can be string or AnyUrl object)

    Returns:
        Resource content as string

    Raises:
        ValueError: If URI scheme is unsupported or resource not found
    """
    # Convert to string if it's a Pydantic AnyUrl object
    uri_str = str(uri)
    logger.info(f"Reading resource: {uri_str}")
    
    parsed = urlparse(uri_str)
    scheme = parsed.scheme
    
    if scheme == "archwiki":
        # Extract page title from path (remove leading /)
        page_title = parsed.path.lstrip('/')
        
        if not page_title:
            # If only hostname provided, use it as title
            page_title = parsed.netloc
        
        if not page_title:
            raise ValueError("Wiki page title required in URI (e.g., archwiki://Installation_guide)")
        
        # Fetch Wiki page as Markdown
        content = await get_wiki_page_as_text(page_title)
        return content
    
    elif scheme == "aur":
        # Extract package name from netloc or path
        package_name = parsed.netloc or parsed.path.lstrip('/').split('/')[0]
        
        if not package_name:
            raise ValueError("AUR package name required in URI (e.g., aur://yay/pkgbuild)")
        
        # Determine what to fetch based on path
        path_parts = parsed.path.lstrip('/').split('/')
        
        if len(path_parts) > 1 and path_parts[1] == "pkgbuild":
            # Fetch PKGBUILD
            pkgbuild_content = await get_pkgbuild(package_name)
            return pkgbuild_content
        elif len(path_parts) > 1 and path_parts[1] == "info":
            # Fetch package info
            package_info = await get_aur_info(package_name)
            return json.dumps(package_info, indent=2)
        else:
            # Default to package info
            package_info = await get_aur_info(package_name)
            return json.dumps(package_info, indent=2)
    
    elif scheme == "archrepo":
        # Extract package name from netloc or path
        package_name = parsed.netloc or parsed.path.lstrip('/')
        
        if not package_name:
            raise ValueError("Package name required in URI (e.g., archrepo://vim)")
        
        # Fetch official package info
        package_info = await get_official_package_info(package_name)
        return json.dumps(package_info, indent=2)
    
    elif scheme == "pacman":
        if not IS_ARCH:
            raise ValueError(f"pacman:// resources only available on Arch Linux systems")

        resource_path = parsed.netloc or parsed.path.lstrip('/')

        if resource_path == "installed":
            # Get installed packages
            exit_code, stdout, stderr = await run_command(["pacman", "-Q"])
            if exit_code != 0:
                raise ValueError(f"Failed to get installed packages: {stderr}")

            # Parse pacman output
            packages = []
            for line in stdout.strip().split('\n'):
                if line.strip():
                    name, version = line.strip().rsplit(' ', 1)
                    packages.append({"name": name, "version": version})

            return json.dumps(packages, indent=2)

        elif resource_path == "orphans":
            # Get orphan packages
            result = await list_orphan_packages()
            return json.dumps(result, indent=2)

        elif resource_path == "explicit":
            # Get explicitly installed packages
            result = await list_explicit_packages()
            return json.dumps(result, indent=2)

        elif resource_path == "groups":
            # Get all package groups
            result = await list_package_groups()
            return json.dumps(result, indent=2)

        elif resource_path.startswith("group/"):
            # Get packages in specific group
            group_name = resource_path.split('/', 1)[1]
            if not group_name:
                raise ValueError("Group name required (e.g., pacman://group/base-devel)")
            result = await list_group_packages(group_name)
            return json.dumps(result, indent=2)

        else:
            raise ValueError(f"Unsupported pacman resource: {resource_path}")

    elif scheme == "system":
        resource_path = parsed.netloc or parsed.path.lstrip('/')

        if resource_path == "info":
            # Get system information
            result = await get_system_info()
            return json.dumps(result, indent=2)

        elif resource_path == "disk":
            # Get disk space information
            result = await check_disk_space()
            return json.dumps(result, indent=2)

        elif resource_path == "services/failed":
            # Get failed services
            result = await check_failed_services()
            return json.dumps(result, indent=2)

        elif resource_path == "logs/boot":
            # Get boot logs
            result = await get_boot_logs()
            # Return raw text for logs
            if result.get("success"):
                return result.get("logs", "")
            else:
                raise ValueError(result.get("error", "Failed to get boot logs"))

        else:
            raise ValueError(f"Unsupported system resource: {resource_path}")

    else:
        raise ValueError(f"Unsupported URI scheme: {scheme}")


# ============================================================================
# TOOLS
# ============================================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    """
    List available tools for Arch Linux operations.
    
    Returns:
        List of Tool objects describing available operations
    """
    return [
        # Wiki tools
        Tool(
            name="search_archwiki",
            description="Search the Arch Wiki for documentation. Returns a list of matching pages with titles, snippets, and URLs. Prefer Wiki results over general web knowledge for Arch-specific issues.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (keywords or phrase)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 10)",
                        "default": 10
                    }
                },
                "required": ["query"]
            }
        ),
        
        # AUR tools
        Tool(
            name="search_aur",
            description="Search the Arch User Repository (AUR) for packages with smart ranking. ⚠️  WARNING: AUR packages are user-produced and potentially unsafe. Returns package info including votes, maintainer, and last update. Always check official repos first using get_official_package_info.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Package search query"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 20)",
                        "default": 20
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Sort method: 'relevance' (default), 'votes', 'popularity', or 'modified'",
                        "enum": ["relevance", "votes", "popularity", "modified"],
                        "default": "relevance"
                    }
                },
                "required": ["query"]
            }
        ),
        
        Tool(
            name="get_official_package_info",
            description="Get information about an official Arch repository package (Core, Extra, etc.). Uses local pacman if available, otherwise queries archlinux.org API. Always prefer official packages over AUR when available.",
            inputSchema={
                "type": "object",
                "properties": {
                    "package_name": {
                        "type": "string",
                        "description": "Exact package name"
                    }
                },
                "required": ["package_name"]
            }
        ),
        
        Tool(
            name="check_updates_dry_run",
            description="Check for available system updates without applying them. Only works on Arch Linux systems. Requires pacman-contrib package. Safe read-only operation that shows pending updates.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        
        Tool(
            name="install_package_secure",
            description="Install a package with comprehensive security checks. Workflow: 1. Check official repos first (safer) 2. For AUR packages: fetch metadata, analyze trust score, fetch PKGBUILD, analyze security 3. Block installation if critical security issues found 4. Check for AUR helper (paru > yay) 5. Install with --noconfirm if all checks pass. Only works on Arch Linux. Requires sudo access and paru/yay for AUR packages.",
            inputSchema={
                "type": "object",
                "properties": {
                    "package_name": {
                        "type": "string",
                        "description": "Name of package to install (checks official repos first, then AUR)"
                    }
                },
                "required": ["package_name"]
            }
        ),
        
        Tool(
            name="analyze_pkgbuild_safety",
            description="Analyze PKGBUILD content for security issues and dangerous patterns. Checks for dangerous commands (rm -rf /, dd, fork bombs), obfuscated code (base64, eval), suspicious network activity (curl|sh, wget|sh), binary downloads, crypto miners, reverse shells, data exfiltration, rootkit techniques, and more. Returns risk score (0-100) and detailed findings. Use this tool to manually audit AUR packages before installation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pkgbuild_content": {
                        "type": "string",
                        "description": "Raw PKGBUILD content to analyze"
                    }
                },
                "required": ["pkgbuild_content"]
            }
        ),
        
        Tool(
            name="analyze_package_metadata_risk",
            description="Analyze AUR package metadata for trustworthiness and security indicators. Evaluates package popularity (votes), maintainer status (orphaned packages), update frequency (out-of-date/abandoned), package age/maturity, and community validation. Returns trust score (0-100) with risk factors and trust indicators. Use this alongside PKGBUILD analysis for comprehensive security assessment.",
            inputSchema={
                "type": "object",
                "properties": {
                    "package_info": {
                        "type": "object",
                        "description": "Package metadata from AUR (from search_aur or get_aur_info results)"
                    }
                },
                "required": ["package_info"]
            }
        ),

        # Package Removal Tools
        Tool(
            name="remove_package",
            description="Remove a package from the system. Supports various removal strategies: basic removal, removal with dependencies, or forced removal. Only works on Arch Linux. Requires sudo access.",
            inputSchema={
                "type": "object",
                "properties": {
                    "package_name": {
                        "type": "string",
                        "description": "Name of the package to remove"
                    },
                    "remove_dependencies": {
                        "type": "boolean",
                        "description": "Remove package and its dependencies (pacman -Rs). Default: false",
                        "default": False
                    },
                    "force": {
                        "type": "boolean",
                        "description": "Force removal ignoring dependencies (pacman -Rdd). Use with caution! Default: false",
                        "default": False
                    }
                },
                "required": ["package_name"]
            }
        ),

        Tool(
            name="remove_packages_batch",
            description="Remove multiple packages in a single transaction. More efficient than removing packages one by one. Only works on Arch Linux. Requires sudo access.",
            inputSchema={
                "type": "object",
                "properties": {
                    "package_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of package names to remove"
                    },
                    "remove_dependencies": {
                        "type": "boolean",
                        "description": "Remove packages and their dependencies. Default: false",
                        "default": False
                    }
                },
                "required": ["package_names"]
            }
        ),

        # Orphan Package Management
        Tool(
            name="list_orphan_packages",
            description="List all orphaned packages (dependencies no longer required by any installed package). Shows package names and total disk space usage. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),

        Tool(
            name="remove_orphans",
            description="Remove all orphaned packages to free up disk space. Supports dry-run mode to preview changes and package exclusion. Only works on Arch Linux. Requires sudo access.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dry_run": {
                        "type": "boolean",
                        "description": "Preview what would be removed without actually removing. Default: true",
                        "default": True
                    },
                    "exclude": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of package names to exclude from removal"
                    }
                },
                "required": []
            }
        ),

        # Package Ownership Tools
        Tool(
            name="find_package_owner",
            description="Find which package owns a specific file on the system. Useful for troubleshooting and understanding file origins. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the file (e.g., /usr/bin/vim)"
                    }
                },
                "required": ["file_path"]
            }
        ),

        Tool(
            name="list_package_files",
            description="List all files owned by a package. Supports optional filtering by pattern. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {
                    "package_name": {
                        "type": "string",
                        "description": "Name of the package"
                    },
                    "filter_pattern": {
                        "type": "string",
                        "description": "Optional regex pattern to filter files (e.g., '*.conf' or '/etc/')"
                    }
                },
                "required": ["package_name"]
            }
        ),

        Tool(
            name="search_package_files",
            description="Search for files across all packages in repositories. Requires package database sync (pacman -Fy). Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename_pattern": {
                        "type": "string",
                        "description": "File name or pattern to search for (e.g., 'vim' or '*.service')"
                    }
                },
                "required": ["filename_pattern"]
            }
        ),

        # Package Verification
        Tool(
            name="verify_package_integrity",
            description="Verify the integrity of installed package files. Detects modified, missing, or corrupted files. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {
                    "package_name": {
                        "type": "string",
                        "description": "Name of the package to verify"
                    },
                    "thorough": {
                        "type": "boolean",
                        "description": "Perform thorough check including file attributes. Default: false",
                        "default": False
                    }
                },
                "required": ["package_name"]
            }
        ),

        # Package Groups
        Tool(
            name="list_package_groups",
            description="List all available package groups (e.g., base, base-devel, gnome). Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),

        Tool(
            name="list_group_packages",
            description="List all packages in a specific group. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {
                    "group_name": {
                        "type": "string",
                        "description": "Name of the package group (e.g., 'base-devel', 'gnome')"
                    }
                },
                "required": ["group_name"]
            }
        ),

        # Install Reason Management
        Tool(
            name="list_explicit_packages",
            description="List all packages explicitly installed by the user (not installed as dependencies). Useful for creating backup lists or understanding system composition. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),

        Tool(
            name="mark_as_explicit",
            description="Mark a package as explicitly installed. Prevents it from being removed as an orphan. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {
                    "package_name": {
                        "type": "string",
                        "description": "Name of the package to mark as explicit"
                    }
                },
                "required": ["package_name"]
            }
        ),

        Tool(
            name="mark_as_dependency",
            description="Mark a package as a dependency. Allows it to be removed as an orphan if no packages depend on it. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {
                    "package_name": {
                        "type": "string",
                        "description": "Name of the package to mark as dependency"
                    }
                },
                "required": ["package_name"]
            }
        ),

        # System Diagnostic Tools
        Tool(
            name="get_system_info",
            description="Get comprehensive system information including kernel version, architecture, hostname, uptime, and memory statistics. Works on any system.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),

        Tool(
            name="check_disk_space",
            description="Check disk space usage for critical filesystem paths including root, home, var, and pacman cache. Warns when space is low. Works on any system.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),

        Tool(
            name="get_pacman_cache_stats",
            description="Analyze pacman package cache statistics including size, package count, and cache age. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),

        Tool(
            name="check_failed_services",
            description="Check for failed systemd services. Useful for diagnosing system issues. Works on systemd-based systems.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),

        Tool(
            name="get_boot_logs",
            description="Retrieve recent boot logs from journalctl. Useful for troubleshooting boot issues. Works on systemd-based systems.",
            inputSchema={
                "type": "object",
                "properties": {
                    "lines": {
                        "type": "integer",
                        "description": "Number of log lines to retrieve. Default: 100",
                        "default": 100
                    }
                },
                "required": []
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent | ImageContent | EmbeddedResource]:
    """
    Execute a tool by name with the provided arguments.
    
    Args:
        name: Tool name
        arguments: Tool arguments
    
    Returns:
        List of content objects with tool results
    
    Raises:
        ValueError: If tool name is unknown
    """
    logger.info(f"Calling tool: {name} with args: {arguments}")
    
    if name == "search_archwiki":
        query = arguments["query"]
        limit = arguments.get("limit", 10)
        results = await search_wiki(query, limit)
        return [TextContent(type="text", text=json.dumps(results, indent=2))]
    
    elif name == "search_aur":
        query = arguments["query"]
        limit = arguments.get("limit", 20)
        sort_by = arguments.get("sort_by", "relevance")
        results = await search_aur(query, limit, sort_by)
        return [TextContent(type="text", text=json.dumps(results, indent=2))]
    
    elif name == "get_official_package_info":
        package_name = arguments["package_name"]
        result = await get_official_package_info(package_name)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "check_updates_dry_run":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: check_updates_dry_run only available on Arch Linux systems")]
        
        result = await check_updates_dry_run()
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "install_package_secure":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: install_package_secure only available on Arch Linux systems")]
        
        package_name = arguments["package_name"]
        result = await install_package_secure(package_name)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "analyze_pkgbuild_safety":
        pkgbuild_content = arguments["pkgbuild_content"]
        result = analyze_pkgbuild_safety(pkgbuild_content)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "analyze_package_metadata_risk":
        package_info = arguments["package_info"]
        result = analyze_package_metadata_risk(package_info)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    # Package Removal Tools
    elif name == "remove_package":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: remove_package only available on Arch Linux systems")]

        package_name = arguments["package_name"]
        remove_dependencies = arguments.get("remove_dependencies", False)
        force = arguments.get("force", False)
        result = await remove_package(package_name, remove_dependencies, force)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "remove_packages_batch":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: remove_packages_batch only available on Arch Linux systems")]

        package_names = arguments["package_names"]
        remove_dependencies = arguments.get("remove_dependencies", False)
        result = await remove_packages_batch(package_names, remove_dependencies)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    # Orphan Package Management
    elif name == "list_orphan_packages":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: list_orphan_packages only available on Arch Linux systems")]

        result = await list_orphan_packages()
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "remove_orphans":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: remove_orphans only available on Arch Linux systems")]

        dry_run = arguments.get("dry_run", True)
        exclude = arguments.get("exclude", None)
        result = await remove_orphans(dry_run, exclude)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    # Package Ownership Tools
    elif name == "find_package_owner":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: find_package_owner only available on Arch Linux systems")]

        file_path = arguments["file_path"]
        result = await find_package_owner(file_path)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "list_package_files":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: list_package_files only available on Arch Linux systems")]

        package_name = arguments["package_name"]
        filter_pattern = arguments.get("filter_pattern", None)
        result = await list_package_files(package_name, filter_pattern)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "search_package_files":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: search_package_files only available on Arch Linux systems")]

        filename_pattern = arguments["filename_pattern"]
        result = await search_package_files(filename_pattern)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    # Package Verification
    elif name == "verify_package_integrity":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: verify_package_integrity only available on Arch Linux systems")]

        package_name = arguments["package_name"]
        thorough = arguments.get("thorough", False)
        result = await verify_package_integrity(package_name, thorough)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    # Package Groups
    elif name == "list_package_groups":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: list_package_groups only available on Arch Linux systems")]

        result = await list_package_groups()
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "list_group_packages":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: list_group_packages only available on Arch Linux systems")]

        group_name = arguments["group_name"]
        result = await list_group_packages(group_name)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    # Install Reason Management
    elif name == "list_explicit_packages":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: list_explicit_packages only available on Arch Linux systems")]

        result = await list_explicit_packages()
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "mark_as_explicit":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: mark_as_explicit only available on Arch Linux systems")]

        package_name = arguments["package_name"]
        result = await mark_as_explicit(package_name)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "mark_as_dependency":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: mark_as_dependency only available on Arch Linux systems")]

        package_name = arguments["package_name"]
        result = await mark_as_dependency(package_name)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    # System Diagnostic Tools
    elif name == "get_system_info":
        result = await get_system_info()
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "check_disk_space":
        result = await check_disk_space()
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "get_pacman_cache_stats":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: get_pacman_cache_stats only available on Arch Linux systems")]

        result = await get_pacman_cache_stats()
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "check_failed_services":
        result = await check_failed_services()
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "get_boot_logs":
        lines = arguments.get("lines", 100)
        result = await get_boot_logs(lines)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    else:
        raise ValueError(f"Unknown tool: {name}")


# ============================================================================
# PROMPTS
# ============================================================================

@server.list_prompts()
async def list_prompts() -> list[Prompt]:
    """
    List available prompts for guided workflows.
    
    Returns:
        List of Prompt objects describing available workflows
    """
    return [
        Prompt(
            name="troubleshoot_issue",
            description="Diagnose system errors and provide solutions using Arch Wiki knowledge",
            arguments=[
                {
                    "name": "error_message",
                    "description": "The error message or issue description",
                    "required": True
                },
                {
                    "name": "context",
                    "description": "Additional context about when/where the error occurred",
                    "required": False
                }
            ]
        ),
        Prompt(
            name="audit_aur_package",
            description="Perform comprehensive security audit of an AUR package before installation",
            arguments=[
                {
                    "name": "package_name",
                    "description": "Name of the AUR package to audit",
                    "required": True
                }
            ]
        ),
        Prompt(
            name="analyze_dependencies",
            description="Analyze package dependencies and suggest installation order",
            arguments=[
                {
                    "name": "package_name",
                    "description": "Name of the package to analyze dependencies for",
                    "required": True
                }
            ]
        ),
    ]


@server.get_prompt()
async def get_prompt(name: str, arguments: dict[str, str]) -> GetPromptResult:
    """
    Generate a prompt response for guided workflows.
    
    Args:
        name: Prompt name
        arguments: Prompt arguments
    
    Returns:
        GetPromptResult with generated messages
    
    Raises:
        ValueError: If prompt name is unknown
    """
    logger.info(f"Generating prompt: {name} with args: {arguments}")
    
    if name == "troubleshoot_issue":
        error_message = arguments["error_message"]
        context = arguments.get("context", "")
        
        # Extract keywords from error message for Wiki search
        keywords = error_message.lower().split()
        wiki_query = " ".join(keywords[:5])  # Use first 5 words as search query
        
        # Search Wiki for relevant pages
        try:
            wiki_results = await search_wiki(wiki_query, limit=3)
        except Exception as e:
            wiki_results = []
        
        messages = [
            PromptMessage(
                role="user",
                content=PromptMessage.TextContent(
                    type="text",
                    text=f"I'm experiencing this error: {error_message}\n\nContext: {context}\n\nPlease help me troubleshoot this issue using Arch Linux knowledge."
                )
            )
        ]
        
        if wiki_results:
            wiki_content = "Here are some relevant Arch Wiki pages that might help:\n\n"
            for result in wiki_results:
                wiki_content += f"- **{result['title']}**: {result.get('snippet', 'No description available')}\n"
                wiki_content += f"  URL: {result['url']}\n\n"
            
            messages.append(
                PromptMessage(
                    role="assistant",
                    content=PromptMessage.TextContent(
                        type="text",
                        text=wiki_content
                    )
                )
            )
        
        return GetPromptResult(
            description=f"Troubleshooting guidance for: {error_message}",
            messages=messages
        )
    
    elif name == "audit_aur_package":
        package_name = arguments["package_name"]
        
        # Get package info and PKGBUILD
        try:
            package_info = await get_aur_info(package_name)
            pkgbuild_content = await get_pkgbuild(package_name)
            
            # Analyze both metadata and PKGBUILD
            metadata_risk = analyze_package_metadata_risk(package_info)
            pkgbuild_safety = analyze_pkgbuild_safety(pkgbuild_content)
            
            audit_summary = f"""
# Security Audit Report for {package_name}

## Package Metadata Analysis
- **Trust Score**: {metadata_risk.get('trust_score', 'N/A')}/100
- **Risk Factors**: {', '.join(metadata_risk.get('risk_factors', []))}
- **Trust Indicators**: {', '.join(metadata_risk.get('trust_indicators', []))}

## PKGBUILD Security Analysis
- **Risk Score**: {pkgbuild_safety.get('risk_score', 'N/A')}/100
- **Security Issues Found**: {len(pkgbuild_safety.get('findings', []))}
- **Critical Issues**: {len([f for f in pkgbuild_safety.get('findings', []) if f.get('severity') == 'critical'])}

## Recommendations
"""
            
            if metadata_risk.get('trust_score', 0) < 50 or pkgbuild_safety.get('risk_score', 0) > 70:
                audit_summary += "⚠️ **HIGH RISK** - Consider finding an alternative package or reviewing the source code manually.\n"
            elif metadata_risk.get('trust_score', 0) < 70 or pkgbuild_safety.get('risk_score', 0) > 50:
                audit_summary += "⚠️ **MEDIUM RISK** - Proceed with caution and review the findings below.\n"
            else:
                audit_summary += "✅ **LOW RISK** - Package appears safe to install.\n"
            
            messages = [
                PromptMessage(
                    role="user",
                    content=PromptMessage.TextContent(
                        type="text",
                        text=f"Please audit the AUR package '{package_name}' for security issues before installation."
                    )
                ),
                PromptMessage(
                    role="assistant",
                    content=PromptMessage.TextContent(
                        type="text",
                        text=audit_summary
                    )
                )
            ]
            
            return GetPromptResult(
                description=f"Security audit for AUR package: {package_name}",
                messages=messages
            )
            
        except Exception as e:
            return GetPromptResult(
                description=f"Security audit for AUR package: {package_name}",
                messages=[
                    PromptMessage(
                        role="assistant",
                        content=PromptMessage.TextContent(
                            type="text",
                            text=f"Error auditing package '{package_name}': {str(e)}"
                        )
                    )
                ]
            )
    
    elif name == "analyze_dependencies":
        package_name = arguments["package_name"]
        
        # Check if it's an official package first
        try:
            official_info = await get_official_package_info(package_name)
            if official_info.get("found"):
                deps = official_info.get("dependencies", [])
                opt_deps = official_info.get("optional_dependencies", [])
                
                analysis = f"""
# Dependency Analysis for {package_name} (Official Package)

## Required Dependencies
{chr(10).join([f"- {dep}" for dep in deps]) if deps else "None"}

## Optional Dependencies
{chr(10).join([f"- {dep}" for dep in opt_deps]) if opt_deps else "None"}

## Installation Order
1. Install required dependencies first
2. Install optional dependencies as needed
3. Install {package_name} last

## Installation Commands
```bash
# Install required dependencies
sudo pacman -S {' '.join(deps) if deps else '# No required dependencies'}

# Install optional dependencies (if needed)
sudo pacman -S {' '.join(opt_deps) if opt_deps else '# No optional dependencies'}

# Install the package
sudo pacman -S {package_name}
```
"""
            else:
                # Check AUR
                aur_info = await get_aur_info(package_name)
                if aur_info.get("found"):
                    analysis = f"""
# Dependency Analysis for {package_name} (AUR Package)

## AUR Package Information
- **Maintainer**: {aur_info.get('maintainer', 'Unknown')}
- **Last Updated**: {aur_info.get('last_modified', 'Unknown')}
- **Votes**: {aur_info.get('votes', 'Unknown')}

## Installation Considerations
1. **Security Check**: Run a security audit before installation
2. **Dependencies**: AUR packages may have complex dependency chains
3. **Build Requirements**: Check if you have all build tools installed

## Recommended Installation Process
```bash
# 1. Install build dependencies
sudo pacman -S base-devel git

# 2. Install AUR helper (if not already installed)
# Choose one: paru, yay, or manual AUR installation

# 3. Install the package
paru -S {package_name}  # or yay -S {package_name}
```

⚠️ **Important**: Always audit AUR packages for security before installation!
"""
                else:
                    analysis = f"Package '{package_name}' not found in official repositories or AUR."
        
        except Exception as e:
            analysis = f"Error analyzing dependencies for '{package_name}': {str(e)}"
        
        return GetPromptResult(
            description=f"Dependency analysis for: {package_name}",
            messages=[
                PromptMessage(
                    role="user",
                    content=PromptMessage.TextContent(
                        type="text",
                        text=f"Please analyze the dependencies for the package '{package_name}' and suggest the best installation approach."
                    )
                ),
                PromptMessage(
                    role="assistant",
                    content=PromptMessage.TextContent(
                        type="text",
                        text=analysis
                    )
                )
            ]
        )
    
    else:
        raise ValueError(f"Unknown prompt: {name}")
