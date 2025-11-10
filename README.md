# Arch Linux MCP Server

<a href="https://glama.ai/mcp/servers/@nihalxkumar/arch-mcp">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@nihalxkumar/arch-mcp/badge" />
</a>

**Disclaimer:** Unofficial community project, not affiliated with Arch Linux.

A [Model Context Protocol](https://modelcontextprotocol.io/) (MCP) server that bridges AI assistants with the Arch Linux ecosystem. Enables intelligent, safe, and efficient access to the Arch Wiki, AUR, and official repositories for AI-assisted Arch Linux usage on Arch and non-Arch systems.

Leverage AI to get  output for digestible, structured results that are ready for follow up questions and actions.

📖 [Complete Documentation with Comfy Guides](https://nxk.mintlify.app/arch-mcp)

## Sneak Peak into what's available

<details open>
<summary>Claude Desktop (no terminal)</summary>

![Claude Desktop Demo](assets/claudedesktop_signalcli.gif)

</details>

<details>
<summary>VS Code (with terminal)</summary>

![VS Code Demo](assets/vscode_notesnook.gif)

</details>

### Resources (URI-based Access)

Direct access to Arch ecosystem data via custom URI schemes:

| URI Scheme | Example | Returns |
|------------|---------|---------|
| `archwiki://` | `archwiki://Installation_guide` | Markdown-formatted Wiki page |
| `aur://*/pkgbuild` | `aur://yay/pkgbuild` | Raw PKGBUILD with safety analysis |
| `aur://*/info` | `aur://yay/info` | AUR package metadata (votes, maintainer, dates) |
| `archrepo://` | `archrepo://vim` | Official repository package details |
| `pacman://installed` | `pacman://installed` | System installed packages list (Arch only) |
| `pacman://orphans` | `pacman://orphans` | Orphaned packages (Arch only) |
| `pacman://explicit` | `pacman://explicit` | Explicitly installed packages (Arch only) |
| `pacman://groups` | `pacman://groups` | All package groups (Arch only) |
| `pacman://group/*` | `pacman://group/base-devel` | Packages in specific group (Arch only) |
| `system://info` | `system://info` | System information (kernel, memory, uptime) |
| `system://disk` | `system://disk` | Disk space usage statistics |
| `system://services/failed` | `system://services/failed` | Failed systemd services |
| `system://logs/boot` | `system://logs/boot` | Recent boot logs |

### Tools (Executable Functions)

| Category | Tool | Description | Key Features |
|----------|------|-------------|--------------|
| **Search** | `search_archwiki` | Query Arch Wiki documentation | Ranked results, keyword extraction |
| | `search_aur` | Search AUR packages | Smart ranking: relevance/votes/popularity/modified |
| | `get_official_package_info` | Lookup official packages | Hybrid local/remote, detailed metadata |
| **Updates** | `check_updates_dry_run` | Check for updates (Arch only) | Read-only, safe, requires pacman-contrib |
| **Installation** | `install_package_secure` | Secure package installation | Auto security checks, blocks malicious packages, uses paru/yay |
| **Removal** | `remove_package` | Remove single package | Options: with deps, forced removal |
| | `remove_packages_batch` | Remove multiple packages | Efficient batch operations |
| **Orphans** | `list_orphan_packages` | Find orphaned packages | Shows disk space usage |
| | `remove_orphans` | Clean orphaned packages | Dry-run mode, exclusion list |
| **Ownership** | `find_package_owner` | Find package owning a file | File-to-package mapping |
| | `list_package_files` | List files in package | Optional regex filtering |
| | `search_package_files` | Search files across packages | Requires `pacman -Fy` |
| **Verification** | `verify_package_integrity` | Check package file integrity | Detects modified/missing files |
| **Groups** | `list_package_groups` | List all package groups | e.g., base, base-devel |
| | `list_group_packages` | Show packages in group | Group member listing |
| **Install Reason** | `list_explicit_packages` | List user-installed packages | For backup/restore |
| | `mark_as_explicit` | Mark as explicitly installed | Prevent orphan removal |
| | `mark_as_dependency` | Mark as dependency | Allow orphan removal |
| **System Info** | `get_system_info` | Get system information | Kernel, memory, uptime |
| | `check_disk_space` | Check disk usage | Warns on low space |
| | `get_pacman_cache_stats` | Analyze package cache | Cache size and age |
| | `check_failed_services` | Find failed services | systemd service status |
| | `get_boot_logs` | Retrieve boot logs | journalctl output |
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

This project is dual-licensed under your choice of:

- **[GPL-3.0-only](https://www.gnu.org/licenses/gpl-3.0.en.html)** - See [LICENSE-GPL](LICENSE-GPL)
- **[MIT License](https://opensource.org/licenses/MIT)** - See [LICENSE-MIT](LICENSE-MIT)

You may use this software under the terms of either license. See [LICENSE](LICENSE) for more details.