# Changelog

## [1.2.0] - 2026-04-07

### Added
- **Playbook knowledge wiki**: LLM-maintained markdown wiki for cross-session consistency. Entities, concepts, decisions, and compiled files that Quarterback reads for task scoring. Follows the Karpathy LLM wiki pattern — accumulated knowledge rather than re-derived context.
- **4 new MCP tools**: `playbook_read`, `playbook_write`, `playbook_search`, `playbook_ingest` for programmatic wiki operations
- **2 new MCP resources**: `context://playbook/index`, `context://playbook/log` for wiki discovery
- **CLI `quarterback playbook` subcommand**: `status`, `index`, `list`, `read`, `search` actions
- **Setup wizard Playbook section**: Interview asks about entities, concepts, decisions, and Obsidian preference; seeds initial wiki pages automatically
- **Obsidian vault support**: Optional `.obsidian/` stub creation for visual browsing and graph view
- **Playbook-first context loading**: `_load_org_context()` reads compiled goals/constraints from Playbook when available, falls back to `org-context/` files for backward compatibility
- **`PLAYBOOK_PATH` environment variable**: Configure custom Playbook location (default: `~/.quarterback/playbook/`)
- **32 new tests** for the Playbook module

## [1.0.0] - 2026-03-23

### Added
- **CLI** (30+ commands): `quarterback priorities`, `add`, `update`, `list`, `quick-wins`, `conflicts`, `projects`, `summary`, `plan-day`, `advisory-*`, `alert-*`, `init`, `migrate`
- **MCP Server** (22 tools): Full Model Context Protocol server for Claude Desktop/Code integration
- **5-factor prioritization engine**: Impact (30%), Urgency (25%), Strategic Alignment (25%), Effort (15%), Quick Win (5%)
- **Advisory document system**: Add, analyze, discuss, and adopt external reference materials with conflict/synergy detection
- **Webhook system**: HMAC-signed webhooks for n8n, Zapier, and custom automation
- **Agent orchestration**: Mark tasks for autonomous execution with configurable autonomy levels (draft, checkpoint, autonomous)
- **Time-aware planning**: Working hours, lunch breaks, buffer time — suggests tasks that fit your available time
- **Conflict detection**: Identifies scheduling conflicts and focus conflicts across projects
- **Quick-win identification**: Finds high-impact, low-effort tasks across all projects
- **Cross-platform notifications**: macOS (osascript), Linux (notify-send), console fallback
- **Alert daemon**: Scheduled alerts for overdue, due-today, and upcoming tasks with quiet hours
- **Organizational context**: YAML/Markdown configuration for goals, constraints, workflows, and projects
- **SQLite backend**: Zero-config database with async support via aiosqlite
- **Migration tool**: `quarterback migrate ~/.task-manager` for seamless transition from task-manager
- **Example configs**: Ready-to-customize org-context templates and alert configuration
- **CI/CD**: GitHub Actions for linting, testing (Python 3.10-3.13), and PyPI publishing
