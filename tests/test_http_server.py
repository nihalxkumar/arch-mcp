# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
Tests for the HTTP transport's network surface.

The tools behind this endpoint can run pacman as root, so the controls tested
here -- bearer authentication, the refusal to listen on a non-loopback address
without it, and opt-in CORS -- are the difference between a local helper and a
remote root surface.
"""

import os
from unittest.mock import patch

import pytest

pytest.importorskip("starlette", reason="HTTP transport requires the [http] extra")

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from arch_ops_server.http_server import (
    ALLOW_INSECURE_BIND_ENV,
    ALLOWED_ORIGINS_ENV,
    AUTH_TOKEN_ENV,
    BearerTokenMiddleware,
    get_auth_token,
    run_http_server,
)

TOKEN = "s3cret-token"


def _app_with_auth(token: str = TOKEN) -> Starlette:
    """A minimal app carrying the real middleware, so the tests stay fast."""
    async def ok(_request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/mcp", ok, methods=["GET", "POST", "OPTIONS"])])
    app.add_middleware(BearerTokenMiddleware, token=token)
    return app


class TestBearerTokenMiddleware:
    def test_request_without_token_is_rejected(self):
        with TestClient(_app_with_auth()) as client:
            response = client.get("/mcp")

        assert response.status_code == 401
        assert response.json() == {"error": "unauthorized"}

    def test_request_with_correct_token_passes(self):
        with TestClient(_app_with_auth()) as client:
            response = client.get(
                "/mcp", headers={"Authorization": f"Bearer {TOKEN}"}
            )

        assert response.status_code == 200
        assert response.text == "ok"

    @pytest.mark.parametrize("header", [
        "Bearer wrong-token",
        f"Basic {TOKEN}",          # right secret, wrong scheme
        TOKEN,                     # no scheme at all
        "Bearer ",
        "",
    ])
    def test_malformed_credentials_are_rejected(self, header):
        with TestClient(_app_with_auth()) as client:
            response = client.get("/mcp", headers={"Authorization": header})

        assert response.status_code == 401

    def test_scheme_is_case_insensitive(self):
        """RFC 7235 makes the scheme case-insensitive; clients vary."""
        with TestClient(_app_with_auth()) as client:
            response = client.get(
                "/mcp", headers={"Authorization": f"bearer {TOKEN}"}
            )

        assert response.status_code == 200

    def test_non_ascii_token_is_rejected_not_crashed(self):
        """
        Starlette decodes headers as latin-1, so a high byte yields a non-ASCII
        str. Comparing those with hmac.compare_digest raises TypeError, which
        would surface as a 500 rather than a 401.
        """
        # Sent as raw bytes: httpx refuses to encode a non-ASCII str itself, but
        # a hostile client is under no such constraint.
        with TestClient(_app_with_auth()) as client:
            response = client.get(
                "/mcp", headers={"Authorization": "Bearer töken".encode("latin-1")}
            )

        assert response.status_code == 401

    def test_preflight_bypasses_auth(self):
        """Preflight carries no credentials; CORS must be able to answer it."""
        with TestClient(_app_with_auth()) as client:
            response = client.options("/mcp")

        assert response.status_code != 401


class TestAuthTokenConfiguration:
    def test_token_is_read_lazily(self):
        """
        Read per call, not captured at import: an embedder that configures the
        variable after importing this module must still get authentication.
        """
        with patch.dict(os.environ, {AUTH_TOKEN_ENV: "set-after-import"}):
            assert get_auth_token() == "set-after-import"

        with patch.dict(os.environ, {}, clear=True):
            assert get_auth_token() == ""


class TestBindRefusal:
    """Listening beyond loopback must be a deliberate, authenticated choice."""

    @pytest.mark.asyncio
    async def test_refuses_public_bind_without_token(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match=AUTH_TOKEN_ENV):
                await run_http_server(host="0.0.0.0")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
    async def test_loopback_needs_no_token(self, host):
        """Loopback binds proceed; uvicorn.Server.serve is stubbed out."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("arch_ops_server.http_server.uvicorn.Server") as server_cls:
                async def _serve():
                    return None

                server_cls.return_value.serve = _serve
                await run_http_server(host=host)

        assert server_cls.called

    @pytest.mark.asyncio
    async def test_public_bind_allowed_with_token(self):
        with patch.dict(os.environ, {AUTH_TOKEN_ENV: TOKEN}, clear=True):
            with patch("arch_ops_server.http_server.uvicorn.Server") as server_cls:
                async def _serve():
                    return None

                server_cls.return_value.serve = _serve
                await run_http_server(host="0.0.0.0")

        assert server_cls.called

    @pytest.mark.asyncio
    async def test_insecure_bind_escape_hatch(self):
        """
        Container platforms that terminate ingress themselves need the process
        to listen on all interfaces inside the sandbox.
        """
        with patch.dict(
            os.environ, {ALLOW_INSECURE_BIND_ENV: "1"}, clear=True
        ):
            with patch("arch_ops_server.http_server.uvicorn.Server") as server_cls:
                async def _serve():
                    return None

                server_cls.return_value.serve = _serve
                await run_http_server(host="0.0.0.0")

        assert server_cls.called


class TestEndpointsAreReachable:
    """
    The /mcp handlers write their reply straight to ``send`` and return None.
    Routing them as ordinary function endpoints made Starlette await that None,
    raising TypeError *after* the reply was sent: a client opening one
    connection per request saw nothing wrong, while a keep-alive client failed
    on its second request. Nothing here exercised the endpoint, so it went
    unnoticed. TestClient re-raises server-side exceptions, so a plain request
    is enough to catch a regression.
    """

    @pytest.fixture
    def app(self):
        from arch_ops_server.http_server import create_app

        with patch.dict(os.environ, {}, clear=True):
            return create_app()

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

    @pytest.mark.parametrize("method", [
        "initialize",
        "tools/list",
        "resources/list",
        "prompts/list",
    ])
    def test_listing_methods_return_serialisable_results(self, app, method):
        """
        Every listing must survive json.dumps.

        prompts/list used to hand back PromptArgument models untouched, so the
        whole response failed to serialise and the endpoint returned a JSON-RPC
        error -- and the error path then tried to start a second response.
        """
        with TestClient(app) as client:
            response = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": {}},
            )

        assert response.status_code == 200
        body = response.json()
        assert "error" not in body, body.get("error")
        assert "result" in body

    def test_prompt_arguments_are_plain_data(self, app):
        with TestClient(app) as client:
            response = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "prompts/list", "params": {}},
            )

        prompts = response.json()["result"]["prompts"]
        assert prompts, "expected at least one prompt"

        for prompt in prompts:
            assert isinstance(prompt["arguments"], list)
            for argument in prompt["arguments"]:
                assert set(argument) == {"name", "description", "required"}
                assert isinstance(argument["required"], bool)

    def test_route_methods_are_still_enforced(self, app):
        """
        Starlette defaults methods to ["GET"] only for function endpoints, so
        routing these as ASGI apps means every route must name its methods.
        """
        with TestClient(app) as client:
            assert client.put("/mcp").status_code == 405
            assert client.post("/sse").status_code == 405
            assert client.get("/messages").status_code == 405


class TestCORS:
    """CORS is opt-in by origin; the old wildcard let any page drive the server."""

    def test_no_cors_headers_when_unset(self):
        from arch_ops_server.http_server import create_app

        with patch.dict(os.environ, {}, clear=True):
            app = create_app()

        # Preflight, not GET: a GET on /mcp opens an SSE stream that never ends.
        with TestClient(app) as client:
            response = client.options(
                "/mcp",
                headers={
                    "Origin": "https://evil.example.com",
                    "Access-Control-Request-Method": "POST",
                },
            )

        assert "access-control-allow-origin" not in response.headers

    def test_listed_origin_is_allowed(self):
        from arch_ops_server.http_server import create_app

        origin = "https://trusted.example.com"
        with patch.dict(os.environ, {ALLOWED_ORIGINS_ENV: origin}, clear=True):
            app = create_app()

        with TestClient(app) as client:
            response = client.options(
                "/mcp",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                },
            )

        assert response.headers.get("access-control-allow-origin") == origin
        # Credentials stay off: an allowed origin must not also carry cookies.
        assert "access-control-allow-credentials" not in response.headers

    def test_unlisted_origin_is_not_allowed(self):
        from arch_ops_server.http_server import create_app

        with patch.dict(
            os.environ,
            {ALLOWED_ORIGINS_ENV: "https://trusted.example.com"},
            clear=True,
        ):
            app = create_app()

        with TestClient(app) as client:
            response = client.options(
                "/mcp",
                headers={
                    "Origin": "https://evil.example.com",
                    "Access-Control-Request-Method": "POST",
                },
            )

        assert "access-control-allow-origin" not in response.headers
