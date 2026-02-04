# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
Arch Linux MCP Server

A Model Context Protocol server that bridges AI assistants with the Arch Linux
ecosystem, providing access to the Arch Wiki, AUR, and official repositories.
"""

__version__ = "3.3.1"

from .wiki import search_wiki, get_wiki_page, get_wiki_page_as_text
from .aur import (
    search_aur, 
    get_aur_info, 
    get_pkgbuild, 
    get_aur_file, 
    analyze_pkgbuild_safety, 
    analyze_package_metadata_risk,
    install_package_secure
)
from .pacman import (
    get_official_package_info,
    check_updates_dry_run,
    remove_package,
    remove_packages_batch,
    remove_packages,
    list_orphan_packages,
    remove_orphans,
    manage_orphans,
    find_package_owner,
    list_package_files,
    search_package_files,
    query_file_ownership,
    verify_package_integrity,
    list_package_groups,
    list_group_packages,
    list_explicit_packages,
    mark_as_explicit,
    mark_as_dependency,
    manage_install_reason,
    check_database_freshness
)
from .system import (
    get_system_info,
    check_disk_space,
    get_pacman_cache_stats,
    check_failed_services,
    get_boot_logs
)
from .system_health_check import run_system_health_check
from .news import (
    get_latest_news,
    check_critical_news,
    get_news_since_last_update
)
from .logs import (
    get_transaction_history,
    find_when_installed,
    find_failed_transactions,
    get_database_sync_history
)
from .mirrors import (
    list_active_mirrors,
    test_mirror_speed,
    suggest_fastest_mirrors,
    check_mirrorlist_health
)
from .config import (
    analyze_pacman_conf,
    analyze_makepkg_conf,
    check_ignored_packages,
    get_parallel_downloads_setting
)
from .utils import IS_ARCH, run_command

# Import server from the server module
from .server import server

# Main function will be defined here
async def main():
    """
    Main entry point for the MCP server.
    Runs the server using STDIO transport (default for Docker MCP Catalog).
    """
    import asyncio
    import mcp.server.stdio
    import logging

    # Set up logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    logger.info("Starting Arch Linux MCP Server (STDIO)")
    logger.info(f"Running on Arch Linux: {IS_ARCH}")

    # Run the server using STDIO
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


def main_sync():
    """Synchronous wrapper for the main function (STDIO transport)."""
    import asyncio
    asyncio.run(main())


def main_http_sync():
    """
    Main entry point for HTTP server (for Smithery).
    Runs the server using SSE (Server-Sent Events) HTTP transport.
    """
    from .http_server import main_http
    main_http()

__all__ = [
    # Wiki
    "search_wiki",
    "get_wiki_page",
    "get_wiki_page_as_text",
    # AUR
    "search_aur",
    "get_aur_info",
    "get_pkgbuild",
    "get_aur_file",
    "analyze_pkgbuild_safety",
    "analyze_package_metadata_risk",
    "install_package_secure",
    # Pacman
    "get_official_package_info",
    "check_updates_dry_run",
    "remove_package",
    "remove_packages_batch",
    "remove_packages",
    "list_orphan_packages",
    "remove_orphans",
    "manage_orphans",
    "find_package_owner",
    "list_package_files",
    "search_package_files",
    "query_file_ownership",
    "verify_package_integrity",
    "list_package_groups",
    "list_group_packages",
    "list_explicit_packages",
    "mark_as_explicit",
    "mark_as_dependency",
    "manage_install_reason",
    "check_database_freshness",
    # System
    "get_system_info",
    "check_disk_space",
    "get_pacman_cache_stats",
    "check_failed_services",
    "get_boot_logs",
    "run_system_health_check",
    # News
    "get_latest_news",
    "check_critical_news",
    "get_news_since_last_update",
    # Logs
    "get_transaction_history",
    "find_when_installed",
    "find_failed_transactions",
    "get_database_sync_history",
    # Mirrors
    "list_active_mirrors",
    "test_mirror_speed",
    "suggest_fastest_mirrors",
    "check_mirrorlist_health",
    # Config
    "analyze_pacman_conf",
    "analyze_makepkg_conf",
    "check_ignored_packages",
    "get_parallel_downloads_setting",
    # Utils
    "IS_ARCH",
    "run_command",
    # Main functions
    "main",
    "main_sync",
    "main_http_sync",
]
