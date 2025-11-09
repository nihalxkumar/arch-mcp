# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
Arch Linux MCP Server

A Model Context Protocol server that bridges AI assistants with the Arch Linux
ecosystem, providing access to the Arch Wiki, AUR, and official repositories.
"""

__version__ = "0.1.0"

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
from .pacman import get_official_package_info, check_updates_dry_run
from .utils import IS_ARCH, run_command

# Import server from the server module
from .server import server

# Main function will be defined here
async def main():
    """
    Main entry point for the MCP server.
    Runs the server using STDIO transport.
    """
    import asyncio
    import mcp.server.stdio
    import logging
    
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    logger.info("Starting Arch Linux MCP Server")
    logger.info(f"Running on Arch Linux: {IS_ARCH}")
    
    # Run the server using STDIO
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


def main_sync():
    """Synchronous wrapper for the main function."""
    import asyncio
    asyncio.run(main())

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
    # Utils
    "IS_ARCH",
    "run_command",
    # Main functions
    "main",
    "main_sync",
]
