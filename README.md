# Arch Linux MCP Server

[![PyPI Downloads](https://static.pepy.tech/personalized-badge/arch-ops-server?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLUE&right_color=BLACK&left_text=PyPi+Downloads)](https://pepy.tech/projects/arch-ops-server)

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

#### Documentation & Search
| URI Scheme | Example | Returns |
|------------|---------|---------|
| `archwiki://` | `archwiki://Installation_guide` | Markdown-formatted Wiki page |

#### Package Information
| URI Scheme | Example | Returns |
|------------|---------|---------|
| `archrepo://` | `archrepo://vim` | Official repository package details |
| `aur://*/info` | `aur://yay/info` | AUR package metadata (votes, maintainer, dates) |
| `aur://*/pkgbuild` | `aur://yay/pkgbuild` | Raw PKGBUILD with safety analysis |

#### System Packages (Arch only)
| URI Scheme | Example | Returns |
|------------|---------|---------|
| `pacman://installed` | `pacman://installed` | System installed packages list |
| `pacman://orphans` | `pacman://orphans` | Orphaned packages |
| `pacman://explicit` | `pacman://explicit` | Explicitly installed packages |
| `pacman://groups` | `pacman://groups` | All package groups |
| `pacman://group/*` | `pacman://group/base-devel` | Packages in specific group |
| `pacman://database/freshness` | `pacman://database/freshness` | Package database sync status |

#### System Monitoring & Logs
| URI Scheme | Example | Returns |
|------------|---------|---------|
| `system://info` | `system://info` | System information (kernel, memory, uptime) |
| `system://disk` | `system://disk` | Disk space usage statistics |
| `system://services/failed` | `system://services/failed` | Failed systemd services |
| `system://logs/boot` | `system://logs/boot` | Recent boot logs |
| `pacman://log/recent` | `pacman://log/recent` | Recent package transactions |
| `pacman://log/failed` | `pacman://log/failed` | Failed package transactions |

#### News & Updates
| URI Scheme | Example | Returns |
|------------|---------|---------|
| `archnews://latest` | `archnews://latest` | Latest Arch Linux news |
| `archnews://critical` | `archnews://critical` | Critical news requiring manual intervention |
| `archnews://since-update` | `archnews://since-update` | News since last system update |

#### Configuration
| URI Scheme | Example | Returns |
|------------|---------|---------|
| `config://pacman` | `config://pacman` | Parsed pacman.conf configuration |
| `config://makepkg` | `config://makepkg` | Parsed makepkg.conf configuration |
| `mirrors://active` | `mirrors://active` | Currently configured mirrors |
| `mirrors://health` | `mirrors://health` | Mirror configuration health status |

### Tools (Executable Functions)

#### Package Search & Information
| Tool | Description | Platform |
|------|-------------|----------|
| `search_archwiki` | Query Arch Wiki with ranked results | Any |
| `search_aur` | Search AUR (relevance/votes/popularity/modified) | Any |
| `get_official_package_info` | Get official package details (hybrid local/remote) | Any |

#### Package Lifecycle Management
| Tool | Description | Platform |
|------|-------------|----------|
| `check_updates_dry_run` | Check for available updates | Arch only |
| `install_package_secure` | Install with security checks (blocks malicious packages) | Arch only |
| `remove_package` | Remove single package (with deps, forced) | Arch only |
| `remove_packages_batch` | Remove multiple packages efficiently | Arch only |

#### Package Analysis & Maintenance
| Tool | Description | Platform |
|------|-------------|----------|
| `list_orphan_packages` | Find orphaned packages | Arch only |
| `remove_orphans` | Clean orphans (dry-run, exclusions) | Arch only |
| `verify_package_integrity` | Check file integrity (modified/missing files) | Arch only |
| `list_explicit_packages` | List user-installed packages | Arch only |
| `mark_as_explicit` | Prevent package from being orphaned | Arch only |
| `mark_as_dependency` | Allow package to be orphaned | Arch only |

#### Package Organization
| Tool | Description | Platform |
|------|-------------|----------|
| `find_package_owner` | Find which package owns a file | Arch only |
| `list_package_files` | List files in package (regex filtering) | Arch only |
| `search_package_files` | Search files across packages | Arch only |
| `list_package_groups` | List all groups (base, base-devel, etc.) | Arch only |
| `list_group_packages` | Show packages in specific group | Arch only |

#### System Monitoring & Diagnostics
| Tool | Description | Platform |
|------|-------------|----------|
| `get_system_info` | System info (kernel, memory, uptime) | Any |
| `check_disk_space` | Disk usage with warnings | Any |
| `get_pacman_cache_stats` | Package cache size and age | Arch only |
| `check_failed_services` | Find failed systemd services | systemd |
| `get_boot_logs` | Retrieve journalctl boot logs | systemd |
| `check_database_freshness` | Check package database sync status | Arch only |

#### Transaction History & Logs
| Tool | Description | Platform |
|------|-------------|----------|
| `get_transaction_history` | Recent package transactions (install/upgrade/remove) | Arch only |
| `find_when_installed` | Package installation history | Arch only |
| `find_failed_transactions` | Failed package operations | Arch only |
| `get_database_sync_history` | Database sync events | Arch only |

#### News & Safety Checks
| Tool | Description | Platform |
|------|-------------|----------|
| `get_latest_news` | Fetch Arch Linux news from RSS | Any |
| `check_critical_news` | Find critical news (manual intervention required) | Any |
| `get_news_since_last_update` | News posted since last system update | Arch only |

#### Mirror Management
| Tool | Description | Platform |
|------|-------------|----------|
| `list_active_mirrors` | Show configured mirrors | Arch only |
| `test_mirror_speed` | Test mirror latency | Arch only |
| `suggest_fastest_mirrors` | Recommend optimal mirrors by location | Any |
| `check_mirrorlist_health` | Verify mirror configuration | Arch only |

#### Configuration Management
| Tool | Description | Platform |
|------|-------------|----------|
| `analyze_pacman_conf` | Parse pacman.conf settings | Arch only |
| `analyze_makepkg_conf` | Parse makepkg.conf settings | Arch only |
| `check_ignored_packages` | List ignored packages (warns on critical) | Arch only |
| `get_parallel_downloads_setting` | Get parallel download config | Arch only |

#### Security Analysis
| Tool | Description | Platform |
|------|-------------|----------|
| `analyze_pkgbuild_safety` | Comprehensive PKGBUILD analysis (50+ red flags) | Any |
| `analyze_package_metadata_risk` | Package trust scoring (votes, maintainer, age) | Any |

### Prompts (Guided Workflows)

| Prompt | Purpose | Workflow |
|--------|---------|----------|
| `troubleshoot_issue` | Diagnose system errors | Extract keywords → Search Wiki → Context-aware suggestions |
| `audit_aur_package` | Pre-installation safety audit | Fetch metadata → Analyze PKGBUILD → Security recommendations |
| `analyze_dependencies` | Installation planning | Check repos → Map dependencies → Suggest install order |
| `safe_system_update` | Safe update workflow | Check critical news → Verify disk space → List updates → Check services → Recommendations |

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

- **[GPL-3.0-only](https://www.gnu.org/licenses/gpl-3.0.en.html)** - For those who prefer strong copyleft protections. See [LICENSE-GPL](LICENSE-GPL)
- **[MIT License](https://opensource.org/licenses/MIT)** - For broader compatibility and adoption, including use in proprietary software and compatibility with platforms like Docker MCP Catalog. See [LICENSE-MIT](LICENSE-MIT)

You may use this software under the terms of either license. When redistributing or modifying this software, you may choose which license to apply.

By contributing to this project, you agree that your contributions will be licensed under both licenses.