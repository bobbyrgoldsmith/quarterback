"""Tests for the setup wizard module."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from quarterback.setup_wizard import (
    generate_goals_md,
    generate_workflows_yaml,
    generate_projects_yaml,
    generate_constraints_md,
    get_setup_status,
    get_interview_template,
    apply_setup,
)


SAMPLE_ANSWERS = {
    "organization": {
        "name": "TestCorp",
        "mission": "Build great developer tools",
        "vision": "Become the top dev tools company in 5 years",
    },
    "goals": {
        "annual": ["Launch 2 products", "Reach $10K MRR"],
        "quarterly": ["Ship MVP", "Get 50 beta users"],
        "anti_goals": ["No consulting work", "No premature optimization"],
    },
    "workflows": [
        {
            "name": "Product Development",
            "description": "Core product work",
            "goals": ["Launch MVP", "Iterate on feedback"],
            "priority": 1,
            "status": "active",
        },
        {
            "name": "Marketing",
            "description": "Growth and content",
            "goals": ["Build audience"],
            "priority": 2,
            "status": "active",
        },
    ],
    "projects": [
        {
            "name": "Widget API",
            "path": "~/projects/widget-api",
            "workflow": "Product Development",
            "description": "REST API for widgets",
            "status": "active",
            "priority": 1,
            "revenue_potential": "high",
            "strategic_value": "high",
            "technical_complexity": "medium",
            "next_milestone": "Beta launch",
        },
        {
            "name": "Blog",
            "path": "~/projects/blog",
            "workflow": "Marketing",
            "description": "Company blog",
            "status": "active",
            "priority": 3,
        },
    ],
    "constraints": {
        "hours_per_week": 30,
        "working_hours": "9am-5pm",
        "working_days": "Monday-Friday",
        "budget_monthly": 200,
        "team_size": 1,
        "preferred_stack": ["Python", "TypeScript"],
        "avoid_stack": ["Java"],
    },
}


class TestGenerateGoalsMd:
    def test_includes_mission(self):
        result = generate_goals_md(SAMPLE_ANSWERS)
        assert "Build great developer tools" in result

    def test_includes_vision(self):
        result = generate_goals_md(SAMPLE_ANSWERS)
        assert "Become the top dev tools company" in result

    def test_includes_annual_goals(self):
        result = generate_goals_md(SAMPLE_ANSWERS)
        assert "Launch 2 products" in result
        assert "Reach $10K MRR" in result

    def test_includes_quarterly_goals(self):
        result = generate_goals_md(SAMPLE_ANSWERS)
        assert "Ship MVP" in result
        assert "Get 50 beta users" in result

    def test_includes_anti_goals(self):
        result = generate_goals_md(SAMPLE_ANSWERS)
        assert "No consulting work" in result

    def test_includes_workflow_goals(self):
        result = generate_goals_md(SAMPLE_ANSWERS)
        assert "### Product Development" in result

    def test_includes_project_goals(self):
        result = generate_goals_md(SAMPLE_ANSWERS)
        assert "### Widget API" in result
        assert "Beta launch" in result

    def test_minimal_answers(self):
        minimal = {"organization": {"mission": "Do stuff"}, "goals": {"annual": ["Goal 1"]}}
        result = generate_goals_md(minimal)
        assert "Do stuff" in result
        assert "Goal 1" in result

    def test_starts_with_header(self):
        result = generate_goals_md(SAMPLE_ANSWERS)
        assert result.startswith("# Organizational Goals")


class TestGenerateWorkflowsYaml:
    def test_produces_valid_yaml(self):
        result = generate_workflows_yaml(SAMPLE_ANSWERS)
        data = yaml.safe_load(result)
        assert "workflows" in data

    def test_workflow_count(self):
        result = generate_workflows_yaml(SAMPLE_ANSWERS)
        data = yaml.safe_load(result)
        assert len(data["workflows"]) == 2

    def test_workflow_fields(self):
        result = generate_workflows_yaml(SAMPLE_ANSWERS)
        data = yaml.safe_load(result)
        wf = data["workflows"][0]
        assert wf["name"] == "Product Development"
        assert wf["description"] == "Core product work"
        assert wf["status"] == "active"
        assert wf["priority"] == 1

    def test_projects_linked_to_workflow(self):
        result = generate_workflows_yaml(SAMPLE_ANSWERS)
        data = yaml.safe_load(result)
        wf = data["workflows"][0]
        assert "Widget API" in wf["projects"]

    def test_empty_workflows(self):
        result = generate_workflows_yaml({"workflows": [], "projects": []})
        data = yaml.safe_load(result)
        assert data["workflows"] == []


class TestGenerateProjectsYaml:
    def test_produces_valid_yaml(self):
        result = generate_projects_yaml(SAMPLE_ANSWERS)
        data = yaml.safe_load(result)
        assert "projects" in data

    def test_project_count(self):
        result = generate_projects_yaml(SAMPLE_ANSWERS)
        data = yaml.safe_load(result)
        assert len(data["projects"]) == 2

    def test_project_fields(self):
        result = generate_projects_yaml(SAMPLE_ANSWERS)
        data = yaml.safe_load(result)
        proj = data["projects"][0]
        assert proj["name"] == "Widget API"
        assert proj["path"] == "~/projects/widget-api"
        assert proj["workflow"] == "Product Development"
        assert proj["priority"] == 1
        assert proj["revenue_potential"] == "high"

    def test_defaults_applied(self):
        result = generate_projects_yaml(SAMPLE_ANSWERS)
        data = yaml.safe_load(result)
        proj = data["projects"][1]  # Blog has fewer fields
        assert proj["revenue_potential"] == "medium"  # default
        assert proj["technical_complexity"] == "medium"  # default


class TestGenerateConstraintsMd:
    def test_includes_hours(self):
        result = generate_constraints_md(SAMPLE_ANSWERS)
        assert "30 hours/week" in result

    def test_includes_working_hours(self):
        result = generate_constraints_md(SAMPLE_ANSWERS)
        assert "9am-5pm" in result

    def test_includes_budget(self):
        result = generate_constraints_md(SAMPLE_ANSWERS)
        assert "$200/month" in result

    def test_includes_team_size(self):
        result = generate_constraints_md(SAMPLE_ANSWERS)
        assert "solo operator" in result

    def test_includes_stack(self):
        result = generate_constraints_md(SAMPLE_ANSWERS)
        assert "Python" in result
        assert "TypeScript" in result

    def test_includes_avoid(self):
        result = generate_constraints_md(SAMPLE_ANSWERS)
        assert "Java" in result

    def test_defaults(self):
        result = generate_constraints_md({})
        assert "40 hours/week" in result
        assert "9am-6pm" in result

    def test_starts_with_header(self):
        result = generate_constraints_md(SAMPLE_ANSWERS)
        assert result.startswith("# Resource Constraints")


class TestGetSetupStatus:
    def test_returns_status_dict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("quarterback.setup_wizard.QUARTERBACK_HOME", Path(tmpdir)):
                with patch("quarterback.setup_wizard.ORG_CONTEXT_DIR", Path(tmpdir) / "org"):
                    status = get_setup_status()
                    assert "quarterback_initialized" in status
                    assert status["quarterback_initialized"] is True
                    assert status["goals_configured"] is False

    def test_detects_existing_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            org_dir = Path(tmpdir) / "org"
            org_dir.mkdir()
            (org_dir / "goals.md").write_text("# Goals")
            with patch("quarterback.setup_wizard.QUARTERBACK_HOME", Path(tmpdir)):
                with patch("quarterback.setup_wizard.ORG_CONTEXT_DIR", org_dir):
                    status = get_setup_status()
                    assert status["goals_configured"] is True


class TestGetInterviewTemplate:
    def test_returns_template_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("quarterback.setup_wizard.QUARTERBACK_HOME", Path(tmpdir)):
                with patch("quarterback.setup_wizard.ORG_CONTEXT_DIR", Path(tmpdir) / "org"):
                    result = get_interview_template()
                    assert "status" in result
                    assert "interview_template" in result
                    assert "instructions" in result
                    assert "current_config" in result


class TestApplySetup:
    @pytest.mark.asyncio
    async def test_writes_all_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            org_dir = Path(tmpdir) / "org"
            config_dir = Path(tmpdir) / "config"

            with (
                patch("quarterback.setup_wizard.DATA_DIR", data_dir),
                patch("quarterback.setup_wizard.ORG_CONTEXT_DIR", org_dir),
                patch("quarterback.setup_wizard.CONFIG_DIR", config_dir),
            ):
                from quarterback.database import init_db

                engine = await init_db(":memory:")

                result = await apply_setup(SAMPLE_ANSWERS, engine=engine)

                assert result["success"] is True
                assert (org_dir / "goals.md").exists()
                assert (org_dir / "workflows.yaml").exists()
                assert (org_dir / "projects.yaml").exists()
                assert (org_dir / "constraints.md").exists()

    @pytest.mark.asyncio
    async def test_refuses_overwrite_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            org_dir = Path(tmpdir) / "org"
            config_dir = Path(tmpdir) / "config"
            org_dir.mkdir()
            (org_dir / "goals.md").write_text("existing")

            with (
                patch("quarterback.setup_wizard.DATA_DIR", data_dir),
                patch("quarterback.setup_wizard.ORG_CONTEXT_DIR", org_dir),
                patch("quarterback.setup_wizard.CONFIG_DIR", config_dir),
            ):
                result = await apply_setup(SAMPLE_ANSWERS)
                assert result["success"] is False
                assert "existing_config" in result["error"]

    @pytest.mark.asyncio
    async def test_overwrites_with_backup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            org_dir = Path(tmpdir) / "org"
            config_dir = Path(tmpdir) / "config"
            org_dir.mkdir()
            (org_dir / "goals.md").write_text("old content")

            with (
                patch("quarterback.setup_wizard.DATA_DIR", data_dir),
                patch("quarterback.setup_wizard.ORG_CONTEXT_DIR", org_dir),
                patch("quarterback.setup_wizard.CONFIG_DIR", config_dir),
            ):
                from quarterback.database import init_db

                engine = await init_db(":memory:")

                result = await apply_setup(SAMPLE_ANSWERS, engine=engine, overwrite=True)
                assert result["success"] is True

                # Check backup was created
                backups = list(org_dir.glob("goals.md.bak.*"))
                assert len(backups) == 1

                # Check new content was written
                new_content = (org_dir / "goals.md").read_text()
                assert "TestCorp" not in new_content or "Build great developer tools" in new_content

    @pytest.mark.asyncio
    async def test_creates_db_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            org_dir = Path(tmpdir) / "org"
            config_dir = Path(tmpdir) / "config"

            with (
                patch("quarterback.setup_wizard.DATA_DIR", data_dir),
                patch("quarterback.setup_wizard.ORG_CONTEXT_DIR", org_dir),
                patch("quarterback.setup_wizard.CONFIG_DIR", config_dir),
            ):
                from sqlalchemy import select as sa_select
                from quarterback.database import (
                    init_db,
                    get_session,
                    Organization,
                    Workflow,
                    Project,
                )

                engine = await init_db(":memory:")
                result = await apply_setup(SAMPLE_ANSWERS, engine=engine)
                assert result["success"] is True

                async with await get_session(engine) as session:
                    orgs = (await session.execute(sa_select(Organization))).scalars().all()
                    assert len(orgs) == 1
                    assert orgs[0].name == "TestCorp"
                    assert orgs[0].mission == "Build great developer tools"

                    wfs = (await session.execute(sa_select(Workflow))).scalars().all()
                    assert len(wfs) == 2

                    projs = (await session.execute(sa_select(Project))).scalars().all()
                    assert len(projs) == 2
