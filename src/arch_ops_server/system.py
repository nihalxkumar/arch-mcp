# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
System diagnostics and information module.
Provides system health checks, disk space monitoring, and service status.
"""

import logging
import os
import re
from pathlib import Path
from typing import Dict, Any, List

from .utils import (
    IS_ARCH,
    run_command,
    create_error_response,
    check_command_exists
)

logger = logging.getLogger(__name__)


async def get_system_info() -> Dict[str, Any]:
    """
    Get core system information.

    Returns:
        Dict with kernel, architecture, hostname, uptime, memory info
    """
    logger.info("Gathering system information")

    info = {}

    try:
        # Kernel version
        exit_code, stdout, _ = await run_command(["uname", "-r"], timeout=5, check=False)
        if exit_code == 0:
            info["kernel"] = stdout.strip()

        # Architecture
        exit_code, stdout, _ = await run_command(["uname", "-m"], timeout=5, check=False)
        if exit_code == 0:
            info["architecture"] = stdout.strip()

        # Hostname
        exit_code, stdout, _ = await run_command(["hostname"], timeout=5, check=False)
        if exit_code == 0:
            info["hostname"] = stdout.strip()

        # Uptime
        exit_code, stdout, _ = await run_command(["uptime", "-p"], timeout=5, check=False)
        if exit_code == 0:
            info["uptime"] = stdout.strip()

        # Memory info from /proc/meminfo
        try:
            meminfo_path = Path("/proc/meminfo")
            if meminfo_path.exists():
                with open(meminfo_path, "r") as f:
                    meminfo = f.read()

                # Parse memory values
                mem_total_match = re.search(r"MemTotal:\s+(\d+)", meminfo)
                mem_available_match = re.search(r"MemAvailable:\s+(\d+)", meminfo)

                if mem_total_match:
                    info["memory_total_kb"] = int(mem_total_match.group(1))
                    info["memory_total_mb"] = int(mem_total_match.group(1)) // 1024

                if mem_available_match:
                    info["memory_available_kb"] = int(mem_available_match.group(1))
                    info["memory_available_mb"] = int(mem_available_match.group(1)) // 1024
        except Exception as e:
            logger.warning(f"Failed to read memory info: {e}")

        info["is_arch_linux"] = IS_ARCH

        logger.info("Successfully gathered system information")
        return info

    except Exception as e:
        logger.error(f"Failed to gather system info: {e}")
        return create_error_response(
            "SystemInfoError",
            f"Failed to gather system information: {str(e)}"
        )


async def check_disk_space() -> Dict[str, Any]:
    """
    Check disk space for critical paths.

    Returns:
        Dict with disk usage for /, /home, /var, /var/cache/pacman/pkg
    """
    logger.info("Checking disk space")

    paths_to_check = ["/", "/home", "/var"]

    if IS_ARCH:
        paths_to_check.append("/var/cache/pacman/pkg")

    disk_info = {}

    try:
        for path in paths_to_check:
            if not Path(path).exists():
                continue

            exit_code, stdout, _ = await run_command(
                ["df", "-h", path],
                timeout=5,
                check=False
            )

            if exit_code == 0:
                lines = stdout.strip().split('\n')
                if len(lines) >= 2:
                    # Parse df output
                    parts = lines[1].split()
                    if len(parts) >= 5:
                        disk_info[path] = {
                            "size": parts[1],
                            "used": parts[2],
                            "available": parts[3],
                            "use_percent": parts[4],
                            "mounted_on": parts[5] if len(parts) > 5 else path
                        }

                        # Check if space is critically low
                        use_pct = int(parts[4].rstrip('%'))
                        if use_pct > 90:
                            disk_info[path]["warning"] = "Critical: Less than 10% free"
                        elif use_pct > 80:
                            disk_info[path]["warning"] = "Low: Less than 20% free"

        logger.info(f"Checked disk space for {len(disk_info)} paths")

        return {
            "disk_usage": disk_info,
            "paths_checked": len(disk_info)
        }

    except Exception as e:
        logger.error(f"Failed to check disk space: {e}")
        return create_error_response(
            "DiskCheckError",
            f"Failed to check disk space: {str(e)}"
        )


async def get_pacman_cache_stats() -> Dict[str, Any]:
    """
    Analyze pacman package cache.

    Returns:
        Dict with cache size, package count, statistics
    """
    if not IS_ARCH:
        return create_error_response(
            "NotSupported",
            "Pacman cache analysis is only available on Arch Linux"
        )

    logger.info("Analyzing pacman cache")

    cache_dir = Path("/var/cache/pacman/pkg")

    try:
        if not cache_dir.exists():
            return create_error_response(
                "NotFound",
                "Pacman cache directory not found"
            )

        # Count packages
        pkg_files = list(cache_dir.glob("*.pkg.tar.*"))
        pkg_count = len(pkg_files)

        # Calculate total size
        total_size = sum(f.stat().st_size for f in pkg_files)
        total_size_mb = total_size / (1024 * 1024)
        total_size_gb = total_size_mb / 1024

        logger.info(f"Cache: {pkg_count} packages, {total_size_gb:.2f} GB")

        return {
            "cache_dir": str(cache_dir),
            "package_count": pkg_count,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size_mb, 2),
            "total_size_gb": round(total_size_gb, 2)
        }

    except Exception as e:
        logger.error(f"Failed to analyze cache: {e}")
        return create_error_response(
            "CacheAnalysisError",
            f"Failed to analyze pacman cache: {str(e)}"
        )


async def check_failed_services() -> Dict[str, Any]:
    """
    Detect failed systemd services.

    Returns:
        Dict with list of failed services
    """
    if not check_command_exists("systemctl"):
        return create_error_response(
            "NotSupported",
            "systemctl not available (systemd-based system required)"
        )

    logger.info("Checking for failed services")

    try:
        exit_code, stdout, _ = await run_command(
            ["systemctl", "--failed", "--no-pager"],
            timeout=10,
            check=False
        )

        # Parse output
        failed_services = []
        lines = stdout.strip().split('\n')

        for line in lines:
            # Skip header and footer lines
            if line.startswith('●') or line.startswith('UNIT'):
                continue
            if 'loaded units listed' in line.lower():
                continue

            # Parse service line
            parts = line.split()
            if parts and parts[0].endswith('.service'):
                failed_services.append({
                    "unit": parts[0],
                    "load": parts[1] if len(parts) > 1 else "",
                    "active": parts[2] if len(parts) > 2 else "",
                    "sub": parts[3] if len(parts) > 3 else "",
                })

        logger.info(f"Found {len(failed_services)} failed services")

        return {
            "failed_count": len(failed_services),
            "failed_services": failed_services,
            "all_ok": len(failed_services) == 0
        }

    except Exception as e:
        logger.error(f"Failed to check services: {e}")
        return create_error_response(
            "ServiceCheckError",
            f"Failed to check failed services: {str(e)}"
        )


async def get_boot_logs(lines: int = 100) -> Dict[str, Any]:
    """
    Retrieve recent boot logs.

    Args:
        lines: Number of lines to retrieve

    Returns:
        Dict with boot log contents
    """
    if not check_command_exists("journalctl"):
        return create_error_response(
            "NotSupported",
            "journalctl not available (systemd-based system required)"
        )

    logger.info(f"Retrieving {lines} lines of boot logs")

    try:
        exit_code, stdout, stderr = await run_command(
            ["journalctl", "-b", "-n", str(lines), "--no-pager"],
            timeout=15,
            check=False
        )

        if exit_code != 0:
            return create_error_response(
                "CommandError",
                f"Failed to retrieve boot logs: {stderr}"
            )

        log_lines = stdout.strip().split('\n')

        logger.info(f"Retrieved {len(log_lines)} lines of boot logs")

        return {
            "line_count": len(log_lines),
            "logs": log_lines
        }

    except Exception as e:
        logger.error(f"Failed to get boot logs: {e}")
        return create_error_response(
            "LogRetrievalError",
            f"Failed to retrieve boot logs: {str(e)}"
        )
