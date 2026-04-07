"""Tests for the Playbook knowledge wiki module."""

from unittest.mock import patch

import pytest

from quarterback import playbook


@pytest.fixture
def initialized_playbook(tmp_path):
    """Initialize a Playbook with seed data and return its path."""
    pb_path = tmp_path / "playbook"
    result = playbook.initialize_playbook(
        playbook_path=pb_path,
        seed_data={
            "organization": {"name": "Test Corp", "mission": "Build great things"},
            "goals": {
                "annual": ["Launch product", "Grow revenue"],
                "anti_goals": ["Consulting work"],
            },
            "constraints": {
                "hours_per_week": 30,
                "budget_monthly": 500,
                "preferred_stack": ["Python", "TypeScript"],
            },
            "entities": [
                {
                    "name": "Acme Product",
                    "description": "Main SaaS product",
                    "current_state": "Beta",
                },
            ],
            "concepts": [
                {"name": "CI Pipeline", "summary": "Automated build and deploy"},
            ],
            "decisions": [
                {
                    "name": "Chose PostgreSQL",
                    "context": "Needed a relational DB",
                    "decision": "PostgreSQL over MySQL",
                },
            ],
            "projects": [
                {"name": "Backend API", "description": "Core REST API"},
            ],
            "obsidian": True,
        },
    )
    assert result["success"]
    return pb_path


class TestInitialization:
    def test_initialize_creates_structure(self, tmp_path):
        pb = tmp_path / "playbook"
        result = playbook.initialize_playbook(playbook_path=pb)
        assert result["success"]
        assert (pb / "CLAUDE.md").exists()
        assert (pb / "wiki" / "index.md").exists()
        assert (pb / "wiki" / "log.md").exists()
        assert (pb / "wiki" / "entities").is_dir()
        assert (pb / "wiki" / "concepts").is_dir()
        assert (pb / "wiki" / "decisions").is_dir()
        assert (pb / "wiki" / "compiled").is_dir()
        assert (pb / "raw").is_dir()

    def test_initialize_with_seed_data(self, initialized_playbook):
        pb = initialized_playbook
        assert (pb / "wiki" / "entities" / "acme-product.md").exists()
        assert (pb / "wiki" / "concepts" / "ci-pipeline.md").exists()
        assert (pb / "wiki" / "decisions" / "chose-postgresql.md").exists()
        assert (pb / "wiki" / "entities" / "backend-api.md").exists()
        assert (pb / "wiki" / "compiled" / "goals.md").exists()
        assert (pb / "wiki" / "compiled" / "constraints.md").exists()

    def test_initialize_with_obsidian(self, initialized_playbook):
        assert (initialized_playbook / ".obsidian" / "app.json").exists()

    def test_initialize_without_obsidian(self, tmp_path):
        pb = tmp_path / "playbook"
        playbook.initialize_playbook(playbook_path=pb, seed_data={"obsidian": False})
        assert not (pb / ".obsidian").exists()


class TestReadOperations:
    def test_read_page_exists(self, initialized_playbook):
        with patch.object(playbook, "PLAYBOOK_WIKI_DIR", initialized_playbook / "wiki"):
            result = playbook.read_page("entities/acme-product.md")
            assert result["exists"]
            assert "Acme Product" in result["content"]
            assert "last_modified" in result

    def test_read_page_not_exists(self, initialized_playbook):
        with patch.object(playbook, "PLAYBOOK_WIKI_DIR", initialized_playbook / "wiki"):
            result = playbook.read_page("entities/nonexistent.md")
            assert not result["exists"]

    def test_read_index(self, initialized_playbook):
        with patch.object(playbook, "PLAYBOOK_WIKI_DIR", initialized_playbook / "wiki"):
            content = playbook.read_index()
            assert "Index" in content
            assert "Acme Product" in content

    def test_list_pages_all(self, initialized_playbook):
        with patch.object(playbook, "PLAYBOOK_WIKI_DIR", initialized_playbook / "wiki"):
            pages = playbook.list_pages()
            assert len(pages) >= 4  # at least entity, concept, decision, compiled

    def test_list_pages_by_category(self, initialized_playbook):
        with patch.object(playbook, "PLAYBOOK_WIKI_DIR", initialized_playbook / "wiki"):
            entities = playbook.list_pages("entities")
            assert all(p["category"] == "entities" for p in entities)
            assert len(entities) >= 1

    def test_search_pages(self, initialized_playbook):
        with patch.object(playbook, "PLAYBOOK_WIKI_DIR", initialized_playbook / "wiki"):
            results = playbook.search_pages("Acme")
            assert len(results) >= 1
            assert any("Acme" in m for r in results for m in r["matches"])

    def test_search_case_insensitive(self, initialized_playbook):
        with patch.object(playbook, "PLAYBOOK_WIKI_DIR", initialized_playbook / "wiki"):
            results = playbook.search_pages("acme")
            assert len(results) >= 1

    def test_search_no_results(self, initialized_playbook):
        with patch.object(playbook, "PLAYBOOK_WIKI_DIR", initialized_playbook / "wiki"):
            results = playbook.search_pages("xyznonexistent")
            assert len(results) == 0


class TestCompiledFiles:
    def test_read_compiled_goals(self, initialized_playbook):
        with patch.object(
            playbook, "PLAYBOOK_COMPILED_DIR", initialized_playbook / "wiki" / "compiled"
        ):
            content = playbook.read_compiled_goals()
            assert content is not None
            assert "Launch product" in content

    def test_read_compiled_constraints(self, initialized_playbook):
        with patch.object(
            playbook, "PLAYBOOK_COMPILED_DIR", initialized_playbook / "wiki" / "compiled"
        ):
            content = playbook.read_compiled_constraints()
            assert content is not None
            assert "30" in content  # hours_per_week

    def test_read_compiled_missing(self, tmp_path):
        with patch.object(playbook, "PLAYBOOK_COMPILED_DIR", tmp_path):
            assert playbook.read_compiled_goals() is None
            assert playbook.read_compiled_constraints() is None


class TestWriteOperations:
    def test_write_new_page(self, initialized_playbook):
        with patch.object(playbook, "PLAYBOOK_WIKI_DIR", initialized_playbook / "wiki"):
            result = playbook.write_page("entities/new-thing.md", "# New Thing\nContent here.")
            assert result["success"]
            assert result["action"] == "created"
            assert (initialized_playbook / "wiki" / "entities" / "new-thing.md").exists()

    def test_write_update_page(self, initialized_playbook):
        with patch.object(playbook, "PLAYBOOK_WIKI_DIR", initialized_playbook / "wiki"):
            playbook.write_page("entities/new-thing.md", "# Original")
            result = playbook.write_page("entities/new-thing.md", "# Updated")
            assert result["action"] == "updated"

    def test_write_with_log(self, initialized_playbook):
        with patch.object(playbook, "PLAYBOOK_WIKI_DIR", initialized_playbook / "wiki"):
            playbook.write_page("entities/logged.md", "# Logged", log_entry="Created logged page")
            log_content = (initialized_playbook / "wiki" / "log.md").read_text()
            assert "Created logged page" in log_content

    def test_append_log(self, initialized_playbook):
        with patch.object(playbook, "PLAYBOOK_WIKI_DIR", initialized_playbook / "wiki"):
            playbook.append_log("Test log entry")
            content = (initialized_playbook / "wiki" / "log.md").read_text()
            assert "Test log entry" in content


class TestStatus:
    def test_enabled_when_initialized(self, initialized_playbook):
        with patch.object(playbook, "PLAYBOOK_SCHEMA_PATH", initialized_playbook / "CLAUDE.md"):
            assert playbook.is_playbook_enabled()

    def test_disabled_when_missing(self, tmp_path):
        with patch.object(playbook, "PLAYBOOK_SCHEMA_PATH", tmp_path / "CLAUDE.md"):
            assert not playbook.is_playbook_enabled()

    def test_status_initialized(self, initialized_playbook):
        with (
            patch.object(playbook, "PLAYBOOK_SCHEMA_PATH", initialized_playbook / "CLAUDE.md"),
            patch.object(playbook, "PLAYBOOK_DIR", initialized_playbook),
            patch.object(playbook, "PLAYBOOK_WIKI_DIR", initialized_playbook / "wiki"),
            patch.object(
                playbook, "PLAYBOOK_COMPILED_DIR", initialized_playbook / "wiki" / "compiled"
            ),
        ):
            status = playbook.get_playbook_status()
            assert status["initialized"]
            assert status["total_pages"] > 0
            assert status["has_compiled_goals"]
            assert status["has_compiled_constraints"]

    def test_status_not_initialized(self, tmp_path):
        with (
            patch.object(playbook, "PLAYBOOK_SCHEMA_PATH", tmp_path / "CLAUDE.md"),
            patch.object(playbook, "PLAYBOOK_DIR", tmp_path),
        ):
            status = playbook.get_playbook_status()
            assert not status["initialized"]


class TestSeedTemplates:
    def test_seed_entity_page(self):
        content = playbook.seed_entity_page("My Product", "A great product", "In beta")
        assert "# My Product" in content
        assert "A great product" in content
        assert "In beta" in content

    def test_seed_concept_page(self):
        content = playbook.seed_concept_page("CI/CD", "Continuous integration")
        assert "# CI/CD" in content
        assert "Continuous integration" in content

    def test_seed_decision_page(self):
        content = playbook.seed_decision_page(
            "Chose Postgres", context="Needed a DB", decision="Postgres"
        )
        assert "# Decision: Chose Postgres" in content
        assert "Needed a DB" in content

    def test_seed_index(self):
        content = playbook.seed_index_md(
            entities=["- [[Foo]]"],
            concepts=["- [[Bar]]"],
            decisions=["- [[Decision - Baz]]"],
            org_name="Test Corp",
        )
        assert "Test Corp" in content
        assert "[[Foo]]" in content
        assert "[[Bar]]" in content

    def test_compiled_goals_has_anti_goals(self):
        content = playbook.seed_compiled_goals(
            {
                "organization": {"mission": "Build stuff"},
                "goals": {"annual": ["Ship it"], "anti_goals": ["Consulting"]},
            }
        )
        assert "Anti-Goals" in content
        assert "Consulting" in content

    def test_compiled_constraints_has_budget(self):
        content = playbook.seed_compiled_constraints(
            {
                "constraints": {"budget_monthly": 200, "hours_per_week": 20},
            }
        )
        assert "$200" in content
        assert "20" in content


class TestSlugify:
    def test_basic(self):
        assert playbook._slugify("My Product") == "my-product"

    def test_special_chars(self):
        assert playbook._slugify("Test (v2.0)") == "test-v20"

    def test_extra_spaces(self):
        assert playbook._slugify("  Lots   of   spaces  ") == "lots-of-spaces"
