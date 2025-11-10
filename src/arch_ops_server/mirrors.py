# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
Mirror management module.
Manages and optimizes pacman mirrors for better download performance.
"""

import logging
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

import httpx

from .utils import (
    IS_ARCH,
    create_error_response,
)

logger = logging.getLogger(__name__)

# Mirror list path
MIRRORLIST_PATH = "/etc/pacman.d/mirrorlist"

# Arch Linux mirror status JSON
MIRROR_STATUS_URL = "https://archlinux.org/mirrors/status/json/"


async def list_active_mirrors() -> Dict[str, Any]:
    """
    List currently configured mirrors from mirrorlist.

    Returns:
        Dict with active and commented mirrors
    """
    if not IS_ARCH:
        return create_error_response(
            "NotSupported",
            "This feature is only available on Arch Linux"
        )

    logger.info("Reading mirrorlist configuration")

    try:
        mirrorlist = Path(MIRRORLIST_PATH)

        if not mirrorlist.exists():
            return create_error_response(
                "NotFound",
                f"Mirrorlist not found at {MIRRORLIST_PATH}"
            )

        active_mirrors = []
        commented_mirrors = []

        with open(mirrorlist, 'r') as f:
            for line in f:
                line = line.strip()

                # Skip empty lines and comments that aren't mirrors
                if not line or (line.startswith('#') and 'Server' not in line):
                    continue

                # Check if it's a commented mirror
                if line.startswith('#'):
                    # Extract mirror URL
                    match = re.search(r'Server\s*=\s*(.+)', line)
                    if match:
                        commented_mirrors.append({
                            "url": match.group(1).strip(),
                            "active": False
                        })
                elif line.startswith('Server'):
                    # Active mirror
                    match = re.search(r'Server\s*=\s*(.+)', line)
                    if match:
                        active_mirrors.append({
                            "url": match.group(1).strip(),
                            "active": True
                        })

        logger.info(f"Found {len(active_mirrors)} active, {len(commented_mirrors)} commented mirrors")

        return {
            "active_count": len(active_mirrors),
            "commented_count": len(commented_mirrors),
            "active_mirrors": active_mirrors,
            "commented_mirrors": commented_mirrors,
            "mirrorlist_path": str(mirrorlist)
        }

    except Exception as e:
        logger.error(f"Failed to read mirrorlist: {e}")
        return create_error_response(
            "MirrorlistError",
            f"Failed to read mirrorlist: {str(e)}"
        )


async def test_mirror_speed(mirror_url: Optional[str] = None) -> Dict[str, Any]:
    """
    Test mirror response time.

    Args:
        mirror_url: Specific mirror URL to test, or None to test all active mirrors

    Returns:
        Dict with mirror latency results
    """
    if not IS_ARCH:
        return create_error_response(
            "NotSupported",
            "This feature is only available on Arch Linux"
        )

    logger.info(f"Testing mirror speed: {mirror_url or 'all active'}")

    try:
        mirrors_to_test = []

        if mirror_url:
            mirrors_to_test = [mirror_url]
        else:
            # Get active mirrors
            result = await list_active_mirrors()
            if "error" in result:
                return result

            mirrors_to_test = [m["url"] for m in result.get("active_mirrors", [])]

        if not mirrors_to_test:
            return create_error_response(
                "NoMirrors",
                "No mirrors to test"
            )

        results = []

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            for mirror in mirrors_to_test:
                # Replace $repo and $arch with actual values for testing
                test_url = mirror.replace("$repo", "core").replace("$arch", "x86_64")
                
                # Add a test file path (core.db is small and always present)
                if not test_url.endswith('/'):
                    test_url += '/'
                test_url += "core.db"

                try:
                    start_time = time.time()
                    response = await client.head(test_url)
                    latency = (time.time() - start_time) * 1000  # Convert to ms

                    results.append({
                        "mirror": mirror,
                        "latency_ms": round(latency, 2),
                        "status_code": response.status_code,
                        "success": response.status_code == 200
                    })

                except httpx.TimeoutException:
                    results.append({
                        "mirror": mirror,
                        "latency_ms": -1,
                        "status_code": 0,
                        "success": False,
                        "error": "timeout"
                    })

                except Exception as e:
                    results.append({
                        "mirror": mirror,
                        "latency_ms": -1,
                        "status_code": 0,
                        "success": False,
                        "error": str(e)
                    })

        # Sort by latency (successful tests first)
        results.sort(key=lambda x: (not x["success"], x["latency_ms"] if x["latency_ms"] > 0 else float('inf')))

        logger.info(f"Tested {len(results)} mirrors")

        return {
            "tested_count": len(results),
            "results": results,
            "fastest": results[0] if results and results[0]["success"] else None
        }

    except Exception as e:
        logger.error(f"Failed to test mirrors: {e}")
        return create_error_response(
            "MirrorTestError",
            f"Failed to test mirror speed: {str(e)}"
        )


async def suggest_fastest_mirrors(
    country: Optional[str] = None,
    limit: int = 10
) -> Dict[str, Any]:
    """
    Suggest optimal mirrors based on official mirror status.

    Args:
        country: Optional country code to filter mirrors (e.g., 'US', 'DE')
        limit: Number of mirrors to suggest (default 10)

    Returns:
        Dict with recommended mirrors
    """
    logger.info(f"Fetching mirror suggestions (country={country}, limit={limit})")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(MIRROR_STATUS_URL)
            response.raise_for_status()

            data = response.json()
            mirrors = data.get("urls", [])

            if not mirrors:
                return create_error_response(
                    "NoData",
                    "No mirror data available from archlinux.org"
                )

            # Filter mirrors
            filtered_mirrors = []

            for mirror in mirrors:
                # Skip if country specified and doesn't match
                if country and mirror.get("country_code") != country.upper():
                    continue

                # Skip if not active or has issues
                if not mirror.get("active", False):
                    continue

                # Skip if last sync is too old (more than 24 hours)
                last_sync = mirror.get("last_sync")
                if last_sync is None:
                    continue

                # Calculate score (lower is better)
                # Factors: completion percentage, delay, duration
                completion = mirror.get("completion_pct", 0)
                delay = mirror.get("delay", 0) or 0  # Handle None
                duration_avg = mirror.get("duration_avg", 0) or 0

                # Skip incomplete mirrors
                if completion < 100:
                    continue

                # Score: delay (hours) + duration (seconds converted to hours equivalent)
                score = delay + (duration_avg / 3600)

                filtered_mirrors.append({
                    "url": mirror.get("url"),
                    "country": mirror.get("country"),
                    "country_code": mirror.get("country_code"),
                    "protocol": mirror.get("protocol"),
                    "completion_pct": completion,
                    "delay_hours": delay,
                    "duration_avg": duration_avg,
                    "duration_stddev": mirror.get("duration_stddev"),
                    "score": round(score, 2),
                    "last_sync": last_sync
                })

            # Sort by score (lower is better)
            filtered_mirrors.sort(key=lambda x: x["score"])

            # Limit results
            suggested_mirrors = filtered_mirrors[:limit]

            logger.info(f"Suggesting {len(suggested_mirrors)} mirrors")

            return {
                "suggested_count": len(suggested_mirrors),
                "total_available": len(filtered_mirrors),
                "country_filter": country,
                "mirrors": suggested_mirrors
            }

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching mirror status: {e}")
        return create_error_response(
            "HTTPError",
            f"Failed to fetch mirror status: HTTP {e.response.status_code}"
        )
    except httpx.TimeoutException:
        logger.error("Timeout fetching mirror status")
        return create_error_response(
            "Timeout",
            "Request to mirror status API timed out"
        )
    except Exception as e:
        logger.error(f"Failed to suggest mirrors: {e}")
        return create_error_response(
            "MirrorSuggestionError",
            f"Failed to suggest mirrors: {str(e)}"
        )


async def check_mirrorlist_health() -> Dict[str, Any]:
    """
    Verify mirror configuration health.
    Checks for common issues like no active mirrors, outdated mirrorlist.

    Returns:
        Dict with health assessment and recommendations
    """
    if not IS_ARCH:
        return create_error_response(
            "NotSupported",
            "This feature is only available on Arch Linux"
        )

    logger.info("Checking mirrorlist health")

    try:
        issues = []
        warnings = []
        recommendations = []

        # Get active mirrors
        result = await list_active_mirrors()
        if "error" in result:
            return result

        active_mirrors = result.get("active_mirrors", [])
        
        # Check: No active mirrors
        if len(active_mirrors) == 0:
            issues.append("No active mirrors configured")
            recommendations.append("Uncomment mirrors in /etc/pacman.d/mirrorlist or use reflector to generate a new mirrorlist")

        # Check: Only one active mirror (no redundancy)
        elif len(active_mirrors) == 1:
            warnings.append("Only one active mirror (no redundancy)")
            recommendations.append("Enable additional mirrors for redundancy")

        # Check: Too many active mirrors (can slow down updates)
        elif len(active_mirrors) > 10:
            warnings.append(f"Many active mirrors ({len(active_mirrors)}) may slow down updates")
            recommendations.append("Consider reducing to 3-5 fastest mirrors")

        # Test mirrors
        test_result = await test_mirror_speed()
        if "error" not in test_result:
            test_results = test_result.get("results", [])
            
            # Check: All mirrors failing
            successful_mirrors = [r for r in test_results if r.get("success", False)]
            
            if len(successful_mirrors) == 0:
                issues.append("All mirrors are unreachable or failing")
                recommendations.append("Check network connectivity and consider updating mirrorlist")
            
            # Check: High latency
            elif successful_mirrors:
                avg_latency = sum(m["latency_ms"] for m in successful_mirrors) / len(successful_mirrors)
                if avg_latency > 1000:
                    warnings.append(f"High average mirror latency ({avg_latency:.0f}ms)")
                    recommendations.append("Consider using geographically closer mirrors")

        # Health score
        health_score = 100
        health_score -= len(issues) * 40
        health_score -= len(warnings) * 15
        health_score = max(0, health_score)

        health_status = "healthy"
        if health_score < 50:
            health_status = "critical"
        elif health_score < 70:
            health_status = "warning"

        logger.info(f"Mirror health: {health_status} (score: {health_score})")

        return {
            "health_status": health_status,
            "health_score": health_score,
            "issues": issues,
            "warnings": warnings,
            "recommendations": recommendations,
            "active_mirrors_count": len(active_mirrors)
        }

    except Exception as e:
        logger.error(f"Failed to check mirror health: {e}")
        return create_error_response(
            "HealthCheckError",
            f"Failed to check mirrorlist health: {str(e)}"
        )

