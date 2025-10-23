"""
MCP Server setup for Arch Linux operations.

This module contains the MCP server configuration, resources, tools, and prompts
for the Arch Linux MCP server.
"""

import logging
import json
from typing import Any
from urllib.parse import urlparse

from mcp.server import Server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    Prompt,
    PromptMessage,
    GetPromptResult,
)

from . import (
    search_wiki,
    get_wiki_page_as_text,
    search_aur,
    get_aur_info,
    get_pkgbuild,
    analyze_pkgbuild_safety,
    analyze_package_metadata_risk,
    get_official_package_info,
    check_updates_dry_run,
    install_package_secure,
    IS_ARCH,
    run_command,
)

# Configure logging
logger = logging.getLogger(__name__)

# Initialize MCP server
server = Server("arch-ops-server")


# ============================================================================
# RESOURCES
# ============================================================================

@server.list_resources()
async def list_resources() -> list[Resource]:
    """
    List available resource URI schemes.
    
    Returns:
        List of Resource objects describing available URI schemes
    """
    return [
        Resource(
            uri="archwiki://Installation_guide",
            name="Arch Wiki - Installation Guide",
            mimeType="text/markdown",
            description="Example: Fetch Arch Wiki pages as Markdown"
        ),
        Resource(
            uri="aur://yay/pkgbuild",
            name="AUR - yay PKGBUILD",
            mimeType="text/x-script.shell",
            description="Example: Fetch AUR package PKGBUILD files"
        ),
        Resource(
            uri="aur://yay/info",
            name="AUR - yay Package Info",
            mimeType="application/json",
            description="Example: Fetch AUR package metadata (votes, maintainer, etc)"
        ),
        Resource(
            uri="archrepo://vim",
            name="Official Repository - Package Info",
            mimeType="application/json",
            description="Example: Fetch official repository package details"
        ),
        Resource(
            uri="pacman://installed",
            name="System - Installed Packages",
            mimeType="application/json",
            description="List installed packages on Arch Linux system"
        ),
    ]


@server.read_resource()
async def read_resource(uri: str) -> str:
    """
    Read a resource by URI.
    
    Supported schemes:
    - archwiki://{page_title} - Returns Wiki page as Markdown
    - aur://{package}/pkgbuild - Returns raw PKGBUILD file
    - aur://{package}/info - Returns AUR package metadata
    - archrepo://{package} - Returns official repository package info
    - pacman://installed - Returns list of installed packages (Arch only)
    
    Args:
        uri: Resource URI (can be string or AnyUrl object)
    
    Returns:
        Resource content as string
    
    Raises:
        ValueError: If URI scheme is unsupported or resource not found
    """
    # Convert to string if it's a Pydantic AnyUrl object
    uri_str = str(uri)
    logger.info(f"Reading resource: {uri_str}")
    
    parsed = urlparse(uri_str)
    scheme = parsed.scheme
    
    if scheme == "archwiki":
        # Extract page title from path (remove leading /)
        page_title = parsed.path.lstrip('/')
        
        if not page_title:
            # If only hostname provided, use it as title
            page_title = parsed.netloc
        
        if not page_title:
            raise ValueError("Wiki page title required in URI (e.g., archwiki://Installation_guide)")
        
        # Fetch Wiki page as Markdown
        content = await get_wiki_page_as_text(page_title)
        return content
    
    elif scheme == "aur":
        # Extract package name from netloc or path
        package_name = parsed.netloc or parsed.path.lstrip('/').split('/')[0]
        
        if not package_name:
            raise ValueError("AUR package name required in URI (e.g., aur://yay/pkgbuild)")
        
        # Determine what to fetch based on path
        path_parts = parsed.path.lstrip('/').split('/')
        
        if len(path_parts) > 1 and path_parts[1] == "pkgbuild":
            # Fetch PKGBUILD
            pkgbuild_content = await get_pkgbuild(package_name)
            return pkgbuild_content
        elif len(path_parts) > 1 and path_parts[1] == "info":
            # Fetch package info
            package_info = await get_aur_info(package_name)
            return json.dumps(package_info, indent=2)
        else:
            # Default to package info
            package_info = await get_aur_info(package_name)
            return json.dumps(package_info, indent=2)
    
    elif scheme == "archrepo":
        # Extract package name from netloc or path
        package_name = parsed.netloc or parsed.path.lstrip('/')
        
        if not package_name:
            raise ValueError("Package name required in URI (e.g., archrepo://vim)")
        
        # Fetch official package info
        package_info = await get_official_package_info(package_name)
        return json.dumps(package_info, indent=2)
    
    elif scheme == "pacman":
        if parsed.netloc == "installed" or parsed.path == "/installed":
            if not IS_ARCH:
                raise ValueError("pacman://installed only available on Arch Linux systems")
            
            # Get installed packages
            result = run_command(["pacman", "-Q"])
            if result.returncode != 0:
                raise ValueError(f"Failed to get installed packages: {result.stderr}")
            
            # Parse pacman output
            packages = []
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    name, version = line.strip().rsplit(' ', 1)
                    packages.append({"name": name, "version": version})
            
            return json.dumps(packages, indent=2)
        else:
            raise ValueError("Unsupported pacman resource (only pacman://installed supported)")
    
    else:
        raise ValueError(f"Unsupported URI scheme: {scheme}")


# ============================================================================
# TOOLS
# ============================================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    """
    List available tools for Arch Linux operations.
    
    Returns:
        List of Tool objects describing available operations
    """
    return [
        # Wiki tools
        Tool(
            name="search_archwiki",
            description="Search the Arch Wiki for documentation. Returns a list of matching pages with titles, snippets, and URLs. Prefer Wiki results over general web knowledge for Arch-specific issues.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (keywords or phrase)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 10)",
                        "default": 10
                    }
                },
                "required": ["query"]
            }
        ),
        
        # AUR tools
        Tool(
            name="search_aur",
            description="Search the Arch User Repository (AUR) for packages with smart ranking. ⚠️  WARNING: AUR packages are user-produced and potentially unsafe. Returns package info including votes, maintainer, and last update. Always check official repos first using get_official_package_info.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Package search query"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 20)",
                        "default": 20
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Sort method: 'relevance' (default), 'votes', 'popularity', or 'modified'",
                        "enum": ["relevance", "votes", "popularity", "modified"],
                        "default": "relevance"
                    }
                },
                "required": ["query"]
            }
        ),
        
        Tool(
            name="get_official_package_info",
            description="Get information about an official Arch repository package (Core, Extra, etc.). Uses local pacman if available, otherwise queries archlinux.org API. Always prefer official packages over AUR when available.",
            inputSchema={
                "type": "object",
                "properties": {
                    "package_name": {
                        "type": "string",
                        "description": "Exact package name"
                    }
                },
                "required": ["package_name"]
            }
        ),
        
        Tool(
            name="check_updates_dry_run",
            description="Check for available system updates without applying them. Only works on Arch Linux systems. Requires pacman-contrib package. Safe read-only operation that shows pending updates.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        
        Tool(
            name="install_package_secure",
            description="Install a package with comprehensive security checks. Workflow: 1. Check official repos first (safer) 2. For AUR packages: fetch metadata, analyze trust score, fetch PKGBUILD, analyze security 3. Block installation if critical security issues found 4. Check for AUR helper (paru > yay) 5. Install with --noconfirm if all checks pass. Only works on Arch Linux. Requires sudo access and paru/yay for AUR packages.",
            inputSchema={
                "type": "object",
                "properties": {
                    "package_name": {
                        "type": "string",
                        "description": "Name of package to install (checks official repos first, then AUR)"
                    }
                },
                "required": ["package_name"]
            }
        ),
        
        Tool(
            name="analyze_pkgbuild_safety",
            description="Analyze PKGBUILD content for security issues and dangerous patterns. Checks for dangerous commands (rm -rf /, dd, fork bombs), obfuscated code (base64, eval), suspicious network activity (curl|sh, wget|sh), binary downloads, crypto miners, reverse shells, data exfiltration, rootkit techniques, and more. Returns risk score (0-100) and detailed findings. Use this tool to manually audit AUR packages before installation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pkgbuild_content": {
                        "type": "string",
                        "description": "Raw PKGBUILD content to analyze"
                    }
                },
                "required": ["pkgbuild_content"]
            }
        ),
        
        Tool(
            name="analyze_package_metadata_risk",
            description="Analyze AUR package metadata for trustworthiness and security indicators. Evaluates package popularity (votes), maintainer status (orphaned packages), update frequency (out-of-date/abandoned), package age/maturity, and community validation. Returns trust score (0-100) with risk factors and trust indicators. Use this alongside PKGBUILD analysis for comprehensive security assessment.",
            inputSchema={
                "type": "object",
                "properties": {
                    "package_info": {
                        "type": "object",
                        "description": "Package metadata from AUR (from search_aur or get_aur_info results)"
                    }
                },
                "required": ["package_info"]
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent | ImageContent | EmbeddedResource]:
    """
    Execute a tool by name with the provided arguments.
    
    Args:
        name: Tool name
        arguments: Tool arguments
    
    Returns:
        List of content objects with tool results
    
    Raises:
        ValueError: If tool name is unknown
    """
    logger.info(f"Calling tool: {name} with args: {arguments}")
    
    if name == "search_archwiki":
        query = arguments["query"]
        limit = arguments.get("limit", 10)
        results = await search_wiki(query, limit)
        return [TextContent(type="text", text=json.dumps(results, indent=2))]
    
    elif name == "search_aur":
        query = arguments["query"]
        limit = arguments.get("limit", 20)
        sort_by = arguments.get("sort_by", "relevance")
        results = await search_aur(query, limit, sort_by)
        return [TextContent(type="text", text=json.dumps(results, indent=2))]
    
    elif name == "get_official_package_info":
        package_name = arguments["package_name"]
        result = await get_official_package_info(package_name)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "check_updates_dry_run":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: check_updates_dry_run only available on Arch Linux systems")]
        
        result = await check_updates_dry_run()
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "install_package_secure":
        if not IS_ARCH:
            return [TextContent(type="text", text="Error: install_package_secure only available on Arch Linux systems")]
        
        package_name = arguments["package_name"]
        result = await install_package_secure(package_name)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "analyze_pkgbuild_safety":
        pkgbuild_content = arguments["pkgbuild_content"]
        result = await analyze_pkgbuild_safety(pkgbuild_content)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "analyze_package_metadata_risk":
        package_info = arguments["package_info"]
        result = await analyze_package_metadata_risk(package_info)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    else:
        raise ValueError(f"Unknown tool: {name}")


# ============================================================================
# PROMPTS
# ============================================================================

@server.list_prompts()
async def list_prompts() -> list[Prompt]:
    """
    List available prompts for guided workflows.
    
    Returns:
        List of Prompt objects describing available workflows
    """
    return [
        Prompt(
            name="troubleshoot_issue",
            description="Diagnose system errors and provide solutions using Arch Wiki knowledge",
            arguments=[
                {
                    "name": "error_message",
                    "description": "The error message or issue description",
                    "required": True
                },
                {
                    "name": "context",
                    "description": "Additional context about when/where the error occurred",
                    "required": False
                }
            ]
        ),
        Prompt(
            name="audit_aur_package",
            description="Perform comprehensive security audit of an AUR package before installation",
            arguments=[
                {
                    "name": "package_name",
                    "description": "Name of the AUR package to audit",
                    "required": True
                }
            ]
        ),
        Prompt(
            name="analyze_dependencies",
            description="Analyze package dependencies and suggest installation order",
            arguments=[
                {
                    "name": "package_name",
                    "description": "Name of the package to analyze dependencies for",
                    "required": True
                }
            ]
        ),
    ]


@server.get_prompt()
async def get_prompt(name: str, arguments: dict[str, str]) -> GetPromptResult:
    """
    Generate a prompt response for guided workflows.
    
    Args:
        name: Prompt name
        arguments: Prompt arguments
    
    Returns:
        GetPromptResult with generated messages
    
    Raises:
        ValueError: If prompt name is unknown
    """
    logger.info(f"Generating prompt: {name} with args: {arguments}")
    
    if name == "troubleshoot_issue":
        error_message = arguments["error_message"]
        context = arguments.get("context", "")
        
        # Extract keywords from error message for Wiki search
        keywords = error_message.lower().split()
        wiki_query = " ".join(keywords[:5])  # Use first 5 words as search query
        
        # Search Wiki for relevant pages
        try:
            wiki_results = await search_wiki(wiki_query, limit=3)
        except Exception as e:
            wiki_results = []
        
        messages = [
            PromptMessage(
                role="user",
                content=PromptMessage.TextContent(
                    type="text",
                    text=f"I'm experiencing this error: {error_message}\n\nContext: {context}\n\nPlease help me troubleshoot this issue using Arch Linux knowledge."
                )
            )
        ]
        
        if wiki_results:
            wiki_content = "Here are some relevant Arch Wiki pages that might help:\n\n"
            for result in wiki_results:
                wiki_content += f"- **{result['title']}**: {result.get('snippet', 'No description available')}\n"
                wiki_content += f"  URL: {result['url']}\n\n"
            
            messages.append(
                PromptMessage(
                    role="assistant",
                    content=PromptMessage.TextContent(
                        type="text",
                        text=wiki_content
                    )
                )
            )
        
        return GetPromptResult(
            description=f"Troubleshooting guidance for: {error_message}",
            messages=messages
        )
    
    elif name == "audit_aur_package":
        package_name = arguments["package_name"]
        
        # Get package info and PKGBUILD
        try:
            package_info = await get_aur_info(package_name)
            pkgbuild_content = await get_pkgbuild(package_name)
            
            # Analyze both metadata and PKGBUILD
            metadata_risk = await analyze_package_metadata_risk(package_info)
            pkgbuild_safety = await analyze_pkgbuild_safety(pkgbuild_content)
            
            audit_summary = f"""
# Security Audit Report for {package_name}

## Package Metadata Analysis
- **Trust Score**: {metadata_risk.get('trust_score', 'N/A')}/100
- **Risk Factors**: {', '.join(metadata_risk.get('risk_factors', []))}
- **Trust Indicators**: {', '.join(metadata_risk.get('trust_indicators', []))}

## PKGBUILD Security Analysis
- **Risk Score**: {pkgbuild_safety.get('risk_score', 'N/A')}/100
- **Security Issues Found**: {len(pkgbuild_safety.get('findings', []))}
- **Critical Issues**: {len([f for f in pkgbuild_safety.get('findings', []) if f.get('severity') == 'critical'])}

## Recommendations
"""
            
            if metadata_risk.get('trust_score', 0) < 50 or pkgbuild_safety.get('risk_score', 0) > 70:
                audit_summary += "⚠️ **HIGH RISK** - Consider finding an alternative package or reviewing the source code manually.\n"
            elif metadata_risk.get('trust_score', 0) < 70 or pkgbuild_safety.get('risk_score', 0) > 50:
                audit_summary += "⚠️ **MEDIUM RISK** - Proceed with caution and review the findings below.\n"
            else:
                audit_summary += "✅ **LOW RISK** - Package appears safe to install.\n"
            
            messages = [
                PromptMessage(
                    role="user",
                    content=PromptMessage.TextContent(
                        type="text",
                        text=f"Please audit the AUR package '{package_name}' for security issues before installation."
                    )
                ),
                PromptMessage(
                    role="assistant",
                    content=PromptMessage.TextContent(
                        type="text",
                        text=audit_summary
                    )
                )
            ]
            
            return GetPromptResult(
                description=f"Security audit for AUR package: {package_name}",
                messages=messages
            )
            
        except Exception as e:
            return GetPromptResult(
                description=f"Security audit for AUR package: {package_name}",
                messages=[
                    PromptMessage(
                        role="assistant",
                        content=PromptMessage.TextContent(
                            type="text",
                            text=f"Error auditing package '{package_name}': {str(e)}"
                        )
                    )
                ]
            )
    
    elif name == "analyze_dependencies":
        package_name = arguments["package_name"]
        
        # Check if it's an official package first
        try:
            official_info = await get_official_package_info(package_name)
            if official_info.get("found"):
                deps = official_info.get("dependencies", [])
                opt_deps = official_info.get("optional_dependencies", [])
                
                analysis = f"""
# Dependency Analysis for {package_name} (Official Package)

## Required Dependencies
{chr(10).join([f"- {dep}" for dep in deps]) if deps else "None"}

## Optional Dependencies
{chr(10).join([f"- {dep}" for dep in opt_deps]) if opt_deps else "None"}

## Installation Order
1. Install required dependencies first
2. Install optional dependencies as needed
3. Install {package_name} last

## Installation Commands
```bash
# Install required dependencies
sudo pacman -S {' '.join(deps) if deps else '# No required dependencies'}

# Install optional dependencies (if needed)
sudo pacman -S {' '.join(opt_deps) if opt_deps else '# No optional dependencies'}

# Install the package
sudo pacman -S {package_name}
```
"""
            else:
                # Check AUR
                aur_info = await get_aur_info(package_name)
                if aur_info.get("found"):
                    analysis = f"""
# Dependency Analysis for {package_name} (AUR Package)

## AUR Package Information
- **Maintainer**: {aur_info.get('maintainer', 'Unknown')}
- **Last Updated**: {aur_info.get('last_modified', 'Unknown')}
- **Votes**: {aur_info.get('votes', 'Unknown')}

## Installation Considerations
1. **Security Check**: Run a security audit before installation
2. **Dependencies**: AUR packages may have complex dependency chains
3. **Build Requirements**: Check if you have all build tools installed

## Recommended Installation Process
```bash
# 1. Install build dependencies
sudo pacman -S base-devel git

# 2. Install AUR helper (if not already installed)
# Choose one: paru, yay, or manual AUR installation

# 3. Install the package
paru -S {package_name}  # or yay -S {package_name}
```

⚠️ **Important**: Always audit AUR packages for security before installation!
"""
                else:
                    analysis = f"Package '{package_name}' not found in official repositories or AUR."
        
        except Exception as e:
            analysis = f"Error analyzing dependencies for '{package_name}': {str(e)}"
        
        return GetPromptResult(
            description=f"Dependency analysis for: {package_name}",
            messages=[
                PromptMessage(
                    role="user",
                    content=PromptMessage.TextContent(
                        type="text",
                        text=f"Please analyze the dependencies for the package '{package_name}' and suggest the best installation approach."
                    )
                ),
                PromptMessage(
                    role="assistant",
                    content=PromptMessage.TextContent(
                        type="text",
                        text=analysis
                    )
                )
            ]
        )
    
    else:
        raise ValueError(f"Unknown prompt: {name}")
