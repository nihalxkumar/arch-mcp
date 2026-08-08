#!/usr/bin/env python3
"""
Manual smoke test for a *running* MCP HTTP server.

This is not part of the pytest suite: it needs a live server and reaches the
network. The automated coverage of this transport lives in
tests/test_http_server.py.

Usage:

    arch-ops-server-http &
    python scripts/smoke_http_server.py

Set ARCH_MCP_URL to point elsewhere, and ARCH_MCP_AUTH_TOKEN to match the
token the server was started with.
"""
import asyncio
import os
import httpx
import json


async def run_smoke_test():
    """Exercise the MCP HTTP endpoint end to end against a running server."""
    base_url = os.getenv("ARCH_MCP_URL", "http://127.0.0.1:8080").rstrip("/")

    # The server rejects unauthenticated requests whenever a token is configured.
    token = os.getenv("ARCH_MCP_AUTH_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    print("Testing MCP HTTP Server...")
    print(f"Connecting to {base_url}")
    print(f"Authentication: {'bearer token' if token else 'none configured'}")

    async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
        # Test 1: Direct HTTP - Initialize
        print("\n1. Testing direct HTTP initialize...")
        try:
            response = await client.post(
                f"{base_url}/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "clientInfo": {"name": "test-client", "version": "1.0.0"}
                    }
                }
            )
            if response.status_code == 200:
                result = response.json()
                print(f"   ✓ Initialize response: {json.dumps(result, indent=2)}")
            elif response.status_code == 401:
                print("   ✗ Status: 401 unauthorized")
                print("   The server was started with ARCH_MCP_AUTH_TOKEN set.")
                print("   Export the same value here and retry.")
                return False
            else:
                print(f"   ✗ Status: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
        except Exception as e:
            print(f"   ✗ Error: {e}")
            return False

        # Test 2: Direct HTTP - List tools
        print("\n2. Testing direct HTTP tools/list...")
        try:
            response = await client.post(
                f"{base_url}/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {}
                }
            )
            if response.status_code == 200:
                result = response.json()
                tools_count = len(result.get("result", {}).get("tools", []))
                print(f"   ✓ Listed {tools_count} tools")
                if tools_count > 0:
                    print(f"   First tool: {result['result']['tools'][0]['name']}")
            else:
                print(f"   ✗ Status: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
        except Exception as e:
            print(f"   ✗ Error: {e}")
            return False

        # Test 3: Direct HTTP - Call a tool (search_archwiki)
        print("\n3. Testing direct HTTP tools/call...")
        try:
            response = await client.post(
                f"{base_url}/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "search_archwiki",
                        "arguments": {
                            "query": "installation",
                            "limit": 3
                        }
                    }
                }
            )
            if response.status_code == 200:
                result = response.json()
                if "error" in result:
                    print(f"   ✗ Error: {result['error']}")
                    return False
                else:
                    content = result.get("result", {}).get("content", [])
                    print(f"   ✓ Tool executed successfully")
                    print(f"   Response content length: {len(str(content))}")
            else:
                print(f"   ✗ Status: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
        except Exception as e:
            print(f"   ✗ Error: {e}")
            return False

        # Test 4: Direct HTTP - List resources
        print("\n4. Testing direct HTTP resources/list...")
        try:
            response = await client.post(
                f"{base_url}/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "resources/list",
                    "params": {}
                }
            )
            if response.status_code == 200:
                result = response.json()
                if "error" in result:
                    print(f"   ✗ Error: {result['error']}")
                    print(f"   Error details: {json.dumps(result['error'], indent=2)}")
                    return False
                else:
                    resources_count = len(result.get("result", {}).get("resources", []))
                    print(f"   ✓ Listed {resources_count} resources")
                    if resources_count > 0:
                        print(f"   First resource: {result['result']['resources'][0]['uri']}")
            else:
                print(f"   ✗ Status: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
        except Exception as e:
            print(f"   ✗ Error: {e}")
            import traceback
            traceback.print_exc()
            return False

        # Test 5: Direct HTTP - List prompts
        print("\n5. Testing direct HTTP prompts/list...")
        try:
            response = await client.post(
                f"{base_url}/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "prompts/list",
                    "params": {}
                }
            )
            if response.status_code == 200:
                result = response.json()
                if "error" in result:
                    print(f"   ✗ Error: {result['error']}")
                    print(f"   Error details: {json.dumps(result['error'], indent=2)}")
                    return False
                else:
                    prompts_count = len(result.get("result", {}).get("prompts", []))
                    print(f"   ✓ Listed {prompts_count} prompts")
                    if prompts_count > 0:
                        print(f"   First prompt: {result['result']['prompts'][0]['name']}")
            else:
                print(f"   ✗ Status: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
        except Exception as e:
            print(f"   ✗ Error: {e}")
            import traceback
            traceback.print_exc()
            return False

        # Test 6: Direct HTTP - Read resource
        print("\n6. Testing direct HTTP resources/read...")
        try:
            response = await client.post(
                f"{base_url}/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "resources/read",
                    "params": {
                        "uri": "archwiki://Installation_guide"
                    }
                }
            )
            if response.status_code == 200:
                result = response.json()
                if "error" in result:
                    print(f"   ✗ Error: {result['error']}")
                    return False
                else:
                    contents = result.get("result", {}).get("contents", [])
                    print(f"   ✓ Resource read successfully")
                    if contents:
                        print(f"   Content length: {len(contents[0].get('text', ''))}")
            else:
                print(f"   ✗ Status: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
        except Exception as e:
            print(f"   ✗ Error: {e}")
            return False

    print("\n✓ HTTP server is working correctly!")
    print("✓ Direct HTTP mode fully functional (no SSE required)")
    print("\nThe server is ready for Smithery deployment.")
    return True


if __name__ == "__main__":
    success = asyncio.run(run_smoke_test())
    exit(0 if success else 1)
