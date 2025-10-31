"""
Utility functions for Arch Linux MCP Server.
Provides platform detection, subprocess execution, and error handling.
"""

import asyncio
import logging
import os
import platform
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


async def run_command(
    cmd: list[str],
    timeout: int = 10,
    check: bool = True,
    skip_sudo_check: bool = False
) -> tuple[int, str, str]:
    """
    Execute a command asynchronously with timeout protection.
    
    Note: For sudo commands, stdin is properly connected to allow password input
    if passwordless sudo is not configured.
    
    Args:
        cmd: Command and arguments as list
        timeout: Timeout in seconds (default: 10)
        check: If True, raise exception on non-zero exit code
        skip_sudo_check: If True, skip the early sudo password check (for testing)
    
    Returns:
        Tuple of (exit_code, stdout, stderr)
    
    Raises:
        asyncio.TimeoutError: If command exceeds timeout
        RuntimeError: If check=True and command fails
    """
    logger.debug(f"Executing command: {' '.join(cmd)}")
    
    # Check if this is a sudo command and if password is cached
    is_sudo_command = cmd and cmd[0] == "sudo"
    if is_sudo_command and not skip_sudo_check:
        # Test if sudo password is cached (non-interactive mode)
        test_cmd = ["sudo", "-n", "true"]
        try:
            test_process = await asyncio.create_subprocess_exec(
                *test_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await test_process.communicate()
            password_cached = test_process.returncode == 0
            logger.debug(f"Sudo password cached: {password_cached}")
            
            if not password_cached:
                logger.warning("Sudo password is required but not cached. "
                              "Please run 'sudo pacman -S <package>' manually in the terminal.")
                return (
                    1,
                    "",
                    "Sudo password required. Please configure passwordless sudo for pacman/paru, "
                    "or run the installation command manually in your terminal."
                )
        except Exception as e:
            logger.warning(f"Could not check sudo status: {e}")
            password_cached = False
    else:
        password_cached = True
    
    try:
        # Attach stdin to subprocess for commands that might need input
        # Use asyncio.subprocess.PIPE to allow stdin interaction
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if is_sudo_command else None
        )
        
        # Communicate with the process
        # For sudo commands, this allows password input if needed
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout
        )
        
        exit_code = process.returncode
        stdout_str = stdout.decode('utf-8', errors='replace') if stdout else ""
        stderr_str = stderr.decode('utf-8', errors='replace') if stderr else ""
        
        logger.debug(f"Command exit code: {exit_code}")
        
        if check and exit_code != 0:
            raise RuntimeError(
                f"Command failed with exit code {exit_code}: {stderr_str}"
            )
        
        return exit_code, stdout_str, stderr_str
        
    except asyncio.TimeoutError:
        logger.error(f"Command timed out after {timeout}s: {' '.join(cmd)}")
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
    try:
        result = os.system(f"which {command} > /dev/null 2>&1")
        return result == 0
    except Exception:
        return False


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

