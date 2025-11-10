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


async def get_news_since_last_update() -> Dict[str, Any]:
    """
    Get news posted since last pacman update.
    Parses /var/log/pacman.log for last update timestamp.

    Returns:
        Dict with news items posted after last update
    """
    if not IS_ARCH:
        return create_error_response(
            "NotSupported",
            "This feature is only available on Arch Linux"
        )

    logger.info("Getting news since last pacman update")

    try:
        # Parse pacman log for last update timestamp
        pacman_log = Path("/var/log/pacman.log")

        if not pacman_log.exists():
            return create_error_response(
                "NotFound",
                "Pacman log file not found at /var/log/pacman.log"
            )

        # Find last system update timestamp
        last_update = None

        with open(pacman_log, 'r') as f:
            for line in f:
                # Look for upgrade entries
                if " upgraded " in line or " installed " in line or "starting full system upgrade" in line:
                    # Extract timestamp [YYYY-MM-DD HH:MM]
                    match = re.match(r'\[(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\]', line)
                    if match:
                        date_str = f"{match.group(1)}T{match.group(2)}:00+00:00"
                        try:
                            last_update = datetime.fromisoformat(date_str)
                        except ValueError:
                            continue

        if last_update is None:
            logger.warning("Could not determine last update timestamp")
            return create_error_response(
                "NotFound",
                "Could not determine last system update timestamp from pacman log"
            )

        logger.info(f"Last update: {last_update.isoformat()}")

        # Fetch recent news
        result = await get_latest_news(limit=30)

        if "error" in result:
            return result

        news_items = result.get("news", [])
        news_since_update = []

        for item in news_items:
            published_str = item.get("published", "")
            if not published_str:
                continue

            try:
                published = datetime.fromisoformat(published_str.replace('Z', '+00:00'))
                if published > last_update:
                    news_since_update.append(item)
            except ValueError as e:
                logger.warning(f"Failed to parse date: {e}")
                continue

        logger.info(f"Found {len(news_since_update)} news items since last update")

        return {
            "last_update": last_update.isoformat(),
            "news_count": len(news_since_update),
            "has_news": len(news_since_update) > 0,
            "news": news_since_update
        }

    except Exception as e:
        logger.error(f"Failed to get news since update: {e}")
        return create_error_response(
            "NewsError",
            f"Failed to get news since last update: {str(e)}"
        )

