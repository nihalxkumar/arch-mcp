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


async def _handle_direct_mcp_request(request_data: dict) -> dict:
    """
    Handle MCP request directly without SSE session.
    
    This is used when Smithery POSTs directly without establishing SSE connection.
    Creates a temporary in-memory connection to process the request.
    
    Args:
        request_data: JSON-RPC request data
        
    Returns:
        JSON-RPC response data
    """
    import json
    from mcp.server import Server
    from mcp.server.sse import SseServerTransport
    
    # Create in-memory streams to simulate SSE connection
    class InMemoryStream:
        def __init__(self):
            self.buffer = []
            self.closed = False
        
        async def read(self):
            if self.buffer:
                return self.buffer.pop(0)
            return None
        
        async def write(self, data):
            self.buffer.append(data)
        
        async def close(self):
            self.closed = True
    
    try:
        # Create temporary streams
        read_stream = InMemoryStream()
        write_stream = InMemoryStream()
        
        # Write the request to the read stream
        await read_stream.write(json.dumps(request_data).encode("utf-8"))
        
        # Process the request through the server
        # We need to run the server's request handler
        # The server expects to handle requests through its internal handlers
        # Let's use the server's handle_request method if available
        
        # Actually, we need to properly integrate with the server
        # For now, let's create a minimal handler that processes initialize requests
        method = request_data.get("method", "")
        params = request_data.get("params", {})
        request_id = request_data.get("id")
        
        if method == "initialize":
            # Handle initialize request
            # Return a basic initialize response matching MCP protocol
            result = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                    "capabilities": {
                        "tools": {},
                        "resources": {},
                        "prompts": {},
                    },
                    "serverInfo": {
                        "name": "arch-ops-server",
                        "version": "3.0.0"
                    }
                }
            }
            return result
        else:
            # For other methods, we'd need to properly route through the server
            # This is a simplified implementation
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32601,
                    "message": f"Method '{method}' not supported in direct HTTP mode. Please use SSE connection."
                },
                "id": request_id
            }
    except Exception as e:
        logger.error(f"Error handling direct MCP request: {e}", exc_info=True)
        return {
            "jsonrpc": "2.0",
            "error": {
                "code": -32603,
                "message": f"Internal error: {str(e)}"
            },
            "id": request_data.get("id")
        }

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
        # The SSE transport might check the path, so we ensure compatibility
        logger.info("GET /mcp - Establishing SSE connection")
        # For GET, the path doesn't matter for connect_sse, but we keep original
        await handle_sse_raw(scope, receive, send)
    elif method == "POST":
        # POST /mcp sends messages
        # Check if session_id exists in query string
        query_string = scope.get("query_string", b"").decode("utf-8")
        has_session_id = "session_id" in query_string
        
        if not has_session_id:
            # Smithery POSTs directly without establishing SSE connection first
            # Handle as regular HTTP request-response (non-SSE)
            logger.info("POST /mcp without session_id - handling as regular HTTP request")
            try:
                # Read request body
                body = b""
                more_body = True
                while more_body:
                    message = await receive()
                    if message["type"] == "http.request":
                        body += message.get("body", b"")
                        more_body = message.get("more_body", False)
                
                # Parse JSON-RPC request
                import json
                request_data = json.loads(body.decode("utf-8"))
                
                # Process the request through the MCP server
                # Create a temporary session-like handler
                from io import BytesIO
                import sys
                
                # Use SSE transport but create a session on-the-fly
                # Actually, we need to handle this differently - create a one-off connection
                logger.info(f"Processing MCP request: {request_data.get('method', 'unknown')}")
                
                # For now, try to establish SSE connection and handle the message
                # Create a modified scope that will establish SSE connection
                modified_scope = dict(scope)
                modified_scope["path"] = "/messages"
                # Add a dummy session_id to make SSE transport happy
                modified_scope["query_string"] = b"session_id=temp"
                
                # Actually, this won't work. Let's try a different approach:
                # Handle it as a direct HTTP request-response
                # We'll need to manually process the MCP message
                response = await _handle_direct_mcp_request(request_data)
                
                await send({
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [[b"content-type", b"application/json"]],
                })
                await send({
                    "type": "http.response.body",
                    "body": json.dumps(response).encode("utf-8"),
                })
                return
            except Exception as e:
                logger.error(f"Error handling direct POST request: {e}", exc_info=True)
                await send({
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [[b"content-type", b"application/json"]],
                })
                await send({
                    "type": "http.response.body",
                    "body": json.dumps({
                        "jsonrpc": "2.0",
                        "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
                        "id": request_data.get("id") if 'request_data' in locals() else None
                    }).encode("utf-8"),
                })
                return
        
        # The SSE transport expects /messages path, so we modify the scope
        logger.info("POST /mcp - Handling message with session_id")
        # Create a modified scope with /messages path for SSE transport compatibility
        modified_scope = dict(scope)
        modified_scope["path"] = "/messages"
        # Preserve query string (includes session_id)
        modified_scope["query_string"] = scope.get("query_string", b"")
        await handle_messages_raw(modified_scope, receive, send)
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
