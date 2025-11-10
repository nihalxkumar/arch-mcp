# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
Tests for arch_ops_server.wiki module.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from arch_ops_server.wiki import (
    WIKI_API_URL,
    WIKI_BASE_URL,
    _fetch_via_api,
    _fetch_via_scraping,
    get_wiki_page,
    get_wiki_page_as_text,
    search_wiki,
)


class TestWikiSearch:
    """Test Arch Wiki search functionality."""

    @pytest.mark.asyncio
    async def test_search_wiki_success(self, mock_httpx_response):
        """Test successful Wiki search."""
        # Mock opensearch API response format
        mock_response = mock_httpx_response(
            status_code=200,
            json_data=[
                "installation",  # Query
                ["Installation guide", "Install"],  # Titles
                ["Guide for installing Arch Linux", "Installation process"],  # Descriptions
                [
                    "https://wiki.archlinux.org/title/Installation_guide",
                    "https://wiki.archlinux.org/title/Install",
                ],  # URLs
            ],
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await search_wiki("installation", limit=10)

            assert result["query"] == "installation"
            assert result["count"] == 2
            assert len(result["results"]) == 2
            assert result["results"][0]["title"] == "Installation guide"
            assert "wiki.archlinux.org" in result["results"][0]["url"]

    @pytest.mark.asyncio
    async def test_search_wiki_no_results(self, mock_httpx_response):
        """Test Wiki search with no results."""
        mock_response = mock_httpx_response(
            status_code=200,
            json_data=["nonexistent", [], [], []],  # Empty results
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await search_wiki("nonexistent")

            assert result["query"] == "nonexistent"
            assert result["count"] == 0
            assert result["results"] == []

    @pytest.mark.asyncio
    async def test_search_wiki_timeout(self):
        """Test Wiki search timeout handling."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.TimeoutException("Request timed out")
            )

            result = await search_wiki("test")

            assert result["error"] is True
            assert result["type"] == "TimeoutError"
            assert "timed out" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_search_wiki_http_error(self, mock_httpx_response):
        """Test Wiki search HTTP error handling."""
        mock_response = mock_httpx_response(status_code=500)

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(return_value=mock_response)
            mock_get.side_effect = httpx.HTTPStatusError(
                "Server error", request=MagicMock(), response=mock_response
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            result = await search_wiki("test")

            assert result["error"] is True
            assert result["type"] == "HTTPError"

    @pytest.mark.asyncio
    async def test_search_wiki_general_exception(self):
        """Test Wiki search general exception handling."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=Exception("Network error")
            )

            result = await search_wiki("test")

            assert result["error"] is True
            assert result["type"] == "SearchError"


class TestFetchViaAPI:
    """Test Wiki page fetching via MediaWiki API."""

    @pytest.mark.asyncio
    async def test_fetch_via_api_success(self, mock_httpx_response):
        """Test successful API fetch."""
        mock_response = mock_httpx_response(
            status_code=200,
            json_data={
                "parse": {
                    "title": "Installation guide",
                    "text": {"*": "<div>Installation guide content</div>"},
                }
            },
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await _fetch_via_api("Installation_guide")

            assert result is not None
            assert "<div>Installation guide content</div>" in result

    @pytest.mark.asyncio
    async def test_fetch_via_api_error_response(self, mock_httpx_response):
        """Test API fetch with error in response."""
        mock_response = mock_httpx_response(
            status_code=200,
            json_data={"error": {"code": "missingtitle", "info": "Page doesn't exist"}},
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await _fetch_via_api("NonexistentPage")

            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_via_api_malformed_response(self, mock_httpx_response):
        """Test API fetch with malformed response."""
        mock_response = mock_httpx_response(
            status_code=200, json_data={"unexpected": "format"}
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await _fetch_via_api("SomePage")

            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_via_api_exception(self):
        """Test API fetch exception handling."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=Exception("Connection error")
            )

            result = await _fetch_via_api("SomePage")

            assert result is None


class TestFetchViaScraping:
    """Test Wiki page fetching via web scraping."""

    @pytest.mark.asyncio
    async def test_fetch_via_scraping_success(self, mock_httpx_response):
        """Test successful scraping."""
        html_content = """
        <html>
            <body>
                <div id="bodyContent">
                    <h1>Installation guide</h1>
                    <p>This is the content</p>
                    <script>alert('remove me');</script>
                </div>
            </body>
        </html>
        """

        mock_response = mock_httpx_response(status_code=200, text_data=html_content)

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await _fetch_via_scraping("Installation_guide")

            assert result is not None
            assert "bodyContent" in result
            assert "Installation guide" in result
            # Scripts should be removed
            assert "alert('remove me')" not in result

    @pytest.mark.asyncio
    async def test_fetch_via_scraping_404(self, mock_httpx_response):
        """Test scraping with 404 error."""
        mock_response = mock_httpx_response(status_code=404)

        with patch("httpx.AsyncClient") as mock_client:
            mock_get = AsyncMock(return_value=mock_response)
            mock_get.side_effect = httpx.HTTPStatusError(
                "Not found", request=MagicMock(), response=mock_response
            )
            mock_client.return_value.__aenter__.return_value.get = mock_get

            result = await _fetch_via_scraping("NonexistentPage")

            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_via_scraping_no_content_div(self, mock_httpx_response):
        """Test scraping when bodyContent div is missing."""
        html_content = "<html><body><p>No content div here</p></body></html>"

        mock_response = mock_httpx_response(status_code=200, text_data=html_content)

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await _fetch_via_scraping("SomePage")

            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_via_scraping_exception(self):
        """Test scraping exception handling."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=Exception("Network error")
            )

            result = await _fetch_via_scraping("SomePage")

            assert result is None


class TestGetWikiPage:
    """Test complete Wiki page retrieval."""

    @pytest.mark.asyncio
    async def test_get_wiki_page_via_api(self, mock_httpx_response):
        """Test page retrieval via API (primary method)."""
        mock_response = mock_httpx_response(
            status_code=200,
            json_data={
                "parse": {
                    "title": "Test",
                    "text": {"*": "<h1>Test</h1><p>Content</p>"},
                }
            },
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await get_wiki_page("Test", as_markdown=True)

            assert result is not None
            # Should be converted to markdown
            assert "Test" in result
            assert "Content" in result

    @pytest.mark.asyncio
    async def test_get_wiki_page_fallback_to_scraping(self, mock_httpx_response):
        """Test fallback to scraping when API fails."""
        html_content = '<div id="bodyContent"><h1>Test</h1></div>'

        # API returns error, scraping succeeds
        api_response = mock_httpx_response(
            status_code=200, json_data={"error": {"info": "Page not found"}}
        )

        scraping_response = mock_httpx_response(status_code=200, text_data=html_content)

        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # First call is API, second is scraping
            return api_response if call_count == 1 else scraping_response

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=mock_get
            )

            result = await get_wiki_page("Test")

            assert result is not None
            assert "Test" in result

    @pytest.mark.asyncio
    async def test_get_wiki_page_not_found(self):
        """Test page not found raises ValueError."""
        with patch("httpx.AsyncClient") as mock_client:
            # Both API and scraping fail
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=Exception("Not found")
            )

            with pytest.raises(ValueError, match="not found or could not be retrieved"):
                await get_wiki_page("NonexistentPage")

    @pytest.mark.asyncio
    async def test_get_wiki_page_as_html(self, mock_httpx_response):
        """Test page retrieval without markdown conversion."""
        mock_response = mock_httpx_response(
            status_code=200,
            json_data={"parse": {"title": "Test", "text": {"*": "<h1>HTML</h1>"}}},
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await get_wiki_page("Test", as_markdown=False)

            assert "<h1>HTML</h1>" in result

    @pytest.mark.asyncio
    async def test_get_wiki_page_markdown_conversion_error(self, mock_httpx_response):
        """Test markdown conversion error handling."""
        mock_response = mock_httpx_response(
            status_code=200,
            json_data={"parse": {"title": "Test", "text": {"*": "<h1>Test</h1>"}}},
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            # Mock markdown conversion to fail
            with patch("arch_ops_server.wiki.md", side_effect=Exception("MD error")):
                result = await get_wiki_page("Test", as_markdown=True)

                # Should return HTML when markdown conversion fails
                assert result is not None
                assert "<h1>Test</h1>" in result


class TestGetWikiPageAsText:
    """Test convenience wrapper function."""

    @pytest.mark.asyncio
    async def test_get_wiki_page_as_text(self, mock_httpx_response):
        """Test get_wiki_page_as_text wrapper."""
        mock_response = mock_httpx_response(
            status_code=200,
            json_data={
                "parse": {"title": "Test", "text": {"*": "<p>Content</p>"}}
            },
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await get_wiki_page_as_text("Test")

            assert result is not None
            assert "Content" in result
