# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
Configuration file parsing module.
Parses and analyzes pacman and makepkg configuration files.
"""

import logging
import re
from pathlib import Path
from typing import Dict, Any, List, Optional

from .utils import (
    IS_ARCH,
    create_error_response,
)

logger = logging.getLogger(__name__)

# Configuration file paths
PACMAN_CONF = "/etc/pacman.conf"
MAKEPKG_CONF = "/etc/makepkg.conf"


def parse_config_file(file_path: str) -> Dict[str, Any]:
    """
    Parse a configuration file with INI-like format.

    Args:
        file_path: Path to configuration file

    Returns:
        Dict with parsed configuration data
    """
    config = {
        "options": {},
        "repositories": [],
        "comments": []
    }

    current_section = None

    try:
        with open(file_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                original_line = line
                line = line.strip()

                # Skip empty lines
                if not line:
                    continue

                # Store comments
                if line.startswith('#'):
                    config["comments"].append({
                        "line": line_num,
                        "text": line
                    })
                    continue

                # Section headers [SectionName]
                section_match = re.match(r'\[(\w+)\]', line)
                if section_match:
                    current_section = section_match.group(1)
                    
                    # If it's a repository section
                    if current_section not in ["options", "Options"]:
                        config["repositories"].append({
                            "name": current_section,
                            "line": line_num
                        })
                    continue

                # Key = Value pairs
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()

                    if current_section and current_section.lower() == "options":
                        config["options"][key] = value
                    elif current_section:
                        # Add to repository config
                        for repo in config["repositories"]:
                            if repo["name"] == current_section:
                                if "config" not in repo:
                                    repo["config"] = {}
                                repo["config"][key] = value

    except Exception as e:
        logger.error(f"Failed to parse config file {file_path}: {e}")

    return config


async def analyze_pacman_conf(focus: str = "full") -> Dict[str, Any]:
    """
    Parse and analyze pacman.conf.

    Args:
        focus: What to analyze - "full" (all settings), "ignored_packages" (only ignored),
               "parallel_downloads" (only parallel downloads setting)

    Returns:
        Dict with parsed pacman configuration (filtered by focus)
    """
    if not IS_ARCH:
        return create_error_response(
            "NotSupported",
            "This feature is only available on Arch Linux"
        )

    logger.info("Analyzing pacman.conf")

    try:
        pacman_conf = Path(PACMAN_CONF)

        if not pacman_conf.exists():
            return create_error_response(
                "NotFound",
                f"pacman.conf not found at {PACMAN_CONF}"
            )

        config = parse_config_file(PACMAN_CONF)

        # Extract specific important options
        options = config.get("options", {})
        
        # Parse multi-value options
        ignored_packages = []
        ignored_groups = []
        
        for key, value in options.items():
            if key == "IgnorePkg":
                ignored_packages = [p.strip() for p in value.split()]
            elif key == "IgnoreGroup":
                ignored_groups = [g.strip() for g in value.split()]

        # Parse ParallelDownloads
        parallel_downloads = options.get("ParallelDownloads", "1")
        try:
            parallel_downloads = int(parallel_downloads)
        except ValueError:
            parallel_downloads = 1

        # Extract repository list
        repositories = [repo["name"] for repo in config.get("repositories", [])]

        # Check for security settings
        sig_level = options.get("SigLevel", "")
        local_file_sig_level = options.get("LocalFileSigLevel", "")

        logger.info(f"Parsed pacman.conf: {len(repositories)} repos, {parallel_downloads} parallel downloads, focus={focus}")

        # Build full result
        full_result = {
            "config_path": str(pacman_conf),
            "repositories": repositories,
            "repository_count": len(repositories),
            "parallel_downloads": parallel_downloads,
            "ignored_packages": ignored_packages,
            "ignored_groups": ignored_groups,
            "sig_level": sig_level,
            "local_file_sig_level": local_file_sig_level,
            "all_options": options,
            "raw_config": config
        }

        # Filter result based on focus
        if focus == "ignored_packages":
            critical_packages = ["linux", "systemd", "pacman", "glibc"]
            critical_ignored = [pkg for pkg in ignored_packages if pkg in critical_packages]
            warnings = []
            if critical_ignored:
                warnings.append(f"Critical system packages are ignored: {', '.join(critical_ignored)}")
            
            return {
                "focus": "ignored_packages",
                "ignored_packages": ignored_packages,
                "ignored_packages_count": len(ignored_packages),
                "ignored_groups": ignored_groups,
                "ignored_groups_count": len(ignored_groups),
                "critical_ignored": critical_ignored,
                "warnings": warnings,
                "has_ignored": len(ignored_packages) > 0 or len(ignored_groups) > 0
            }
        
        elif focus == "parallel_downloads":
            recommendations = []
            if parallel_downloads == 1:
                recommendations.append("Consider increasing ParallelDownloads to 3-5 for faster updates")
            elif parallel_downloads > 10:
                recommendations.append("Very high ParallelDownloads may strain mirrors; consider reducing to 5-7")
            
            return {
                "focus": "parallel_downloads",
                "parallel_downloads": parallel_downloads,
                "is_default": parallel_downloads == 1,
                "recommendations": recommendations
            }
        
        else:  # focus == "full" or any other value
            return full_result

    except Exception as e:
        logger.error(f"Failed to analyze pacman.conf: {e}")
        return create_error_response(
            "ConfigParseError",
            f"Failed to analyze pacman.conf: {str(e)}"
        )


async def analyze_makepkg_conf() -> Dict[str, Any]:
    """
    Parse and analyze makepkg.conf.

    Returns:
        Dict with parsed makepkg configuration
    """
    if not IS_ARCH:
        return create_error_response(
            "NotSupported",
            "This feature is only available on Arch Linux"
        )

    logger.info("Analyzing makepkg.conf")

    try:
        makepkg_conf = Path(MAKEPKG_CONF)

        if not makepkg_conf.exists():
            return create_error_response(
                "NotFound",
                f"makepkg.conf not found at {MAKEPKG_CONF}"
            )

        config = {}

        # Parse as shell script variables
        with open(makepkg_conf, 'r') as f:
            for line in f:
                line = line.strip()

                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue

                # Match VAR=value or VAR="value"
                match = re.match(r'^([A-Z_]+)=(.+)$', line)
                if match:
                    key = match.group(1)
                    value = match.group(2)
                    
                    # Remove quotes
                    value = value.strip('"').strip("'")
                    
                    config[key] = value

        # Extract important settings
        cflags = config.get("CFLAGS", "")
        cxxflags = config.get("CXXFLAGS", "")
        makeflags = config.get("MAKEFLAGS", "")
        buildenv = config.get("BUILDENV", "")
        options = config.get("OPTIONS", "")
        
        # Parse MAKEFLAGS for job count
        jobs = 1
        jobs_match = re.search(r'-j\s*(\d+)', makeflags)
        if jobs_match:
            jobs = int(jobs_match.group(1))

        # Parse BUILDENV
        buildenv_list = [opt.strip() for opt in buildenv.split()] if buildenv else []
        
        # Parse OPTIONS
        options_list = [opt.strip() for opt in options.split()] if options else []

        # Detect architecture
        carch = config.get("CARCH", "unknown")

        # Compression settings
        pkgext = config.get("PKGEXT", ".pkg.tar.zst")

        logger.info(f"Parsed makepkg.conf: {jobs} jobs, {carch} arch")

        return {
            "config_path": str(makepkg_conf),
            "cflags": cflags,
            "cxxflags": cxxflags,
            "makeflags": makeflags,
            "jobs": jobs,
            "buildenv": buildenv_list,
            "options": options_list,
            "carch": carch,
            "pkgext": pkgext,
            "all_config": config
        }

    except Exception as e:
        logger.error(f"Failed to analyze makepkg.conf: {e}")
        return create_error_response(
            "ConfigParseError",
            f"Failed to analyze makepkg.conf: {str(e)}"
        )


async def check_ignored_packages() -> Dict[str, Any]:
    """
    List packages ignored in updates.

    Returns:
        Dict with ignored packages and groups
    """
    if not IS_ARCH:
        return create_error_response(
            "NotSupported",
            "This feature is only available on Arch Linux"
        )

    logger.info("Checking ignored packages")

    try:
        result = await analyze_pacman_conf()

        if "error" in result:
            return result

        ignored_packages = result.get("ignored_packages", [])
        ignored_groups = result.get("ignored_groups", [])

        # Warnings for critical packages
        critical_packages = ["linux", "systemd", "pacman", "glibc"]
        critical_ignored = [pkg for pkg in ignored_packages if pkg in critical_packages]

        warnings = []
        if critical_ignored:
            warnings.append(f"Critical system packages are ignored: {', '.join(critical_ignored)}")

        logger.info(f"Found {len(ignored_packages)} ignored packages, {len(ignored_groups)} ignored groups")

        return {
            "ignored_packages": ignored_packages,
            "ignored_packages_count": len(ignored_packages),
            "ignored_groups": ignored_groups,
            "ignored_groups_count": len(ignored_groups),
            "critical_ignored": critical_ignored,
            "warnings": warnings,
            "has_ignored": len(ignored_packages) > 0 or len(ignored_groups) > 0
        }

    except Exception as e:
        logger.error(f"Failed to check ignored packages: {e}")
        return create_error_response(
            "ConfigCheckError",
            f"Failed to check ignored packages: {str(e)}"
        )


async def get_parallel_downloads_setting() -> Dict[str, Any]:
    """
    Get parallel downloads configuration.

    Returns:
        Dict with parallel downloads setting and recommendations
    """
    if not IS_ARCH:
        return create_error_response(
            "NotSupported",
            "This feature is only available on Arch Linux"
        )

    logger.info("Checking parallel downloads setting")

    try:
        result = await analyze_pacman_conf()

        if "error" in result:
            return result

        parallel_downloads = result.get("parallel_downloads", 1)

        # Recommendations
        recommendations = []
        if parallel_downloads == 1:
            recommendations.append("Consider increasing ParallelDownloads to 3-5 for faster updates")
        elif parallel_downloads > 10:
            recommendations.append("Very high ParallelDownloads may strain mirrors; consider reducing to 5-7")

        logger.info(f"Parallel downloads: {parallel_downloads}")

        return {
            "parallel_downloads": parallel_downloads,
            "is_default": parallel_downloads == 1,
            "recommendations": recommendations
        }

    except Exception as e:
        logger.error(f"Failed to check parallel downloads: {e}")
        return create_error_response(
            "ConfigCheckError",
            f"Failed to check parallel downloads setting: {str(e)}"
        )

