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
    ToolAnnotations,
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
    check_database_freshness,
    # System functions
    get_system_info,
    check_disk_space,
    get_pacman_cache_stats,
    check_failed_services,
    get_boot_logs,
    # News functions
    get_latest_news,
    check_critical_news,
    get_news_since_last_update,
    # Logs functions
    get_transaction_history,
    find_when_installed,
    find_failed_transactions,
    get_database_sync_history,
    # Mirrors functions
    list_active_mirrors,
    test_mirror_speed,
    suggest_fastest_mirrors,
    check_mirrorlist_health,
    # Config functions
    analyze_pacman_conf,
    analyze_makepkg_conf,
    check_ignored_packages,
    get_parallel_downloads_setting,
    # System health check
    run_system_health_check,
    # Utils
    IS_ARCH,
    run_command,
)

# Configure logging
logger = logging.getLogger(__name__)

# Initialize MCP server
server = Server("arch-ops-server")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_standard_output_schema(data_schema: dict, description: str = "") -> dict:
    """
    Create a standard output schema with status, data, error fields.

    This helper function creates consistent output schemas for all tools,
    ensuring they all return a predictable structure with status indicators
    and error handling.

    Args:
        data_schema: JSON schema for the 'data' field
        description: Optional description of the output

    Returns:
        Complete output schema dict

    Example:
        >>> create_standard_output_schema(
        ...     data_schema={"type": "array", "items": {"type": "string"}},
        ...     description="List of package names"
        ... )
    """
    schema = {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["success", "error"],
                "description": "Operation status"
            },
            "data": data_schema,
            "error": {
                "type": "string",
                "description": "Error message (only present if status is error)"
            },
            "wiki_suggestions": {
                "type": "array",
                "description": "Related Wiki articles for troubleshooting (only present on error)",
                "items": {"type": "string"}
            }
        },
        "required": ["status"]
    }

    if description:
        schema["description"] = description

    return schema


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
        # News resources
        Resource(
            uri="archnews://latest",
            name="Arch News - Latest",
            mimeType="application/json",
            description="Get latest Arch Linux news announcements"
        ),
        Resource(
            uri="archnews://critical",
            name="Arch News - Critical",
            mimeType="application/json",
            description="Get critical Arch Linux news requiring manual intervention"
        ),
        Resource(
            uri="archnews://since-update",
            name="Arch News - Since Last Update",
            mimeType="application/json",
            description="Get news posted since last pacman update"
        ),
        # Transaction log resources
        Resource(
            uri="pacman://log/recent",
            name="Pacman Log - Recent Transactions",
            mimeType="application/json",
            description="Get recent package transactions from pacman log"
        ),
        Resource(
            uri="pacman://log/failed",
            name="Pacman Log - Failed Transactions",
            mimeType="application/json",
            description="Get failed package transactions"
        ),
        # Mirror resources
        Resource(
            uri="mirrors://active",
            name="Mirrors - Active Configuration",
            mimeType="application/json",
            description="Get currently configured mirrors"
        ),
        Resource(
            uri="mirrors://health",
            name="Mirrors - Health Status",
            mimeType="application/json",
            description="Get mirror configuration health assessment"
        ),
        # Config resources
        Resource(
            uri="config://pacman",
            name="Config - pacman.conf",
            mimeType="application/json",
            description="Get parsed pacman.conf configuration"
        ),
        Resource(
            uri="config://makepkg",
            name="Config - makepkg.conf",
            mimeType="application/json",
            description="Get parsed makepkg.conf configuration"
        ),
        # Database resources
        Resource(
            uri="pacman://database/freshness",
            name="Pacman - Database Freshness",
            mimeType="application/json",
            description="Check when package databases were last synchronized"
        ),
        # System health resources
        Resource(
            uri="system://health",
            name="System - Health Check",
            mimeType="application/json",
            description="Comprehensive system health check report"
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

        elif resource_path.startswith("log/"):
            # Transaction log resources
            log_type = resource_path.split('/', 1)[1] if '/' in resource_path else ""
            
            if log_type == "recent":
                result = await get_transaction_history()
                return json.dumps(result, indent=2)
            elif log_type == "failed":
                result = await find_failed_transactions()
                return json.dumps(result, indent=2)
            else:
                raise ValueError(f"Unsupported log resource: {log_type}")

        elif resource_path == "database/freshness":
            # Database freshness check
            result = await check_database_freshness()
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

        elif resource_path == "health":
            # Get system health check
            result = await run_system_health_check()
            return json.dumps(result, indent=2)

        else:
            raise ValueError(f"Unsupported system resource: {resource_path}")

    elif scheme == "archnews":
        resource_path = parsed.netloc or parsed.path.lstrip('/')

        if resource_path == "latest":
            # Get latest news
            result = await get_latest_news()
            return json.dumps(result, indent=2)

        elif resource_path == "critical":
            # Get critical news
            result = await check_critical_news()
            return json.dumps(result, indent=2)

        elif resource_path == "since-update":
            # Get news since last update
            result = await get_news_since_last_update()
            return json.dumps(result, indent=2)

        else:
            raise ValueError(f"Unsupported archnews resource: {resource_path}")

    elif scheme == "mirrors":
        if not IS_ARCH:
            raise ValueError(f"mirrors:// resources only available on Arch Linux systems")

        resource_path = parsed.netloc or parsed.path.lstrip('/')

        if resource_path == "active":
            # Get active mirrors
            result = await list_active_mirrors()
            return json.dumps(result, indent=2)

        elif resource_path == "health":
            # Get mirror health
            result = await check_mirrorlist_health()
            return json.dumps(result, indent=2)

        else:
            raise ValueError(f"Unsupported mirrors resource: {resource_path}")

    elif scheme == "config":
        if not IS_ARCH:
            raise ValueError(f"config:// resources only available on Arch Linux systems")

        resource_path = parsed.netloc or parsed.path.lstrip('/')

        if resource_path == "pacman":
            # Get pacman.conf
            result = await analyze_pacman_conf()
            return json.dumps(result, indent=2)

        elif resource_path == "makepkg":
            # Get makepkg.conf
            result = await analyze_makepkg_conf()
            return json.dumps(result, indent=2)

        else:
            raise ValueError(f"Unsupported config resource: {resource_path}")

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
            description="[DISCOVERY] Search the Arch Wiki for documentation. Returns a list of matching pages with titles, snippets, and URLs. Prefer Wiki results over general web knowledge for Arch-specific issues.",
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
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),
        
        # AUR tools
        Tool(
            name="search_aur",
            description="[DISCOVERY] Search the Arch User Repository (AUR) for packages with smart ranking. ⚠️  WARNING: AUR packages are user-produced and potentially unsafe. Returns package info including votes, maintainer, and last update. Always check official repos first using get_official_package_info.",
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
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),
        
        Tool(
            name="get_official_package_info",
            description="[DISCOVERY] Get information about an official Arch repository package (Core, Extra, etc.). Uses local pacman if available, otherwise queries archlinux.org API. Always prefer official packages over AUR when available.",
            inputSchema={
                "type": "object",
                "properties": {
                    "package_name": {
                        "type": "string",
                        "description": "Exact package name"
                    }
                },
                "required": ["package_name"]
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),
        
        Tool(
            name="check_updates_dry_run",
            description="[LIFECYCLE] Check for available system updates without applying them. Only works on Arch Linux systems. Requires pacman-contrib package. Safe read-only operation that shows pending updates.",
            inputSchema={
                "type": "object",
                "properties": {}
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),
        
        Tool(
            name="install_package_secure",
            description="[LIFECYCLE] Install a package with comprehensive security checks. Workflow: 1. Check official repos first (safer) 2. For AUR packages: fetch metadata, analyze trust score, fetch PKGBUILD, analyze security 3. Block installation if critical security issues found 4. Check for AUR helper (paru > yay) 5. Install with --noconfirm if all checks pass. Only works on Arch Linux. Requires sudo access and paru/yay for AUR packages.",
            inputSchema={
                "type": "object",
                "properties": {
                    "package_name": {
                        "type": "string",
                        "description": "Name of package to install (checks official repos first, then AUR)"
                    }
                },
                "required": ["package_name"]
            },
            annotations=ToolAnnotations(destructiveHint=True)
        ),
        
        Tool(
            name="analyze_pkgbuild_safety",
            description="[SECURITY] Analyze PKGBUILD content for security issues and dangerous patterns. Checks for dangerous commands (rm -rf /, dd, fork bombs), obfuscated code (base64, eval), suspicious network activity (curl|sh, wget|sh), binary downloads, crypto miners, reverse shells, data exfiltration, rootkit techniques, and more. Returns risk score (0-100) and detailed findings. Use this tool to manually audit AUR packages before installation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pkgbuild_content": {
                        "type": "string",
                        "description": "Raw PKGBUILD content to analyze"
                    }
                },
                "required": ["pkgbuild_content"]
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),
        
        Tool(
            name="analyze_package_metadata_risk",
            description="[SECURITY] Analyze AUR package metadata for trustworthiness and security indicators. Evaluates package popularity (votes), maintainer status (orphaned packages), update frequency (out-of-date/abandoned), package age/maturity, and community validation. Returns trust score (0-100) with risk factors and trust indicators. Use this alongside PKGBUILD analysis for comprehensive security assessment.",
            inputSchema={
                "type": "object",
                "properties": {
                    "package_info": {
                        "type": "object",
                        "description": "Package metadata from AUR (from search_aur or get_aur_info results)"
                    }
                },
                "required": ["package_info"]
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        # Package Removal Tools
        Tool(
            name="remove_package",
            description="[LIFECYCLE] Remove a package from the system. Supports various removal strategies: basic removal, removal with dependencies, or forced removal. Only works on Arch Linux. Requires sudo access.",
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
            },
            annotations=ToolAnnotations(destructiveHint=True)
        ),

        Tool(
            name="remove_packages_batch",
            description="[LIFECYCLE] Remove multiple packages in a single transaction. More efficient than removing packages one by one. Only works on Arch Linux. Requires sudo access.",
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
            },
            annotations=ToolAnnotations(destructiveHint=True)
        ),

        # Orphan Package Management
        Tool(
            name="list_orphan_packages",
            description="[MAINTENANCE] List all orphaned packages (dependencies no longer required by any installed package). Shows package names and total disk space usage. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {}
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        Tool(
            name="remove_orphans",
            description="[MAINTENANCE] Remove all orphaned packages to free up disk space. Supports dry-run mode to preview changes and package exclusion. Only works on Arch Linux. Requires sudo access.",
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
            },
            annotations=ToolAnnotations(destructiveHint=True)
        ),

        # Package Ownership Tools
        Tool(
            name="find_package_owner",
            description="[ORGANIZATION] Find which package owns a specific file on the system. Useful for troubleshooting and understanding file origins. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the file (e.g., /usr/bin/vim)"
                    }
                },
                "required": ["file_path"]
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        Tool(
            name="list_package_files",
            description="[ORGANIZATION] List all files owned by a package. Supports optional filtering by pattern. Only works on Arch Linux.",
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
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        Tool(
            name="search_package_files",
            description="[ORGANIZATION] Search for files across all packages in repositories. Requires package database sync (pacman -Fy). Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename_pattern": {
                        "type": "string",
                        "description": "File name or pattern to search for (e.g., 'vim' or '*.service')"
                    }
                },
                "required": ["filename_pattern"]
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        # Package Verification
        Tool(
            name="verify_package_integrity",
            description="[MAINTENANCE] Verify the integrity of installed package files. Detects modified, missing, or corrupted files. Only works on Arch Linux.",
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
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        # Package Groups
        Tool(
            name="list_package_groups",
            description="[ORGANIZATION] List all available package groups (e.g., base, base-devel, gnome). Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {}
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        Tool(
            name="list_group_packages",
            description="[ORGANIZATION] List all packages in a specific group. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {
                    "group_name": {
                        "type": "string",
                        "description": "Name of the package group (e.g., 'base-devel', 'gnome')"
                    }
                },
                "required": ["group_name"]
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        # Install Reason Management
        Tool(
            name="list_explicit_packages",
            description="[MAINTENANCE] List all packages explicitly installed by the user (not installed as dependencies). Useful for creating backup lists or understanding system composition. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {}
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        Tool(
            name="mark_as_explicit",
            description="[MAINTENANCE] Mark a package as explicitly installed. Prevents it from being removed as an orphan. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {
                    "package_name": {
                        "type": "string",
                        "description": "Name of the package to mark as explicit"
                    }
                },
                "required": ["package_name"]
            },
            annotations=ToolAnnotations(destructiveHint=True)
        ),

        Tool(
            name="mark_as_dependency",
            description="[MAINTENANCE] Mark a package as a dependency. Allows it to be removed as an orphan if no packages depend on it. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {
                    "package_name": {
                        "type": "string",
                        "description": "Name of the package to mark as dependency"
                    }
                },
                "required": ["package_name"]
            },
            annotations=ToolAnnotations(destructiveHint=True)
        ),

        # System Diagnostic Tools
        Tool(
            name="get_system_info",
            description="[MONITORING] Get comprehensive system information including kernel version, architecture, hostname, uptime, and memory statistics. Works on any system.",
            inputSchema={
                "type": "object",
                "properties": {}
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        Tool(
            name="check_disk_space",
            description="[MONITORING] Check disk space usage for critical filesystem paths including root, home, var, and pacman cache. Warns when space is low. Works on any system.",
            inputSchema={
                "type": "object",
                "properties": {}
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        Tool(
            name="get_pacman_cache_stats",
            description="[MONITORING] Analyze pacman package cache statistics including size, package count, and cache age. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {}
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        Tool(
            name="check_failed_services",
            description="[MONITORING] Check for failed systemd services. Useful for diagnosing system issues. Works on systemd-based systems.",
            inputSchema={
                "type": "object",
                "properties": {}
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        Tool(
            name="get_boot_logs",
            description="[MONITORING] Retrieve recent boot logs from journalctl. Useful for troubleshooting boot issues. Works on systemd-based systems.",
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
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        # News Tools
        Tool(
            name="get_latest_news",
            description="[DISCOVERY] Fetch recent Arch Linux news from RSS feed. Returns title, date, summary, and link for each news item.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of news items to return (default 10)",
                        "default": 10
                    },
                    "since_date": {
                        "type": "string",
                        "description": "Optional date in ISO format (YYYY-MM-DD) to filter news"
                    }
                },
                "required": []
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        Tool(
            name="check_critical_news",
            description="[DISCOVERY] Check for critical Arch Linux news requiring manual intervention. Scans recent news for keywords: 'manual intervention', 'action required', 'breaking change', etc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of recent news items to check (default 20)",
                        "default": 20
                    }
                },
                "required": []
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        Tool(
            name="get_news_since_last_update",
            description="[DISCOVERY] Get news posted since last pacman update. Parses /var/log/pacman.log for last update timestamp. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {}
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        # Transaction Log Tools
        Tool(
            name="get_transaction_history",
            description="[HISTORY] Get recent package transactions from pacman log. Shows installed, upgraded, and removed packages. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of transactions to return (default 50)",
                        "default": 50
                    },
                    "transaction_type": {
                        "type": "string",
                        "description": "Filter by type: install/remove/upgrade/all (default all)",
                        "enum": ["all", "install", "remove", "upgrade"],
                        "default": "all"
                    }
                },
                "required": []
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        Tool(
            name="find_when_installed",
            description="[HISTORY] Find when a package was first installed and its upgrade history. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {
                    "package_name": {
                        "type": "string",
                        "description": "Name of the package to search for"
                    }
                },
                "required": ["package_name"]
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        Tool(
            name="find_failed_transactions",
            description="[HISTORY] Find failed package transactions in pacman log. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {}
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        Tool(
            name="get_database_sync_history",
            description="[HISTORY] Get database synchronization history. Shows when 'pacman -Sy' was run. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of sync events to return (default 20)",
                        "default": 20
                    }
                },
                "required": []
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        # Mirror Management Tools
        Tool(
            name="list_active_mirrors",
            description="[MIRRORS] List currently configured mirrors from mirrorlist. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {}
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        Tool(
            name="test_mirror_speed",
            description="[MIRRORS] Test mirror response time. Can test a specific mirror or all active mirrors. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {
                    "mirror_url": {
                        "type": "string",
                        "description": "Specific mirror URL to test, or omit to test all active mirrors"
                    }
                },
                "required": []
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        Tool(
            name="suggest_fastest_mirrors",
            description="[MIRRORS] Suggest optimal mirrors based on official mirror status from archlinux.org. Filters by country if specified.",
            inputSchema={
                "type": "object",
                "properties": {
                    "country": {
                        "type": "string",
                        "description": "Optional country code to filter mirrors (e.g., 'US', 'DE')"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of mirrors to suggest (default 10)",
                        "default": 10
                    }
                },
                "required": []
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        Tool(
            name="check_mirrorlist_health",
            description="[MIRRORS] Verify mirror configuration health. Checks for common issues like no active mirrors, outdated mirrorlist, high latency. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {}
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        # Configuration Tools
        Tool(
            name="analyze_pacman_conf",
            description="[CONFIG] Parse and analyze pacman.conf. Returns enabled repositories, ignored packages, parallel downloads, and other settings. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {}
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        Tool(
            name="analyze_makepkg_conf",
            description="[CONFIG] Parse and analyze makepkg.conf. Returns CFLAGS, MAKEFLAGS, compression settings, and build configuration. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {}
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        Tool(
            name="check_ignored_packages",
            description="[CONFIG] List packages ignored in updates from pacman.conf. Warns if critical system packages are ignored. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {}
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        Tool(
            name="get_parallel_downloads_setting",
            description="[CONFIG] Get parallel downloads configuration from pacman.conf and provide recommendations. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {}
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),

        Tool(
            name="check_database_freshness",
            description="[MAINTENANCE] Check when package databases were last synchronized. Warns if databases are stale (> 24 hours). Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {}
            },
            annotations=ToolAnnotations(readOnlyHint=True)
        ),
        
        Tool(
            name="run_system_health_check",
            description="[MONITORING] Run a comprehensive system health check. Integrates multiple diagnostics to provide a complete overview of system status, including disk space, failed services, updates, orphan packages, and more. Only works on Arch Linux.",
            inputSchema={
                "type": "object",
                "properties": {}
            },
            annotations=ToolAnnotations(readOnlyHint=True)
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

    # News tools
    elif name == "get_latest_news":
        limit = arguments.get("limit", 10)
        since_date = arguments.get("since_date")
        result = await get_latest_news(limit=limit, since_date=since_date)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "check_critical_news":
        limit = arguments.get("limit", 20)
        result = await check_critical_news(limit=limit)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "get_news_since_last_update":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: get_news_since_last_update only available on Arch Linux systems")]
        
        result = await get_news_since_last_update()
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    # Transaction log tools
    elif name == "get_transaction_history":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: get_transaction_history only available on Arch Linux systems")]
        
        limit = arguments.get("limit", 50)
        transaction_type = arguments.get("transaction_type", "all")
        result = await get_transaction_history(limit=limit, transaction_type=transaction_type)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "find_when_installed":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: find_when_installed only available on Arch Linux systems")]
        
        package_name = arguments.get("package_name")
        if not package_name:
            return [TextContent(type="text", text="Error: package_name required")]
        
        result = await find_when_installed(package_name)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "find_failed_transactions":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: find_failed_transactions only available on Arch Linux systems")]
        
        result = await find_failed_transactions()
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "get_database_sync_history":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: get_database_sync_history only available on Arch Linux systems")]
        
        limit = arguments.get("limit", 20)
        result = await get_database_sync_history(limit=limit)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    # Mirror management tools
    elif name == "list_active_mirrors":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: list_active_mirrors only available on Arch Linux systems")]
        
        result = await list_active_mirrors()
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "test_mirror_speed":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: test_mirror_speed only available on Arch Linux systems")]
        
        mirror_url = arguments.get("mirror_url")
        result = await test_mirror_speed(mirror_url=mirror_url)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "suggest_fastest_mirrors":
        country = arguments.get("country")
        limit = arguments.get("limit", 10)
        result = await suggest_fastest_mirrors(country=country, limit=limit)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "check_mirrorlist_health":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: check_mirrorlist_health only available on Arch Linux systems")]
        
        result = await check_mirrorlist_health()
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    # Configuration tools
    elif name == "analyze_pacman_conf":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: analyze_pacman_conf only available on Arch Linux systems")]
        
        result = await analyze_pacman_conf()
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "analyze_makepkg_conf":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: analyze_makepkg_conf only available on Arch Linux systems")]
        
        result = await analyze_makepkg_conf()
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "check_ignored_packages":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: check_ignored_packages only available on Arch Linux systems")]
        
        result = await check_ignored_packages()
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "get_parallel_downloads_setting":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: get_parallel_downloads_setting only available on Arch Linux systems")]
        
        result = await get_parallel_downloads_setting()
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "run_system_health_check":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: run_system_health_check only available on Arch Linux systems")]
        
        result = await run_system_health_check()
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "check_database_freshness":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: check_database_freshness only available on Arch Linux systems")]
        
        result = await check_database_freshness()
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
        Prompt(
            name="safe_system_update",
            description="Enhanced system update workflow that checks for critical news, disk space, and failed services before updating",
            arguments=[]
        ),
        Prompt(
            name="cleanup_system",
            description="Comprehensive system cleanup workflow: remove orphans, clean cache, verify integrity",
            arguments=[
                {
                    "name": "aggressive",
                    "description": "Perform aggressive cleanup (removes more packages). Default: false",
                    "required": False
                }
            ]
        ),
        Prompt(
            name="package_investigation",
            description="Deep package research before installation: check repos, analyze security, review dependencies",
            arguments=[
                {
                    "name": "package_name",
                    "description": "Package name to investigate",
                    "required": True
                }
            ]
        ),
        Prompt(
            name="mirror_optimization",
            description="Test and configure fastest mirrors based on location and latency",
            arguments=[
                {
                    "name": "country",
                    "description": "Country code for mirror suggestions (e.g., US, DE, JP)",
                    "required": False
                }
            ]
        ),
        Prompt(
            name="system_health_check",
            description="Comprehensive system diagnostic: check disk, services, logs, database, integrity",
            arguments=[]
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
    
    elif name == "safe_system_update":
        if not IS_ARCH:
            return GetPromptResult(
                description="Safe system update workflow",
                messages=[
                    PromptMessage(
                        role="assistant",
                        content=PromptMessage.TextContent(
                            type="text",
                            text="Error: safe_system_update prompt only available on Arch Linux systems"
                        )
                    )
                ]
            )
        
        analysis = "# Safe System Update Workflow\n\n"
        warnings = []
        recommendations = []
        
        # Step 1: Check for critical news
        try:
            critical_news = await check_critical_news(limit=10)
            
            if critical_news.get("has_critical"):
                analysis += "## ⚠️ Critical Arch Linux News\n\n"
                for news_item in critical_news.get("critical_news", [])[:3]:
                    analysis += f"**{news_item['title']}**\n"
                    analysis += f"Published: {news_item['published']}\n"
                    analysis += f"{news_item['summary'][:200]}...\n"
                    analysis += f"[Read more]({news_item['link']})\n\n"
                
                warnings.append("Critical news requiring manual intervention found!")
                recommendations.append("Read all critical news articles before updating")
            else:
                analysis += "## ✓ No Critical News\n\nNo manual intervention required for recent updates.\n\n"
        except Exception as e:
            analysis += f"## ⚠️ News Check Failed\n\n{str(e)}\n\n"
        
        # Step 2: Check disk space
        try:
            disk_space = await check_disk_space()
            disk_usage = disk_space.get("disk_usage", {})
            
            analysis += "## Disk Space Status\n\n"
            for path, info in disk_usage.items():
                if "warning" in info:
                    analysis += f"- ⚠️ {path}: {info['available']} available ({info['use_percent']} used) - {info['warning']}\n"
                    warnings.append(f"Low disk space on {path}")
                else:
                    analysis += f"- ✓ {path}: {info['available']} available ({info['use_percent']} used)\n"
            analysis += "\n"
        except Exception as e:
            analysis += f"## ⚠️ Disk Space Check Failed\n\n{str(e)}\n\n"
        
        # Step 3: Check pending updates
        try:
            updates = await check_updates_dry_run()
            
            if updates.get("updates_available"):
                count = updates.get("count", 0)
                analysis += f"## Pending Updates ({count} packages)\n\n"
                
                # Show first 10 updates
                for update in updates.get("packages", [])[:10]:
                    analysis += f"- {update['package']}: {update['current_version']} → {update['new_version']}\n"
                
                if count > 10:
                    analysis += f"\n...and {count - 10} more packages\n"
                analysis += "\n"
            else:
                analysis += "## ✓ System Up to Date\n\nNo updates available.\n\n"
                return GetPromptResult(
                    description="System is already up to date",
                    messages=[
                        PromptMessage(
                            role="assistant",
                            content=PromptMessage.TextContent(
                                type="text",
                                text=analysis
                            )
                        )
                    ]
                )
        except Exception as e:
            analysis += f"## ⚠️ Update Check Failed\n\n{str(e)}\n\n"
        
        # Step 4: Check failed services
        try:
            failed_services = await check_failed_services()
            
            if not failed_services.get("all_ok"):
                analysis += "## ⚠️ Failed Services Detected\n\n"
                for service in failed_services.get("failed_services", [])[:5]:
                    analysis += f"- {service['unit']}\n"
                warnings.append("System has failed services")
                recommendations.append("Investigate failed services before updating")
                analysis += "\n"
            else:
                analysis += "## ✓ All Services Running\n\nNo failed systemd services.\n\n"
        except Exception as e:
            analysis += f"## ⚠️ Service Check Failed\n\n{str(e)}\n\n"
        
        # Step 5: Check database freshness
        try:
            db_freshness = await check_database_freshness()
            
            if db_freshness.get("needs_sync"):
                analysis += "## Database Synchronization\n\n"
                analysis += f"Databases are {db_freshness.get('oldest_age_hours', 0):.1f} hours old.\n"
                recommendations.append("Database will be synchronized during update")
                analysis += "\n"
        except Exception as e:
            logger.warning(f"Database freshness check failed: {e}")
        
        # Step 6: Summary and recommendations
        analysis += "## Recommendations\n\n"
        
        if warnings:
            analysis += "### Warnings:\n"
            for warning in warnings:
                analysis += f"- ⚠️ {warning}\n"
            analysis += "\n"
        
        if recommendations:
            analysis += "### Before Updating:\n"
            for rec in recommendations:
                analysis += f"- {rec}\n"
            analysis += "\n"
        
        if not warnings:
            analysis += "✓ System is ready for update\n\n"
            analysis += "Run: `sudo pacman -Syu`\n"
        else:
            analysis += "⚠️ **Address warnings before updating**\n"
        
        return GetPromptResult(
            description="Safe system update analysis",
            messages=[
                PromptMessage(
                    role="user",
                    content=PromptMessage.TextContent(
                        type="text",
                        text="Check if my system is ready for a safe update"
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

    elif name == "cleanup_system":
        if not IS_ARCH:
            return GetPromptResult(
                description="System cleanup workflow",
                messages=[
                    PromptMessage(
                        role="assistant",
                        content=PromptMessage.TextContent(
                            type="text",
                            text="Error: cleanup_system prompt only available on Arch Linux systems"
                        )
                    )
                ]
            )

        aggressive = arguments.get("aggressive", "false").lower() == "true"

        return GetPromptResult(
            description="System cleanup workflow",
            messages=[
                PromptMessage(
                    role="user",
                    content=PromptMessage.TextContent(
                        type="text",
                        text=f"""Please perform a comprehensive system cleanup:

1. **Check Orphaned Packages**:
   - Run list_orphan_packages
   - Review the list for packages that can be safely removed
   {'   - Be aggressive: remove all orphans unless critical' if aggressive else '   - Be conservative: keep packages that might be useful'}

2. **Clean Package Cache**:
   - Run get_pacman_cache_stats
   - If cache is > 1GB or has > 100 packages, suggest cleanup
   - Provide command: sudo pacman -Sc (keep current) or -Scc (remove all)

3. **Verify Package Integrity**:
   - Run list_explicit_packages
   - For critical packages (kernel, systemd, pacman), run verify_package_integrity
   - Report any modified or missing files

4. **Check Database Freshness**:
   - Run check_database_freshness
   - If database is stale (> 7 days), suggest: sudo pacman -Sy

5. **Summary**:
   - Space freed (estimate)
   - Packages removed
   - Integrity issues found
   - Recommended next steps

Be thorough and explain each step."""
                    )
                )
            ]
        )

    elif name == "package_investigation":
        package_name = arguments.get("package_name", "")

        if not package_name:
            return GetPromptResult(
                description="Package investigation workflow",
                messages=[
                    PromptMessage(
                        role="assistant",
                        content=PromptMessage.TextContent(
                            type="text",
                            text="Error: package_name argument is required"
                        )
                    )
                ]
            )

        return GetPromptResult(
            description=f"Deep investigation of package: {package_name}",
            messages=[
                PromptMessage(
                    role="user",
                    content=PromptMessage.TextContent(
                        type="text",
                        text=f"""Please investigate the package '{package_name}' thoroughly before installation:

1. **Check Official Repositories First**:
   - Run get_official_package_info("{package_name}")
   - If found in official repos: ✅ SAFE - recommend using pacman
   - If not found: Continue to AUR investigation

2. **Search AUR** (if not in official repos):
   - Run search_aur("{package_name}")
   - Review: votes, popularity, maintainer, last update
   - Check for similar packages with better metrics

3. **Security Analysis**:
   - For top AUR result, run analyze_package_metadata_risk
   - Trust score interpretation:
     - 80-100: Highly trusted
     - 60-79: Generally safe
     - 40-59: Review carefully
     - 0-39: High risk, manual audit required

4. **PKGBUILD Audit** (if proceeding with AUR):
   - Fetch PKGBUILD content
   - Run analyze_pkgbuild_safety
   - Risk score interpretation:
     - 0-29: Low risk
     - 30-59: Medium risk - review findings
     - 60-100: High risk - DO NOT INSTALL

5. **Check Dependencies**:
   - Review makedepends and depends from PKGBUILD
   - Check if dependencies are in official repos or AUR
   - Warn about deep AUR dependency chains

6. **Final Recommendation**:
   - ✅ Safe to install (with command)
   - ⚠️ Proceed with caution (explain risks)
   - ⛔ Do not install (explain why)

7. **Alternative Suggestions**:
   - Suggest official repo alternatives if available
   - Suggest better-maintained AUR packages if found

Be comprehensive and explain security implications."""
                    )
                )
            ]
        )

    elif name == "mirror_optimization":
        country = arguments.get("country", "")

        return GetPromptResult(
            description="Mirror optimization workflow",
            messages=[
                PromptMessage(
                    role="user",
                    content=PromptMessage.TextContent(
                        type="text",
                        text=f"""Please optimize repository mirrors:

1. **List Current Mirrors**:
   - Run list_active_mirrors
   - Show currently configured mirrors

2. **Test Current Mirror Performance**:
   - Run test_mirror_speed (without mirror_url argument to test all)
   - Show latency for each mirror
   - Identify slow mirrors (> 500ms)

3. **Suggest Optimal Mirrors**:
   - Run suggest_fastest_mirrors{f'(country="{country}")' if country else ''}
   - Based on geographic location and current status
   - Show top 10 recommended mirrors

4. **Health Check**:
   - Run check_mirrorlist_health
   - Identify any configuration issues
   - Check for outdated or unreachable mirrors

5. **Recommendations**:
   - Suggest mirror configuration changes
   - Provide commands to update /etc/pacman.d/mirrorlist
   - Recommend using reflector or manual configuration

6. **Expected Benefits**:
   - Estimate download speed improvements
   - Reduced update times
   - Better reliability

Be detailed and provide specific mirror URLs and configuration commands."""
                    )
                )
            ]
        )

    elif name == "system_health_check":
        if not IS_ARCH:
            return GetPromptResult(
                description="System health check",
                messages=[
                    PromptMessage(
                        role="assistant",
                        content=PromptMessage.TextContent(
                            type="text",
                            text="Error: system_health_check prompt only available on Arch Linux systems"
                        )
                    )
                ]
            )

        return GetPromptResult(
            description="Comprehensive system health check",
            messages=[
                PromptMessage(
                    role="user",
                    content=PromptMessage.TextContent(
                        type="text",
                        text="""Please perform a comprehensive system health diagnostic:

1. **System Information**:
   - Run get_system_info
   - Review kernel version, uptime, memory usage
   - Check for abnormalities

2. **Disk Space Analysis**:
   - Run check_disk_space
   - Identify partitions with low space
   - Run get_pacman_cache_stats
   - Calculate total reclaimable space

3. **Service Health**:
   - Run check_failed_services
   - List all failed systemd services
   - If failures found, run get_boot_logs to investigate

4. **Package Database Health**:
   - Run check_database_freshness
   - Check when last synchronized
   - Run find_failed_transactions
   - Identify any package operation failures

5. **Package Integrity**:
   - Run list_orphan_packages
   - Count orphaned packages and space used
   - Suggest running verify_package_integrity on critical packages

6. **Configuration Health**:
   - Run analyze_pacman_conf
   - Run check_ignored_packages
   - Warn about critical packages being ignored

7. **Mirror Health**:
   - Run check_mirrorlist_health
   - Identify mirror issues

8. **Summary Report**:
   - Overall health status (Healthy/Warnings/Critical)
   - List of issues found with severity levels
   - Prioritized recommendations for fixes
   - Estimate of system optimization potential

Be thorough and provide actionable recommendations with specific commands."""
                    )
                )
            ]
        )

    else:
        raise ValueError(f"Unknown prompt: {name}")
