# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
Tests for the HTTP transport's endpoints.

The /mcp, /sse and /messages handlers are raw ASGI: they write their reply
straight to ``send`` and return None. Routing them as ordinary function
endpoints made Starlette await that None and raise TypeError *after* the reply
was sent -- invisible to a client that opens one connection per request, fatal
to a keep-alive client on its second. Nothing exercised the endpoints, so it
went unnoticed. TestClient re-raises server-side exceptions, so a plain request
is enough to catch a regression.
"""

import pytest

pytest.importorskip("starlette", reason="HTTP transport requires the [http] extra")

from starlette.testclient import TestClient


@pytest.fixture
def app():
    from arch_ops_server.http_server import create_app

    return create_app()


class TestEndpointsAreReachable:
    def test_post_mcp_returns_a_response(self, app):
        with TestClient(app) as client:
            response = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            )

        assert response.status_code == 200
        assert response.json()["id"] == 1
        assert "result" in response.json()

    def test_repeated_requests_on_one_client_all_succeed(self, app):
        """The second request is the one that used to fail."""
        with TestClient(app) as client:
            for request_id in range(1, 4):
                response = client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "method": "initialize",
                        "params": {},
                    },
                )
                assert response.status_code == 200, f"request {request_id} failed"

    def test_route_methods_are_still_enforced(self, app):
        """
        Starlette defaults methods to ["GET"] only for function endpoints, so
        routing these as ASGI apps means every route must name its methods.
        """
        with TestClient(app) as client:
            assert client.put("/mcp").status_code == 405
            assert client.post("/sse").status_code == 405
            assert client.get("/messages").status_code == 405
