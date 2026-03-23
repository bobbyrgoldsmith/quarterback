# Changelog

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
