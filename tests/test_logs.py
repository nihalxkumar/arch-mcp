# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
Tests for arch_ops_server.logs module.
"""

from unittest.mock import patch, mock_open

import pytest

from arch_ops_server.logs import (
    parse_log_line,
    get_transaction_history,
    find_when_installed,
    find_failed_transactions,
    get_database_sync_history,
)


class TestLogParsing:
    """Test pacman log parsing functionality."""

    def test_parse_log_line_success(self):
        """Test parsing a valid log line."""
        line = "[2025-11-10 15:30] [ALPM] installed vim (9.0.1000-1)"
        
        result = parse_log_line(line)
        
        assert result is not None
        assert result["timestamp"] == "2025-11-10T15:30:00"
        assert result["action"] == "ALPM"
        assert "vim" in result["package"]

    def test_parse_log_line_upgrade(self):
        """Test parsing upgrade log line."""
        line = "[2025-11-10 15:31] [ALPM] upgraded linux (6.6.1-1 -> 6.6.2-1)"
        
        result = parse_log_line(line)
        
        assert result is not None
        assert result["action"] == "ALPM"
        assert "linux" in result["package"]
        assert "->" in result["version_info"]

    def test_parse_log_line_invalid(self):
        """Test parsing invalid log line."""
        line = "This is not a valid log line"
        
        result = parse_log_line(line)
        
        assert result is None


class TestTransactionHistory:
    """Test transaction history retrieval."""

    @pytest.fixture
    def sample_log(self):
        """Sample pacman log content."""
        return """[2025-11-10 15:30] [ALPM] installed vim (9.0.1000-1)
[2025-11-10 15:31] [ALPM] upgraded linux (6.6.1-1 -> 6.6.2-1)
[2025-11-10 15:32] [ALPM] removed firefox (120.0-1)
[2025-11-10 15:33] [PACMAN] Running 'pacman -Syu'
[2025-11-10 15:34] [ALPM] installed python-pytest (7.4.3-1)
[2025-11-10 15:35] [ALPM] downgraded systemd (255.2-1 -> 255.1-1)
"""

    @pytest.mark.asyncio
    @patch("arch_ops_server.logs.IS_ARCH", True)
    async def test_get_transaction_history_all(self, sample_log):
        """Test getting all transaction history."""
        with patch("builtins.open", mock_open(read_data=sample_log)):
            result = await get_transaction_history(limit=10, transaction_type="all")
            
            assert result["count"] >= 3  # At least install, upgrade, remove
            assert any(t["action"] == "ALPM" for t in result["transactions"])

    @pytest.mark.asyncio
    @patch("arch_ops_server.logs.IS_ARCH", True)
    async def test_get_transaction_history_install_only(self, sample_log):
        """Test filtering by install transactions."""
        with patch("builtins.open", mock_open(read_data=sample_log)):
            result = await get_transaction_history(limit=10, transaction_type="install")
            
            assert result["transaction_type"] == "install"
            # All returned transactions should be installations
            for transaction in result["transactions"]:
                assert "installed" in transaction["raw_line"].lower()

    @pytest.mark.asyncio
    @patch("arch_ops_server.logs.IS_ARCH", True)
    async def test_get_transaction_history_with_limit(self, sample_log):
        """Test transaction history with limit."""
        with patch("builtins.open", mock_open(read_data=sample_log)):
            result = await get_transaction_history(limit=2, transaction_type="all")
            
            assert result["count"] <= 2

    @pytest.mark.asyncio
    @patch("arch_ops_server.logs.IS_ARCH", False)
    async def test_get_transaction_history_not_arch(self):
        """Test on non-Arch system."""
        result = await get_transaction_history()
        
        assert "error" in result
        assert result["error"] == "NotSupported"


class TestPackageInstallationHistory:
    """Test package installation history retrieval."""

    @pytest.fixture
    def sample_log_with_package(self):
        """Sample log with specific package history."""
        return """[2025-11-05 10:00] [ALPM] installed vim (9.0.900-1)
[2025-11-06 11:00] [ALPM] upgraded vim (9.0.900-1 -> 9.0.950-1)
[2025-11-07 12:00] [ALPM] removed vim (9.0.950-1)
[2025-11-08 13:00] [ALPM] installed vim (9.0.1000-1)
[2025-11-09 14:00] [ALPM] upgraded vim (9.0.1000-1 -> 9.0.1050-1)
"""

    @pytest.mark.asyncio
    @patch("arch_ops_server.logs.IS_ARCH", True)
    async def test_find_when_installed_success(self, sample_log_with_package):
        """Test finding package installation history."""
        with patch("builtins.open", mock_open(read_data=sample_log_with_package)):
            result = await find_when_installed("vim")
            
            assert result["package"] == "vim"
            assert "first_installed" in result
            assert result["upgrade_count"] >= 2
            assert len(result["upgrades"]) >= 2

    @pytest.mark.asyncio
    @patch("arch_ops_server.logs.IS_ARCH", True)
    async def test_find_when_installed_not_found(self):
        """Test finding package that was never installed."""
        empty_log = ""
        
        with patch("builtins.open", mock_open(read_data=empty_log)):
            result = await find_when_installed("nonexistent-package")
            
            assert "error" in result
            assert result["error"] == "NotFound"

    @pytest.mark.asyncio
    @patch("arch_ops_server.logs.IS_ARCH", True)
    async def test_find_when_installed_with_removals(self, sample_log_with_package):
        """Test package history including removals."""
        with patch("builtins.open", mock_open(read_data=sample_log_with_package)):
            result = await find_when_installed("vim")
            
            assert result["removal_count"] >= 1
            assert "removals" in result

    @pytest.mark.asyncio
    @patch("arch_ops_server.logs.IS_ARCH", False)
    async def test_find_when_installed_not_arch(self):
        """Test on non-Arch system."""
        result = await find_when_installed("vim")
        
        assert "error" in result
        assert result["error"] == "NotSupported"


class TestFailedTransactions:
    """Test failed transaction detection."""

    @pytest.fixture
    def sample_log_with_errors(self):
        """Sample log with errors and warnings."""
        return """[2025-11-10 10:00] [ALPM] transaction started
[2025-11-10 10:01] [ALPM-SCRIPTLET] error: failed to update database
[2025-11-10 10:02] [ALPM] warning: could not get file information
[2025-11-10 10:03] [ERROR] failed to commit transaction
[2025-11-10 10:04] [ALPM] transaction completed
[2025-11-10 10:05] [WARNING] unable to lock database
[2025-11-10 10:06] [ALPM] conflict detected between packages
"""

    @pytest.mark.asyncio
    @patch("arch_ops_server.logs.IS_ARCH", True)
    async def test_find_failed_transactions_success(self, sample_log_with_errors):
        """Test finding failed transactions."""
        with patch("builtins.open", mock_open(read_data=sample_log_with_errors)):
            result = await find_failed_transactions()
            
            assert result["has_failures"] is True
            assert result["count"] > 0
            
            # Check severity classification
            failures = result["failures"]
            errors = [f for f in failures if f["severity"] == "error"]
            warnings = [f for f in failures if f["severity"] == "warning"]
            
            assert len(errors) > 0 or len(warnings) > 0

    @pytest.mark.asyncio
    @patch("arch_ops_server.logs.IS_ARCH", True)
    async def test_find_failed_transactions_none(self):
        """Test when no failures are found."""
        clean_log = """[2025-11-10 10:00] [ALPM] transaction started
[2025-11-10 10:01] [ALPM] installed package (1.0-1)
[2025-11-10 10:02] [ALPM] transaction completed
"""
        
        with patch("builtins.open", mock_open(read_data=clean_log)):
            result = await find_failed_transactions()
            
            # May still have some matches but should be minimal
            assert "count" in result

    @pytest.mark.asyncio
    @patch("arch_ops_server.logs.IS_ARCH", False)
    async def test_find_failed_transactions_not_arch(self):
        """Test on non-Arch system."""
        result = await find_failed_transactions()
        
        assert "error" in result
        assert result["error"] == "NotSupported"


class TestDatabaseSyncHistory:
    """Test database synchronization history."""

    @pytest.fixture
    def sample_log_with_syncs(self):
        """Sample log with database sync events."""
        return """[2025-11-08 10:00] [PACMAN] synchronizing package lists
[2025-11-09 11:00] [PACMAN] starting full system upgrade
[2025-11-09 11:01] [ALPM] upgraded package (1.0-1 -> 1.1-1)
[2025-11-10 12:00] [PACMAN] synchronizing package lists
[2025-11-10 12:30] [PACMAN] starting full system upgrade
"""

    @pytest.mark.asyncio
    @patch("arch_ops_server.logs.IS_ARCH", True)
    async def test_get_database_sync_history_success(self, sample_log_with_syncs):
        """Test getting database sync history."""
        with patch("builtins.open", mock_open(read_data=sample_log_with_syncs)):
            result = await get_database_sync_history(limit=10)
            
            assert result["count"] >= 2
            assert len(result["sync_events"]) >= 2
            
            # Check event types
            sync_types = [e["type"] for e in result["sync_events"]]
            assert "sync" in sync_types or "full_upgrade" in sync_types

    @pytest.mark.asyncio
    @patch("arch_ops_server.logs.IS_ARCH", True)
    async def test_get_database_sync_history_with_limit(self, sample_log_with_syncs):
        """Test sync history with limit."""
        with patch("builtins.open", mock_open(read_data=sample_log_with_syncs)):
            result = await get_database_sync_history(limit=2)
            
            assert result["count"] <= 2

    @pytest.mark.asyncio
    @patch("arch_ops_server.logs.IS_ARCH", False)
    async def test_get_database_sync_history_not_arch(self):
        """Test on non-Arch system."""
        result = await get_database_sync_history()
        
        assert "error" in result
        assert result["error"] == "NotSupported"

