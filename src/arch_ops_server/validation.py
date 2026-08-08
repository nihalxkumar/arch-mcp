# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
Input validation for values that reach a subprocess argument vector.

Commands are executed with ``asyncio.create_subprocess_exec`` and an argv list,
so there is no shell to inject into. The risk this module addresses is different:
pacman parses options anywhere in its argument list, so an unvalidated
"package name" such as ``--dbpath=/tmp/evil`` or ``-Rdd`` changes what the
command does. Call sites additionally place a ``--`` end-of-options separator
before user-supplied values; validation here is the second layer.
"""

import ipaddress
import re
import socket
from typing import Iterable, List
from urllib.parse import urlparse

# pacman accepts alphanumerics plus '@', '.', '_', '+' and '-' in package names.
# A leading '-' is excluded by construction so a name can never look like a flag.
# An optional 'repo/' prefix is allowed because 'core/linux' is ordinary usage.
_PACKAGE_NAME = re.compile(r"^(?:[a-zA-Z0-9_][a-zA-Z0-9._-]*/)?[a-zA-Z0-9@._+][a-zA-Z0-9@._+-]*$")

# Package groups follow the same naming rules, without the repo prefix.
_GROUP_NAME = re.compile(r"^[a-zA-Z0-9@._+][a-zA-Z0-9@._+-]*$")

# Cap batch operations so a single call cannot build an unbounded argv.
MAX_PACKAGES = 256

# Longest package name in the repos is well under this; the bound is a sanity check.
MAX_NAME_LENGTH = 256


class ValidationError(ValueError):
    """Raised when an argument is not safe to place in an argument vector."""


def _reject_control_characters(value: str, kind: str) -> None:
    """Reject NUL and newlines, which corrupt argv and log output respectively."""
    if "\x00" in value:
        raise ValidationError(f"{kind} may not contain a null byte")
    if "\n" in value or "\r" in value:
        raise ValidationError(f"{kind} may not contain a newline")


def validate_package_name(name: str) -> str:
    """
    Validate a single package name.

    Args:
        name: Candidate package name, optionally 'repo/'-qualified.

    Returns:
        The name unchanged, once validated.

    Raises:
        ValidationError: If the name could be parsed by pacman as an option or
            is otherwise not a well-formed package name.
    """
    if not isinstance(name, str):
        raise ValidationError(f"package name must be a string, got {type(name).__name__}")

    if not name:
        raise ValidationError("package name may not be empty")

    _reject_control_characters(name, "package name")

    if len(name) > MAX_NAME_LENGTH:
        raise ValidationError(f"package name exceeds {MAX_NAME_LENGTH} characters")

    if not _PACKAGE_NAME.match(name):
        raise ValidationError(
            f"invalid package name: {name!r}. Names may contain letters, digits and "
            "'@', '.', '_', '+', '-', may not begin with '-', and may carry an "
            "optional 'repo/' prefix."
        )

    return name


def validate_package_names(names: Iterable[str]) -> List[str]:
    """
    Validate a list of package names for a batch operation.

    Args:
        names: Candidate package names.

    Returns:
        The names as a list, once every entry is validated.

    Raises:
        ValidationError: If the list is empty, too long, or any entry is invalid.
    """
    validated = [validate_package_name(name) for name in names]

    if not validated:
        raise ValidationError("no packages specified")

    if len(validated) > MAX_PACKAGES:
        raise ValidationError(
            f"too many packages in one operation ({len(validated)} > {MAX_PACKAGES})"
        )

    return validated


def validate_group_name(name: str) -> str:
    """
    Validate a package group name.

    Args:
        name: Candidate group name.

    Returns:
        The name unchanged, once validated.

    Raises:
        ValidationError: If the name is not a well-formed group name.
    """
    if not isinstance(name, str):
        raise ValidationError(f"group name must be a string, got {type(name).__name__}")

    if not name:
        raise ValidationError("group name may not be empty")

    _reject_control_characters(name, "group name")

    if len(name) > MAX_NAME_LENGTH:
        raise ValidationError(f"group name exceeds {MAX_NAME_LENGTH} characters")

    if not _GROUP_NAME.match(name):
        raise ValidationError(
            f"invalid group name: {name!r}. Names may contain letters, digits and "
            "'@', '.', '_', '+', '-', and may not begin with '-'."
        )

    return name


def validate_file_path(path: str) -> str:
    """
    Validate a filesystem path passed to a pacman query.

    Paths legitimately contain characters a package name may not, so this only
    rejects values that would corrupt argv. A leading '-' is harmless because
    call sites pass '--' before the path.

    Args:
        path: Candidate filesystem path.

    Returns:
        The path unchanged, once validated.

    Raises:
        ValidationError: If the path is empty or contains control characters.
    """
    if not isinstance(path, str):
        raise ValidationError(f"file path must be a string, got {type(path).__name__}")

    if not path:
        raise ValidationError("file path may not be empty")

    _reject_control_characters(path, "file path")

    if len(path) > 4096:
        raise ValidationError("file path exceeds 4096 characters")

    return path


def validate_glob_pattern(pattern: str) -> str:
    """
    Validate a filename glob pattern used for package file searches.

    Glob metacharacters are the point of the value, so they are permitted; only
    argv-corrupting characters are rejected.

    Args:
        pattern: Candidate glob pattern.

    Returns:
        The pattern unchanged, once validated.

    Raises:
        ValidationError: If the pattern is empty or contains control characters.
    """
    if not isinstance(pattern, str):
        raise ValidationError(f"pattern must be a string, got {type(pattern).__name__}")

    if not pattern:
        raise ValidationError("pattern may not be empty")

    _reject_control_characters(pattern, "pattern")

    if len(pattern) > 1024:
        raise ValidationError("pattern exceeds 1024 characters")

    return pattern


def validate_public_url(url: str) -> str:
    """
    Validate a caller-supplied URL before the server fetches it.

    Without this, a tool that accepts a URL becomes a probe for whatever the
    host can reach that the caller cannot: loopback services, link-local
    metadata endpoints, and other machines on the local network.

    Args:
        url: Candidate URL.

    Returns:
        The URL unchanged, once validated.

    Raises:
        ValidationError: If the scheme is not http(s), the host is missing, or
            the host resolves to a non-public address.
    """
    if not isinstance(url, str) or not url:
        raise ValidationError("URL may not be empty")

    _reject_control_characters(url, "URL")

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValidationError(
            f"unsupported URL scheme {parsed.scheme!r}; only http and https are allowed"
        )

    host = parsed.hostname
    if not host:
        raise ValidationError("URL has no host")

    try:
        resolved = socket.getaddrinfo(host, None)
    except socket.gaierror:
        # A name we cannot resolve is a name the HTTP client cannot reach
        # either, since it uses the same resolver. Allowing it here blocks
        # nothing and lets the fetch report the real failure.
        return url

    # Every address the name resolves to must be public, so a name that maps to
    # both a public and a private address is still rejected.
    for family, _, _, _, sockaddr in resolved:
        address = ipaddress.ip_address(sockaddr[0])
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
            or address.is_unspecified
        ):
            raise ValidationError(
                f"host {host!r} resolves to the non-public address {address}; "
                "refusing to fetch it"
            )

    return url


__all__ = [
    "ValidationError",
    "MAX_PACKAGES",
    "validate_package_name",
    "validate_package_names",
    "validate_group_name",
    "validate_file_path",
    "validate_glob_pattern",
    "validate_public_url",
]
