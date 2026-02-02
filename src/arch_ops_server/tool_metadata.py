# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
Tool metadata and relationship definitions.

Provides structured information about tool categories, relationships, and workflows
to improve tool discovery and organization.
"""

from typing import List, Literal
from dataclasses import dataclass, field

# Type aliases for clarity
Category = Literal[
    "discovery",
    "lifecycle",
    "maintenance",
    "organization",
    "security",
    "monitoring",
    "history",
    "mirrors",
    "config"
]

Platform = Literal["any", "arch", "systemd"]
Permission = Literal["read", "write"]


@dataclass
class ToolMetadata:
    """Metadata for a single tool."""
    name: str
    category: Category
    platform: Platform
    permission: Permission
    workflow: str
    related_tools: List[str] = field(default_factory=list)
    prerequisite_tools: List[str] = field(default_factory=list)


# Complete tool metadata definitions for all 41 tools
TOOL_METADATA = {
    # ========================================================================
    # Discovery & Information (6 tools)
    # ========================================================================
    "search_archwiki": ToolMetadata(
        name="search_archwiki",
        category="discovery",
        platform="any",
        permission="read",
        workflow="research",
        related_tools=["search_aur", "get_official_package_info"],
        prerequisite_tools=[]
    ),
    "search_aur": ToolMetadata(
        name="search_aur",
        category="discovery",
        platform="any",
        permission="read",
        workflow="research",
        related_tools=[
            "get_official_package_info",
            "analyze_package_metadata_risk",
            "analyze_pkgbuild_safety",
            "install_package_secure"
        ],
        prerequisite_tools=[]
    ),
    "get_official_package_info": ToolMetadata(
        name="get_official_package_info",
        category="discovery",
        platform="any",
        permission="read",
        workflow="research",
        related_tools=["search_aur", "install_package_secure"],
        prerequisite_tools=[]
    ),
    "get_latest_news": ToolMetadata(
        name="get_latest_news",
        category="discovery",
        platform="any",
        permission="read",
        workflow="safety",
        related_tools=["check_critical_news", "get_news_since_last_update"],
        prerequisite_tools=[]
    ),
    "check_critical_news": ToolMetadata(
        name="check_critical_news",
        category="discovery",
        platform="any",
        permission="read",
        workflow="safety",
        related_tools=["get_latest_news", "check_updates_dry_run"],
        prerequisite_tools=[]
    ),
    "get_news_since_last_update": ToolMetadata(
        name="get_news_since_last_update",
        category="discovery",
        platform="arch",
        permission="read",
        workflow="safety",
        related_tools=["get_latest_news", "check_critical_news"],
        prerequisite_tools=[]
    ),

    # ========================================================================
    # Package Lifecycle (4 tools)
    # ========================================================================
    "check_updates_dry_run": ToolMetadata(
        name="check_updates_dry_run",
        category="lifecycle",
        platform="arch",
        permission="read",
        workflow="update",
        related_tools=["check_critical_news", "check_disk_space"],
        prerequisite_tools=[]
    ),
    "install_package_secure": ToolMetadata(
        name="install_package_secure",
        category="lifecycle",
        platform="arch",
        permission="write",
        workflow="installation",
        related_tools=[
            "check_updates_dry_run",
            "verify_package_integrity",
            "get_transaction_history"
        ],
        prerequisite_tools=[
            "get_official_package_info",
            "analyze_pkgbuild_safety",
            "analyze_package_metadata_risk"
        ]
    ),
    "remove_package": ToolMetadata(
        name="remove_package",
        category="lifecycle",
        platform="arch",
        permission="write",
        workflow="removal",
        related_tools=["remove_packages_batch", "list_orphan_packages"],
        prerequisite_tools=[]
    ),
    "remove_packages_batch": ToolMetadata(
        name="remove_packages_batch",
        category="lifecycle",
        platform="arch",
        permission="write",
        workflow="removal",
        related_tools=["remove_package", "remove_orphans"],
        prerequisite_tools=[]
    ),

    # ========================================================================
    # Package Maintenance (7 tools)
    # ========================================================================
    "list_orphan_packages": ToolMetadata(
        name="list_orphan_packages",
        category="maintenance",
        platform="arch",
        permission="read",
        workflow="cleanup",
        related_tools=["remove_orphans", "mark_as_explicit"],
        prerequisite_tools=[]
    ),
    "remove_orphans": ToolMetadata(
        name="remove_orphans",
        category="maintenance",
        platform="arch",
        permission="write",
        workflow="cleanup",
        related_tools=["list_orphan_packages"],
        prerequisite_tools=["list_orphan_packages"]
    ),
    "verify_package_integrity": ToolMetadata(
        name="verify_package_integrity",
        category="maintenance",
        platform="arch",
        permission="read",
        workflow="verify",
        related_tools=["get_transaction_history", "find_package_owner"],
        prerequisite_tools=[]
    ),
    "list_explicit_packages": ToolMetadata(
        name="list_explicit_packages",
        category="maintenance",
        platform="arch",
        permission="read",
        workflow="audit",
        related_tools=["mark_as_explicit", "mark_as_dependency"],
        prerequisite_tools=[]
    ),
    "mark_as_explicit": ToolMetadata(
        name="mark_as_explicit",
        category="maintenance",
        platform="arch",
        permission="write",
        workflow="organize",
        related_tools=["list_explicit_packages", "list_orphan_packages"],
        prerequisite_tools=[]
    ),
    "mark_as_dependency": ToolMetadata(
        name="mark_as_dependency",
        category="maintenance",
        platform="arch",
        permission="write",
        workflow="organize",
        related_tools=["list_explicit_packages", "list_orphan_packages"],
        prerequisite_tools=[]
    ),
    "check_database_freshness": ToolMetadata(
        name="check_database_freshness",
        category="maintenance",
        platform="arch",
        permission="read",
        workflow="verify",
        related_tools=["get_database_sync_history"],
        prerequisite_tools=[]
    ),

    # ========================================================================
    # File Organization (5 tools)
    # ========================================================================
    "find_package_owner": ToolMetadata(
        name="find_package_owner",
        category="organization",
        platform="arch",
        permission="read",
        workflow="debug",
        related_tools=["list_package_files", "verify_package_integrity"],
        prerequisite_tools=[]
    ),
    "list_package_files": ToolMetadata(
        name="list_package_files",
        category="organization",
        platform="arch",
        permission="read",
        workflow="explore",
        related_tools=["find_package_owner", "search_package_files"],
        prerequisite_tools=[]
    ),
    "search_package_files": ToolMetadata(
        name="search_package_files",
        category="organization",
        platform="arch",
        permission="read",
        workflow="search",
        related_tools=["list_package_files", "find_package_owner"],
        prerequisite_tools=[]
    ),
    "list_package_groups": ToolMetadata(
        name="list_package_groups",
        category="organization",
        platform="arch",
        permission="read",
        workflow="explore",
        related_tools=["list_group_packages"],
        prerequisite_tools=[]
    ),
    "list_group_packages": ToolMetadata(
        name="list_group_packages",
        category="organization",
        platform="arch",
        permission="read",
        workflow="explore",
        related_tools=["list_package_groups"],
        prerequisite_tools=["list_package_groups"]
    ),

    # ========================================================================
    # Security Analysis (2 tools)
    # ========================================================================
    "analyze_pkgbuild_safety": ToolMetadata(
        name="analyze_pkgbuild_safety",
        category="security",
        platform="any",
        permission="read",
        workflow="audit",
        related_tools=["analyze_package_metadata_risk", "install_package_secure"],
        prerequisite_tools=[]
    ),
    "analyze_package_metadata_risk": ToolMetadata(
        name="analyze_package_metadata_risk",
        category="security",
        platform="any",
        permission="read",
        workflow="audit",
        related_tools=["analyze_pkgbuild_safety", "install_package_secure"],
        prerequisite_tools=["search_aur"]
    ),

    # ========================================================================
    # System Monitoring (5 tools)
    # ========================================================================
    "get_system_info": ToolMetadata(
        name="get_system_info",
        category="monitoring",
        platform="any",
        permission="read",
        workflow="diagnose",
        related_tools=["check_disk_space", "check_failed_services"],
        prerequisite_tools=[]
    ),
    "check_disk_space": ToolMetadata(
        name="check_disk_space",
        category="monitoring",
        platform="any",
        permission="read",
        workflow="diagnose",
        related_tools=["get_pacman_cache_stats", "list_orphan_packages"],
        prerequisite_tools=[]
    ),
    "get_pacman_cache_stats": ToolMetadata(
        name="get_pacman_cache_stats",
        category="monitoring",
        platform="arch",
        permission="read",
        workflow="diagnose",
        related_tools=["check_disk_space"],
        prerequisite_tools=[]
    ),
    "check_failed_services": ToolMetadata(
        name="check_failed_services",
        category="monitoring",
        platform="systemd",
        permission="read",
        workflow="diagnose",
        related_tools=["get_boot_logs", "get_system_info"],
        prerequisite_tools=[]
    ),
    "get_boot_logs": ToolMetadata(
        name="get_boot_logs",
        category="monitoring",
        platform="systemd",
        permission="read",
        workflow="diagnose",
        related_tools=["check_failed_services"],
        prerequisite_tools=[]
    ),

    # ========================================================================
    # Transaction History (4 tools)
    # ========================================================================
    "get_transaction_history": ToolMetadata(
        name="get_transaction_history",
        category="history",
        platform="arch",
        permission="read",
        workflow="audit",
        related_tools=["find_when_installed", "find_failed_transactions"],
        prerequisite_tools=[]
    ),
    "find_when_installed": ToolMetadata(
        name="find_when_installed",
        category="history",
        platform="arch",
        permission="read",
        workflow="audit",
        related_tools=["get_transaction_history"],
        prerequisite_tools=[]
    ),
    "find_failed_transactions": ToolMetadata(
        name="find_failed_transactions",
        category="history",
        platform="arch",
        permission="read",
        workflow="debug",
        related_tools=["get_transaction_history"],
        prerequisite_tools=[]
    ),
    "get_database_sync_history": ToolMetadata(
        name="get_database_sync_history",
        category="history",
        platform="arch",
        permission="read",
        workflow="audit",
        related_tools=["check_database_freshness"],
        prerequisite_tools=[]
    ),

    # ========================================================================
    # Mirror Management (4 tools)
    # ========================================================================
    "list_active_mirrors": ToolMetadata(
        name="list_active_mirrors",
        category="mirrors",
        platform="arch",
        permission="read",
        workflow="optimize",
        related_tools=["test_mirror_speed", "check_mirrorlist_health"],
        prerequisite_tools=[]
    ),
    "test_mirror_speed": ToolMetadata(
        name="test_mirror_speed",
        category="mirrors",
        platform="arch",
        permission="read",
        workflow="optimize",
        related_tools=["suggest_fastest_mirrors", "list_active_mirrors"],
        prerequisite_tools=["list_active_mirrors"]
    ),
    "suggest_fastest_mirrors": ToolMetadata(
        name="suggest_fastest_mirrors",
        category="mirrors",
        platform="any",
        permission="read",
        workflow="optimize",
        related_tools=["test_mirror_speed"],
        prerequisite_tools=[]
    ),
    "check_mirrorlist_health": ToolMetadata(
        name="check_mirrorlist_health",
        category="mirrors",
        platform="arch",
        permission="read",
        workflow="verify",
        related_tools=["list_active_mirrors", "suggest_fastest_mirrors"],
        prerequisite_tools=[]
    ),

    # ========================================================================
    # Configuration Management (4 tools)
    # ========================================================================
    "analyze_pacman_conf": ToolMetadata(
        name="analyze_pacman_conf",
        category="config",
        platform="arch",
        permission="read",
        workflow="explore",
        related_tools=["check_ignored_packages", "get_parallel_downloads_setting"],
        prerequisite_tools=[]
    ),
    "analyze_makepkg_conf": ToolMetadata(
        name="analyze_makepkg_conf",
        category="config",
        platform="arch",
        permission="read",
        workflow="explore",
        related_tools=["analyze_pacman_conf"],
        prerequisite_tools=[]
    ),
    "check_ignored_packages": ToolMetadata(
        name="check_ignored_packages",
        category="config",
        platform="arch",
        permission="read",
        workflow="verify",
        related_tools=["analyze_pacman_conf"],
        prerequisite_tools=[]
    ),
    "get_parallel_downloads_setting": ToolMetadata(
        name="get_parallel_downloads_setting",
        category="config",
        platform="arch",
        permission="read",
        workflow="explore",
        related_tools=["analyze_pacman_conf"],
        prerequisite_tools=[]
    ),
    "run_system_health_check": ToolMetadata(
        name="run_system_health_check",
        category="monitoring",
        platform="arch",
        permission="read",
        workflow="diagnose",
        related_tools=[
            "get_system_info",
            "check_disk_space",
            "check_failed_services",
            "get_pacman_cache_stats",
            "check_updates_dry_run",
            "check_critical_news",
            "list_orphan_packages",
            "check_database_freshness",
            "check_mirrorlist_health"
        ],
        prerequisite_tools=[]
    ),
}


# Category metadata with descriptions and icons
CATEGORIES = {
    "discovery": {
        "name": "Discovery & Information",
        "icon": "🔍",
        "description": "Search and retrieve package/documentation information",
        "color": "#e1f5ff"
    },
    "lifecycle": {
        "name": "Package Lifecycle",
        "icon": "📦",
        "description": "Install, update, and remove packages",
        "color": "#ffe1e1"
    },
    "maintenance": {
        "name": "Package Maintenance",
        "icon": "🔧",
        "description": "Analyze, verify, and maintain package health",
        "color": "#fff4e1"
    },
    "organization": {
        "name": "File Organization",
        "icon": "📁",
        "description": "Navigate package-file relationships",
        "color": "#e1ffe1"
    },
    "security": {
        "name": "Security Analysis",
        "icon": "🔒",
        "description": "Evaluate package safety before installation",
        "color": "#ffe1f5"
    },
    "monitoring": {
        "name": "System Monitoring",
        "icon": "📊",
        "description": "Monitor system health and diagnostics",
        "color": "#f5e1ff"
    },
    "history": {
        "name": "Transaction History",
        "icon": "📜",
        "description": "Audit package operations",
        "color": "#e1fff5"
    },
    "mirrors": {
        "name": "Mirror Management",
        "icon": "🌐",
        "description": "Optimize repository mirrors",
        "color": "#fffce1"
    },
    "config": {
        "name": "Configuration",
        "icon": "⚙️",
        "description": "Analyze system configuration",
        "color": "#e1e1ff"
    }
}


# ============================================================================
# Helper Functions
# ============================================================================

def get_tools_by_category(category: Category) -> List[str]:
    """Get all tool names in a category."""
    return [
        name for name, meta in TOOL_METADATA.items()
        if meta.category == category
    ]


def get_tools_by_platform(platform: Platform) -> List[str]:
    """Get all tool names for a platform."""
    return [
        name for name, meta in TOOL_METADATA.items()
        if meta.platform == platform or meta.platform == "any"
    ]


def get_tools_by_permission(permission: Permission) -> List[str]:
    """Get all tool names by permission level."""
    return [
        name for name, meta in TOOL_METADATA.items()
        if meta.permission == permission
    ]


def get_related_tools(tool_name: str) -> List[str]:
    """Get tools related to a given tool."""
    if tool_name not in TOOL_METADATA:
        return []
    return TOOL_METADATA[tool_name].related_tools


def get_prerequisite_tools(tool_name: str) -> List[str]:
    """Get prerequisite tools for a given tool."""
    if tool_name not in TOOL_METADATA:
        return []
    return TOOL_METADATA[tool_name].prerequisite_tools


def get_workflow_tools(workflow: str) -> List[str]:
    """Get all tools for a specific workflow."""
    return [
        name for name, meta in TOOL_METADATA.items()
        if meta.workflow == workflow
    ]


def get_category_info(category: Category) -> dict:
    """Get metadata about a category."""
    return CATEGORIES.get(category, {})


def get_tool_category_icon(tool_name: str) -> str:
    """Get the category icon for a tool."""
    if tool_name not in TOOL_METADATA:
        return ""
    category = TOOL_METADATA[tool_name].category
    return CATEGORIES.get(category, {}).get("icon", "")


# ============================================================================
# Statistics Functions
# ============================================================================

def get_tool_statistics() -> dict:
    """Get statistics about tool distribution."""
    category_counts = {}
    platform_counts = {}
    permission_counts = {}

    for meta in TOOL_METADATA.values():
        # Count by category
        category_counts[meta.category] = category_counts.get(meta.category, 0) + 1
        # Count by platform
        platform_counts[meta.platform] = platform_counts.get(meta.platform, 0) + 1
        # Count by permission
        permission_counts[meta.permission] = permission_counts.get(meta.permission, 0) + 1

    return {
        "total_tools": len(TOOL_METADATA),
        "by_category": category_counts,
        "by_platform": platform_counts,
        "by_permission": permission_counts
    }


__all__ = [
    "ToolMetadata",
    "TOOL_METADATA",
    "CATEGORIES",
    "Category",
    "Platform",
    "Permission",
    "get_tools_by_category",
    "get_tools_by_platform",
    "get_tools_by_permission",
    "get_related_tools",
    "get_prerequisite_tools",
    "get_workflow_tools",
    "get_category_info",
    "get_tool_category_icon",
    "get_tool_statistics",
]
