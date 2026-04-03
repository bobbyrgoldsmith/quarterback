"""
Setup wizard for Quarterback.
Provides interview template and config generation for LLM-driven onboarding.
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select

from quarterback.config import (
    DATA_DIR,
    ORG_CONTEXT_DIR,
    CONFIG_DIR,
    QUARTERBACK_HOME,
)
from quarterback.database import (
    init_db,
    get_session,
    Organization,
    Goal,
    Workflow,
    Project,
)


INTERVIEW_TEMPLATE = {
    "organization": {
        "name": {
            "type": "string",
            "prompt": "What is your business or project called?",
            "required": True,
        },
        "mission": {
            "type": "string",
            "prompt": "Describe what you do in one sentence.",
            "required": True,
        },
        "vision": {
            "type": "string",
            "prompt": "Where do you want to be in 2-3 years?",
            "required": False,
        },
    },
    "goals": {
        "annual": {
            "type": "array",
            "prompt": "What are your top 2-3 goals for this year?",
            "required": True,
        },
        "quarterly": {
            "type": "array",
            "prompt": "What are you focused on this quarter?",
            "required": False,
        },
        "anti_goals": {
            "type": "array",
            "prompt": "Is there anything you explicitly do NOT want to work on?",
            "required": False,
        },
    },
    "workflows": {
        "type": "array",
        "prompt": "What are the main areas or themes of your work? (e.g., Product Development, Content, Client Work)",
        "item_fields": {
            "name": {"type": "string", "required": True},
            "description": {"type": "string", "required": False},
            "goals": {"type": "array", "required": False},
            "priority": {"type": "integer", "required": False, "default": 3},
            "status": {"type": "string", "required": False, "default": "active"},
        },
    },
    "projects": {
        "type": "array",
        "prompt": "What projects are you actively working on?",
        "item_fields": {
            "name": {"type": "string", "required": True},
            "path": {"type": "string", "required": False},
            "workflow": {"type": "string", "required": False},
            "description": {"type": "string", "required": False},
            "status": {"type": "string", "required": False, "default": "active"},
            "priority": {"type": "integer", "required": False, "default": 3},
            "revenue_potential": {"type": "string", "required": False, "default": "medium"},
            "strategic_value": {"type": "string", "required": False, "default": "medium"},
            "technical_complexity": {"type": "string", "required": False, "default": "medium"},
            "next_milestone": {"type": "string", "required": False},
        },
    },
    "constraints": {
        "hours_per_week": {
            "type": "number",
            "prompt": "How many hours per week do you have for this work?",
            "required": False,
            "default": 40,
        },
        "working_hours": {
            "type": "string",
            "prompt": "What are your working hours? (e.g., 9am-6pm)",
            "required": False,
            "default": "9am-6pm",
        },
        "working_days": {
            "type": "string",
            "prompt": "What days do you work? (e.g., Monday-Friday)",
            "required": False,
            "default": "Monday-Friday",
        },
        "budget_monthly": {
            "type": "number",
            "prompt": "What's your monthly budget for tools/infrastructure?",
            "required": False,
        },
        "team_size": {
            "type": "integer",
            "prompt": "How many people on your team?",
            "required": False,
            "default": 1,
        },
        "preferred_stack": {
            "type": "array",
            "prompt": "What's your preferred tech stack?",
            "required": False,
        },
        "avoid_stack": {
            "type": "array",
            "prompt": "Any technologies you want to avoid?",
            "required": False,
        },
    },
}


def get_setup_status() -> dict[str, Any]:
    """Check which config files exist and return current setup state."""
    goals_path = ORG_CONTEXT_DIR / "goals.md"
    workflows_path = ORG_CONTEXT_DIR / "workflows.yaml"
    projects_path = ORG_CONTEXT_DIR / "projects.yaml"
    constraints_path = ORG_CONTEXT_DIR / "constraints.md"

    return {
        "quarterback_initialized": QUARTERBACK_HOME.exists(),
        "goals_configured": goals_path.exists() and goals_path.stat().st_size > 0,
        "workflows_configured": workflows_path.exists() and workflows_path.stat().st_size > 0,
        "projects_configured": projects_path.exists() and projects_path.stat().st_size > 0,
        "constraints_configured": constraints_path.exists() and constraints_path.stat().st_size > 0,
    }


def get_interview_template() -> dict[str, Any]:
    """Return the interview structure, current status, and existing config values."""
    status = get_setup_status()

    current_config = {}
    if status["goals_configured"]:
        current_config["goals_content"] = (ORG_CONTEXT_DIR / "goals.md").read_text()
    if status["workflows_configured"]:
        current_config["workflows"] = yaml.safe_load(
            (ORG_CONTEXT_DIR / "workflows.yaml").read_text()
        )
    if status["projects_configured"]:
        current_config["projects"] = yaml.safe_load((ORG_CONTEXT_DIR / "projects.yaml").read_text())
    if status["constraints_configured"]:
        current_config["constraints_content"] = (ORG_CONTEXT_DIR / "constraints.md").read_text()

    return {
        "status": status,
        "current_config": current_config,
        "interview_template": INTERVIEW_TEMPLATE,
        "instructions": (
            "Interview the user to gather the information described in the template above. "
            "Ask conversationally — don't dump all questions at once. Start with identity "
            "(name, mission, vision), then goals, then workflows and projects, then constraints. "
            "For each section, ask the questions naturally, accept free-form answers, and "
            "synthesize them into the structured format. Once you have enough information, "
            "call setup_quarterback with action='apply_setup' and the structured answers. "
            "If current_config shows existing values, mention them so the user can keep or change them."
        ),
    }


def generate_goals_md(answers: dict) -> str:
    """Generate goals.md content from structured answers."""
    org = answers.get("organization", {})
    goals = answers.get("goals", {})
    workflows = answers.get("workflows", [])
    projects = answers.get("projects", [])

    lines = ["# Organizational Goals", ""]

    # Mission
    lines.append("## Mission")
    mission = org.get("mission", "")
    if mission:
        lines.append(f"- {mission}")
    lines.append("")

    # Vision
    vision = org.get("vision", "")
    if vision:
        lines.append("## Vision")
        lines.append(f"- {vision}")
        lines.append("")

    # Strategic Goals
    lines.append("## Strategic Goals")
    lines.append("")

    annual = goals.get("annual", [])
    if annual:
        lines.append("### Annual Goals (Current Year)")
        for g in annual:
            lines.append(f"- {g}")
        lines.append("")

    quarterly = goals.get("quarterly", [])
    if quarterly:
        lines.append("### Quarterly Goals (Current Quarter)")
        for g in quarterly:
            lines.append(f"- {g}")
        lines.append("")

    # Workflow Goals
    if workflows:
        lines.append("## Workflow Goals")
        lines.append("")
        for wf in workflows:
            name = wf.get("name", "Unnamed")
            lines.append(f"### {name}")
            for g in wf.get("goals", []):
                lines.append(f"- {g}")
            if not wf.get("goals"):
                lines.append(f"- Advance {name} objectives")
            lines.append("")

    # Project Goals
    if projects:
        lines.append("## Project Goals")
        lines.append("")
        for proj in projects:
            name = proj.get("name", "Unnamed")
            lines.append(f"### {name}")
            milestone = proj.get("next_milestone")
            if milestone:
                lines.append(f"- {milestone}")
            desc = proj.get("description")
            if desc and not milestone:
                lines.append(f"- {desc}")
            if not milestone and not desc:
                lines.append(f"- Complete current phase")
            lines.append("")

    # Anti-Goals
    anti_goals = goals.get("anti_goals", [])
    if anti_goals:
        lines.append("## Anti-Goals")
        for g in anti_goals:
            lines.append(f"- {g}")
        lines.append("")

    return "\n".join(lines)


def generate_workflows_yaml(answers: dict) -> str:
    """Generate workflows.yaml content from structured answers."""
    workflows = answers.get("workflows", [])
    projects = answers.get("projects", [])

    workflow_list = []
    for wf in workflows:
        name = wf.get("name", "Unnamed")
        # Find projects belonging to this workflow
        wf_projects = [p["name"] for p in projects if p.get("workflow", "").lower() == name.lower()]
        entry = {
            "name": name,
            "description": wf.get("description", ""),
            "projects": wf_projects,
            "goals": wf.get("goals", []),
            "status": wf.get("status", "active"),
            "priority": wf.get("priority", 3),
        }
        workflow_list.append(entry)

    data = {"workflows": workflow_list}
    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)


def generate_projects_yaml(answers: dict) -> str:
    """Generate projects.yaml content from structured answers."""
    projects = answers.get("projects", [])

    project_list = []
    for proj in projects:
        entry = {
            "name": proj.get("name", "Unnamed"),
            "path": proj.get("path", ""),
            "workflow": proj.get("workflow", ""),
            "description": proj.get("description", ""),
            "status": proj.get("status", "active"),
            "priority": proj.get("priority", 3),
            "current_phase": proj.get("current_phase", ""),
            "revenue_potential": proj.get("revenue_potential", "medium"),
            "strategic_value": proj.get("strategic_value", "medium"),
            "technical_complexity": proj.get("technical_complexity", "medium"),
            "dependencies": proj.get("dependencies", []),
            "next_milestone": proj.get("next_milestone", ""),
            "notes": proj.get("notes", ""),
        }
        project_list.append(entry)

    data = {"projects": project_list}
    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)


def generate_constraints_md(answers: dict) -> str:
    """Generate constraints.md content from structured answers."""
    c = answers.get("constraints", {})

    hours = c.get("hours_per_week", 40)
    working_hours = c.get("working_hours", "9am-6pm")
    working_days = c.get("working_days", "Monday-Friday")
    budget = c.get("budget_monthly")
    team_size = c.get("team_size", 1)
    preferred = c.get("preferred_stack", [])
    avoid = c.get("avoid_stack", [])

    lines = ["# Resource Constraints & Strategic Boundaries", ""]

    # Time Constraints
    lines.append("## Time Constraints")
    lines.append("")
    lines.append("### Available Time")
    lines.append(f"- Development time: ~{hours} hours/week")
    lines.append(f"- Business hours: {working_days}, {working_hours}")
    lines.append("")

    # Resource Constraints
    lines.append("## Resource Constraints")
    lines.append("")
    if budget:
        lines.append("### Budget")
        lines.append(f"- Total monthly budget: ${budget}/month")
        lines.append("")

    lines.append("### Technical Resources")
    if team_size == 1:
        lines.append("- Team size: 1 developer (solo operator)")
    else:
        lines.append(f"- Team size: {team_size}")
    if preferred:
        lines.append(f"- Preferred stack: {', '.join(preferred)}")
    if avoid:
        lines.append(f"- Avoid: {', '.join(avoid)}")
    lines.append("")

    # Conflict Resolution
    lines.append("## Conflict Resolution Guidelines")
    lines.append("")
    lines.append("When priorities conflict:")
    lines.append("1. Revenue-generating work trumps experimental projects")
    lines.append("2. Unblocking other projects takes priority")
    lines.append("3. Quick wins (< 2 hours) can interrupt planned work")
    lines.append("")

    return "\n".join(lines)


def _backup_file(path: Path):
    """Back up an existing file with timestamp suffix."""
    if path.exists():
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = path.with_suffix(f"{path.suffix}.bak.{ts}")
        shutil.copy2(path, backup)


async def create_db_records(answers: dict, engine):
    """Create or update Organization, Workflow, Project, and Goal records."""
    org_data = answers.get("organization", {})
    goals_data = answers.get("goals", {})
    workflows_data = answers.get("workflows", [])
    projects_data = answers.get("projects", [])

    async with await get_session(engine) as session:
        # Upsert Organization
        result = await session.execute(select(Organization))
        org = result.scalars().first()
        if org:
            org.name = org_data.get("name", org.name)
            org.mission = org_data.get("mission", org.mission)
            org.vision = org_data.get("vision", org.vision)
        else:
            org = Organization(
                name=org_data.get("name", "My Organization"),
                mission=org_data.get("mission"),
                vision=org_data.get("vision"),
            )
            session.add(org)
            await session.flush()

        # Create Goal records
        for g in goals_data.get("annual", []):
            goal = Goal(org_id=org.id, level="annual", description=g, timeframe="annual")
            session.add(goal)
        for g in goals_data.get("quarterly", []):
            goal = Goal(org_id=org.id, level="quarterly", description=g, timeframe="quarterly")
            session.add(goal)

        # Upsert Workflows
        workflow_map = {}
        for wf_data in workflows_data:
            name = wf_data.get("name", "")
            result = await session.execute(select(Workflow).where(Workflow.name == name))
            wf = result.scalars().first()
            if wf:
                wf.description = wf_data.get("description", wf.description)
                wf.goals = json.dumps(wf_data.get("goals", []))
                wf.status = wf_data.get("status", wf.status)
            else:
                wf = Workflow(
                    org_id=org.id,
                    name=name,
                    description=wf_data.get("description", ""),
                    goals=json.dumps(wf_data.get("goals", [])),
                    status=wf_data.get("status", "active"),
                )
                session.add(wf)
                await session.flush()
            workflow_map[name.lower()] = wf

        # Upsert Projects
        for proj_data in projects_data:
            name = proj_data.get("name", "")
            result = await session.execute(select(Project).where(Project.name == name))
            proj = result.scalars().first()

            wf_name = proj_data.get("workflow", "")
            wf = workflow_map.get(wf_name.lower()) if wf_name else None
            wf_id = wf.id if wf else None

            if proj:
                proj.workflow_id = wf_id or proj.workflow_id
                proj.path = proj_data.get("path", proj.path)
                proj.description = proj_data.get("description", proj.description)
                proj.status = proj_data.get("status", proj.status)
                proj.priority = proj_data.get("priority", proj.priority)
            else:
                proj = Project(
                    workflow_id=wf_id,
                    name=name,
                    path=proj_data.get("path", ""),
                    description=proj_data.get("description", ""),
                    status=proj_data.get("status", "active"),
                    priority=proj_data.get("priority", 3),
                )
                session.add(proj)

        await session.commit()


async def apply_setup(answers: dict, engine=None, overwrite: bool = False) -> dict[str, Any]:
    """Write all config files and create DB records from interview answers."""
    # Ensure directories exist
    for d in [DATA_DIR, ORG_CONTEXT_DIR, CONFIG_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    # Check for existing config files
    config_files = {
        "goals.md": ORG_CONTEXT_DIR / "goals.md",
        "workflows.yaml": ORG_CONTEXT_DIR / "workflows.yaml",
        "projects.yaml": ORG_CONTEXT_DIR / "projects.yaml",
        "constraints.md": ORG_CONTEXT_DIR / "constraints.md",
    }

    existing = [name for name, path in config_files.items() if path.exists()]
    if existing and not overwrite:
        return {
            "success": False,
            "error": "existing_config",
            "files": existing,
            "message": (
                f"Config files already exist: {', '.join(existing)}. "
                "Set overwrite_existing=true to replace them (originals will be backed up)."
            ),
        }

    # Backup existing files if overwriting
    if existing and overwrite:
        for path in config_files.values():
            _backup_file(path)

    # Generate and write config files
    files_written = []

    goals_content = generate_goals_md(answers)
    config_files["goals.md"].write_text(goals_content)
    files_written.append("goals.md")

    workflows_content = generate_workflows_yaml(answers)
    config_files["workflows.yaml"].write_text(workflows_content)
    files_written.append("workflows.yaml")

    projects_content = generate_projects_yaml(answers)
    config_files["projects.yaml"].write_text(projects_content)
    files_written.append("projects.yaml")

    constraints_content = generate_constraints_md(answers)
    config_files["constraints.md"].write_text(constraints_content)
    files_written.append("constraints.md")

    # Initialize DB if needed and create records
    if engine is None:
        engine = await init_db()
    await create_db_records(answers, engine)

    return {
        "success": True,
        "files_written": files_written,
        "message": "Quarterback is configured! Your org context, goals, workflows, projects, and constraints are all set up.",
        "next_steps": [
            "Add tasks to your projects with add_task",
            "Check priorities with get_priorities",
            "Run 'quarterback plan-day' for daily planning",
        ],
    }
