# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
Tests for arch_ops_server.config module.
"""

from unittest.mock import patch, mock_open

import pytest

from arch_ops_server.config import (
    PACMAN_CONF,
    MAKEPKG_CONF,
    parse_config_file,
    analyze_pacman_conf,
    analyze_makepkg_conf,
    check_ignored_packages,
    get_parallel_downloads_setting,
)


class TestConfigParsing:
    """Test configuration file parsing."""

    def test_parse_config_file_basic(self, tmp_path):
        """Test parsing a basic config file."""
        config_file = tmp_path / "test.conf"
        config_content = """# Comment line
[options]
Architecture = x86_64
ParallelDownloads = 5

[core]
Server = https://mirror.example.com/core/$arch
"""
        config_file.write_text(config_content)
        
        result = parse_config_file(str(config_file))
        
        assert "options" in result
        assert result["options"]["Architecture"] == "x86_64"
        assert result["options"]["ParallelDownloads"] == "5"
        assert len(result["repositories"]) == 1
        assert result["repositories"][0]["name"] == "core"

    def test_parse_config_file_with_comments(self, tmp_path):
        """Test parsing config with comments."""
        config_file = tmp_path / "test.conf"
        config_content = """# This is a comment
[options]
# Another comment
Key = Value
"""
        config_file.write_text(config_content)
        
        result = parse_config_file(str(config_file))
        
        assert len(result["comments"]) >= 1


class TestPacmanConf:
    """Test pacman.conf parsing."""

    @pytest.fixture
    def sample_pacman_conf(self):
        """Sample pacman.conf content."""
        return """#
# /etc/pacman.conf
#

[options]
Architecture = auto
ParallelDownloads = 5
IgnorePkg = linux firefox
IgnoreGroup = gnome
SigLevel = Required DatabaseOptional
LocalFileSigLevel = Optional

[core]
Include = /etc/pacman.d/mirrorlist

[extra]
Include = /etc/pacman.d/mirrorlist

[multilib]
Include = /etc/pacman.d/mirrorlist
"""

    @pytest.mark.asyncio
    @patch("arch_ops_server.config.IS_ARCH", True)
    async def test_analyze_pacman_conf_success(self, sample_pacman_conf):
        """Test successful pacman.conf analysis."""
        with patch("builtins.open", mock_open(read_data=sample_pacman_conf)):
            result = await analyze_pacman_conf()
            
            assert result["repository_count"] == 3
            assert "core" in result["repositories"]
            assert "extra" in result["repositories"]
            assert "multilib" in result["repositories"]
            assert result["parallel_downloads"] == 5
            assert len(result["ignored_packages"]) == 2
            assert "linux" in result["ignored_packages"]
            assert "firefox" in result["ignored_packages"]

    @pytest.mark.asyncio
    @patch("arch_ops_server.config.IS_ARCH", True)
    async def test_analyze_pacman_conf_ignored_groups(self, sample_pacman_conf):
        """Test detecting ignored groups."""
        with patch("builtins.open", mock_open(read_data=sample_pacman_conf)):
            result = await analyze_pacman_conf()
            
            assert len(result["ignored_groups"]) == 1
            assert "gnome" in result["ignored_groups"]

    @pytest.mark.asyncio
    @patch("arch_ops_server.config.IS_ARCH", True)
    async def test_analyze_pacman_conf_default_parallel(self):
        """Test default parallel downloads value."""
        minimal_conf = """[options]
Architecture = auto

[core]
Include = /etc/pacman.d/mirrorlist
"""
        
        with patch("builtins.open", mock_open(read_data=minimal_conf)):
            result = await analyze_pacman_conf()
            
            assert result["parallel_downloads"] == 1  # Default value

    @pytest.mark.asyncio
    @patch("arch_ops_server.config.IS_ARCH", False)
    async def test_analyze_pacman_conf_not_arch(self):
        """Test on non-Arch system."""
        result = await analyze_pacman_conf()
        
        assert "error" in result
        assert result["error"] == "NotSupported"

    @pytest.mark.asyncio
    @patch("arch_ops_server.config.IS_ARCH", True)
    async def test_analyze_pacman_conf_not_found(self):
        """Test when pacman.conf doesn't exist."""
        with patch("pathlib.Path.exists", return_value=False):
            result = await analyze_pacman_conf()
            
            assert "error" in result
            assert result["error"] == "NotFound"


class TestMakepkgConf:
    """Test makepkg.conf parsing."""

    @pytest.fixture
    def sample_makepkg_conf(self):
        """Sample makepkg.conf content."""
        return """#!/hint/bash
#
# /etc/makepkg.conf
#

CARCH="x86_64"
CHOST="x86_64-pc-linux-gnu"

CFLAGS="-march=x86-64 -mtune=generic -O2 -pipe"
CXXFLAGS="-march=x86-64 -mtune=generic -O2 -pipe"

MAKEFLAGS="-j8"

BUILDENV=(!distcc color !ccache check !sign)
OPTIONS=(strip docs !libtool !staticlibs emptydirs zipman purge !debug lto)

PKGEXT='.pkg.tar.zst'
"""

    @pytest.mark.asyncio
    @patch("arch_ops_server.config.IS_ARCH", True)
    async def test_analyze_makepkg_conf_success(self, sample_makepkg_conf):
        """Test successful makepkg.conf analysis."""
        with patch("builtins.open", mock_open(read_data=sample_makepkg_conf)):
            result = await analyze_makepkg_conf()
            
            assert result["carch"] == "x86_64"
            assert result["jobs"] == 8
            assert "-O2" in result["cflags"]
            assert result["pkgext"] == ".pkg.tar.zst"

    @pytest.mark.asyncio
    @patch("arch_ops_server.config.IS_ARCH", True)
    async def test_analyze_makepkg_conf_buildenv(self, sample_makepkg_conf):
        """Test BUILDENV parsing."""
        with patch("builtins.open", mock_open(read_data=sample_makepkg_conf)):
            result = await analyze_makepkg_conf()
            
            assert "buildenv" in result
            assert isinstance(result["buildenv"], list)

    @pytest.mark.asyncio
    @patch("arch_ops_server.config.IS_ARCH", True)
    async def test_analyze_makepkg_conf_options(self, sample_makepkg_conf):
        """Test OPTIONS parsing."""
        with patch("builtins.open", mock_open(read_data=sample_makepkg_conf)):
            result = await analyze_makepkg_conf()
            
            assert "options" in result
            assert isinstance(result["options"], list)

    @pytest.mark.asyncio
    @patch("arch_ops_server.config.IS_ARCH", False)
    async def test_analyze_makepkg_conf_not_arch(self):
        """Test on non-Arch system."""
        result = await analyze_makepkg_conf()
        
        assert "error" in result
        assert result["error"] == "NotSupported"


class TestIgnoredPackages:
    """Test ignored packages detection."""

    @pytest.fixture
    def pacman_conf_with_ignored(self):
        """pacman.conf with ignored packages."""
        return """[options]
Architecture = auto
IgnorePkg = linux systemd glibc
IgnoreGroup = kde-applications

[core]
Include = /etc/pacman.d/mirrorlist
"""

    @pytest.mark.asyncio
    @patch("arch_ops_server.config.IS_ARCH", True)
    async def test_check_ignored_packages_success(self, pacman_conf_with_ignored):
        """Test checking ignored packages."""
        with patch("builtins.open", mock_open(read_data=pacman_conf_with_ignored)):
            result = await check_ignored_packages()
            
            assert result["has_ignored"] is True
            assert result["ignored_packages_count"] == 3
            assert "linux" in result["ignored_packages"]
            assert "systemd" in result["ignored_packages"]
            assert "glibc" in result["ignored_packages"]

    @pytest.mark.asyncio
    @patch("arch_ops_server.config.IS_ARCH", True)
    async def test_check_ignored_packages_critical_warning(self, pacman_conf_with_ignored):
        """Test warning for critical ignored packages."""
        with patch("builtins.open", mock_open(read_data=pacman_conf_with_ignored)):
            result = await check_ignored_packages()
            
            # Should have warnings for critical packages
            assert len(result["critical_ignored"]) > 0
            assert len(result["warnings"]) > 0

    @pytest.mark.asyncio
    @patch("arch_ops_server.config.IS_ARCH", True)
    async def test_check_ignored_packages_none(self):
        """Test when no packages are ignored."""
        clean_conf = """[options]
Architecture = auto

[core]
Include = /etc/pacman.d/mirrorlist
"""
        
        with patch("builtins.open", mock_open(read_data=clean_conf)):
            result = await check_ignored_packages()
            
            assert result["has_ignored"] is False
            assert result["ignored_packages_count"] == 0

    @pytest.mark.asyncio
    @patch("arch_ops_server.config.IS_ARCH", False)
    async def test_check_ignored_packages_not_arch(self):
        """Test on non-Arch system."""
        result = await check_ignored_packages()
        
        assert "error" in result
        assert result["error"] == "NotSupported"


class TestParallelDownloads:
    """Test parallel downloads setting retrieval."""

    @pytest.mark.asyncio
    @patch("arch_ops_server.config.IS_ARCH", True)
    async def test_get_parallel_downloads_default(self):
        """Test default parallel downloads value."""
        conf = """[options]
Architecture = auto

[core]
Include = /etc/pacman.d/mirrorlist
"""
        
        with patch("builtins.open", mock_open(read_data=conf)):
            result = await get_parallel_downloads_setting()
            
            assert result["parallel_downloads"] == 1
            assert result["is_default"] is True
            assert len(result["recommendations"]) > 0

    @pytest.mark.asyncio
    @patch("arch_ops_server.config.IS_ARCH", True)
    async def test_get_parallel_downloads_configured(self):
        """Test configured parallel downloads."""
        conf = """[options]
Architecture = auto
ParallelDownloads = 5

[core]
Include = /etc/pacman.d/mirrorlist
"""
        
        with patch("builtins.open", mock_open(read_data=conf)):
            result = await get_parallel_downloads_setting()
            
            assert result["parallel_downloads"] == 5
            assert result["is_default"] is False

    @pytest.mark.asyncio
    @patch("arch_ops_server.config.IS_ARCH", True)
    async def test_get_parallel_downloads_very_high(self):
        """Test very high parallel downloads setting."""
        conf = """[options]
Architecture = auto
ParallelDownloads = 15

[core]
Include = /etc/pacman.d/mirrorlist
"""
        
        with patch("builtins.open", mock_open(read_data=conf)):
            result = await get_parallel_downloads_setting()
            
            assert result["parallel_downloads"] == 15
            # Should have recommendation to reduce
            assert len(result["recommendations"]) > 0

    @pytest.mark.asyncio
    @patch("arch_ops_server.config.IS_ARCH", False)
    async def test_get_parallel_downloads_not_arch(self):
        """Test on non-Arch system."""
        result = await get_parallel_downloads_setting()
        
        assert "error" in result
        assert result["error"] == "NotSupported"

