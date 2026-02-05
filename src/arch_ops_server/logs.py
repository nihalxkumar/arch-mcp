# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
Pacman transaction log parsing module.
Parses and analyzes pacman transaction logs for troubleshooting and auditing.
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from .utils import (
    IS_ARCH,
    create_error_response,
)

logger = logging.getLogger(__name__)

# Pacman log file path
PACMAN_LOG = "/var/log/pacman.log"


def parse_log_line(line: str) -> Optional[Dict[str, Any]]:
    """
    Parse a single line from pacman log.

    Args:
        line: Log line to parse

    Returns:
        Dict with parsed data or None if not a transaction line
    """
    # Format: [YYYY-MM-DD HH:MM] [ACTION] package (version)
    match = re.match(
        r'\[(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\]\s+\[(\w+)\]\s+(.+)',
        line
    )

    if not match:
        return None

    date_str, time_str, log_type, details = match.groups()
    timestamp = f"{date_str}T{time_str}:00"

    action = log_type
    package = details
    version_info = ""

    # Parse ALPM actions
    if log_type == "ALPM":
        # Format: action package (version)
        # e.g. installed vim (9.0.1000-1)
        # e.g. upgraded linux (6.6.1-1 -> 6.6.2-1)
        pkg_match = re.match(r'(\w+)\s+(\S+)\s+\((.+)\)', details)
        
        if pkg_match:
            action = pkg_match.group(1)  # installed, upgraded, etc.
            package = pkg_match.group(2)
            version_info = pkg_match.group(3)
    
    # Fallback for old parsing or non-ALPM lines that might match the old regex
    if action == log_type and log_type != "ALPM":
         # Parse package details for generic logs if needed
         # Format: "package_name (version)" or "package_name (old -> new)"
         pkg_match = re.match(r'(\S+)\s+\((.+)\)', details)
         if pkg_match:
             package = pkg_match.group(1)
             version_info = pkg_match.group(2)

    return {
        "timestamp": timestamp,
        "source": log_type,
        "action": action,
        "package": package,
        "version_info": version_info,
        "raw_line": line.strip()
    }


async def query_package_history(
    query_type: str,
    package_name: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """
    Unified tool for querying package history from pacman logs.
    
    Consolidates four previous tools into one with different query types:
    - 'all': Get recent package transactions (replaces get_transaction_history)
    - 'package': Find when a package was installed (replaces find_when_installed)
    - 'failures': Find failed transactions (replaces find_failed_transactions)
    - 'sync': Get database sync history (replaces get_database_sync_history)
    
    Args:
        query_type: Type of query - 'all', 'package', 'failures', or 'sync'
        package_name: Package name (required for 'package' query type)
        limit: Maximum number of results to return (default 50)
    
    Returns:
        Dict with query results based on query_type
    """
    if not IS_ARCH:
        return create_error_response(
            "NotSupported",
            "This feature is only available on Arch Linux"
        )
    
    logger.info(f"Querying package history: type={query_type}, package={package_name}, limit={limit}")
    
    # Validate query_type
    valid_types = ["all", "package", "failures", "sync"]
    if query_type not in valid_types:
        return create_error_response(
            "InvalidParameter",
            f"Invalid query_type '{query_type}'. Must be one of: {', '.join(valid_types)}"
        )
    
    # Validate package_name for 'package' query
    if query_type == "package" and not package_name:
        return create_error_response(
            "InvalidParameter",
            "package_name is required for query_type='package'"
        )
    
    try:
        pacman_log = Path(PACMAN_LOG)
        
        if not pacman_log.exists():
            return create_error_response(
                "NotFound",
                f"Pacman log file not found at {PACMAN_LOG}"
            )
        
        # Route to appropriate query handler
        if query_type == "all":
            return await _query_all_transactions(pacman_log, limit)
        elif query_type == "package":
            return await _query_package_history(pacman_log, package_name, limit)
        elif query_type == "failures":
            return await _query_failed_transactions(pacman_log, limit)
        elif query_type == "sync":
            return await _query_sync_history(pacman_log, limit)
    
    except Exception as e:
        logger.error(f"Failed to query package history: {e}")
        return create_error_response(
            "LogParseError",
            f"Failed to query package history: {str(e)}"
        )


async def _query_all_transactions(
    pacman_log: Path,
    limit: int
) -> Dict[str, Any]:
    """Get recent package transactions."""
    transactions = []
    
    with open(pacman_log, 'r') as f:
        lines = f.readlines()
    
    # Process in reverse order for most recent first
    for line in reversed(lines):
        if len(transactions) >= limit:
            break
        
        parsed = parse_log_line(line)
        if parsed and parsed["action"].lower() in ["installed", "upgraded", "removed", "downgraded", "reinstalled"]:
            transactions.append(parsed)
    
    logger.info(f"Found {len(transactions)} transactions")
    
    return {
        "query_type": "all",
        "count": len(transactions),
        "transactions": transactions
    }


async def _query_package_history(
    pacman_log: Path,
    package_name: str,
    limit: int
) -> Dict[str, Any]:
    """Find when a package was installed and its history."""
    first_install = None
    upgrades = []
    removals = []
    
    with open(pacman_log, 'r') as f:
        for line in f:
            parsed = parse_log_line(line)
            if not parsed or parsed["package"] != package_name:
                continue
            
            action = parsed["action"].lower()
            
            if action == "installed":
                if first_install is None:
                    first_install = parsed
            elif action in ["upgraded", "downgraded", "reinstalled"]:
                upgrades.append(parsed)
            elif action == "removed":
                removals.append(parsed)
    
    if first_install is None:
        return create_error_response(
            "NotFound",
            f"No installation record found for package: {package_name}"
        )
    
    logger.info(f"Package {package_name}: installed {first_install['timestamp']}, {len(upgrades)} upgrades, {len(removals)} removals")
    
    return {
        "query_type": "package",
        "package": package_name,
        "first_installed": first_install,
        "upgrade_count": len(upgrades),
        "upgrades": upgrades,
        "removal_count": len(removals),
        "removals": removals,
        "currently_removed": len(removals) > 0 and (not upgrades or removals[-1]["timestamp"] > upgrades[-1]["timestamp"])
    }


async def _query_failed_transactions(
    pacman_log: Path,
    limit: int
) -> Dict[str, Any]:
    """Find failed package transactions."""
    failed_transactions = []
    error_keywords = ["error", "failed", "warning", "could not", "unable to", "conflict"]
    
    with open(pacman_log, 'r') as f:
        for line in f:
            line_lower = line.lower()
            
            # Check for error indicators
            if any(keyword in line_lower for keyword in error_keywords):
                # Extract timestamp if available
                timestamp_match = re.match(r'\[(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\]', line)
                timestamp = ""
                if timestamp_match:
                    timestamp = f"{timestamp_match.group(1)}T{timestamp_match.group(2)}:00"
                
                # Extract severity
                severity = "error" if "error" in line_lower or "failed" in line_lower else "warning"
                
                failed_transactions.append({
                    "timestamp": timestamp,
                    "severity": severity,
                    "message": line.strip()
                })
    
    # Limit to most recent entries
    failed_transactions = failed_transactions[-limit:]
    
    logger.info(f"Found {len(failed_transactions)} failed/warning entries")
    
    return {
        "query_type": "failures",
        "count": len(failed_transactions),
        "has_failures": len(failed_transactions) > 0,
        "failures": failed_transactions
    }


async def _query_sync_history(
    pacman_log: Path,
    limit: int
) -> Dict[str, Any]:
    """Get database synchronization history."""
    sync_events = []
    
    with open(pacman_log, 'r') as f:
        lines = f.readlines()
    
    # Process in reverse order for most recent first
    for line in reversed(lines):
        if len(sync_events) >= limit:
            break
        
        # Look for database synchronization entries
        if "synchronizing package lists" in line.lower() or "starting full system upgrade" in line.lower():
            timestamp_match = re.match(r'\[(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\]', line)
            
            if timestamp_match:
                timestamp = f"{timestamp_match.group(1)}T{timestamp_match.group(2)}:00"
                
                event_type = "sync"
                if "starting full system upgrade" in line.lower():
                    event_type = "full_upgrade"
                
                sync_events.append({
                    "timestamp": timestamp,
                    "type": event_type,
                    "message": line.strip()
                })
    
    logger.info(f"Found {len(sync_events)} sync events")
    
    return {
        "query_type": "sync",
        "count": len(sync_events),
        "sync_events": sync_events
    }


# ============================================================================
# LEGACY FUNCTIONS (kept for backward compatibility)
# ============================================================================

async def get_transaction_history(
    limit: int = 50,
    transaction_type: str = "all"
) -> Dict[str, Any]:
    """
    Get recent package transactions from pacman log.

    Args:
        limit: Maximum number of transactions to return (default 50)
        transaction_type: Filter by type - install/remove/upgrade/all (default all)

    Returns:
        Dict with transaction history
    """
    if not IS_ARCH:
        return create_error_response(
            "NotSupported",
            "This feature is only available on Arch Linux"
        )

    logger.info(f"Getting transaction history (limit={limit}, type={transaction_type})")

    try:
        pacman_log = Path(PACMAN_LOG)

        if not pacman_log.exists():
            return create_error_response(
                "NotFound",
                f"Pacman log file not found at {PACMAN_LOG}"
            )

        transactions = []
        valid_actions = {
            "all": ["installed", "upgraded", "removed", "downgraded", "reinstalled"],
            "install": ["installed"],
            "remove": ["removed"],
            "upgrade": ["upgraded", "downgraded", "reinstalled"]
        }

        actions_to_match = valid_actions.get(transaction_type, valid_actions["all"])

        # Read log file from end (most recent first)
        with open(pacman_log, 'r') as f:
            lines = f.readlines()

        # Process in reverse order for most recent first
        for line in reversed(lines):
            if len(transactions) >= limit:
                break

            parsed = parse_log_line(line)
            if parsed and parsed["action"].lower() in actions_to_match:
                transactions.append(parsed)

        logger.info(f"Found {len(transactions)} transactions")

        return {
            "count": len(transactions),
            "transaction_type": transaction_type,
            "transactions": transactions
        }

    except Exception as e:
        logger.error(f"Failed to parse transaction history: {e}")
        return create_error_response(
            "LogParseError",
            f"Failed to parse transaction history: {str(e)}"
        )


async def find_when_installed(package_name: str) -> Dict[str, Any]:
    """
    Find when a package was first installed and its upgrade history.

    Args:
        package_name: Name of the package to search for

    Returns:
        Dict with installation date and upgrade history
    """
    if not IS_ARCH:
        return create_error_response(
            "NotSupported",
            "This feature is only available on Arch Linux"
        )

    logger.info(f"Finding installation history for package: {package_name}")

    try:
        pacman_log = Path(PACMAN_LOG)

        if not pacman_log.exists():
            return create_error_response(
                "NotFound",
                f"Pacman log file not found at {PACMAN_LOG}"
            )

        first_install = None
        upgrades = []
        removals = []

        with open(pacman_log, 'r') as f:
            for line in f:
                parsed = parse_log_line(line)
                if not parsed or parsed["package"] != package_name:
                    continue

                action = parsed["action"].lower()

                if action == "installed":
                    if first_install is None:
                        first_install = parsed
                elif action in ["upgraded", "downgraded", "reinstalled"]:
                    upgrades.append(parsed)
                elif action == "removed":
                    removals.append(parsed)

        if first_install is None:
            return create_error_response(
                "NotFound",
                f"No installation record found for package: {package_name}"
            )

        logger.info(f"Package {package_name}: installed {first_install['timestamp']}, {len(upgrades)} upgrades, {len(removals)} removals")

        return {
            "package": package_name,
            "first_installed": first_install,
            "upgrade_count": len(upgrades),
            "upgrades": upgrades,
            "removal_count": len(removals),
            "removals": removals,
            "currently_removed": len(removals) > 0 and (not upgrades or removals[-1]["timestamp"] > upgrades[-1]["timestamp"])
        }

    except Exception as e:
        logger.error(f"Failed to find installation history: {e}")
        return create_error_response(
            "LogParseError",
            f"Failed to find installation history: {str(e)}"
        )


async def find_failed_transactions() -> Dict[str, Any]:
    """
    Find failed package transactions in pacman log.

    Returns:
        Dict with failed transaction information
    """
    if not IS_ARCH:
        return create_error_response(
            "NotSupported",
            "This feature is only available on Arch Linux"
        )

    logger.info("Searching for failed transactions")

    try:
        pacman_log = Path(PACMAN_LOG)

        if not pacman_log.exists():
            return create_error_response(
                "NotFound",
                f"Pacman log file not found at {PACMAN_LOG}"
            )

        failed_transactions = []
        error_keywords = ["error", "failed", "warning", "could not", "unable to", "conflict"]

        with open(pacman_log, 'r') as f:
            for line in f:
                line_lower = line.lower()

                # Check for error indicators
                if any(keyword in line_lower for keyword in error_keywords):
                    # Extract timestamp if available
                    timestamp_match = re.match(r'\[(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\]', line)
                    timestamp = ""
                    if timestamp_match:
                        timestamp = f"{timestamp_match.group(1)}T{timestamp_match.group(2)}:00"

                    # Extract severity
                    severity = "error" if "error" in line_lower or "failed" in line_lower else "warning"

                    failed_transactions.append({
                        "timestamp": timestamp,
                        "severity": severity,
                        "message": line.strip()
                    })

        # Limit to most recent 100 failures
        failed_transactions = failed_transactions[-100:]

        logger.info(f"Found {len(failed_transactions)} failed/warning entries")

        return {
            "count": len(failed_transactions),
            "has_failures": len(failed_transactions) > 0,
            "failures": failed_transactions
        }

    except Exception as e:
        logger.error(f"Failed to search for failures: {e}")
        return create_error_response(
            "LogParseError",
            f"Failed to search for failed transactions: {str(e)}"
        )


async def get_database_sync_history(limit: int = 20) -> Dict[str, Any]:
    """
    Get database synchronization history.
    Shows when 'pacman -Sy' was run.

    Args:
        limit: Maximum number of sync events to return (default 20)

    Returns:
        Dict with database sync history
    """
    if not IS_ARCH:
        return create_error_response(
            "NotSupported",
            "This feature is only available on Arch Linux"
        )

    logger.info(f"Getting database sync history (limit={limit})")

    try:
        pacman_log = Path(PACMAN_LOG)

        if not pacman_log.exists():
            return create_error_response(
                "NotFound",
                f"Pacman log file not found at {PACMAN_LOG}"
            )

        sync_events = []

        with open(pacman_log, 'r') as f:
            lines = f.readlines()

        # Process in reverse order for most recent first
        for line in reversed(lines):
            if len(sync_events) >= limit:
                break

            # Look for database synchronization entries
            if "synchronizing package lists" in line.lower() or "starting full system upgrade" in line.lower():
                timestamp_match = re.match(r'\[(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\]', line)
                
                if timestamp_match:
                    timestamp = f"{timestamp_match.group(1)}T{timestamp_match.group(2)}:00"
                    
                    event_type = "sync"
                    if "starting full system upgrade" in line.lower():
                        event_type = "full_upgrade"

                    sync_events.append({
                        "timestamp": timestamp,
                        "type": event_type,
                        "message": line.strip()
                    })

        logger.info(f"Found {len(sync_events)} sync events")

        return {
            "count": len(sync_events),
            "sync_events": sync_events
        }

    except Exception as e:
        logger.error(f"Failed to get sync history: {e}")
        return create_error_response(
            "LogParseError",
            f"Failed to get database sync history: {str(e)}"
        )

