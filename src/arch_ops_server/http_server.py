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
from . import __version__

logger = logging.getLogger(__name__)

# Import handlers - try to get them from server if direct import fails
try:
    from .server import list_tools, list_resources, list_prompts, call_tool, read_resource, get_prompt
    logger.info("Successfully imported all handlers")
except ImportError as e:
    logger.warning(f"Could not import handlers directly: {e}")
    # Fallback: we'll access them through server handlers if needed
    list_tools = None
    list_resources = None
    list_prompts = None
    call_tool = None
    read_resource = None
    get_prompt = None
except Exception as e:
    logger.error(f"Unexpected error importing handlers: {e}", exc_info=True)
    # Set to None to prevent crashes
    list_tools = None
    list_resources = None
    list_prompts = None
    call_tool = None
    read_resource = None
    get_prompt = None


async def _handle_direct_mcp_request(request_data: dict) -> dict:
    """
    Handle MCP request directly without SSE session.
    
    This is used when Smithery POSTs directly without establishing SSE connection.
    Processes requests using the server's registered handlers.
    
    Args:
        request_data: JSON-RPC request data
        
    Returns:
        JSON-RPC response data
    """
    import json
    
    try:
        method = request_data.get("method", "")
        params = request_data.get("params", {})
        request_id = request_data.get("id")
        
        if method == "initialize":
            # Handle initialize request - return proper capabilities
            # Indicate that we support tools, resources, and prompts
            result = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                    "capabilities": {
                        "tools": {
                            "listChanged": False
                        },
                        "resources": {
                            "subscribe": False,
                            "listChanged": False
                        },
                        "prompts": {
                            "listChanged": False
                        }
                    },
                    "serverInfo": {
                        "name": "arch-ops-server",
                        "version": __version__
                    }
                }
            }
            return result
        elif method == "tools/list":
            # Call the server's list_tools handler directly
            logger.info("Handling tools/list request")
            try:
                tools = await list_tools()
                logger.info(f"Got {len(tools)} tools")
                # Convert Tool objects to dicts
                tools_list = []
                for tool in tools:
                    tools_list.append({
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.inputSchema
                    })
                logger.info(f"Returning {len(tools_list)} tools")
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": tools_list
                    }
                }
            except Exception as e:
                logger.error(f"Error in tools/list: {e}", exc_info=True)
                return {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32603,
                        "message": f"Failed to list tools: {str(e)}"
                    },
                    "id": request_id
                }
        elif method == "resources/list":
            # Call the server's list_resources handler directly
            logger.info("Handling resources/list request")
            try:
                # Ensure we await the async function properly
                resources = await list_resources()
                logger.info(f"Got {len(resources)} resources")
                # Convert Resource objects to dicts
                resources_list = []
                for resource in resources:
                    try:
                        resources_list.append({
                            "uri": str(resource.uri),
                            "name": str(resource.name) if resource.name else "",
                            "mimeType": str(resource.mimeType) if resource.mimeType else "text/plain",
                            "description": str(resource.description) if resource.description else ""
                        })
                    except Exception as e:
                        logger.error(f"Error converting resource to dict: {e}", exc_info=True)
                        # Skip this resource but continue with others
                        continue
                logger.info(f"Returning {len(resources_list)} resources")
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "resources": resources_list
                    }
                }
            except Exception as e:
                logger.error(f"Error in resources/list: {e}", exc_info=True)
                import traceback
                logger.error(traceback.format_exc())
                return {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32603,
                        "message": f"Failed to list resources: {str(e)}"
                    },
                    "id": request_id
                }
        elif method == "prompts/list":
            # Call the server's list_prompts handler directly
            logger.info("Handling prompts/list request - starting")
            try:
                # Try to get the handler function
                if list_prompts is None:
                    # Fallback: try to get it from server's registered handlers
                    logger.warning("list_prompts not imported, trying to access via server")
                    # The server object should have the handler registered
                    # We can't easily access it, so return an error
                    return {
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32603,
                            "message": "list_prompts handler not available"
                        },
                        "id": request_id
                    }
                
                # Verify list_prompts is callable
                if not callable(list_prompts):
                    logger.error("list_prompts is not callable!")
                    return {
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32603,
                            "message": "list_prompts function is not callable"
                        },
                        "id": request_id
                    }
                
                # Log before calling the function
                logger.info("About to call list_prompts()")
                # Ensure we await the async function properly
                prompts = await list_prompts()
                logger.info(f"Got {len(prompts)} prompts from list_prompts()")
                # Convert Prompt objects to dicts
                prompts_list = []
                for idx, prompt in enumerate(prompts):
                    try:
                        logger.debug(f"Processing prompt {idx+1}/{len(prompts)}: {getattr(prompt, 'name', 'unknown')}")
                        # Safely extract prompt fields
                        prompt_dict = {
                            "name": str(prompt.name) if hasattr(prompt, 'name') and prompt.name else "",
                        }
                        
                        # Handle description (may be None)
                        if hasattr(prompt, 'description'):
                            prompt_dict["description"] = str(prompt.description) if prompt.description else ""
                        else:
                            prompt_dict["description"] = ""
                        
                        # Handle arguments (may be None or empty list)
                        if hasattr(prompt, 'arguments') and prompt.arguments:
                            # Ensure arguments is a list
                            if isinstance(prompt.arguments, list):
                                prompt_dict["arguments"] = prompt.arguments
                            else:
                                # Try to convert to list if it's not
                                prompt_dict["arguments"] = list(prompt.arguments) if prompt.arguments else []
                        else:
                            prompt_dict["arguments"] = []
                        
                        prompts_list.append(prompt_dict)
                        logger.debug(f"Added prompt: {prompt_dict['name']}")
                    except Exception as e:
                        logger.error(f"Error converting prompt {idx+1} to dict: {e}", exc_info=True)
                        import traceback
                        logger.error(traceback.format_exc())
                        # Skip this prompt but continue with others
                        continue
                
                logger.info(f"Returning {len(prompts_list)} prompts")
                result = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "prompts": prompts_list
                    }
                }
                logger.info("Successfully prepared prompts/list response")
                return result
            except Exception as e:
                logger.error(f"Error in prompts/list: {e}", exc_info=True)
                import traceback
                logger.error(traceback.format_exc())
                return {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32603,
                        "message": f"Failed to list prompts: {str(e)}"
                    },
                    "id": request_id
                }
        elif method == "tools/call":
            # Call tool execution
            logger.info(f"Direct HTTP tools/call: {params.get('name')}")
            tool_name = params.get("name", "")
            tool_arguments = params.get("arguments", {})
            
            try:
                # Execute the tool
                result_content = await call_tool(tool_name, tool_arguments)
                
                # Convert content objects to dicts
                content_list = []
                for content in result_content:
                    if hasattr(content, 'type') and content.type == "text":
                        content_list.append({
                            "type": "text",
                            "text": content.text
                        })
                    elif hasattr(content, 'type') and content.type == "image":
                        content_list.append({
                            "type": "image",
                            "data": content.data,
                            "mimeType": content.mimeType
                        })
                    elif hasattr(content, 'type') and content.type == "resource":
                        content_list.append({
                            "type": "resource",
                            "resource": {
                                "uri": content.resource.uri,
                                "mimeType": content.resource.mimeType,
                                "text": content.resource.text if hasattr(content.resource, 'text') else None,
                                "blob": content.resource.blob if hasattr(content.resource, 'blob') else None,
                            }
                        })
                
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": content_list
                    }
                }
            except ValueError as e:
                # Tool not found or invalid arguments
                logger.error(f"Tool error: {e}")
                return {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32602,
                        "message": str(e)
                    },
                    "id": request_id
                }
            except Exception as e:
                # Other errors during tool execution
                logger.error(f"Tool execution error: {e}", exc_info=True)
                return {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32603,
                        "message": f"Tool execution failed: {str(e)}"
                    },
                    "id": request_id
                }
        elif method == "resources/read":
            # Read resource
            logger.info(f"Direct HTTP resources/read: {params.get('uri')}")
            uri = params.get("uri", "")
            
            try:
                # Read the resource
                resource_content = await read_resource(uri)
                
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "text/plain",
                                "text": resource_content
                            }
                        ]
                    }
                }
            except ValueError as e:
                # Resource not found or invalid URI
                logger.error(f"Resource error: {e}")
                return {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32602,
                        "message": str(e)
                    },
                    "id": request_id
                }
            except Exception as e:
                # Other errors during resource read
                logger.error(f"Resource read error: {e}", exc_info=True)
                return {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32603,
                        "message": f"Resource read failed: {str(e)}"
                    },
                    "id": request_id
                }
        elif method == "prompts/get":
            # Get prompt
            logger.info(f"Direct HTTP prompts/get: {params.get('name')}")
            prompt_name = params.get("name", "")
            prompt_arguments = params.get("arguments", {})
            
            try:
                # Get the prompt
                prompt_result = await get_prompt(prompt_name, prompt_arguments)
                
                # Convert PromptMessage objects to dicts
                messages_list = []
                for message in prompt_result.messages:
                    msg_dict = {
                        "role": message.role,
                        "content": {
                            "type": "text",
                            "text": message.content.text
                        }
                    }
                    messages_list.append(msg_dict)
                
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "description": prompt_result.description,
                        "messages": messages_list
                    }
                }
            except ValueError as e:
                # Prompt not found or invalid arguments
                logger.error(f"Prompt error: {e}")
                return {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32602,
                        "message": str(e)
                    },
                    "id": request_id
                }
            except Exception as e:
                # Other errors during prompt generation
                logger.error(f"Prompt generation error: {e}", exc_info=True)
                return {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32603,
                        "message": f"Prompt generation failed: {str(e)}"
                    },
                    "id": request_id
                }
        else:
            # For other methods, return method not found
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
        import traceback
        logger.error(traceback.format_exc())
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
    
    # Wrap everything in a try-except to catch any unhandled exceptions
    try:
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
                request_data = None
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
                    logger.info(f"Processing MCP request: {request_data.get('method', 'unknown')}")
                    
                    # Handle it as a direct HTTP request-response
                    response = await _handle_direct_mcp_request(request_data)
                    
                    await send({
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [[b"content-type", b"application/json"], [b"access-control-allow-origin", b"*"]],
                    })
                    await send({
                        "type": "http.response.body",
                        "body": json.dumps(response).encode("utf-8"),
                    })
                    return
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}", exc_info=True)
                    import json
                    await send({
                        "type": "http.response.start",
                        "status": 400,
                        "headers": [[b"content-type", b"application/json"]],
                    })
                    await send({
                        "type": "http.response.body",
                        "body": json.dumps({
                            "jsonrpc": "2.0",
                            "error": {"code": -32700, "message": f"Parse error: {str(e)}"},
                            "id": None
                        }).encode("utf-8"),
                    })
                    return
                except Exception as e:
                    logger.error(f"Error handling direct POST request: {e}", exc_info=True)
                    import traceback
                    logger.error(traceback.format_exc())
                    import json
                    await send({
                        "type": "http.response.start",
                        "status": 500,
                        "headers": [[b"content-type", b"application/json"]],
                    })
                    error_response = {
                        "jsonrpc": "2.0",
                        "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
                        "id": request_data.get("id") if request_data else None
                    }
                    await send({
                        "type": "http.response.body",
                        "body": json.dumps(error_response).encode("utf-8"),
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
    except Exception as e:
        # Catch any unhandled exceptions at the top level
        logger.error(f"Unhandled exception in handle_mcp_raw: {e}", exc_info=True)
        import traceback
        logger.error(traceback.format_exc())
        import json
        try:
            await send({
                "type": "http.response.start",
                "status": 500,
                "headers": [[b"content-type", b"application/json"]],
            })
            await send({
                "type": "http.response.body",
                "body": json.dumps({
                    "jsonrpc": "2.0",
                    "error": {"code": -32603, "message": f"Internal server error: {str(e)}"},
                    "id": None
                }).encode("utf-8"),
            })
        except Exception as send_error:
            logger.error(f"Failed to send error response: {send_error}", exc_info=True)


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
