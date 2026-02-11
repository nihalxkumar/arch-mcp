# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
AUR (Arch User Repository) interface module.
Provides search, package info, and PKGBUILD retrieval via AUR RPC v5.
"""

import logging
from typing import Dict, Any, List, Optional, Literal
import httpx
from datetime import datetime

from .utils import (
    create_error_response, 
    add_aur_warning, 
    get_aur_helper,
    IS_ARCH,
    run_command
)

logger = logging.getLogger(__name__)

# AUR API endpoints
AUR_RPC_URL = "https://aur.archlinux.org/rpc"
AUR_CGIT_BASE_URL = "https://aur.archlinux.org/cgit/aur.git/plain"  # No cloning - direct file access via web

# HTTP client settings
DEFAULT_TIMEOUT = 10.0
MAX_RESULTS = 50  # AUR RPC limit


async def search_aur(query: str, limit: int = 20, sort_by: str = "relevance") -> Dict[str, Any]:
    """
    Search AUR packages using RPC v5 interface with smart ranking.
    
    Args:
        query: Search term (searches name and description)
        limit: Maximum results to return (default: 20, max: 50)
        sort_by: Sorting method - "relevance", "votes", "popularity", "modified" (default: relevance)
    
    Returns:
        Dict with AUR packages and safety warning
    """
    logger.info(f"Searching AUR for: {query} (sort: {sort_by})")
    
    # Clamp limit
    limit = min(limit, MAX_RESULTS)
    
    params = {
        "v": "5",
        "type": "search",
        "arg": query
    }
    
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(AUR_RPC_URL, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("type") == "error":
                return create_error_response(
                    "AURError",
                    data.get("error", "Unknown AUR error")
                )
            
            results = data.get("results", [])
            
            # Apply smart ranking based on sort_by parameter
            sorted_results = _apply_smart_ranking(results, query, sort_by)
            
            # Limit and format results
            formatted_results = [
                _format_package_info(pkg)
                for pkg in sorted_results[:limit]
            ]
            
            logger.info(f"Found {len(formatted_results)} AUR packages for '{query}'")
            
            # Wrap with safety warning
            return add_aur_warning({
                "query": query,
                "count": len(formatted_results),
                "total_found": len(results),
                "sort_by": sort_by,
                "results": formatted_results
            })
            
    except httpx.TimeoutException:
        logger.error(f"AUR search timed out for query: {query}")
        return create_error_response(
            "TimeoutError",
            f"AUR search timed out for query: {query}",
            "The AUR server did not respond in time. Try again later."
        )
    except httpx.HTTPStatusError as e:
        # Handle rate limiting specifically
        if e.response.status_code == 429:
            logger.error("AUR rate limit exceeded")
            return create_error_response(
                "RateLimitError",
                "AUR rate limit exceeded",
                "Too many requests. Please wait before trying again."
            )
        logger.error(f"AUR search HTTP error: {e}")
        return create_error_response(
            "HTTPError",
            f"AUR search failed with status {e.response.status_code}",
            str(e)
        )
    except Exception as e:
        logger.error(f"AUR search failed: {e}")
        return create_error_response(
            "SearchError",
            f"Failed to search AUR: {str(e)}"
        )


async def get_aur_info(package_name: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific AUR package.
    
    Args:
        package_name: Exact package name
    
    Returns:
        Dict with package details and safety warning
    """
    logger.info(f"Fetching AUR info for: {package_name}")
    
    params = {
        "v": "5",
        "type": "info",
        "arg[]": package_name
    }
    
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(AUR_RPC_URL, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("type") == "error":
                return create_error_response(
                    "AURError",
                    data.get("error", "Unknown AUR error")
                )
            
            results = data.get("results", [])
            
            if not results:
                return create_error_response(
                    "NotFound",
                    f"AUR package '{package_name}' not found"
                )
            
            package_info = _format_package_info(results[0], detailed=True)
            
            logger.info(f"Successfully fetched info for {package_name}")
            
            # Wrap with safety warning
            return add_aur_warning(package_info)
            
    except httpx.TimeoutException:
        logger.error(f"AUR info fetch timed out for: {package_name}")
        return create_error_response(
            "TimeoutError",
            f"AUR info fetch timed out for package: {package_name}"
        )
    except httpx.HTTPStatusError as e:
        logger.error(f"AUR info HTTP error: {e}")
        return create_error_response(
            "HTTPError",
            f"AUR info fetch failed with status {e.response.status_code}",
            str(e)
        )
    except Exception as e:
        logger.error(f"AUR info fetch failed: {e}")
        return create_error_response(
            "InfoError",
            f"Failed to get AUR package info: {str(e)}"
        )


async def get_aur_file(package_name: str, filename: str = "PKGBUILD") -> str:
    """
    Fetch any file from an AUR package via cgit web interface (no cloning required).
    
    Uses AUR's cgit interface to fetch files directly via HTTP, avoiding the need
    to clone the entire git repository.
    
    Args:
        package_name: Package name
        filename: File to fetch (default: "PKGBUILD")
                  Common files: "PKGBUILD", ".SRCINFO", ".install", "*.patch"
    
    Returns:
        Raw file content as string
    
    Raises:
        ValueError: If file cannot be retrieved
    
    Examples:
        >>> pkgbuild = await get_aur_file("yay", "PKGBUILD")
        >>> srcinfo = await get_aur_file("yay", ".SRCINFO")
    """
    logger.info(f"Fetching {filename} for package: {package_name}")
    
    # Construct cgit URL for the specific file
    # Format: https://aur.archlinux.org/cgit/aur.git/plain/{filename}?h={package_name}
    base_url = "https://aur.archlinux.org/cgit/aur.git/plain"
    url = f"{base_url}/{filename}?h={package_name}"
    
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            
            content = response.text
            
            # Basic validation - ensure we got actual content
            if not content or len(content) < 10:
                raise ValueError(f"Retrieved {filename} appears to be empty or invalid")
            
            logger.info(f"Successfully fetched {filename} for {package_name} ({len(content)} bytes)")
            
            return content
            
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            error_msg = f"{filename} not found for package '{package_name}'"
            logger.error(error_msg)
            raise ValueError(error_msg)
        else:
            logger.error(f"HTTP error fetching {filename}: {e}")
            raise ValueError(f"Failed to fetch {filename}: HTTP {e.response.status_code}")
    except httpx.TimeoutException:
        error_msg = f"Timeout fetching {filename} for {package_name}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    except Exception as e:
        logger.error(f"{filename} fetch failed: {e}")
        raise ValueError(f"Failed to fetch {filename}: {str(e)}")


async def get_pkgbuild(package_name: str) -> str:
    """
    Fetch the PKGBUILD file for an AUR package (no cloning required).
    
    This is a convenience wrapper around get_aur_file() specifically for PKGBUILDs.
    Uses AUR's cgit web interface to fetch the file directly via HTTP.
    
    Args:
        package_name: Package name
    
    Returns:
        Raw PKGBUILD content as string
    
    Raises:
        ValueError: If PKGBUILD cannot be retrieved
    """
    return await get_aur_file(package_name, "PKGBUILD")


def _format_package_info(pkg: Dict[str, Any], detailed: bool = False) -> Dict[str, Any]:
    """
    Format AUR package data into clean structure.
    
    Args:
        pkg: Raw package data from AUR RPC
        detailed: Include extended fields (default: False)
    
    Returns:
        Formatted package info dict
    """
    # Basic info always included
    info = {
        "name": pkg.get("Name"),
        "version": pkg.get("Version"),
        "description": pkg.get("Description"),
        "maintainer": pkg.get("Maintainer"),
        "votes": pkg.get("NumVotes", 0),
        "popularity": round(pkg.get("Popularity", 0.0), 2),
        "last_modified": _format_timestamp(pkg.get("LastModified")),
        "out_of_date": pkg.get("OutOfDate") is not None,
    }
    
    # Extended info for detailed view
    if detailed:
        info.update({
            "first_submitted": _format_timestamp(pkg.get("FirstSubmitted")),
            "url": pkg.get("URL"),
            "url_path": pkg.get("URLPath"),
            "package_base": pkg.get("PackageBase"),
            "depends": pkg.get("Depends", []),
            "makedepends": pkg.get("MakeDepends", []),
            "optdepends": pkg.get("OptDepends", []),
            "conflicts": pkg.get("Conflicts", []),
            "provides": pkg.get("Provides", []),
            "license": pkg.get("License", []),
            "keywords": pkg.get("Keywords", []),
        })
    
    return info


def _format_timestamp(timestamp: Optional[int]) -> Optional[str]:
    """
    Convert Unix timestamp to human-readable date.
    
    Args:
        timestamp: Unix timestamp
    
    Returns:
        ISO format date string or None
    """
    if timestamp is None:
        return None
    
    try:
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def analyze_package_metadata_risk(package_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze AUR package metadata for security and trustworthiness indicators.
    
    Evaluates:
    - Package popularity and community trust (votes)
    - Maintainer status (orphaned packages)
    - Update frequency (out-of-date, abandoned packages)
    - Package age and maturity
    - Maintainer history
    
    Args:
        package_info: Package info dict from AUR RPC (formatted or raw)
    
    Returns:
        Dict with metadata risk analysis including:
        - trust_score: 0-100 (higher = more trustworthy)
        - risk_factors: list of identified risks
        - trust_indicators: list of positive indicators
        - recommendation: trust recommendation
    """
    from datetime import datetime, timedelta
    
    risk_factors = []
    trust_indicators = []
    
    logger.debug(f"Analyzing metadata for package: {package_info.get('name', 'unknown')}")
    
    # ========================================================================
    # EXTRACT METADATA
    # ========================================================================
    votes = package_info.get("votes", package_info.get("NumVotes", 0))
    popularity = package_info.get("popularity", package_info.get("Popularity", 0.0))
    maintainer = package_info.get("maintainer", package_info.get("Maintainer"))
    out_of_date = package_info.get("out_of_date", package_info.get("OutOfDate"))
    last_modified = package_info.get("last_modified", package_info.get("LastModified"))
    first_submitted = package_info.get("first_submitted", package_info.get("FirstSubmitted"))
    
    # ========================================================================
    # ANALYZE VOTING/POPULARITY
    # ========================================================================
    if votes == 0:
        risk_factors.append({
            "category": "popularity",
            "severity": "HIGH",
            "issue": "Package has zero votes - untested by community"
        })
    elif votes < 5:
        risk_factors.append({
            "category": "popularity",
            "severity": "MEDIUM",
            "issue": f"Low vote count ({votes}) - limited community validation"
        })
    elif votes >= 50:
        trust_indicators.append({
            "category": "popularity",
            "indicator": f"High vote count ({votes}) - well-trusted by community"
        })
    elif votes >= 20:
        trust_indicators.append({
            "category": "popularity",
            "indicator": f"Moderate vote count ({votes}) - some community validation"
        })
    
    # Popularity scoring
    if popularity < 0.001:
        risk_factors.append({
            "category": "popularity",
            "severity": "MEDIUM",
            "issue": f"Very low popularity score ({popularity:.4f}) - rarely used"
        })
    elif popularity >= 1.0:
        trust_indicators.append({
            "category": "popularity",
            "indicator": f"High popularity score ({popularity:.2f}) - widely used"
        })
    
    # ========================================================================
    # ANALYZE MAINTAINER STATUS
    # ========================================================================
    if not maintainer or maintainer == "None":
        risk_factors.append({
            "category": "maintainer",
            "severity": "CRITICAL",
            "issue": "Package is ORPHANED - no active maintainer"
        })
    else:
        trust_indicators.append({
            "category": "maintainer",
            "indicator": f"Active maintainer: {maintainer}"
        })
    
    # ========================================================================
    # ANALYZE OUT-OF-DATE STATUS
    # ========================================================================
    if out_of_date:
        # Check if out_of_date is a boolean or timestamp
        if isinstance(out_of_date, bool) and out_of_date:
            risk_factors.append({
                "category": "maintenance",
                "severity": "MEDIUM",
                "issue": "Package is flagged as out-of-date"
            })
        elif isinstance(out_of_date, (int, float)):
            # It's a timestamp
            try:
                ood_date = datetime.fromtimestamp(out_of_date)
                ood_days = (datetime.now() - ood_date).days
                risk_factors.append({
                    "category": "maintenance",
                    "severity": "MEDIUM" if ood_days < 90 else "HIGH",
                    "issue": f"Out-of-date for {ood_days} days since {ood_date.strftime('%Y-%m-%d')}"
                })
            except Exception:
                risk_factors.append({
                    "category": "maintenance",
                    "severity": "MEDIUM",
                    "issue": "Package is flagged as out-of-date"
                })
    
    # ========================================================================
    # ANALYZE LAST MODIFICATION TIME
    # ========================================================================
    if last_modified:
        try:
            # Handle both timestamp formats
            if isinstance(last_modified, str):
                # Try to parse from formatted string
                last_mod_date = datetime.strptime(last_modified.split()[0], "%Y-%m-%d")
            else:
                # It's a Unix timestamp
                last_mod_date = datetime.fromtimestamp(last_modified)
            
            days_since_update = (datetime.now() - last_mod_date).days
            
            if days_since_update > 730:  # 2 years
                risk_factors.append({
                    "category": "maintenance",
                    "severity": "HIGH",
                    "issue": f"Not updated in {days_since_update} days (~{days_since_update//365} years) - possibly abandoned"
                })
            elif days_since_update > 365:  # 1 year
                risk_factors.append({
                    "category": "maintenance",
                    "severity": "MEDIUM",
                    "issue": f"Not updated in {days_since_update} days (~{days_since_update//365} year) - low activity"
                })
            elif days_since_update <= 30:
                trust_indicators.append({
                    "category": "maintenance",
                    "indicator": f"Recently updated ({days_since_update} days ago) - actively maintained"
                })
        except Exception as e:
            logger.debug(f"Failed to parse last_modified: {e}")
    
    # ========================================================================
    # ANALYZE PACKAGE AGE
    # ========================================================================
    if first_submitted:
        try:
            # Handle both timestamp formats
            if isinstance(first_submitted, str):
                first_submit_date = datetime.strptime(first_submitted.split()[0], "%Y-%m-%d")
            else:
                first_submit_date = datetime.fromtimestamp(first_submitted)
            
            package_age_days = (datetime.now() - first_submit_date).days
            
            if package_age_days < 7:
                risk_factors.append({
                    "category": "age",
                    "severity": "HIGH",
                    "issue": f"Very new package ({package_age_days} days old) - needs community review time"
                })
            elif package_age_days < 30:
                risk_factors.append({
                    "category": "age",
                    "severity": "MEDIUM",
                    "issue": f"New package ({package_age_days} days old) - limited track record"
                })
            elif package_age_days >= 365:
                trust_indicators.append({
                    "category": "age",
                    "indicator": f"Mature package ({package_age_days//365}+ years old) - established track record"
                })
        except Exception as e:
            logger.debug(f"Failed to parse first_submitted: {e}")
    
    # ========================================================================
    # CALCULATE TRUST SCORE
    # ========================================================================
    # Start with base score of 50
    trust_score = 50
    
    # Adjust based on votes (max +30)
    if votes >= 100:
        trust_score += 30
    elif votes >= 50:
        trust_score += 20
    elif votes >= 20:
        trust_score += 10
    elif votes >= 5:
        trust_score += 5
    elif votes == 0:
        trust_score -= 20
    
    # Adjust based on popularity (max +10)
    if popularity >= 5.0:
        trust_score += 10
    elif popularity >= 1.0:
        trust_score += 5
    elif popularity < 0.001:
        trust_score -= 10
    
    # Penalties for risk factors
    for risk in risk_factors:
        if risk["severity"] == "CRITICAL":
            trust_score -= 30
        elif risk["severity"] == "HIGH":
            trust_score -= 15
        elif risk["severity"] == "MEDIUM":
            trust_score -= 10
    
    # Clamp between 0 and 100
    trust_score = max(0, min(100, trust_score))
    
    # ========================================================================
    # GENERATE RECOMMENDATION
    # ========================================================================
    if trust_score >= 70:
        recommendation = "✅ TRUSTED - Package has good community validation and maintenance"
    elif trust_score >= 50:
        recommendation = "⚠️  MODERATE TRUST - Package is acceptable but verify PKGBUILD carefully"
    elif trust_score >= 30:
        recommendation = "⚠️  LOW TRUST - Package has significant risk factors, extra caution needed"
    else:
        recommendation = "❌ UNTRUSTED - Package has critical trust issues, avoid unless necessary"
    
    logger.info(f"Package metadata analysis: trust_score={trust_score}, "
                f"{len(risk_factors)} risk factors, {len(trust_indicators)} trust indicators")
    
    return {
        "trust_score": trust_score,
        "risk_factors": risk_factors,
        "trust_indicators": trust_indicators,
        "recommendation": recommendation,
        "summary": {
            "votes": votes,
            "popularity": round(popularity, 4),
            "is_orphaned": not maintainer or maintainer == "None",
            "is_out_of_date": bool(out_of_date),
            "total_risk_factors": len(risk_factors),
            "total_trust_indicators": len(trust_indicators)
        }
    }


def _apply_smart_ranking(
    packages: List[Dict[str, Any]], 
    query: str, 
    sort_by: str
) -> List[Dict[str, Any]]:
    """
    Apply smart ranking to AUR search results.
    
    Sorting methods:
    - relevance: Name match priority, then by votes and popularity
    - votes: Sort by number of votes (most popular first)
    - popularity: Sort by AUR popularity metric
    - modified: Sort by last modification date (most recent first)
    
    Args:
        packages: List of package dicts from AUR RPC
        query: Original search query for relevance scoring
        sort_by: Sorting method
    
    Returns:
        Sorted list of packages
    """
    if not packages:
        return packages
    
    query_lower = query.lower()
    
    # Relevance scoring: prioritize exact name matches, then partial matches
    if sort_by == "relevance":
        def relevance_score(pkg: Dict[str, Any]) -> tuple:
            name = pkg.get("Name", "").lower()
            votes = pkg.get("NumVotes", 0)
            popularity = pkg.get("Popularity", 0.0)
            
            # Scoring priority (negative for reverse sort):
            # 1. Exact name match (highest priority)
            # 2. Name starts with query
            # 3. Name contains query
            # 4. Then by votes and popularity
            exact_match = -1 if name == query_lower else 0
            starts_with = -1 if name.startswith(query_lower) else 0
            contains = -1 if query_lower in name else 0
            
            return (exact_match, starts_with, contains, -votes, -popularity)
        
        return sorted(packages, key=relevance_score)
    
    elif sort_by == "votes":
        return sorted(packages, key=lambda p: p.get("NumVotes", 0), reverse=True)
    
    elif sort_by == "popularity":
        return sorted(packages, key=lambda p: p.get("Popularity", 0.0), reverse=True)
    
    elif sort_by == "modified":
        return sorted(packages, key=lambda p: p.get("LastModified", 0), reverse=True)
    
    else:
        # Default to relevance if unknown sort method
        logger.warning(f"Unknown sort method: {sort_by}, using relevance")
        return _apply_smart_ranking(packages, query, "relevance")


async def install_package_secure(package_name: str) -> Dict[str, Any]:
    """
    Install a package with comprehensive security checks.
    
    Workflow:
    1. Check if package exists in official repos first (safer)
    2. For AUR packages:
       a. Fetch package metadata and analyze trust
       b. Fetch and analyze PKGBUILD for security issues
       c. Only proceed if security checks pass
    3. Check for AUR helper availability (paru > yay)
    4. Install with --noconfirm if all checks pass
    
    Args:
        package_name: Package name to install
    
    Returns:
        Dict with installation status and security analysis
    """
    logger.info(f"Starting secure installation workflow for: {package_name}")
    
    # Only supported on Arch Linux
    if not IS_ARCH:
        return create_error_response(
            "NotSupported",
            "Package installation is only supported on Arch Linux systems",
            "This server is not running on Arch Linux"
        )
    
    result = {
        "package": package_name,
        "installed": False,
        "security_checks": {},
        "messages": []
    }
    
    # ========================================================================
    # STEP 0: Verify sudo is configured properly
    # ========================================================================
    logger.info("[STEP 0/5] Verifying sudo configuration...")
    
    # Test if sudo password is cached or passwordless sudo is configured
    # Use skip_sudo_check=True to avoid recursive check
    test_exit_code, _, test_stderr = await run_command(
        ["sudo", "-n", "true"],
        timeout=5,
        check=False,
        skip_sudo_check=True
    )
    
    if test_exit_code != 0:
        result["messages"].append("⚠️  SUDO PASSWORD REQUIRED")
        result["messages"].append("")
        result["messages"].append("Package installation requires sudo privileges.")
        result["messages"].append("Please choose one of these options:")
        result["messages"].append("")
        result["messages"].append("Option 1: Configure passwordless sudo for pacman:")
        result["messages"].append("  sudo visudo -f /etc/sudoers.d/arch-package-install")
        result["messages"].append("  Add: your_username ALL=(ALL) NOPASSWD: /usr/bin/pacman")
        result["messages"].append("")
        result["messages"].append("Option 2: Cache sudo password temporarily:")
        result["messages"].append("  Run: sudo -v")
        result["messages"].append("  Then retry the installation")
        result["messages"].append("")
        result["messages"].append("Option 3: Install manually in terminal:")
        result["messages"].append(f"  sudo pacman -S {package_name}")
        result["security_checks"]["decision"] = "SUDO_REQUIRED"
        return result
    
    result["messages"].append("✅ Sudo privileges verified")
    
    # ========================================================================
    # STEP 1: Check if package is in official repos first
    # ========================================================================
    logger.info(f"[STEP 1/5] Checking if '{package_name}' is in official repos...")
    result["messages"].append("🔍 Checking official repositories first...")
    
    from .pacman import get_official_package_info
    official_pkg = await get_official_package_info(package_name)
    
    # If found in official repos, install directly with pacman
    if not official_pkg.get("error"):
        logger.info(f"Package '{package_name}' found in official repos - installing via pacman")
        result["messages"].append(f"✅ Package found in official repository: {official_pkg.get('repository', 'unknown')}")
        result["is_official"] = True
        result["security_checks"]["source"] = "official_repository"
        result["security_checks"]["risk_level"] = "LOW"
        result["security_checks"]["recommendation"] = "✅ SAFE - Official repository package"
        
        # Install using sudo pacman -S --noconfirm
        try:
            result["messages"].append("📦 Installing from official repository...")
            exit_code, stdout, stderr = await run_command(
                ["sudo", "pacman", "-S", "--noconfirm", package_name],
                timeout=300,  # 5 minutes for installation
                check=False
            )
            
            if exit_code == 0:
                result["installed"] = True
                result["messages"].append(f"✅ Successfully installed {package_name} from official repository")
                logger.info(f"Successfully installed official package: {package_name}")
            else:
                result["messages"].append(f"❌ Installation failed: {stderr}")
                logger.error(f"pacman installation failed: {stderr}")
                
                # Check for sudo password issues
                if "password" in stderr.lower() or "sudo" in stderr.lower():
                    result["messages"].append("")
                    result["messages"].append("⚠️  SUDO PASSWORD REQUIRED")
                    result["messages"].append("To enable passwordless installation, run one of these commands:")
                    result["messages"].append("1. For passwordless sudo (less secure):")
                    result["messages"].append("   sudo visudo -f /etc/sudoers.d/arch-package-install")
                    result["messages"].append("   Add: your_username ALL=(ALL) NOPASSWD: /usr/bin/pacman")
                    result["messages"].append("2. Or run the installation manually in your terminal:")
                    result["messages"].append(f"   sudo pacman -S {package_name}")
                
            result["install_output"] = stdout
            result["install_errors"] = stderr
            
            return result
            
        except Exception as e:
            logger.error(f"Installation failed: {e}")
            return create_error_response(
                "InstallError",
                f"Failed to install official package: {str(e)}"
            )
    
    # ========================================================================
    # STEP 2: Package is in AUR - fetch and analyze metadata
    # ========================================================================
    logger.info(f"[STEP 2/5] Package not in official repos - checking AUR...")
    result["messages"].append("⚠️  Package not in official repos - checking AUR...")
    result["is_official"] = False
    
    # Search AUR for package
    aur_info = await get_aur_info(package_name)
    
    if aur_info.get("error"):
        return create_error_response(
            "NotFound",
            f"Package '{package_name}' not found in official repos or AUR"
        )
    
    # Extract actual package data (may be wrapped in warning)
    pkg_data = aur_info.get("data", aur_info)
    result["messages"].append(f"📦 Found in AUR: {pkg_data.get('name')} v{pkg_data.get('version')}")
    
    # Analyze package metadata for trust
    logger.info(f"[STEP 3/5] Analyzing package metadata for trust indicators...")
    result["messages"].append("🔍 Analyzing package metadata (votes, maintainer, age)...")
    
    metadata_analysis = analyze_package_metadata_risk(pkg_data)
    result["security_checks"]["metadata_analysis"] = metadata_analysis
    result["messages"].append(f"📊 Trust Score: {metadata_analysis['trust_score']}/100")
    result["messages"].append(f"   {metadata_analysis['recommendation']}")
    
    # ========================================================================
    # STEP 3: Fetch and analyze PKGBUILD
    # ========================================================================
    logger.info(f"[STEP 4/5] Fetching and analyzing PKGBUILD for security issues...")
    result["messages"].append("🔍 Fetching PKGBUILD for security analysis...")
    
    try:
        pkgbuild_content = await get_pkgbuild(package_name)
        result["messages"].append(f"✅ PKGBUILD fetched ({len(pkgbuild_content)} bytes)")
        
        # Analyze PKGBUILD for security issues
        result["messages"].append("🛡️  Analyzing PKGBUILD for security threats...")
        pkgbuild_analysis = analyze_pkgbuild_safety(pkgbuild_content)
        result["security_checks"]["pkgbuild_analysis"] = pkgbuild_analysis
        result["messages"].append(f"🛡️  Risk Score: {pkgbuild_analysis['risk_score']}/100")
        result["messages"].append(f"   {pkgbuild_analysis['recommendation']}")
        
        # Log findings
        if pkgbuild_analysis["red_flags"]:
            result["messages"].append(f"   🚨 {len(pkgbuild_analysis['red_flags'])} CRITICAL issues found!")
            for flag in pkgbuild_analysis["red_flags"][:3]:  # Show first 3
                result["messages"].append(f"      - Line {flag['line']}: {flag['issue']}")
        
        if pkgbuild_analysis["warnings"]:
            result["messages"].append(f"   ⚠️  {len(pkgbuild_analysis['warnings'])} warnings found")
        
        # Check if package is safe to install
        if not pkgbuild_analysis["safe"]:
            result["messages"].append("❌ INSTALLATION BLOCKED - Security analysis failed")
            result["messages"].append("   Package has critical security issues and will NOT be installed")
            result["security_checks"]["decision"] = "BLOCKED"
            result["security_checks"]["reason"] = "Critical security issues detected in PKGBUILD"
            logger.warning(f"Installation blocked for {package_name} due to security issues")
            return result
        
        # Additional check for high-risk warnings
        if len(pkgbuild_analysis["warnings"]) >= 5:
            result["messages"].append("⚠️  HIGH RISK - Multiple suspicious patterns detected")
            result["messages"].append("   Manual review recommended before installation")
            result["security_checks"]["decision"] = "REVIEW_RECOMMENDED"
        
    except ValueError as e:
        logger.error(f"Failed to fetch PKGBUILD: {e}")
        return create_error_response(
            "FetchError",
            f"Failed to fetch PKGBUILD for security analysis: {str(e)}"
        )
    
    # ========================================================================
    # STEP 4: Check for AUR helper
    # ========================================================================
    logger.info(f"[STEP 5/5] Checking for AUR helper (paru/yay)...")
    result["messages"].append("🔧 Checking for AUR helper...")
    
    aur_helper = get_aur_helper()
    
    if not aur_helper:
        result["messages"].append("❌ No AUR helper found (paru or yay)")
        result["messages"].append("   Please install an AUR helper:")
        result["messages"].append("   - Recommended: paru (pacman -S paru)")
        result["messages"].append("   - Alternative: yay")
        result["security_checks"]["decision"] = "NO_HELPER"
        return result
    
    result["messages"].append(f"✅ Using AUR helper: {aur_helper}")
    result["aur_helper"] = aur_helper
    
    # ========================================================================
    # STEP 5: Install package with AUR helper
    # ========================================================================
    result["messages"].append(f"📦 Installing {package_name} via {aur_helper} (no confirmation)...")
    logger.info(f"Installing AUR package {package_name} with {aur_helper}")
    
    try:
        # Install with --noconfirm flag
        exit_code, stdout, stderr = await run_command(
            [aur_helper, "-S", "--noconfirm", package_name],
            timeout=600,  # 10 minutes for AUR package build
            check=False
        )
        
        if exit_code == 0:
            result["installed"] = True
            result["messages"].append(f"✅ Successfully installed {package_name} from AUR")
            result["security_checks"]["decision"] = "INSTALLED"
            logger.info(f"Successfully installed AUR package: {package_name}")
        else:
            result["messages"].append(f"❌ Installation failed with exit code {exit_code}")
            result["messages"].append(f"   Error: {stderr}")
            result["security_checks"]["decision"] = "INSTALL_FAILED"
            logger.error(f"AUR installation failed for {package_name}: {stderr}")
            
            # Check for sudo password issues
            if "password" in stderr.lower() or "sudo" in stderr.lower():
                result["messages"].append("")
                result["messages"].append("⚠️  SUDO PASSWORD REQUIRED")
                result["messages"].append("To enable passwordless installation for AUR packages:")
                result["messages"].append("1. For passwordless sudo for pacman:")
                result["messages"].append("   sudo visudo -f /etc/sudoers.d/arch-aur-install")
                result["messages"].append("   Add: your_username ALL=(ALL) NOPASSWD: /usr/bin/pacman")
                result["messages"].append("2. Or run the installation manually in your terminal:")
                result["messages"].append(f"   {aur_helper} -S {package_name}")
        
        result["install_output"] = stdout
        result["install_errors"] = stderr
        
    except Exception as e:
        logger.error(f"Installation failed: {e}")
        result["messages"].append(f"❌ Installation exception: {str(e)}")
        result["security_checks"]["decision"] = "INSTALL_ERROR"
    
    return result


def analyze_pkgbuild_safety(pkgbuild_content: str) -> Dict[str, Any]:
    """
    Perform comprehensive safety analysis on PKGBUILD content.
    
    Checks for:
    - Dangerous commands (rm -rf /, dd, fork bombs, etc.)
    - Obfuscated code (base64, eval, encoding tricks)
    - Network activity (reverse shells, data exfiltration)
    - Binary downloads and execution
    - Privilege escalation attempts
    - Cryptocurrency mining patterns
    - Source URL validation
    - Suspicious file operations
    
    Args:
        pkgbuild_content: Raw PKGBUILD text
    
    Returns:
        Dict with detailed safety analysis results including:
        - safe: boolean
        - red_flags: critical security issues
        - warnings: suspicious patterns
        - info: informational notices
        - risk_score: 0-100 (higher = more dangerous)
        - recommendation: action recommendation
    """
    import re
    from urllib.parse import urlparse
    
    red_flags = []  # Critical security issues
    warnings = []   # Suspicious but not necessarily malicious
    info = []       # Informational notices
    
    lines = pkgbuild_content.split('\n')
    logger.debug(f"Analyzing PKGBUILD with {len(lines)} lines")
    
    # ========================================================================
    # CRITICAL PATTERNS - Definitely malicious
    # ========================================================================
    dangerous_patterns = [
        # Destructive commands
        (r"rm\s+-rf\s+/[^a-zA-Z]", "CRITICAL: rm -rf / or /something detected - system destruction"),
        (r"\bdd\b.*if=/dev/(zero|random|urandom).*of=/dev/sd", "CRITICAL: dd overwriting disk detected"),
        (r":\(\)\{.*:\|:.*\}", "CRITICAL: Fork bomb detected"),
        (r"\bmkfs\.", "CRITICAL: Filesystem formatting detected"),
        (r"fdisk.*-w", "CRITICAL: Partition table modification detected"),
        
        # Reverse shells and backdoors
        (r"/dev/tcp/\d+\.\d+\.\d+\.\d+/\d+", "CRITICAL: Reverse shell via /dev/tcp detected"),
        (r"nc\s+-[^-]*e\s+/bin/(ba)?sh", "CRITICAL: Netcat reverse shell detected"),
        (r"bash\s+-i\s+>&\s+/dev/tcp/", "CRITICAL: Interactive reverse shell detected"),
        (r"python.*socket.*connect", "CRITICAL: Python socket connection (potential backdoor)"),
        (r"perl.*socket.*connect", "CRITICAL: Perl socket connection (potential backdoor)"),
        
        # Malicious downloads and execution
        (r"curl[^|]*\|\s*(ba)?sh", "CRITICAL: Piping curl to shell (remote code execution)"),
        (r"wget[^|]*\|\s*(ba)?sh", "CRITICAL: Piping wget to shell (remote code execution)"),
        (r"curl.*-o.*&&.*chmod\s+\+x.*&&\s*\./", "CRITICAL: Download, make executable, and run pattern"),
        
        # Crypto mining patterns
        (r"xmrig|minerd|cpuminer|ccminer", "CRITICAL: Cryptocurrency miner detected"),
        (r"stratum\+tcp://", "CRITICAL: Mining pool connection detected"),
        (r"--donate-level", "CRITICAL: XMRig miner option detected"),
        
        # Rootkit/malware installation
        (r"chattr\s+\+i", "CRITICAL: Making files immutable (rootkit technique)"),
        (r"/etc/ld\.so\.preload", "CRITICAL: LD_PRELOAD manipulation (rootkit technique)"),
        (r"HISTFILE=/dev/null", "CRITICAL: History clearing (covering tracks)"),
    ]
    
    # ========================================================================
    # SUSPICIOUS PATTERNS - Require careful review
    # ========================================================================
    suspicious_patterns = [
        # Obfuscation techniques
        (r"base64\s+-d", "Obfuscation: base64 decoding detected"),
        (r"xxd\s+-r", "Obfuscation: hex decoding detected"),
        (r"\beval\b", "Obfuscation: eval usage (can execute arbitrary code)"),
        (r"\$\(.*base64.*\)", "Obfuscation: base64 in command substitution"),
        (r"openssl\s+enc\s+-d", "Obfuscation: encrypted content decoding"),
        (r"echo.*\|.*sh", "Obfuscation: piping echo to shell"),
        (r"printf.*\|.*sh", "Obfuscation: piping printf to shell"),
        
        # Suspicious permissions and ownership
        (r"chmod\s+[0-7]*7[0-7]*7", "Dangerous: world-writable permissions"),
        (r"chown\s+root", "Suspicious: changing ownership to root"),
        (r"chmod\s+[u+]*s", "Suspicious: setuid/setgid (privilege escalation risk)"),
        
        # Suspicious file operations
        (r"mktemp.*&&.*chmod", "Suspicious: temp file creation with permission change"),
        (r">/dev/null\s+2>&1", "Suspicious: suppressing all output (hiding activity)"),
        (r"nohup.*&", "Suspicious: background process that persists"),
        
        # Network activity
        (r"curl.*-s.*-o", "Network: silent download detected"),
        (r"wget.*-q.*-O", "Network: quiet download detected"),
        (r"nc\s+-l", "Network: netcat listening mode (potential backdoor)"),
        (r"socat", "Network: socat usage (advanced networking tool)"),
        (r"ssh.*-R\s+\d+:", "Network: SSH reverse tunnel detected"),
        
        # Data exfiltration
        (r"curl.*-X\s+POST.*--data", "Data exfiltration: HTTP POST with data"),
        (r"tar.*\|.*ssh", "Data exfiltration: tar over SSH"),
        (r"scp.*-r.*\*", "Data exfiltration: recursive SCP"),
        
        # Systemd/init manipulation
        (r"systemctl.*enable.*\.service", "System: enabling systemd service"),
        (r"/etc/systemd/system/", "System: systemd unit file modification"),
        (r"update-rc\.d", "System: SysV init modification"),
        (r"@reboot", "System: cron job at reboot"),
        
        # Kernel module manipulation
        (r"modprobe", "System: kernel module loading"),
        (r"insmod", "System: kernel module insertion"),
        (r"/lib/modules/", "System: kernel module directory access"),
        
        # Compiler/build chain manipulation
        (r"gcc.*-fPIC.*-shared", "Build: creating shared library (could be malicious)"),
        (r"LD_PRELOAD=", "Build: LD_PRELOAD manipulation (function hijacking)"),
    ]
    
    # ========================================================================
    # INFORMATIONAL PATTERNS - Good to know but not necessarily bad
    # ========================================================================
    info_patterns = [
        (r"sudo\s+", "Info: sudo usage detected"),
        (r"git\s+clone", "Info: git clone detected"),
        (r"make\s+install", "Info: make install detected"),
        (r"pip\s+install", "Info: pip install detected"),
        (r"npm\s+install", "Info: npm install detected"),
        (r"cargo\s+install", "Info: cargo install detected"),
    ]
    
    # ========================================================================
    # SCAN PATTERNS LINE BY LINE
    # ========================================================================
    for i, line in enumerate(lines, 1):
        # Skip comments and empty lines for pattern matching
        stripped_line = line.strip()
        if stripped_line.startswith('#') or not stripped_line:
            continue
        
        # Check dangerous patterns (red flags)
        for pattern, message in dangerous_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                logger.warning(f"Red flag found at line {i}: {message}")
                red_flags.append({
                    "line": i,
                    "content": line.strip()[:100],  # Limit length for output
                    "issue": message,
                    "severity": "CRITICAL"
                })
        
        # Check suspicious patterns
        for pattern, message in suspicious_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                logger.info(f"Warning found at line {i}: {message}")
                warnings.append({
                    "line": i,
                    "content": line.strip()[:100],
                    "issue": message,
                    "severity": "WARNING"
                })
        
        # Check informational patterns
        for pattern, message in info_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                info.append({
                    "line": i,
                    "content": line.strip()[:100],
                    "issue": message,
                    "severity": "INFO"
                })
    
    # ========================================================================
    # ANALYZE SOURCE URLs
    # ========================================================================
    source_urls = re.findall(r'source=\([^)]+\)|source_\w+=\([^)]+\)', pkgbuild_content, re.MULTILINE)
    suspicious_domains = []
    
    # Known suspicious TLDs and patterns
    suspicious_tlds = ['.tk', '.ml', '.ga', '.cf', '.gq', '.cn', '.ru']
    suspicious_url_patterns = [
        (r'bit\.ly|tinyurl|shorturl', "URL shortener (hides true destination)"),
        (r'pastebin|hastebin|paste\.ee', "Paste site (common for malware hosting)"),
        (r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', "Raw IP address (suspicious)"),
    ]
    
    for source_block in source_urls:
        # Extract URLs from source array
        urls = re.findall(r'https?://[^\s\'"]+', source_block)
        
        for url in urls:
            try:
                parsed = urlparse(url)
                domain = parsed.netloc.lower()
                
                # Check for suspicious TLDs
                if any(domain.endswith(tld) for tld in suspicious_tlds):
                    warnings.append({
                        "line": 0,
                        "content": url,
                        "issue": f"Suspicious domain TLD: {domain}",
                        "severity": "WARNING"
                    })
                    suspicious_domains.append(domain)
                
                # Check for suspicious URL patterns
                for pattern, message in suspicious_url_patterns:
                    if re.search(pattern, url, re.IGNORECASE):
                        warnings.append({
                            "line": 0,
                            "content": url,
                            "issue": message,
                            "severity": "WARNING"
                        })
            except Exception as e:
                logger.debug(f"Failed to parse URL {url}: {e}")
    
    # ========================================================================
    # DETECT BINARY DOWNLOADS
    # ========================================================================
    binary_extensions = ['.bin', '.exe', '.AppImage', '.deb', '.rpm', '.jar', '.apk']
    for ext in binary_extensions:
        if ext in pkgbuild_content.lower():
            warnings.append({
                "line": 0,
                "content": "",
                "issue": f"Binary file type detected: {ext}",
                "severity": "WARNING"
            })
    
    # ========================================================================
    # CALCULATE RISK SCORE
    # ========================================================================
    # Risk scoring: red_flags = 50 points each, warnings = 5 points each, cap at 100
    risk_score = min(100, (len(red_flags) * 50) + (len(warnings) * 5))
    
    # ========================================================================
    # GENERATE RECOMMENDATION
    # ========================================================================
    if len(red_flags) > 0:
        recommendation = "❌ DANGEROUS - Critical security issues detected. DO NOT INSTALL."
        safe = False
    elif len(warnings) >= 5:
        recommendation = "⚠️  HIGH RISK - Multiple suspicious patterns detected. Review carefully before installing."
        safe = False
    elif len(warnings) > 0:
        recommendation = "⚠️  CAUTION - Some suspicious patterns detected. Manual review recommended."
        safe = True  # Technically safe but needs review
    else:
        recommendation = "✅ SAFE - No critical issues detected. Standard review still recommended."
        safe = True
    
    logger.info(f"PKGBUILD analysis complete: {len(red_flags)} red flags, {len(warnings)} warnings, risk score: {risk_score}")
    
    return {
        "safe": safe,
        "red_flags": red_flags,
        "warnings": warnings,
        "info": info,
        "risk_score": risk_score,
         "suspicious_domains": list(set(suspicious_domains)),
         "recommendation": recommendation,
         "summary": {
             "total_red_flags": len(red_flags),
             "total_warnings": len(warnings),
             "total_info": len(info),
             "lines_analyzed": len(lines)
         }
     }


async def audit_package_security(
    action: Literal["pkgbuild_analysis", "metadata_risk"],
    pkgbuild_content: Optional[str] = None,
    package_name: Optional[str] = None,
    package_info: Optional[dict] = None
) -> dict:
    """
    Unified security audit tool for AUR packages.
    
    Args:
        action: Type of security audit
        pkgbuild_content: PKGBUILD content (for pkgbuild_analysis)
        package_name: Package name (for metadata_risk)
        package_info: Pre-fetched package metadata (optional, for metadata_risk)
    
    Returns:
        Security analysis results
    """
    if action == "pkgbuild_analysis":
        if not pkgbuild_content:
            return create_error_response(
                "pkgbuild_content is required for pkgbuild_analysis",
                error_type="validation_error"
            )
        result = analyze_pkgbuild_safety(pkgbuild_content)
        result["action"] = "pkgbuild_analysis"
        return result
    
    elif action == "metadata_risk":
        if not package_name and not package_info:
            return create_error_response(
                "Either package_name or package_info is required for metadata_risk",
                error_type="validation_error"
            )
        
        if package_info:
            result = analyze_package_metadata_risk(package_info)
        else:
            # Fetch package info first
            search_result = await search_aur(package_name, limit=1)
            if "error" in search_result or not search_result.get("results"):
                return create_error_response(
                    f"Could not find package '{package_name}' in AUR",
                    error_type="not_found"
                )
            result = analyze_package_metadata_risk(search_result["results"][0])
        
        result["action"] = "metadata_risk"
        return add_aur_warning(result)
    
    else:
        return create_error_response(
            f"Unknown action: {action}",
            error_type="validation_error"
        )


__all__ = [
    "search_aur",
    "get_aur_info",
    "get_aur_file",
    "get_pkgbuild",
    "install_package_secure",
    "analyze_pkgbuild_safety",
    "analyze_package_metadata_risk",
    "audit_package_security",
]

