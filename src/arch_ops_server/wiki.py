# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
Arch Wiki interface module.
Provides search and page retrieval via MediaWiki API with BeautifulSoup fallback.
"""

import logging
from typing import List, Dict, Any, Optional
import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify as md

from .utils import create_error_response

logger = logging.getLogger(__name__)

# Arch Wiki API endpoint
WIKI_API_URL = "https://wiki.archlinux.org/api.php"
WIKI_BASE_URL = "https://wiki.archlinux.org"

# HTTP client settings
DEFAULT_TIMEOUT = 10.0


async def search_wiki(query: str, limit: int = 10) -> Dict[str, Any]:
    """
    Search the Arch Wiki using MediaWiki API.
    
    Uses the opensearch action which returns suggestions.
    
    Args:
        query: Search term
        limit: Maximum number of results (default: 10)
    
    Returns:
        Dict containing search results with titles, snippets, and URLs
    """
    logger.info(f"Searching Arch Wiki for: {query}")
    
    params = {
        "action": "opensearch",
        "search": query,
        "limit": limit,
        "namespace": "0",  # Main namespace only
        "format": "json"
    }
    
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(WIKI_API_URL, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # OpenSearch returns: [query, [titles], [descriptions], [urls]]
            if len(data) >= 4:
                titles = data[1]
                descriptions = data[2]
                urls = data[3]
                
                results = [
                    {
                        "title": title,
                        "snippet": desc,
                        "url": url
                    }
                    for title, desc, url in zip(titles, descriptions, urls)
                ]
                
                logger.info(f"Found {len(results)} results for '{query}'")
                
                return {
                    "query": query,
                    "count": len(results),
                    "results": results
                }
            else:
                return {
                    "query": query,
                    "count": 0,
                    "results": []
                }
                
    except httpx.TimeoutException:
        logger.error(f"Wiki search timed out for query: {query}")
        return create_error_response(
            "TimeoutError",
            f"Arch Wiki search timed out for query: {query}",
            "The Wiki server did not respond in time. Try again later."
        )
    except httpx.HTTPStatusError as e:
        logger.error(f"Wiki search HTTP error: {e}")
        return create_error_response(
            "HTTPError",
            f"Wiki search failed with status {e.response.status_code}",
            str(e)
        )
    except Exception as e:
        logger.error(f"Wiki search failed: {e}")
        return create_error_response(
            "SearchError",
            f"Failed to search Arch Wiki: {str(e)}"
        )


async def get_wiki_page(title: str, as_markdown: bool = True) -> str:
    """
    Fetch a Wiki page using MediaWiki API, with scraping fallback.
    
    Args:
        title: Page title (e.g., "Installation_guide")
        as_markdown: Convert HTML to Markdown (default: True)
    
    Returns:
        Page content as Markdown or HTML string
    """
    logger.info(f"Fetching Wiki page: {title}")
    
    # Try MediaWiki API first
    content = await _fetch_via_api(title)
    
    # Fallback to scraping if API fails
    if content is None:
        logger.warning(f"API fetch failed for {title}, falling back to scraping")
        content = await _fetch_via_scraping(title)
    
    if content is None:
        error_msg = f"Page '{title}' not found or could not be retrieved"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    # Convert to Markdown if requested
    if as_markdown and content:
        try:
            content = md(content, heading_style="ATX", strip=['script', 'style'])
        except Exception as e:
            logger.warning(f"Markdown conversion failed: {e}, returning HTML")
    
    return content


async def _fetch_via_api(title: str) -> Optional[str]:
    """
    Fetch page content via MediaWiki API.
    
    Args:
        title: Page title
    
    Returns:
        HTML content or None if failed
    """
    params = {
        "action": "parse",
        "page": title,
        "format": "json",
        "prop": "text",
        "disableeditsection": "1",
        "disabletoc": "1"
    }
    
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(WIKI_API_URL, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # Check for errors in response
            if "error" in data:
                logger.warning(f"API error: {data['error'].get('info', 'Unknown error')}")
                return None
            
            # Extract HTML content
            if "parse" in data and "text" in data["parse"]:
                html_content = data["parse"]["text"]["*"]
                logger.info(f"Successfully fetched {title} via API")
                return html_content
            
            return None
            
    except Exception as e:
        logger.warning(f"API fetch failed for {title}: {e}")
        return None


async def _fetch_via_scraping(title: str) -> Optional[str]:
    """
    Fetch page content via direct HTTP scraping (fallback).
    
    Args:
        title: Page title
    
    Returns:
        HTML content or None if failed
    """
    # Construct URL
    url = f"{WIKI_BASE_URL}/title/{title}"
    
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'lxml')
            
            # Find main content div
            content_div = soup.find('div', {'id': 'bodyContent'})
            
            if content_div:
                # Remove unnecessary elements
                for element in content_div.find_all(['script', 'style', 'nav']):
                    element.decompose()
                
                logger.info(f"Successfully scraped {title}")
                return str(content_div)
            
            return None
            
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.error(f"Page not found: {title}")
        else:
            logger.error(f"HTTP error scraping {title}: {e}")
        return None
    except Exception as e:
        logger.error(f"Scraping failed for {title}: {e}")
        return None


async def get_wiki_page_as_text(title: str) -> str:
    """
    Convenience wrapper to get Wiki page as clean Markdown text.
    
    Args:
        title: Page title
    
    Returns:
        Markdown content
    
    Raises:
        ValueError: If page cannot be retrieved
    """
    return await get_wiki_page(title, as_markdown=True)

