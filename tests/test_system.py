# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
Tests for arch_ops_server.system module.
"""

from unittest.mock import AsyncMock, MagicMock, patch, mock_open

import pytest

from arch_ops_server.system import (
    get_system_info,
    check_disk_space,
    get_pacman_cache_stats,
    check_failed_services,
    get_boot_logs,
)


class TestSystemInfo:
    """Test system information retrieval."""

    @pytest.mark.asyncio
    async def test_get_system_info_success(self):
        """Test successful system info retrieval."""
        async def mock_run_command(cmd, **kwargs):
            if "uname" in cmd and "-r" in cmd:
                return (0, "6.6.1-arch1-1\n", "")
            elif "uname" in cmd and "-m" in cmd:
                return (0, "x86_64\n", "")
            elif "hostname" in cmd:
                return (0, "archbox\n", "")
            elif "uptime" in cmd:
                return (0, "up 2 days, 3 hours\n", "")
            return (0, "", "")
        
        meminfo_content = """MemTotal:       16384000 kB
MemFree:         8192000 kB
MemAvailable:   12288000 kB
"""
        
        with patch("arch_ops_server.system.run_command", mock_run_command), \
             patch("builtins.open", mock_open(read_data=meminfo_content)):
            result = await get_system_info()
            
            assert result["kernel"] == "6.6.1-arch1-1"
            assert result["architecture"] == "x86_64"
            assert result["hostname"] == "archbox"
            assert "uptime" in result
            assert result["memory_total_mb"] > 0

    @pytest.mark.asyncio
    async def test_get_system_info_partial_failure(self):
        """Test system info with some commands failing."""
        async def mock_run_command(cmd, **kwargs):
            if "uname" in cmd and "-r" in cmd:
                return (0, "6.6.1-arch1-1\n", "")
            return (1, "", "error")
        
        with patch("arch_ops_server.system.run_command", mock_run_command):
            result = await get_system_info()
            
            # Should still return partial info
            assert "kernel" in result
            assert result["kernel"] == "6.6.1-arch1-1"


class TestDiskSpace:
    """Test disk space checking."""

    @pytest.mark.asyncio
    async def test_check_disk_space_success(self):
        """Test successful disk space check."""
        df_output = """Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1       100G   60G   40G  60% /
"""
        async def mock_run_command(cmd, **kwargs):
            return (0, df_output, "")
        
        with patch("arch_ops_server.system.run_command", mock_run_command):
            result = await check_disk_space()
            
            assert "disk_usage" in result
            assert "/" in result["disk_usage"]
            assert result["disk_usage"]["/"]["size"] == "100G"
            assert result["disk_usage"]["/"]["use_percent"] == "60%"

    @pytest.mark.asyncio
    async def test_check_disk_space_critical(self):
        """Test disk space with critical warning."""
        df_output = """Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1       100G   95G    5G  95% /
"""
        async def mock_run_command(cmd, **kwargs):
            return (0, df_output, "")
        
        with patch("arch_ops_server.system.run_command", mock_run_command):
            result = await check_disk_space()
            
            assert "/" in result["disk_usage"]
            assert "warning" in result["disk_usage"]["/"]
            assert "Critical" in result["disk_usage"]["/"]["warning"]

    @pytest.mark.asyncio
    async def test_check_disk_space_low(self):
        """Test disk space with low warning."""
        df_output = """Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1       100G   85G   15G  85% /
"""
        async def mock_run_command(cmd, **kwargs):
            return (0, df_output, "")
        
        with patch("arch_ops_server.system.run_command", mock_run_command):
            result = await check_disk_space()
            
            assert "/" in result["disk_usage"]
            assert "warning" in result["disk_usage"]["/"]
            assert "Low" in result["disk_usage"]["/"]["warning"]


class TestPacmanCache:
    """Test pacman cache statistics."""

    @pytest.mark.asyncio
    @patch("arch_ops_server.system.IS_ARCH", True)
    async def test_get_pacman_cache_stats_success(self, tmp_path):
        """Test successful cache stats retrieval."""
        # Create fake package files
        cache_dir = tmp_path / "pkg"
        cache_dir.mkdir()
        
        (cache_dir / "vim-9.0.1000-1-x86_64.pkg.tar.zst").write_bytes(b"0" * 1024 * 1024)  # 1MB
        (cache_dir / "linux-6.6.1-1-x86_64.pkg.tar.zst").write_bytes(b"0" * 2 * 1024 * 1024)  # 2MB
        
        with patch("arch_ops_server.system.Path") as mock_path:
            mock_path.return_value.exists.return_value = True
            mock_path.return_value.glob.return_value = list(cache_dir.glob("*.pkg.tar.*"))
            
            result = await get_pacman_cache_stats()
            
            assert result["package_count"] == 2
            assert result["total_size_mb"] > 0

    @pytest.mark.asyncio
    @patch("arch_ops_server.system.IS_ARCH", False)
    async def test_get_pacman_cache_stats_not_arch(self):
        """Test on non-Arch system."""
        result = await get_pacman_cache_stats()
        
        assert "error" in result
        assert result["error"] == "NotSupported"


class TestFailedServices:
    """Test failed services detection."""

    @pytest.mark.asyncio
    async def test_check_failed_services_none(self):
        """Test when no services have failed."""
        systemctl_output = """0 loaded units listed.
"""
        async def mock_run_command(cmd, **kwargs):
            return (0, systemctl_output, "")
        
        with patch("arch_ops_server.system.check_command_exists", return_value=True), \
             patch("arch_ops_server.system.run_command", mock_run_command):
            result = await check_failed_services()
            
            assert result["all_ok"] is True
            assert result["failed_count"] == 0

    @pytest.mark.asyncio
    async def test_check_failed_services_some_failed(self):
        """Test when some services have failed."""
        systemctl_output = """● docker.service    loaded failed failed Docker Application Container Engine
● ssh.service       loaded failed failed OpenSSH server daemon
2 loaded units listed.
"""
        async def mock_run_command(cmd, **kwargs):
            return (0, systemctl_output, "")
        
        with patch("arch_ops_server.system.check_command_exists", return_value=True), \
             patch("arch_ops_server.system.run_command", mock_run_command):
            result = await check_failed_services()
            
            assert result["all_ok"] is False
            assert result["failed_count"] >= 2
            
            # Check service details
            services = result["failed_services"]
            service_names = [s["unit"] for s in services]
            assert any("docker.service" in name for name in service_names)

    @pytest.mark.asyncio
    async def test_check_failed_services_no_systemctl(self):
        """Test when systemctl is not available."""
        with patch("arch_ops_server.system.check_command_exists", return_value=False):
            result = await check_failed_services()
            
            assert "error" in result
            assert result["error"] == "NotSupported"


class TestBootLogs:
    """Test boot log retrieval."""

    @pytest.mark.asyncio
    async def test_get_boot_logs_success(self):
        """Test successful boot log retrieval."""
        log_output = """Nov 10 10:00:00 archbox kernel: Linux version 6.6.1
Nov 10 10:00:01 archbox systemd[1]: Starting system...
Nov 10 10:00:02 archbox systemd[1]: System started successfully
"""
        async def mock_run_command(cmd, **kwargs):
            return (0, log_output, "")
        
        with patch("arch_ops_server.system.check_command_exists", return_value=True), \
             patch("arch_ops_server.system.run_command", mock_run_command):
            result = await get_boot_logs(lines=100)
            
            assert result["line_count"] == 3
            assert len(result["logs"]) == 3
            assert "kernel" in result["logs"][0]

    @pytest.mark.asyncio
    async def test_get_boot_logs_custom_lines(self):
        """Test boot logs with custom line count."""
        log_output = "\n".join([f"Line {i}" for i in range(50)])
        
        async def mock_run_command(cmd, **kwargs):
            # Check that correct line count was requested
            assert "-n" in cmd
            assert "50" in cmd
            return (0, log_output, "")
        
        with patch("arch_ops_server.system.check_command_exists", return_value=True), \
             patch("arch_ops_server.system.run_command", mock_run_command):
            result = await get_boot_logs(lines=50)
            
            assert result["line_count"] == 50

    @pytest.mark.asyncio
    async def test_get_boot_logs_failure(self):
        """Test boot log retrieval failure."""
        async def mock_run_command(cmd, **kwargs):
            return (1, "", "journalctl error")
        
        with patch("arch_ops_server.system.check_command_exists", return_value=True), \
             patch("arch_ops_server.system.run_command", mock_run_command):
            result = await get_boot_logs()
            
            assert "error" in result
            assert result["error"] == "CommandError"

    @pytest.mark.asyncio
    async def test_get_boot_logs_no_journalctl(self):
        """Test when journalctl is not available."""
        with patch("arch_ops_server.system.check_command_exists", return_value=False):
            result = await get_boot_logs()
            
            assert "error" in result
            assert result["error"] == "NotSupported"

