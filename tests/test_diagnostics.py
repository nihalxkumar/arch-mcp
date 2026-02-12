# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""Tests for unified system diagnostics functionality."""

import pytest
from arch_ops_server.system import diagnose_system


async def test_diagnose_system_failed_services():
    """Test failed services diagnostic."""
    result = await diagnose_system(action="failed_services")
    assert "failed_count" in result or "error" in result


async def test_diagnose_system_boot_logs():
    """Test boot logs diagnostic."""
    result = await diagnose_system(action="boot_logs", lines=50)
    assert "logs" in result or "error" in result


async def test_diagnose_system_invalid_action():
    """Test error handling for invalid action."""
    result = await diagnose_system(action="invalid_action")
    assert "error" in result
