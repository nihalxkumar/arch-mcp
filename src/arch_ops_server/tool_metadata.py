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


# Complete tool metadata definitions for 28 registered tools
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
             "audit_package_security",
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
    # Package Lifecycle (2 tools)
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
             "query_package_history"
         ],
         prerequisite_tools=[
             "get_official_package_info",
             "audit_package_security"
         ]
     ),

    # ========================================================================
    # Package Maintenance (2 tools)
    # ========================================================================
    "verify_package_integrity": ToolMetadata(
        name="verify_package_integrity",
        category="maintenance",
        platform="arch",
        permission="read",
        workflow="verify",
        related_tools=["query_package_history", "query_file_ownership"],
        prerequisite_tools=[]
    ),
    "check_database_freshness": ToolMetadata(
        name="check_database_freshness",
        category="maintenance",
        platform="arch",
        permission="read",
        workflow="verify",
        related_tools=["query_package_history"],
        prerequisite_tools=[]
    ),

    # ========================================================================
    # File Organization (3 tools)
    # ========================================================================
    "query_file_ownership": ToolMetadata(
        name="query_file_ownership",
        category="organization",
        platform="arch",
        permission="read",
        workflow="debug",
        related_tools=["verify_package_integrity", "manage_groups"],
        prerequisite_tools=[]
    ),
    "manage_groups": ToolMetadata(
        name="manage_groups",
        category="organization",
        platform="arch",
        permission="read",
        workflow="explore",
        related_tools=["query_file_ownership"],
        prerequisite_tools=[]
    ),

     # ========================================================================
     # Security Analysis (1 tool)
     # ========================================================================
     "audit_package_security": ToolMetadata(
         name="audit_package_security",
         category="security",
         platform="any",
         permission="read",
         workflow="audit",
         related_tools=["search_aur", "install_package_secure"],
         prerequisite_tools=[]
     ),

    # ========================================================================
    # System Monitoring (6 tools)
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
        related_tools=["get_pacman_cache_stats", "manage_orphans"],
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
            "manage_orphans",
            "check_database_freshness",
            "optimize_mirrors"
        ],
        prerequisite_tools=[]
    ),

    # ========================================================================
    # Package Removal & Maintenance (2 unified tools)
    # ========================================================================
    "remove_packages": ToolMetadata(
        name="remove_packages",
        category="lifecycle",
        platform="arch",
        permission="write",
        workflow="removal",
        related_tools=["manage_orphans", "verify_package_integrity"],
        prerequisite_tools=[]
    ),
    "manage_orphans": ToolMetadata(
        name="manage_orphans",
        category="maintenance",
        platform="arch",
        permission="write",
        workflow="cleanup",
        related_tools=["remove_packages", "manage_install_reason"],
        prerequisite_tools=[]
    ),
    "query_package_history": ToolMetadata(
        name="query_package_history",
        category="history",
        platform="arch",
        permission="read",
        workflow="audit",
        related_tools=["verify_package_integrity", "check_database_freshness"],
        prerequisite_tools=[]
    ),
    "manage_install_reason": ToolMetadata(
        name="manage_install_reason",
        category="maintenance",
        platform="arch",
        permission="write",
        workflow="organize",
        related_tools=["manage_orphans", "query_package_history"],
        prerequisite_tools=[]
    ),

    # ========================================================================
    # Mirror Management (1 unified tool)
    # ========================================================================
    "optimize_mirrors": ToolMetadata(
        name="optimize_mirrors",
        category="mirrors",
        platform="arch",
        permission="read",
        workflow="optimize",
        related_tools=["analyze_pacman_conf", "check_disk_space"],
        prerequisite_tools=[]
    ),

    # ========================================================================
    # Configuration Management (2 tools)
    # ========================================================================
    "analyze_pacman_conf": ToolMetadata(
        name="analyze_pacman_conf",
        category="config",
        platform="arch",
        permission="read",
        workflow="explore",
        related_tools=["analyze_makepkg_conf", "optimize_mirrors"],
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
