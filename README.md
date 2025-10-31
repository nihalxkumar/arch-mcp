# Arch Linux MCP Server

<a href="https://glama.ai/mcp/servers/@nihalxkumar/arch-mcp">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@nihalxkumar/arch-mcp/badge" />
</a>

**Disclaimer:** Unofficial community project, not affiliated with Arch Linux.

A [Model Context Protocol](https://modelcontextprotocol.io/) (MCP) server that bridges AI assistants with the Arch Linux ecosystem. Enables intelligent, safe, and efficient access to the Arch Wiki, AUR, and official repositories for AI-assisted Arch Linux usage on Arch and non-Arch systems.

Leverage AI to get  output for digestible, structured results that are ready for follow up questions and actions.

📖 [Complete Documentation with Comfy Guides](https://nxk.mintlify.app/arch-mcp)

## Sneak Peak into what's available

Example Usage: [Prompts](https://nxk.mintlify.app/arch-mcp/examples)

### Resources (URI-based Access)

Direct access to Arch ecosystem data via custom URI schemes:

| URI Scheme | Example | Returns |
|------------|---------|---------|
| `archwiki://` | `archwiki://Installation_guide` | Markdown-formatted Wiki page |
| `aur://*/pkgbuild` | `aur://yay/pkgbuild` | Raw PKGBUILD with safety analysis |
| `aur://*/info` | `aur://yay/info` | AUR package metadata (votes, maintainer, dates) |
| `archrepo://` | `archrepo://vim` | Official repository package details |
| `pacman://installed` | `pacman://installed` | System installed packages list (Arch only) |

### Tools (Executable Functions)

| Category | Tool | Description | Key Features |
|----------|------|-------------|--------------|
| **Search** | `search_archwiki` | Query Arch Wiki documentation | Ranked results, keyword extraction |
| | `search_aur` | Search AUR packages | Smart ranking: relevance/votes/popularity/modified |
| | `get_official_package_info` | Lookup official packages | Hybrid local/remote, detailed metadata |
| **System** | `check_updates_dry_run` | Check for updates (Arch only) | Read-only, safe, requires pacman-contrib |
| **Installation** | `install_package_secure` | Secure package installation | Auto security checks, blocks malicious packages, uses paru/yay |
| **Security** | `analyze_pkgbuild_safety` | Comprehensive PKGBUILD analysis | Detects: malicious commands based on 50+ red flags |
| | `analyze_package_metadata_risk` | Package trust evaluation | Analyzes: votes, maintainer, age, updates, trust scoring |

### Prompts (Guided Workflows)

| Prompt | Purpose | Workflow |
|--------|---------|----------|
| `troubleshoot_issue` | Diagnose system errors | Extract keywords → Search Wiki → Context-aware suggestions |
| `audit_aur_package` | Pre-installation safety audit | Fetch metadata → Analyze PKGBUILD → Security recommendations |
| `analyze_dependencies` | Installation planning | Check repos → Map dependencies → Suggest install order |

---

## Installation

### Prerequisites
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### Quick Install with `uvx`

```bash
uvx arch-ops-server
```

---

## Configuration

Claude / Cursor / Any MCP client that supports STDIO transport

```json
{
  "mcpServers": {
    "arch-ops": {
      "command": "uvx",
      "args": ["arch-ops-server"]
    }
  }
}
```

## Contributing

Contributions are greatly appreciated. Please feel free to submit a pull request or open an issue and help make things better for everyone.

[Contributing Guide](https://nxk.mintlify.app/arch-mcp/contributing)

## License

[GPL-3.0-only](https://www.gnu.org/licenses/gpl-3.0.en.html)