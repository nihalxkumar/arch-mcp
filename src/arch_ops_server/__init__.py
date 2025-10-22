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
from .utils import IS_ARCH

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
]
