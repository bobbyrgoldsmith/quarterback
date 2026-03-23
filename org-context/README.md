# Organizational Context Directory

This directory contains your organizational documentation that Quarterback uses
to provide intelligent prioritization and recommendations.

## Directory Structure

- `goals.md` - Your organizational, workflow, project, and task-level goals
- `workflows.yaml` - Definitions of your workflows (groups of related projects)
- `projects.yaml` - Active projects and their metadata
- `constraints.md` - Resource constraints, time limitations, and strategic boundaries

## Getting Started

Example template files are provided for each configuration file:

```bash
# Quick setup
cp goals.example.md goals.md
cp projects.example.yaml projects.yaml
cp workflows.example.yaml workflows.yaml
cp constraints.example.md constraints.md
```

Then edit each file to reflect your actual organization, projects, and goals.

## How It Works

The Quarterback server (MCP and CLI) automatically reads these files when
analyzing priorities and making recommendations. Update these files to reflect
your current organizational state, and you'll get better prioritization:

```bash
quarterback priorities          # Uses org context for scoring
quarterback conflicts           # Detects conflicts against constraints
quarterback advisory-add --url  # Analyzes articles against your goals
```

## Tips

1. **Keep it updated**: Regular updates ensure accurate prioritization
2. **Be specific**: Clear goals lead to better recommendations
3. **Use markdown**: Rich formatting is supported
4. **Personal files are gitignored**: Your actual goals.md, projects.yaml, etc.
   are excluded from version control to protect your personal information
