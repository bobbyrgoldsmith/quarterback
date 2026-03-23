# Contributing to Quarterback

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

```bash
# Clone the repo
git clone https://github.com/bobbyrgoldsmith/quarterback.git
cd quarterback

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in development mode with all extras
pip install -e ".[dev,mcp,import]"

# Verify installation
quarterback init
quarterback --help
```

## Code Style

We use [ruff](https://github.com/astral-sh/ruff) for linting and formatting:

```bash
# Check linting
ruff check .

# Auto-fix issues
ruff check --fix .

# Check formatting
ruff format --check .

# Auto-format
ruff format .
```

- Line length: 100 characters
- Target: Python 3.10+
- No unnecessary type annotations or docstrings — code should be self-documenting

## Running Tests

```bash
# Run all tests
pytest -v

# Run specific test file
pytest tests/test_prioritization.py -v

# Run with coverage
pytest --cov=quarterback -v
```

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Run `ruff check . && ruff format --check . && pytest -v`
5. Commit with a clear message explaining **why** (not just what)
6. Open a PR with:
   - Summary of changes (2-3 bullets)
   - Test plan (what you tested and how)

## Architecture

```
src/quarterback/
├── cli.py              # CLI entry point (argparse)
├── server.py           # MCP server (mcp library)
├── config.py           # Centralized path configuration
├── database.py         # SQLAlchemy models + async init
├── prioritization.py   # 5-factor scoring engine
├── advisory_analyzer.py # Document analysis + recommendations
├── webhooks.py         # HMAC-signed webhook delivery
├── time_planner.py     # Working hours + task filtering
├── notifications.py    # Cross-platform notifications
├── alert_daemon.py     # Scheduled alert checking
└── context_manager.py  # Project context from files + DB
```

## Reporting Issues

Use [GitHub Issues](https://github.com/bobbyrgoldsmith/quarterback/issues). Include:
- What you expected
- What actually happened
- Steps to reproduce
- Python version and OS
