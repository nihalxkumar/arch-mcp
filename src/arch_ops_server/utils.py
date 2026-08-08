# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
Utility functions for Arch Linux MCP Server.
Provides platform detection, subprocess execution, and error handling.
"""

import asyncio
import logging
import os
import platform
import re
import shlex
import shutil
from pathlib import Path
from typing import Optional, Dict, Any

# Configure logging to stderr (STDIO server requirement)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)


def is_arch_linux() -> bool:
    """
    Detect if the current system is Arch Linux.
    
    Checks for:
    1. /etc/arch-release file existence
    2. Platform identification
    
    Returns:
        bool: True if running on Arch Linux, False otherwise
    """
    # Check for Arch release file
    if Path("/etc/arch-release").exists():
        logger.info("Detected Arch Linux via /etc/arch-release")
        return True
    
    # Fallback check via platform info
    try:
        with open("/etc/os-release", "r") as f:
            content = f.read()
            if "Arch Linux" in content or "ID=arch" in content:
                logger.info("Detected Arch Linux via /etc/os-release")
                return True
    except FileNotFoundError:
        pass
    
    logger.info("Not running on Arch Linux")
    return False


# Cache the result since it won't change during runtime
IS_ARCH = is_arch_linux()


# Graphical password helpers, in the order they are tried.
# Askpass helpers that are normally on PATH, across desktops. No desktop
# environment is assumed: whichever is installed gets used.
ASKPASS_HELPERS = (
    "ssh-askpass",              # Debian/Ubuntu alternatives, generic
    "ksshaskpass",              # KDE / Plasma
    "ssh-askpass-gnome",        # GNOME
    "lxqt-openssh-askpass",     # LXQt
    "ssh-askpass-fullscreen",
    "x11-ssh-askpass",          # plain X11
    "qt4-ssh-askpass",
)

# Several distributions install their helper outside PATH, so shutil.which
# alone would report "not installed" on a perfectly working desktop.
ASKPASS_PATHS = (
    "/usr/lib/seahorse/ssh-askpass",            # GNOME/Seahorse, Arch
    "/usr/libexec/seahorse/ssh-askpass",        # GNOME/Seahorse, Fedora
    "/usr/libexec/openssh/gnome-ssh-askpass",   # Fedora
    "/usr/lib/openssh/gnome-ssh-askpass",       # Debian/Ubuntu
    "/usr/lib/ssh/x11-ssh-askpass",             # Arch x11-ssh-askpass
    "/usr/lib/ssh/ssh-askpass",
)


def _is_executable(path: str) -> bool:
    """Return True if path is an existing executable file."""
    return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


def _askpass_from_sudo_conf() -> Optional[str]:
    """
    Read the askpass helper configured in /etc/sudo.conf, if any.

    sudo itself supports `Path askpass <program>`, so an administrator may have
    already chosen a helper. Honour it rather than second-guessing.

    Returns:
        The configured path, or None if unset or unreadable.
    """
    try:
        with open("/etc/sudo.conf", "r") as f:
            for line in f:
                match = re.match(r"^\s*Path\s+askpass\s+(\S+)", line, re.IGNORECASE)
                if match:
                    return match.group(1)
    except OSError:
        pass
    return None


def find_askpass() -> Optional[str]:
    """
    Locate a helper sudo can use to prompt for a password.

    The server has no controlling terminal it can safely prompt on -- for the
    STDIO transport, stdin carries the MCP protocol -- so sudo needs a separate
    helper. The user types their password into their own session; it never
    passes through this process.

    No desktop environment is assumed. The search order is: an explicitly
    configured SUDO_ASKPASS, then /etc/sudo.conf, then the helpers that ship
    with each major desktop, on PATH and in the lib directories distributions
    put them in.

    Returns:
        Path to an executable askpass helper, or None if no graphical session
        is available or no helper is installed.
    """
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        logger.debug("No graphical session; askpass unavailable")
        return None

    configured = os.environ.get("SUDO_ASKPASS")
    if _is_executable(configured):
        logger.debug(f"Using configured SUDO_ASKPASS: {configured}")
        return configured

    from_conf = _askpass_from_sudo_conf()
    if _is_executable(from_conf):
        logger.debug(f"Using askpass from /etc/sudo.conf: {from_conf}")
        return from_conf

    for helper in ASKPASS_HELPERS:
        path = shutil.which(helper)
        if path:
            logger.debug(f"Found askpass helper on PATH: {path}")
            return path

    for path in ASKPASS_PATHS:
        if _is_executable(path):
            logger.debug(f"Found askpass helper: {path}")
            return path

    logger.debug("No askpass helper installed")
    return None


def _is_sudo_auth_failure(stderr: str) -> bool:
    """
    Decide whether sudo failed for want of a password rather than on the command.

    Args:
        stderr: Captured standard error from the sudo invocation.

    Returns:
        True if sudo reported that it could not authenticate the user.
    """
    lowered = stderr.lower()
    return any(marker in lowered for marker in (
        "a password is required",
        "no askpass program",
        "a terminal is required",
        "no tty present",
        "sorry, a password is required",
    ))


def format_command(cmd: list[str]) -> str:
    """
    Render an argument vector as a copy-pasteable shell command.

    Args:
        cmd: Command and arguments as a list.

    Returns:
        A quoted command string safe to show the user.
    """
    return shlex.join(cmd)


async def run_command(
    cmd: list[str],
    timeout: int = 10,
    check: bool = True
) -> tuple[int, str, str]:
    """
    Execute a command asynchronously with timeout protection.

    Privileged commands are escalated through sudo's askpass helper, so the
    password is entered by the user in their own graphical session. This process
    never reads, relays or stores it, and no passwordless sudo rule is required.
    The child's stdin is always closed: nothing here writes a password to a pipe.

    Args:
        cmd: Command and arguments as list
        timeout: Timeout in seconds (default: 10)
        check: If True, raise exception on non-zero exit code

    Returns:
        Tuple of (exit_code, stdout, stderr)

    Raises:
        asyncio.TimeoutError: If command exceeds timeout
        RuntimeError: If check=True and command fails
    """
    logger.debug(f"Executing command: {format_command(cmd)}")

    env = os.environ.copy()

    # Route sudo through an askpass helper. There is no terminal to prompt on,
    # so without one sudo would block or fall back to a NOPASSWD rule.
    needs_sudo_fallback_message = False
    if cmd and cmd[0] == "sudo":
        askpass = find_askpass()
        if askpass:
            env["SUDO_ASKPASS"] = askpass
            # -A tells sudo to use SUDO_ASKPASS rather than looking for a terminal.
            if "-A" not in cmd:
                cmd = [cmd[0], "-A"] + list(cmd[1:])
        else:
            # No helper, but sudo may not need to ask: the user may have a valid
            # cached timestamp, or an authorisation rule they chose themselves.
            # -n makes sudo either proceed without prompting or fail at once,
            # so this can never block on a terminal we do not have.
            if "-n" not in cmd:
                cmd = [cmd[0], "-n"] + list(cmd[1:])
            needs_sudo_fallback_message = True
            logger.debug("No askpass helper; attempting sudo non-interactively")

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL,
            env=env
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout
        )

        exit_code = process.returncode
        stdout_str = stdout.decode('utf-8', errors='replace') if stdout else ""
        stderr_str = stderr.decode('utf-8', errors='replace') if stderr else ""

        logger.debug(f"Command exit code: {exit_code}")

        # Distinguish "sudo could not ask for a password" from a real command
        # failure, and tell the user how to proceed without weakening sudo.
        if needs_sudo_fallback_message and exit_code != 0 and _is_sudo_auth_failure(stderr_str):
            logger.warning("sudo needs a password but no askpass helper is available")
            return 1, "", (
                "This command needs root, but there is no password prompt available: "
                "no askpass helper is installed and your sudo credentials are not "
                "currently valid.\n\n"
                "Run it yourself in a terminal:\n\n"
                f"    {format_command([c for c in cmd if c != '-n'])}\n\n"
                "Or install an askpass helper for your desktop and retry -- for "
                "example seahorse on GNOME, ksshaskpass on KDE, or "
                "lxqt-openssh-askpass on LXQt.\n\n"
                "Do not add a passwordless sudo rule to work around this: it would "
                "let any tool call reach root with no confirmation."
            )

        if check and exit_code != 0:
            raise RuntimeError(
                f"Command failed with exit code {exit_code}: {stderr_str}"
            )

        return exit_code, stdout_str, stderr_str

    except asyncio.TimeoutError:
        logger.error(f"Command timed out after {timeout}s: {format_command(cmd)}")
        raise
    except Exception as e:
        logger.error(f"Command execution failed: {e}")
        raise


def add_aur_warning(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Wrap AUR data with prominent safety warning.
    
    The AUR contains user-produced content that may be outdated,
    broken, or malicious. Always inspect PKGBUILDs before installation.
    
    Args:
        data: Original AUR response data
    
    Returns:
        Dict with added warning metadata
    """
    return {
        "warning": (
            "⚠️  AUR PACKAGE WARNING ⚠️\n"
            "AUR packages are USER-PRODUCED content and are not officially supported.\n"
            "These packages may be outdated, broken, or even malicious.\n"
            "ALWAYS review the PKGBUILD and other files before installing.\n"
            "Use at your own risk."
        ),
        "data": data
    }


def create_error_response(
    error_type: str,
    message: str,
    details: Optional[str] = None,
    suggest_wiki_search: bool = True
) -> Dict[str, Any]:
    """
    Create a structured error response with Wiki suggestions.
    
    Args:
        error_type: Type of error (e.g., "NetworkError", "NotFound")
        message: Human-readable error message
        details: Optional additional details
        suggest_wiki_search: Whether to suggest related Wiki searches (default: True)
    
    Returns:
        Structured error dict with Wiki suggestions
    """
    response = {
        "error": True,
        "type": error_type,
        "message": message
    }
    
    if details:
        response["details"] = details
    
    # Add Wiki suggestions for common error types
    if suggest_wiki_search:
        wiki_suggestions = _get_wiki_suggestions_for_error(error_type, message)
        if wiki_suggestions:
            response["wiki_suggestions"] = wiki_suggestions
            response["help_text"] = (
                "💡 Search the Arch Wiki for these topics to find solutions. "
                "Use the search_archwiki tool with these keywords."
            )
    
    logger.error(f"{error_type}: {message}")
    
    return response


def _get_wiki_suggestions_for_error(error_type: str, message: str) -> list[str]:
    """
    Generate relevant Arch Wiki search suggestions based on error type.
    
    Args:
        error_type: Type of error
        message: Error message
    
    Returns:
        List of suggested Wiki search terms
    """
    suggestions = []
    message_lower = message.lower()
    
    # Map error types to Wiki topics
    error_wiki_map = {
        "NotFound": ["Package management", "AUR"],
        "TimeoutError": ["Network configuration", "Mirrors"],
        "HTTPError": ["Network configuration", "Proxy"],
        "CommandNotFound": ["Pacman", "System maintenance"],
        "NotSupported": ["Installation guide", "System requirements"],
        "RateLimitError": ["AUR", "Mirror"],
    }
    
    # Add general suggestions based on error type
    if error_type in error_wiki_map:
        suggestions.extend(error_wiki_map[error_type])
    
    # Add context-specific suggestions based on message keywords
    keyword_map = {
        "pacman": ["Pacman", "Pacman/Rosetta"],
        "package": ["Package management", "Official repositories"],
        "dependency": ["Dependency", "Package management"],
        "mirror": ["Mirrors", "Reflector"],
        "network": ["Network configuration", "Systemd-networkd"],
        "update": ["System maintenance", "Pacman#Upgrading packages"],
        "gpg": ["Pacman/Package signing", "GnuPG"],
        "disk": ["File systems", "Partitioning"],
        "boot": ["Boot process", "Arch boot process"],
        "kernel": ["Kernel", "Kernel modules"],
        "driver": ["Kernel modules", "Xorg"],
        "graphics": ["Xorg", "NVIDIA", "AMD"],
    }
    
    for keyword, topics in keyword_map.items():
        if keyword in message_lower:
            suggestions.extend(topics)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_suggestions = []
    for suggestion in suggestions:
        if suggestion not in seen:
            seen.add(suggestion)
            unique_suggestions.append(suggestion)
    
    return unique_suggestions[:5]  # Limit to top 5 suggestions


def check_command_exists(command: str) -> bool:
    """
    Check if a command exists in the system PATH.

    Args:
        command: Command name to check

    Returns:
        bool: True if command exists, False otherwise
    """
    # shutil.which does not involve a shell, so a command name containing shell
    # metacharacters cannot be executed here.
    return shutil.which(command) is not None


def get_aur_helper() -> Optional[str]:
    """
    Detect available AUR helper with priority: paru > yay.
    
    Returns:
        str: Name of available AUR helper ('paru' or 'yay'), or None if neither exists
    """
    # Check in priority order
    if check_command_exists("paru"):
        logger.info("Found AUR helper: paru")
        return "paru"
    elif check_command_exists("yay"):
        logger.info("Found AUR helper: yay")
        return "yay"
    else:
        logger.warning("No AUR helper found (paru or yay)")
        return None

