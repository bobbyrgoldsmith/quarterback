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
