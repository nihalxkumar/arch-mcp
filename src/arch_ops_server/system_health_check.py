# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
System health check module.
Provides a comprehensive system health check by integrating multiple system diagnostics.
"""

import logging
from typing import Dict, Any

from .utils import IS_ARCH
from . import (
    get_system_info,
    check_disk_space,
    check_failed_services,
    get_pacman_cache_stats,
    check_updates_dry_run,
    check_critical_news,
    list_orphan_packages,
    check_database_freshness,
    check_mirrorlist_health
)

logger = logging.getLogger(__name__)


async def run_system_health_check() -> Dict[str, Any]:
    """
    Run a comprehensive system health check.
    
    This function integrates multiple system diagnostics to provide a complete
    overview of the system's health status in a single call.
    
    Returns:
        Dict with comprehensive health check results
    """
    logger.info("Starting comprehensive system health check")
    
    health_report = {
        "status": "success",
        "system_info": {},
        "disk_space": {},
        "services": {},
        "pacman_cache": {},
        "updates": {},
        "news": {},
        "orphans": {},
        "database": {},
        "mirrors": {},
        "issues": [],
        "suggestions": []
    }
    
    try:
        # System information
        logger.info("Checking system information")
        system_info = await get_system_info()
        health_report["system_info"] = system_info
        
        # Disk space check
        logger.info("Checking disk space")
        disk_space = await check_disk_space()
        health_report["disk_space"] = disk_space
        
        # Check for low disk space
        if disk_space.get("status") == "success":
            for partition in disk_space.get("data", []):
                if partition.get("used_percent", 0) > 90:
                    health_report["issues"].append({
                        "type": "critical",
                        "message": f"Low disk space on {partition['mount_point']}: {partition['used_percent']}% used",
                        "suggestion": "Clean up unnecessary files or resize the partition"
                    })
                elif partition.get("used_percent", 0) > 80:
                    health_report["issues"].append({
                        "type": "warning",
                        "message": f"Disk space getting low on {partition['mount_point']}: {partition['used_percent']}% used",
                        "suggestion": "Consider cleaning up files to free up space"
                    })
        
        # Failed services check
        logger.info("Checking for failed services")
        failed_services = await check_failed_services()
        health_report["services"] = failed_services
        
        if failed_services.get("status") == "success" and failed_services.get("data"):
            health_report["issues"].append({
                "type": "warning",
                "message": f"{len(failed_services['data'])} failed systemd services detected",
                "suggestion": "Check systemd journal logs for details about failed services"
            })
        
        # Pacman cache statistics
        logger.info("Checking pacman cache")
        cache_stats = await get_pacman_cache_stats()
        health_report["pacman_cache"] = cache_stats
        
        if cache_stats.get("status") == "success":
            cache_size = cache_stats.get("data", {}).get("total_size_mb", 0)
            if cache_size > 5000:  # 5GB
                health_report["suggestions"].append({
                    "message": f"Pacman cache is large ({cache_size:.1f}MB)",
                    "action": "Run 'paccache -r' to clean old packages"
                })
        
        # Updates check
        logger.info("Checking for available updates")
        updates = await check_updates_dry_run()
        health_report["updates"] = updates
        
        if updates.get("status") == "success":
            if updates.get("updates_available"):
                count = updates.get("count", 0)
                health_report["suggestions"].append({
                    "message": f"{count} updates available",
                    "action": "Run 'sudo pacman -Syu' to update the system"
                })
        
        # Critical news check
        logger.info("Checking for critical news")
        critical_news = await check_critical_news()
        health_report["news"] = critical_news
        
        if critical_news.get("status") == "success" and critical_news.get("data"):
            health_report["issues"].append({
                "type": "critical",
                "message": f"{len(critical_news['data'])} critical news items require attention",
                "suggestion": "Review the news items before updating"
            })
        
        # Orphan packages check
        logger.info("Checking for orphan packages")
        orphans = await list_orphan_packages()
        health_report["orphans"] = orphans
        
        if orphans.get("status") == "success":
            orphan_count = len(orphans.get("data", []))
            if orphan_count > 0:
                health_report["suggestions"].append({
                    "message": f"{orphan_count} orphan packages detected",
                    "action": "Run 'sudo pacman -Rns $(pacman -Qtdq)' to remove orphans"
                })
        
        # Database freshness
        logger.info("Checking database freshness")
        db_freshness = await check_database_freshness()
        health_report["database"] = db_freshness
        
        # Mirrorlist health
        logger.info("Checking mirrorlist health")
        mirror_health = await check_mirrorlist_health()
        health_report["mirrors"] = mirror_health
        
        if mirror_health.get("status") == "success":
            if not mirror_health.get("data", {}).get("healthy", True):
                health_report["issues"].append({
                    "type": "warning",
                    "message": "Mirrorlist configuration has issues",
                    "suggestion": "Run 'reflector' to update your mirrorlist"
                })
        
        # Overall health assessment
        issue_count = len(health_report["issues"])
        suggestion_count = len(health_report["suggestions"])
        
        health_report["summary"] = {
            "total_issues": issue_count,
            "critical_issues": len([i for i in health_report["issues"] if i["type"] == "critical"]),
            "warnings": len([i for i in health_report["issues"] if i["type"] == "warning"]),
            "suggestions": suggestion_count
        }
        
        logger.info(f"Health check completed: {issue_count} issues, {suggestion_count} suggestions")
        
        return health_report
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "issues": [],
            "suggestions": [],
            "summary": {
                "total_issues": 1,
                "critical_issues": 1,
                "warnings": 0,
                "suggestions": 0
            }
        }
