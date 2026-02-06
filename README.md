# Arch Linux MCP Server

[![PyPI Downloads](https://static.pepy.tech/personalized-badge/arch-ops-server?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLUE&right_color=BLACK&left_text=PyPi+Downloads)](https://pepy.tech/projects/arch-ops-server)

<a href="https://glama.ai/mcp/servers/@nihalxkumar/arch-mcp">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@nihalxkumar/arch-mcp/badge" />
</a>

**Disclaimer:** Unofficial community project, not affiliated with Arch Linux.

A [Model Context Protocol](https://modelcontextprotocol.io/) (MCP) server that bridges AI assistants with the Arch Linux ecosystem. Enables intelligent, safe, and efficient access to the Arch Wiki, AUR, and official repositories for AI-assisted Arch Linux usage on Arch and non-Arch systems.

Leverage AI to get digestible, structured results that are ready for follow up questions and actions.

📖 [Complete Documentation with Comfy Guides](https://nxk.mintlify.app/arch-mcp)

## Sneak Peak into what's available

<details>

<summary>Using VS Code Sonnet 3.5 for Safe Installation from AUR</summary>

![VS Code Demo](assets/vscode_notesnook.gif)

</details>

<details>
<summary> Asking Claude Code Sonnet 4.5 for fedora equivalent command </summary>

![Equivalent Command Demo](assets/equivalent-commands.gif)

</details>

### Resources (URI-based Access)

Direct access to Arch ecosystem data via custom URI schemes:

#### Documentation & Search

| URI Scheme    | Example                         | Returns                      |
| ------------- | ------------------------------- | ---------------------------- |
| `archwiki://` | `archwiki://Installation_guide` | Markdown-formatted Wiki page |

#### Package Information

| URI Scheme         | Example              | Returns                                         |
| ------------------ | -------------------- | ----------------------------------------------- |
| `archrepo://`      | `archrepo://vim`     | Official repository package details             |
| `aur://*/info`     | `aur://yay/info`     | AUR package metadata (votes, maintainer, dates) |
| `aur://*/pkgbuild` | `aur://yay/pkgbuild` | Raw PKGBUILD with safety analysis               |

#### System Packages (Arch only)

| URI Scheme                    | Example                       | Returns                        |
| ----------------------------- | ----------------------------- | ------------------------------ |
| `pacman://installed`          | `pacman://installed`          | System installed packages list |
| `pacman://orphans`            | `pacman://orphans`            | Orphaned packages              |
| `pacman://explicit`           | `pacman://explicit`           | Explicitly installed packages  |
| `pacman://groups`             | `pacman://groups`             | All package groups             |
| `pacman://group/*`            | `pacman://group/base-devel`   | Packages in specific group     |
| `pacman://database/freshness` | `pacman://database/freshness` | Package database sync status   |

#### System Monitoring & Logs

| URI Scheme                 | Example                    | Returns                                     |
| -------------------------- | -------------------------- | ------------------------------------------- |
| `system://info`            | `system://info`            | System information (kernel, memory, uptime) |
| `system://disk`            | `system://disk`            | Disk space usage statistics                 |
| `system://services/failed` | `system://services/failed` | Failed systemd services                     |
| `system://logs/boot`       | `system://logs/boot`       | Recent boot logs                            |
| `pacman://log/recent`      | `pacman://log/recent`      | Recent package transactions                 |
| `pacman://log/failed`      | `pacman://log/failed`      | Failed package transactions                 |

#### News & Updates

| URI Scheme                | Example                   | Returns                                     |
| ------------------------- | ------------------------- | ------------------------------------------- |
| `archnews://latest`       | `archnews://latest`       | Latest Arch Linux news                      |
| `archnews://critical`     | `archnews://critical`     | Critical news requiring manual intervention |
| `archnews://since-update` | `archnews://since-update` | News since last system update               |

#### Configuration

| URI Scheme         | Example            | Returns                            |
| ------------------ | ------------------ | ---------------------------------- |
| `config://pacman`  | `config://pacman`  | Parsed pacman.conf configuration   |
| `config://makepkg` | `config://makepkg` | Parsed makepkg.conf configuration  |
| `mirrors://active` | `mirrors://active` | Currently configured mirrors       |
| `mirrors://health` | `mirrors://health` | Mirror configuration health status |

### Tools (Executable Functions)

#### Package Search & Information

| Tool                        | Description                                        | Platform |
| --------------------------- | -------------------------------------------------- | -------- |
| `search_archwiki`           | Query Arch Wiki with ranked results                | Any      |
| `search_aur`                | Search AUR (relevance/votes/popularity/modified)   | Any      |
| `get_official_package_info` | Get official package details (hybrid local/remote) | Any      |

#### Package Lifecycle Management

| Tool                     | Description                                                                   | Platform  |
| ------------------------ | ----------------------------------------------------------------------------- | --------- |
| `check_updates_dry_run`  | Check for available updates                                                   | Arch only |
| `install_package_secure` | Install with security checks (blocks malicious packages)                      | Arch only |
| `remove_packages`        | Remove packages - accepts single package name or list (with deps, forced)     | Arch only |

#### Package Analysis & Maintenance

| Tool                       | Description                                                                                                                | Platform  |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------- | --------- |
| `manage_orphans`           | Manage orphaned packages (2 actions: list orphaned packages, remove orphans). Always runs in dry-run mode first for safety. | Arch only |
| `verify_package_integrity` | Check file integrity (modified/missing files)                                                                              | Arch only |
| `manage_install_reason`    | Manage install reasons (3 actions: list explicit packages, mark as explicit/dependency)                                    | Arch only |

#### Package Organization

| Tool                   | Description                                                                                    | Platform  |
| ---------------------- | ---------------------------------------------------------------------------------------------- | --------- |
| `query_file_ownership` | Unified file-package ownership queries (3 modes: file→package, package→files, filename search) | Arch only |
| `list_package_groups`  | List all groups (base, base-devel, etc.)                                                       | Arch only |
| `list_group_packages`  | Show packages in specific group                                                                | Arch only |

#### System Monitoring & Diagnostics

| Tool                       | Description                          | Platform  |
| -------------------------- | ------------------------------------ | --------- |
| `get_system_info`          | System info (kernel, memory, uptime) | Any       |
| `check_disk_space`         | Disk usage with warnings             | Any       |
| `get_pacman_cache_stats`   | Package cache size and age           | Arch only |
| `check_failed_services`    | Find failed systemd services         | systemd   |
| `get_boot_logs`            | Retrieve journalctl boot logs        | systemd   |
| `check_database_freshness` | Check package database sync status   | Arch only |

#### Transaction History & Logs

| Tool                    | Description                                                                                                                                                                                                                                                             | Platform  |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| `query_package_history` | Unified tool for querying package history from pacman logs (4 query types). Examples: `query_type='all'` shows recent transactions; `query_type='package', package_name='docker'` shows when docker was installed/upgraded; `query_type='failures'` shows failed operations; `query_type='sync'` shows database sync history. | Arch only |

#### News & Safety Checks

| Tool                         | Description                                       | Platform  |
| ---------------------------- | ------------------------------------------------- | --------- |
| `get_latest_news`            | Fetch Arch Linux news from RSS                    | Any       |
| `check_critical_news`        | Find critical news (manual intervention required) | Any       |
| `get_news_since_last_update` | News posted since last system update              | Arch only |

#### Mirror Management

| Tool              | Description                                                                                           | Platform  |
| ----------------- | ----------------------------------------------------------------------------------------------------- | --------- |
| `optimize_mirrors` | Smart mirror management (4 actions: status, test, suggest, health). Examples: `optimize_mirrors(action='status', auto_test=True)` lists and tests all mirrors; `optimize_mirrors(action='suggest', country='US', limit=5)` suggests top 5 US mirrors; `optimize_mirrors(action='health')` checks for issues and gives recommendations. | Arch/Any  |

#### Configuration Management

| Tool                             | Description                                                                                                                                                                                                           | Platform  |
| -------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| `analyze_pacman_conf`            | Parse pacman.conf settings with optional focus. Examples: `focus='full'` (default) returns all settings; `focus='ignored_packages'` returns only ignored packages with warnings for critical ones; `focus='parallel_downloads'` returns only parallel downloads setting with optimization recommendations. | Arch only |
| `analyze_makepkg_conf`           | Parse makepkg.conf settings (CFLAGS, MAKEFLAGS, build configuration)                                                                                                                                                  | Arch only |

#### Security Analysis

| Tool                            | Description                                     | Platform |
| ------------------------------- | ----------------------------------------------- | -------- |
| `analyze_pkgbuild_safety`       | Comprehensive PKGBUILD analysis (50+ red flags) | Any      |
| `analyze_package_metadata_risk` | Package trust scoring (votes, maintainer, age)  | Any      |

### Prompts (Guided Workflows)

| Prompt                 | Purpose                       | Workflow                                                                                  |
| ---------------------- | ----------------------------- | ----------------------------------------------------------------------------------------- |
| `troubleshoot_issue`   | Diagnose system errors        | Extract keywords → Search Wiki → Context-aware suggestions                                |
| `audit_aur_package`    | Pre-installation safety audit | Fetch metadata → Analyze PKGBUILD → Security recommendations                              |
| `analyze_dependencies` | Installation planning         | Check repos → Map dependencies → Suggest install order                                    |
| `safe_system_update`   | Safe update workflow          | Check critical news → Verify disk space → List updates → Check services → Recommendations |

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
