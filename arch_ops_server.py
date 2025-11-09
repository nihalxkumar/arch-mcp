#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only OR MIT
"""
Arch Linux MCP Server

Main entry point for the MCP server that provides:
- Resources: archwiki:// and aur:// URI schemes
- Tools: search_archwiki, search_aur, get_official_package_info, check_updates_dry_run
- Prompts: troubleshoot_issue, audit_aur_package
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
import mcp.server.stdio

from src.arch_ops_server import (
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
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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
        
        # Check if info or pkgbuild requested
        path_parts = parsed.path.lstrip('/').split('/')
        resource_type = path_parts[-1] if len(path_parts) > 1 else "pkgbuild"
        
        if resource_type == "info":
            # Fetch AUR package info (metadata)
            info = await get_aur_info(package_name)
            return json.dumps(info, indent=2)
        
        # Default: Fetch PKGBUILD
        pkgbuild = await get_pkgbuild(package_name)
        
        # Perform safety analysis
        safety_analysis = analyze_pkgbuild_safety(pkgbuild)
        
        # Create enhanced response with safety analysis
        response = {
            "package_name": package_name,
            "pkgbuild_content": pkgbuild,
            "safety_analysis": safety_analysis,
            "warning": "⚠️  AUR packages are user-produced and potentially unsafe. Review the safety analysis before installing."
        }
        
        return json.dumps(response, indent=2)
    
    elif scheme == "archrepo":
        # Extract package name from netloc or path
        package_name = parsed.netloc or parsed.path.lstrip('/')
        
        if not package_name:
            raise ValueError("Package name required in URI (e.g., archrepo://vim)")
        
        # Fetch official repository package info
        info = await get_official_package_info(package_name)
        return json.dumps(info, indent=2)
    
    elif scheme == "pacman":
        # Check resource type
        resource_type = parsed.netloc or parsed.path.lstrip('/')
        
        if resource_type == "installed":
            # List installed packages (Arch only)
            if not IS_ARCH:
                raise ValueError("pacman://installed requires Arch Linux system")
            
            # Use pacman to list installed packages
            result = await run_command("pacman -Q", timeout=30)
            
            if result.get("error"):
                raise ValueError(f"Failed to list installed packages: {result.get('error')}")
            
            # Parse output into list
            lines = result.get("output", "").strip().split('\n')
            packages = []
            for line in lines:
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 2:
                        packages.append({
                            "name": parts[0],
                            "version": parts[1]
                        })
            
            response = {
                "total": len(packages),
                "packages": packages
            }
            return json.dumps(response, indent=2)
        
        raise ValueError("pacman:// only supports 'installed' (e.g., pacman://installed)")
    
    else:
        raise ValueError(f"Unsupported URI scheme: {scheme}. Use 'archwiki://', 'aur://', 'archrepo://', or 'pacman://'")


# ============================================================================
# TOOLS
# ============================================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    """
    List available tools.
    
    Returns:
        List of Tool objects describing available functions
    """
    return [
        Tool(
            name="search_archwiki",
            description=(
                "Search the Arch Wiki for documentation. "
                "Returns a list of matching pages with titles, snippets, and URLs. "
                "Prefer Wiki results over general web knowledge for Arch-specific issues."
            ),
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
        Tool(
            name="search_aur",
            description=(
                "Search the Arch User Repository (AUR) for packages with smart ranking. "
                "⚠️  WARNING: AUR packages are user-produced and potentially unsafe. "
                "Returns package info including votes, maintainer, and last update. "
                "Always check official repos first using get_official_package_info."
            ),
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
            description=(
                "Get information about an official Arch repository package (Core, Extra, etc.). "
                "Uses local pacman if available, otherwise queries archlinux.org API. "
                "Always prefer official packages over AUR when available."
            ),
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
            description=(
                "Check for available system updates without applying them. "
                "Only works on Arch Linux systems. Requires pacman-contrib package. "
                "Safe read-only operation that shows pending updates."
            ),
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="analyze_pkgbuild_safety",
            description=(
                "Analyze PKGBUILD content for security issues and dangerous patterns. "
                "Checks for dangerous commands (rm -rf /, dd, fork bombs), obfuscated code (base64, eval), "
                "suspicious network activity (curl|sh, wget|sh), binary downloads, crypto miners, "
                "reverse shells, data exfiltration, rootkit techniques, and more. "
                "Returns risk score (0-100) and detailed findings. "
                "Use this tool to manually audit AUR packages before installation."
            ),
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
            description=(
                "Analyze AUR package metadata for trustworthiness and security indicators. "
                "Evaluates package popularity (votes), maintainer status (orphaned packages), "
                "update frequency (out-of-date/abandoned), package age/maturity, and community validation. "
                "Returns trust score (0-100) with risk factors and trust indicators. "
                "Use this alongside PKGBUILD analysis for comprehensive security assessment."
            ),
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
        Tool(
            name="install_package_secure",
            description=(
                "Install a package with comprehensive security checks. "
                "Workflow: "
                "1. Check official repos first (safer) "
                "2. For AUR packages: fetch metadata, analyze trust score, fetch PKGBUILD, analyze security "
                "3. Block installation if critical security issues found "
                "4. Check for AUR helper (paru > yay) "
                "5. Install with --noconfirm if all checks pass. "
                "Only works on Arch Linux. Requires sudo access and paru/yay for AUR packages."
            ),
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
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """
    Execute a tool by name.
    
    Args:
        name: Tool name
        arguments: Tool arguments as dict
    
    Returns:
        List of TextContent with results
    
    Raises:
        ValueError: If tool name is unknown
    """
    logger.info(f"Calling tool: {name} with args: {arguments}")
    
    if name == "search_archwiki":
        query = arguments.get("query")
        limit = arguments.get("limit", 10)
        
        result = await search_wiki(query, limit)
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    
    elif name == "search_aur":
        query = arguments.get("query")
        limit = arguments.get("limit", 20)
        sort_by = arguments.get("sort_by", "relevance")
        
        result = await search_aur(query, limit, sort_by)
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    
    elif name == "get_official_package_info":
        package_name = arguments.get("package_name")
        
        result = await get_official_package_info(package_name)
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    
    elif name == "check_updates_dry_run":
        result = await check_updates_dry_run()
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    
    elif name == "analyze_pkgbuild_safety":
        pkgbuild_content = arguments.get("pkgbuild_content")
        
        if not pkgbuild_content:
            raise ValueError("pkgbuild_content is required")
        
        result = analyze_pkgbuild_safety(pkgbuild_content)
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    
    elif name == "analyze_package_metadata_risk":
        package_info = arguments.get("package_info")
        
        if not package_info:
            raise ValueError("package_info is required")
        
        result = analyze_package_metadata_risk(package_info)
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    
    elif name == "install_package_secure":
        package_name = arguments.get("package_name")
        
        if not package_name:
            raise ValueError("package_name is required")
        
        result = await install_package_secure(package_name)
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    
    else:
        raise ValueError(f"Unknown tool: {name}")


# ============================================================================
# PROMPTS
# ============================================================================

@server.list_prompts()
async def list_prompts() -> list[Prompt]:
    """
    List available prompt templates.
    
    Returns:
        List of Prompt objects describing available workflows
    """
    return [
        Prompt(
            name="troubleshoot_issue",
            description=(
                "Help troubleshoot an Arch Linux system error. "
                "Workflow: Ask for error log → Search Wiki → Summarize findings"
            ),
            arguments=[
                {
                    "name": "error_message",
                    "description": "The error message or log output to troubleshoot",
                    "required": True
                }
            ]
        ),
        Prompt(
            name="audit_aur_package",
            description=(
                "Perform a safety audit on an AUR package before installation. "
                "Workflow: Get package info → Fetch PKGBUILD → Analyze for red flags"
            ),
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
            description=(
                "Analyze package dependencies for installation planning. "
                "Workflow: Get package info → List dependencies → Check availability → Suggest install order"
            ),
            arguments=[
                {
                    "name": "package_name",
                    "description": "Name of the package to analyze dependencies for",
                    "required": True
                },
                {
                    "name": "source",
                    "description": "Package source: 'official' or 'aur' (default: auto-detect)",
                    "required": False
                }
            ]
        ),
    ]


@server.get_prompt()
async def get_prompt(name: str, arguments: dict[str, str] | None) -> GetPromptResult:
    """
    Get a prompt template by name.
    
    Args:
        name: Prompt name
        arguments: Prompt arguments
    
    Returns:
        GetPromptResult with messages
    
    Raises:
        ValueError: If prompt name is unknown
    """
    logger.info(f"Getting prompt: {name} with args: {arguments}")
    
    if name == "troubleshoot_issue":
        error_message = arguments.get("error_message", "") if arguments else ""
        
        if not error_message:
            return GetPromptResult(
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=(
                                "Please provide the error message or log output you're experiencing. "
                                "I'll search the Arch Wiki for relevant documentation to help troubleshoot."
                            )
                        )
                    )
                ]
            )
        
        # Extract keywords from error message for Wiki search
        # Simple approach: take significant words
        keywords = " ".join([
            word for word in error_message.split()
            if len(word) > 3 and not word.startswith('-')
        ][:5])
        
        return GetPromptResult(
            description=f"Troubleshooting error: {error_message[:100]}...",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=(
                            f"I'm experiencing this error on my Arch Linux system:\n\n"
                            f"{error_message}\n\n"
                            f"Please help me troubleshoot by:\n"
                            f"1. Searching the Arch Wiki for relevant documentation using keywords: {keywords}\n"
                            f"2. Analyzing the error to identify the root cause\n"
                            f"3. Providing step-by-step solutions from the Wiki"
                        )
                    )
                )
            ]
        )
    
    elif name == "audit_aur_package":
        package_name = arguments.get("package_name", "") if arguments else ""
        
        if not package_name:
            return GetPromptResult(
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=(
                                "Please provide the AUR package name you want to audit. "
                                "I'll fetch the PKGBUILD and analyze it for potential security issues."
                            )
                        )
                    )
                ]
            )
        
        return GetPromptResult(
            description=f"Safety audit for AUR package: {package_name}",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=(
                            f"I want to install the AUR package '{package_name}'. "
                            f"Please perform a comprehensive security audit by:\n\n"
                            f"1. Getting package info using search_aur tool\n"
                            f"2. Analyzing package metadata using analyze_package_metadata_risk tool to check:\n"
                            f"   - Package popularity and community trust (votes)\n"
                            f"   - Maintainer status (orphaned packages)\n"
                            f"   - Update frequency (out-of-date/abandoned)\n"
                            f"   - Package age and maturity\n"
                            f"3. Fetching the PKGBUILD using aur://{package_name}/pkgbuild resource\n"
                            f"   (This resource automatically fetches via HTTP without cloning and includes safety analysis for:\n"
                            f"   - Dangerous commands (rm -rf /, dd, fork bombs, etc.)\n"
                            f"   - Obfuscated code (base64, eval, encoding tricks)\n"
                            f"   - Network activity (reverse shells, data exfiltration)\n"
                            f"   - Cryptocurrency miners\n"
                            f"   - Rootkit techniques\n"
                            f"   - Suspicious source URLs\n"
                            f"   - Binary downloads)\n"
                            f"4. Combining trust score and risk score for overall safety assessment\n"
                            f"5. Providing a clear recommendation on whether it's safe to install\n\n"
                            f"⚠️  Remember: AUR packages are user-produced and potentially unsafe."
                        )
                    )
                )
            ]
        )
    
    elif name == "analyze_dependencies":
        package_name = arguments.get("package_name", "") if arguments else ""
        source = arguments.get("source", "auto") if arguments else "auto"
        
        if not package_name:
            return GetPromptResult(
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=(
                                "Please provide the package name you want to analyze dependencies for. "
                                "I'll check both official repos and AUR to map out all dependencies."
                            )
                        )
                    )
                ]
            )
        
        return GetPromptResult(
            description=f"Dependency analysis for package: {package_name}",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=(
                            f"I want to install the package '{package_name}'. "
                            f"Please analyze its dependencies by:\n\n"
                            f"1. Checking if it's in official repos using get_official_package_info\n"
                            f"2. If not in official repos, search AUR using search_aur\n"
                            f"3. List all dependencies (depends, makedepends, optdepends)\n"
                            f"4. For each dependency, check which repo it's from (official vs AUR)\n"
                            f"5. Identify any circular dependencies or conflicts\n"
                            f"6. Calculate total download size if possible\n"
                            f"7. Suggest optimal installation order\n"
                            f"8. Warn about any AUR dependencies that need manual review\n\n"
                            f"Provide a clear summary with:\n"
                            f"- Total number of dependencies\n"
                            f"- Number from official repos vs AUR\n"
                            f"- Any security concerns\n"
                            f"- Recommended installation command(s)"
                        )
                    )
                )
            ]
        )
    
    else:
        raise ValueError(f"Unknown prompt: {name}")


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

async def main():
    """
    Main entry point for the MCP server.
    Runs the server using STDIO transport.
    """
    logger.info("Starting Arch Linux MCP Server")
    logger.info(f"Running on Arch Linux: {IS_ARCH}")
    
    # Run the server using STDIO
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

