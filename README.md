<!-- mcp-name: io.github.bobbyrgoldsmith/quarterback -->

# Quarterback

**Read the field. Call the play.**

Strategic task prioritization and agent orchestration for multi-project operators.

[![PyPI](https://img.shields.io/pypi/v/quarterback)](https://pypi.org/project/quarterback/)
[![Python](https://img.shields.io/pypi/pyversions/quarterback)](https://pypi.org/project/quarterback/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/bobbyrgoldsmith/quarterback/actions/workflows/ci.yml/badge.svg)](https://github.com/bobbyrgoldsmith/quarterback/actions/workflows/ci.yml)

---

Every other AI task manager breaks down **one project** into subtasks. Quarterback helps you decide which of your **ten projects** to prioritize right now — using a 5-factor weighted scoring engine, organizational context, and time-aware planning. It runs locally, costs nothing, and works as both a standalone CLI and an MCP server for Claude.

## What Makes Quarterback Different

| Feature | Quarterback | TaskMaster AI | Shrimp Task Manager |
|---------|-------------|---------------|---------------------|
| **Multi-project prioritization** | 5-factor weighted engine | Single-project breakdown | Single-project |
| **Advisory document system** | Analyze articles against your goals | No | No |
| **Agent orchestration** | Autonomy levels + webhooks | No | No |
| **Time-aware planning** | Working hours, lunch, buffer time | No | No |
| **Organizational context** | Goals, constraints, workflows | No | No |
| **Conflict detection** | Cross-project scheduling conflicts | No | No |
| **Standalone CLI** | Full CLI without AI runtime | Requires AI | Requires AI |
| **Cost** | Free (MIT) | Free | Free |

## Quick Start

```bash
# Install
pip install quarterback

# Initialize (creates ~/.quarterback/)
quarterback init

# Interactive setup wizard — walks you through org, goals, workflows, projects, constraints
quarterback setup

# Add your first project and tasks
quarterback add "Launch landing page" --project "My Startup" --priority 4 --effort 3 --impact 5
quarterback add "Write blog post" --project "Content" --priority 3 --effort 2 --impact 3

# See what to work on
quarterback priorities

# Find quick wins
quarterback quick-wins

# Plan your day with time awareness
quarterback plan-day
```

### LLM-Powered Setup (via MCP)

When using Quarterback as an MCP server, ask Claude: *"Set up Quarterback for me"* — it will call the `setup_quarterback` tool, interview you conversationally about your business, goals, workflows, projects, and constraints, then write all config files and database records in one shot. No manual YAML editing required.

## MCP Server (for Claude Desktop / Claude Code)

```bash
# Install with MCP support
pip install quarterback[mcp]
```

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "quarterback": {
      "command": "quarterback-server"
    }
  }
}
```

Or for Claude Code (`~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "quarterback": {
      "command": "quarterback-server"
    }
  }
}
```

Then ask Claude: *"What should I work on today?"* — it will use all 23 Quarterback tools to analyze your priorities.

## Features

### 5-Factor Prioritization Engine

Every task is scored across five dimensions:

| Factor | Weight | What it measures |
|--------|--------|-----------------|
| **Impact** | 30% | Task impact + project revenue/strategic value |
| **Urgency** | 25% | Due date proximity + blocking status |
| **Strategic** | 25% | Project priority + milestone status |
| **Effort** | 15% | Inverted effort score (quick tasks score higher) |
| **Quick Win** | 5% | High impact + low effort bonus |

### Advisory Document System

Analyze external articles, books, and advice against your organizational context:

```bash
# Import and auto-analyze an article
quarterback advisory-add --title "Growth Strategy" --url https://example.com/article

# Review the analysis
quarterback advisory-view --id 1

# Approve recommendations (optionally create tasks)
quarterback advisory-approve --id 1 --approve 1,3,5 --create-tasks
```

The analyzer checks every recommendation against your goals and constraints, flagging conflicts and synergies.

### Agent Orchestration

Mark tasks for autonomous agent execution with configurable autonomy:

- **Draft**: Agent creates a draft for your review
- **Checkpoint**: Agent pauses at key decisions for approval
- **Autonomous**: Agent runs to completion

Webhooks notify your automation layer (n8n, Zapier, custom) when tasks are ready.

### CI/CD Pipeline Integration

Quarterback's CLI and webhook system make it a natural fit for automated pipelines — update task status, log deliverables, and trigger downstream work without a human in the loop.

#### Direct CLI in pipelines

Add Quarterback commands to any CI/CD step. The CLI is stateless and scriptable:

```yaml
# GitHub Actions example: auto-update task on deploy
- name: Mark deploy task complete
  run: |
    pip install quarterback
    export QUARTERBACK_HOME=${{ runner.temp }}/.quarterback
    quarterback update 42 --status completed --notes "Deployed via CI, SHA: ${{ github.sha }}"
```

```yaml
# After test suite passes, log results to a task
- name: Report test results
  run: |
    quarterback update 38 --notes "Tests passed: 106/106, coverage 87%. Build #${{ github.run_number }}"
```

```yaml
# Nightly: check for overdue deliverables and alert
- name: Nightly priority check
  run: |
    quarterback alert-check
    quarterback priorities today --limit 5
```

#### Agentic CI/CD with webhooks

Register a webhook and let your automation layer react to task events in real time:

```bash
# Register a webhook pointing at your n8n/Zapier/custom endpoint
quarterback-server  # MCP tools available, or use CLI:
```

```python
# In your automation script: mark a task agent-ready after PR merge
import subprocess
subprocess.run([
    "quarterback", "update", "55",
    "--status", "completed",
    "--notes", f"PR #{pr_number} merged. Deployed to staging."
])
```

**Use cases:**

| Pipeline event | Quarterback action | What happens |
|---------------|-------------------|--------------|
| PR merged | `update_task` status=completed | Task marked done, webhook fires to Slack |
| Deploy succeeds | `update_task` with SHA + environment notes | Deliverable tracked with audit trail |
| Nightly cron | `get_priorities` + `alert-check` | Team gets daily summary of what's overdue |
| Test suite fails | `add_task` with failure details | Bug auto-filed, linked to project |
| Sprint starts | `get_priorities` + `detect_conflicts` | Surface scheduling conflicts before work begins |
| Agent completes work | `update_agent_status` status=completed | Webhook notifies orchestrator, next task dispatched |
| Release tagged | `advisory-add` with release notes | Changelog analyzed against project goals |

#### Shared database across environments

Point multiple environments at the same Quarterback instance:

```bash
# All CI runners share one database via mounted volume or network path
export QUARTERBACK_HOME=/shared/quarterback

# Or per-environment with migration
quarterback migrate /path/to/source
```

This lets your local CLI, CI pipelines, and MCP-connected agents all read and write to the same task graph — giving you a single source of truth across manual and automated workflows.

### Time-Aware Planning

```bash
quarterback plan-day
```

Considers your working hours, lunch break, buffer time for meetings, and current time to suggest tasks that actually fit in your remaining day.

## Configuration

### Organizational Context

After `quarterback init`, run `quarterback setup` for an interactive wizard, or ask Claude to run the setup wizard via MCP. You can also manually configure your context in `~/.quarterback/org-context/`:

```
~/.quarterback/org-context/
├── goals.md          # Your strategic, workflow, and project goals
├── projects.yaml     # Active projects with metadata
├── workflows.yaml    # Groups of related projects
└── constraints.md    # Time, budget, and strategic boundaries
```

Example templates are included — copy from `.example` files and customize.

### Alert Configuration

Configure notifications in `~/.quarterback/config/alerts.yaml`:

- Quiet hours (no notifications at night)
- Priority thresholds (only notify for P4+ tasks)
- Time-sensitive projects (always notify for Bills, Tax, etc.)
- Working hours and lunch break settings

## CLI Commands

| Command | Description |
|---------|-------------|
| `quarterback init` | Initialize Quarterback |
| `quarterback setup` | Interactive setup wizard |
| `quarterback migrate <dir>` | Migrate from task-manager |
| `quarterback priorities [today\|week\|all]` | Prioritized task list |
| `quarterback add "task" [options]` | Add a task |
| `quarterback update <id> [options]` | Update a task |
| `quarterback list [-s status]` | List tasks |
| `quarterback quick-wins` | Find quick wins |
| `quarterback conflicts` | Detect priority conflicts |
| `quarterback projects` | List projects |
| `quarterback summary` | Organizational summary |
| `quarterback plan-day` | Time-aware daily plan |
| `quarterback advisory-add` | Add advisory document |
| `quarterback advisory-list` | List advisory documents |
| `quarterback advisory-view --id N` | View document details |
| `quarterback advisory-analyze --id N` | Analyze document |
| `quarterback advisory-approve --id N` | Approve/reject recommendations |
| `quarterback alert-check` | Check for alerts |
| `quarterback alert-summary` | Send daily summary |

## MCP Tools (23 total)

When used as an MCP server, Quarterback exposes these tools to Claude:

**Task Management**: `get_priorities`, `add_task`, `update_task`, `get_quick_wins`, `detect_conflicts`, `assess_task_value`, `get_blocking_tasks`

**Project Management**: `add_project`, `list_projects`, `update_project`, `get_organizational_summary`

**Advisory System**: `add_advisory_document`, `list_advisory_documents`, `get_advisory_document`, `analyze_advisory_document`, `discuss_advisory_recommendations`, `adopt_advisory_recommendations`

**Webhooks**: `register_webhook`, `list_webhooks`, `update_webhook`, `delete_webhook`

**Agent Orchestration**: `mark_task_agent_ready`, `get_agent_ready_tasks`, `update_agent_status`

**Setup**: `setup_quarterback`

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `QUARTERBACK_HOME` | `~/.quarterback` | Data directory |
| `QUARTERBACK_API_URL` | None | Reserved for Pro features |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code style, and PR process.

## License

MIT - see [LICENSE](LICENSE)

---

Built by [NodeBridge Automation Solutions](https://nodebridge.dev) | [GitHub Sponsors](https://github.com/sponsors/bobbyrgoldsmith)
