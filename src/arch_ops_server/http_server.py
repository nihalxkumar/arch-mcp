# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
HTTP Server for MCP using SSE (Server-Sent Events) transport.

This module provides HTTP transport support for Smithery and other
HTTP-based MCP clients, while keeping STDIO transport for Docker MCP Catalog.
"""

import asyncio
import logging
import os
from typing import Any

try:
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.responses import Response
    from starlette.requests import Request
    from starlette.middleware.cors import CORSMiddleware
    import uvicorn
    STARLETTE_AVAILABLE = True
except ImportError:
    STARLETTE_AVAILABLE = False

try:
    from mcp.server.sse import SseServerTransport
    SSE_AVAILABLE = True
except ImportError:
    SSE_AVAILABLE = False

from .server import server

logger = logging.getLogger(__name__)

# Initialize SSE transport at module level
sse: Any = None
if SSE_AVAILABLE:
    sse = SseServerTransport("/messages")


async def handle_sse_raw(scope: dict, receive: Any, send: Any) -> None:
    """
    Raw ASGI handler for Server-Sent Events (SSE) endpoint for MCP.

    This is the main MCP endpoint that Smithery will connect to.

    Args:
        scope: ASGI scope dictionary
        receive: ASGI receive callable
        send: ASGI send callable
    """
    if not SSE_AVAILABLE or sse is None:
        logger.error("SSE transport not available - MCP package needs SSE support")
        await send({
            "type": "http.response.start",
            "status": 500,
            "headers": [[b"content-type", b"text/plain"]],
        })
        await send({
            "type": "http.response.body",
            "body": b"SSE transport not available. Install mcp package with SSE support.",
        })
        return

    logger.info("New SSE connection established")

    try:
        async with sse.connect_sse(scope, receive, send) as streams:
            await server.run(
                streams[0],
                streams[1],
                server.create_initialization_options()
            )
    except Exception as e:
        logger.error(f"SSE connection error: {e}", exc_info=True)
        raise


async def handle_sse(request: Request) -> None:
    """
    Starlette request handler wrapper for SSE endpoint.

    Args:
        request: Starlette Request object
    """
    await handle_sse_raw(request.scope, request.receive, request._send)


async def handle_messages_raw(scope: dict, receive: Any, send: Any) -> None:
    """
    Raw ASGI handler for POST requests to /messages endpoint for SSE transport.

    Args:
        scope: ASGI scope dictionary
        receive: ASGI receive callable
        send: ASGI send callable
    """
    if not SSE_AVAILABLE or sse is None:
        await send({
            "type": "http.response.start",
            "status": 500,
            "headers": [[b"content-type", b"text/plain"]],
        })
        await send({
            "type": "http.response.body",
            "body": b"SSE transport not available.",
        })
        return

    try:
        await sse.handle_post_message(scope, receive, send)
    except Exception as e:
        logger.error(f"Message handling error: {e}", exc_info=True)
        await send({
            "type": "http.response.start",
            "status": 500,
            "headers": [[b"content-type", b"application/json"]],
        })
        await send({
            "type": "http.response.body",
            "body": f'{{"jsonrpc": "2.0", "error": {{"code": -32603, "message": "Internal error: {str(e)}"}}, "id": null}}'.encode(),
        })


async def handle_messages(request: Request) -> None:
    """
    Starlette request handler wrapper for messages endpoint.

    Args:
        request: Starlette Request object
    """
    await handle_messages_raw(request.scope, request.receive, request._send)


async def handle_mcp_raw(scope: dict, receive: Any, send: Any) -> None:
    """
    Raw ASGI handler for /mcp endpoint (Smithery requirement).
    
    Smithery expects a single /mcp endpoint that handles:
    - GET: Establish SSE connection (streamable HTTP)
    - POST: Send messages
    - DELETE: Close connection
    
    Args:
        scope: ASGI scope dictionary
        receive: ASGI receive callable
        send: ASGI send callable
    """
    method = scope.get("method", "")
    
    if method == "GET":
        # GET /mcp establishes SSE connection
        logger.info("GET /mcp - Establishing SSE connection")
        await handle_sse_raw(scope, receive, send)
    elif method == "POST":
        # POST /mcp sends messages
        logger.info("POST /mcp - Handling message")
        await handle_messages_raw(scope, receive, send)
    elif method == "DELETE":
        # DELETE /mcp closes connection
        logger.info("DELETE /mcp - Closing connection")
        # SSE connections are closed when the stream ends, so just return 200
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"text/plain"]],
        })
        await send({
            "type": "http.response.body",
            "body": b"Connection closed",
        })
    else:
        await send({
            "type": "http.response.start",
            "status": 405,
            "headers": [[b"content-type", b"text/plain"]],
        })
        await send({
            "type": "http.response.body",
            "body": f"Method {method} not allowed".encode(),
        })


async def handle_mcp(request: Request) -> None:
    """
    Starlette request handler wrapper for /mcp endpoint.
    
    Args:
        request: Starlette Request object
    """
    await handle_mcp_raw(request.scope, request.receive, request._send)


def create_app() -> Any:
    """
    Create Starlette application with MCP SSE endpoints.

    Returns:
        Starlette application instance

    Raises:
        ImportError: If starlette is not installed
    """
    if not STARLETTE_AVAILABLE:
        raise ImportError(
            "Starlette and uvicorn are required for HTTP transport. "
            "Install with: pip install 'arch-ops-server[http]'"
        )

    if not SSE_AVAILABLE or sse is None:
        raise ImportError(
            "MCP SSE transport not available. Install mcp package with SSE support."
        )

    # Create routes
    # - /mcp: Required by Smithery (handles GET/POST/DELETE for streamable HTTP)
    # - /sse and /messages: Alternative endpoints for other clients
    routes = [
        Route("/mcp", endpoint=handle_mcp, methods=["GET", "POST", "DELETE"]),
        Route("/sse", endpoint=handle_sse),
        Route("/messages", endpoint=handle_messages, methods=["POST"]),
    ]

    # Create app
    app = Starlette(debug=False, routes=routes)

    # Add CORS middleware for browser-based clients
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS", "DELETE"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    logger.info("MCP HTTP Server initialized with SSE transport")
    logger.info("Endpoints: GET/POST/DELETE /mcp (Smithery), GET /sse, POST /messages")

    return app


async def run_http_server(host: str = "0.0.0.0", port: int = 8080) -> None:
    """
    Run MCP server with HTTP transport.

    Args:
        host: Host to bind to (default: 0.0.0.0)
        port: Port to listen on (default: 8080, or PORT env var)
    """
    if not STARLETTE_AVAILABLE:
        logger.error("HTTP transport requires starlette and uvicorn packages")
        logger.error("Install with: pip install starlette uvicorn")
        raise ImportError("starlette not available")

    # Get port from environment if specified (Smithery sets this)
    port = int(os.getenv("PORT", port))

    logger.info(f"Starting Arch Linux MCP HTTP Server on {host}:{port}")
    logger.info("Transport: Server-Sent Events (SSE)")
    logger.info("Endpoints: GET/POST/DELETE /mcp (Smithery), GET /sse, POST /messages")

    # Create app
    app = create_app()

    # Configure uvicorn
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="info",
        access_log=True,
    )

    # Run server
    server_instance = uvicorn.Server(config)
    await server_instance.serve()


def main_http():
    """Synchronous wrapper for HTTP server."""
    asyncio.run(run_http_server())


if __name__ == "__main__":
    main_http()
