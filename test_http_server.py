#!/usr/bin/env python3
"""
Simple test script to verify MCP HTTP server functionality.
"""
import asyncio
import httpx
import json


async def test_http_server():
    """Test the MCP HTTP server by connecting and listing tools."""
    base_url = "http://localhost:8080"

    print("Testing MCP HTTP Server...")
    print(f"Connecting to {base_url}")

    async with httpx.AsyncClient(timeout=10.0) as client:
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

        # Test 4: Direct HTTP - Read resource
        print("\n4. Testing direct HTTP resources/read...")
        try:
            response = await client.post(
                f"{base_url}/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 4,
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
    success = asyncio.run(test_http_server())
    exit(0 if success else 1)
