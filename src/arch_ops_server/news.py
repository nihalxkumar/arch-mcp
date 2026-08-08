# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
Arch Linux news feed integration module.
Fetches and parses Arch Linux news announcements for critical updates.
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from xml.etree import ElementTree as ET

import httpx

from .utils import (
    IS_ARCH,
    run_command,
    create_error_response,
)

logger = logging.getLogger(__name__)

# Arch Linux news RSS feed URL
ARCH_NEWS_URL = "https://archlinux.org/feeds/news/"

# Keywords indicating critical/manual intervention required
CRITICAL_KEYWORDS = [
    "manual intervention",
    "action required",
    "before upgrading",
    "breaking change",
    "manual action",
    "requires manual",
    "important notice"
]

# pacman has logged ISO-8601 timestamps since 5.2 (2019):
#   [2026-08-08T16:50:25+0200] [PACMAN] starting full system upgrade
# Capture the whole stamp and let fromisoformat read the offset rather than
# rebuilding the string, which is how the timezone used to be lost.
PACMAN_LOG_TIMESTAMP = re.compile(r"^\[([^\]]+)\]")

# Only a full system upgrade marks the boundary the user actually crossed.
# " installed "/" upgraded " would let a single-package install shrink the
# window and hide announcements.
FULL_UPGRADE_MARKER = "starting full system upgrade"


async def get_latest_news(
    limit: int = 10,
    since_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Fetch recent Arch Linux news from RSS feed.

    Args:
        limit: Maximum number of news items to return (default 10)
        since_date: Optional date in ISO format (YYYY-MM-DD) to filter news

    Returns:
        Dict with news items (title, date, summary, link)
    """
    logger.info(f"Fetching latest Arch Linux news (limit={limit})")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(ARCH_NEWS_URL)
            response.raise_for_status()

            # Parse RSS feed
            root = ET.fromstring(response.content)

            # Find all items (RSS 2.0 format)
            news_items = []
            
            for item in root.findall('.//item')[:limit]:
                title_elem = item.find('title')
                link_elem = item.find('link')
                pub_date_elem = item.find('pubDate')
                description_elem = item.find('description')

                if title_elem is None or link_elem is None:
                    continue

                title = title_elem.text
                link = link_elem.text
                pub_date = pub_date_elem.text if pub_date_elem is not None else ""
                
                # Parse description and strip HTML tags
                description = ""
                if description_elem is not None and description_elem.text:
                    description = re.sub(r'<[^>]+>', '', description_elem.text)
                    # Truncate to first 300 chars for summary
                    description = description[:300] + "..." if len(description) > 300 else description

                # Parse date
                published_date = ""
                if pub_date:
                    try:
                        # Parse RFC 822 date format
                        dt = datetime.strptime(pub_date, "%a, %d %b %Y %H:%M:%S %z")
                        published_date = dt.isoformat()
                    except ValueError:
                        published_date = pub_date

                # Filter by date if requested
                if since_date and published_date:
                    try:
                        item_date = datetime.fromisoformat(published_date.replace('Z', '+00:00'))
                        filter_date = datetime.fromisoformat(since_date + "T00:00:00+00:00")
                        if item_date < filter_date:
                            continue
                    except ValueError as e:
                        logger.warning(f"Failed to parse date for filtering: {e}")

                news_items.append({
                    "title": title,
                    "link": link,
                    "published": published_date,
                    "summary": description.strip()
                })

            logger.info(f"Successfully fetched {len(news_items)} news items")

            return {
                "count": len(news_items),
                "news": news_items
            }

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching news: {e}")
        return create_error_response(
            "HTTPError",
            f"Failed to fetch Arch news: HTTP {e.response.status_code}"
        )
    except httpx.TimeoutException:
        logger.error("Timeout fetching Arch news")
        return create_error_response(
            "Timeout",
            "Request to Arch news feed timed out"
        )
    except ET.ParseError as e:
        logger.error(f"Failed to parse RSS feed: {e}")
        return create_error_response(
            "ParseError",
            f"Failed to parse Arch news RSS feed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error fetching news: {e}")
        return create_error_response(
            "NewsError",
            f"Failed to fetch Arch news: {str(e)}"
        )


async def check_critical_news(limit: int = 20) -> Dict[str, Any]:
    """
    Check for critical Arch Linux news requiring manual intervention.

    Args:
        limit: Number of recent news items to check (default 20)

    Returns:
        Dict with critical news items
    """
    logger.info("Checking for critical Arch Linux news")

    result = await get_latest_news(limit=limit)

    if "error" in result:
        return result

    news_items = result.get("news", [])
    critical_items = []

    # Scan for critical keywords
    for item in news_items:
        title_lower = item["title"].lower()
        summary_lower = item["summary"].lower()

        # Check if any critical keyword is in title or summary
        is_critical = any(
            keyword in title_lower or keyword in summary_lower
            for keyword in CRITICAL_KEYWORDS
        )

        if is_critical:
            # Identify which keywords matched
            matched_keywords = [
                keyword for keyword in CRITICAL_KEYWORDS
                if keyword in title_lower or keyword in summary_lower
            ]

            critical_items.append({
                **item,
                "matched_keywords": matched_keywords,
                "severity": "critical"
            })

    logger.info(f"Found {len(critical_items)} critical news items")

    return {
        "critical_count": len(critical_items),
        "has_critical": len(critical_items) > 0,
        "critical_news": critical_items,
        "checked_items": len(news_items)
    }


def _parse_last_full_upgrade(pacman_log: Path) -> Optional[datetime]:
    """
    Find the timestamp of the last full system upgrade in a pacman log.

    Args:
        pacman_log: Path to the log to read

    Returns:
        Timezone-aware timestamp of the last full upgrade, or None if the log
        records none
    """
    last_update = None

    with open(pacman_log, 'r') as f:
        for line in f:
            if FULL_UPGRADE_MARKER not in line:
                continue

            match = PACMAN_LOG_TIMESTAMP.match(line)
            if not match:
                continue

            try:
                stamp = datetime.fromisoformat(match.group(1))
            except ValueError:
                continue

            # Pre-5.2 log lines parse naive; treat them as local time so the
            # comparison against timezone-aware feed dates is well defined.
            last_update = stamp if stamp.tzinfo else stamp.astimezone()

    return last_update


async def get_news_since_last_update() -> Dict[str, Any]:
    """
    Get news posted since last pacman update.
    Parses /var/log/pacman.log for last update timestamp.

    Returns:
        Dict with news items posted after last update. When the log records no
        full system upgrade, every recent item is returned with
        boundary_known set to False rather than an error: over-reporting costs
        the user a moment's reading, under-reporting defeats the check.
    """
    if not IS_ARCH:
        return create_error_response(
            "NotSupported",
            "This feature is only available on Arch Linux"
        )

    logger.info("Getting news since last pacman update")

    pacman_log = Path("/var/log/pacman.log")

    if not pacman_log.exists():
        return create_error_response(
            "NotFound",
            "Pacman log file not found at /var/log/pacman.log"
        )

    try:
        last_update = _parse_last_full_upgrade(pacman_log)
    except OSError as e:
        logger.error(f"Failed to read {pacman_log}: {e}")
        return create_error_response(
            "ReadError",
            f"Could not read {pacman_log}: {e}"
        )

    # Fetch recent news
    result = await get_latest_news(limit=30)

    if "error" in result:
        return result

    news_items = result.get("news", [])

    if last_update is None:
        logger.warning(f"No full system upgrade recorded in {pacman_log}")
        return {
            "last_update": None,
            "boundary_known": False,
            "note": (
                "No full system upgrade found in /var/log/pacman.log; the log "
                "may be rotated. Reporting all recent news rather than filtering."
            ),
            "news_count": len(news_items),
            "has_news": bool(news_items),
            "news": news_items
        }

    logger.info(f"Last update: {last_update.isoformat()}")

    news_since_update = []

    for item in news_items:
        published_str = item.get("published", "")
        if not published_str:
            continue

        try:
            published = datetime.fromisoformat(published_str.replace('Z', '+00:00'))
        except ValueError as e:
            logger.warning(f"Failed to parse date: {e}")
            continue

        # get_latest_news falls back to the raw pubDate when it cannot parse
        # one, so a naive date can reach here; compare like with like.
        if published.tzinfo is None:
            published = published.astimezone()

        if published > last_update:
            news_since_update.append(item)

    logger.info(f"Found {len(news_since_update)} news items since last update")

    return {
        "last_update": last_update.isoformat(),
        "boundary_known": True,
        "news_count": len(news_since_update),
        "has_news": len(news_since_update) > 0,
        "news": news_since_update
    }


async def fetch_news(
    action: str,
    limit: int = 10,
    since_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Unified news fetching tool.
    
    Args:
        action: "latest", "critical", or "since_update"
        limit: Maximum number of news items
        since_date: ISO date string for filtering (for latest action)
    
    Returns:
        News results based on action
    """
    if action == "latest":
        return await get_latest_news(limit=limit, since_date=since_date)
    elif action == "critical":
        return await check_critical_news(limit=limit)
    elif action == "since_update":
        return await get_news_since_last_update()
    else:
        return create_error_response(
            "InvalidAction",
            f"Unknown action: {action}. Use 'latest', 'critical', or 'since_update'"
        )


__all__ = [
    "get_latest_news",
    "check_critical_news",
    "get_news_since_last_update",
    "fetch_news",
]

