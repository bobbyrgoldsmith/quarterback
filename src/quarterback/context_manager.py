"""
Context Manager - handles project context from files and database.
Provides unified access to context stored in:
1. Database (project.context field)
2. Context files (.quarterback/context.md in project directory)
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime


class ProjectContextManager:
    """Manages project context from multiple sources."""

    def __init__(self, project_path: Optional[str] = None):
        self.project_path = Path(os.path.expanduser(project_path)) if project_path else None
        self.context_dir = self.project_path / ".quarterback" if self.project_path else None
        self.context_file = self.context_dir / "context.md" if self.context_dir else None

    def get_unified_context(self, db_context: Optional[str] = None) -> str:
        parts = []

        if db_context:
            parts.append("## Database Context\n\n" + db_context)

        file_context = self.read_context_file()
        if file_context:
            parts.append("## File Context\n\n" + file_context)

        return "\n\n---\n\n".join(parts) if parts else ""

    def read_context_file(self) -> Optional[str]:
        if not self.context_file or not self.context_file.exists():
            return None

        try:
            return self.context_file.read_text()
        except Exception as e:
            print(f"Error reading context file: {e}")
            return None

    def write_context_file(self, content: str, append: bool = False) -> bool:
        if not self.context_dir:
            return False

        try:
            self.context_dir.mkdir(parents=True, exist_ok=True)

            if append and self.context_file.exists():
                existing = self.context_file.read_text()
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                content = f"{existing}\n\n---\n\nAdded {timestamp}:\n\n{content}"

            self.context_file.write_text(content)
            return True

        except Exception as e:
            print(f"Error writing context file: {e}")
            return False

    def context_file_exists(self) -> bool:
        return bool(self.context_file and self.context_file.exists())

    def get_context_file_path(self) -> Optional[Path]:
        return self.context_file

    def create_context_template(self) -> bool:
        if not self.context_dir:
            return False

        template = """# Project Context

## Overview
[Brief description of the project]

## Architecture
[Key architectural decisions, frameworks, patterns]

## Entry Points
- Main file:
- Configuration:
- Dependencies:

## Development Notes
[Important notes for development]

## Agent Mode Notes
[Context that should be available in future agent sessions]

---

*This file is read by Quarterback in both CLI and Agent Mode*
"""

        return self.write_context_file(template, append=False)


def get_project_context(
    project_name: str, project_path: Optional[str], db_context: Optional[str]
) -> Dict[str, Any]:
    manager = ProjectContextManager(project_path)

    return {
        "project_name": project_name,
        "has_db_context": bool(db_context),
        "has_file_context": manager.context_file_exists(),
        "context_file_path": str(manager.get_context_file_path())
        if manager.get_context_file_path()
        else None,
        "unified_context": manager.get_unified_context(db_context),
        "db_context": db_context,
        "file_context": manager.read_context_file(),
    }
