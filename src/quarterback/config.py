"""
Centralized configuration for Quarterback.
All paths resolve from QUARTERBACK_HOME (default: ~/.quarterback).
"""

import os
from pathlib import Path

QUARTERBACK_HOME = Path(os.environ.get("QUARTERBACK_HOME", Path.home() / ".quarterback"))
DATA_DIR = QUARTERBACK_HOME / "data"
ORG_CONTEXT_DIR = QUARTERBACK_HOME / "org-context"
CONFIG_DIR = QUARTERBACK_HOME / "config"
DB_PATH = DATA_DIR / "tasks.db"
ALERTS_CONFIG_PATH = CONFIG_DIR / "alerts.yaml"
LOG_DIR = QUARTERBACK_HOME / "logs"

# Placeholder for future Quarterback Pro license validation API
QUARTERBACK_API_URL = os.environ.get("QUARTERBACK_API_URL", None)


# Playbook — compiled knowledge layer
# Resolution order: PLAYBOOK_PATH env var > config/playbook.yaml > default
def _resolve_playbook_path() -> Path:
    env_path = os.environ.get("PLAYBOOK_PATH")
    if env_path:
        return Path(env_path).expanduser()

    config_file = CONFIG_DIR / "playbook.yaml"
    if config_file.exists():
        try:
            import yaml

            cfg = yaml.safe_load(config_file.read_text()) or {}
            if cfg.get("playbook_path"):
                return Path(cfg["playbook_path"]).expanduser()
        except Exception:
            pass

    return QUARTERBACK_HOME / "playbook"


PLAYBOOK_DIR = _resolve_playbook_path()
PLAYBOOK_WIKI_DIR = PLAYBOOK_DIR / "wiki"
PLAYBOOK_RAW_DIR = PLAYBOOK_DIR / "raw"
PLAYBOOK_COMPILED_DIR = PLAYBOOK_WIKI_DIR / "compiled"
PLAYBOOK_SCHEMA_PATH = PLAYBOOK_DIR / "CLAUDE.md"
