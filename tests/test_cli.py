"""Smoke tests for the CLI."""

import pytest
import subprocess
import sys
import sqlite3


class TestInit:
    def test_init_creates_directories(self, tmp_path, monkeypatch):
        qb_home = tmp_path / ".quarterback"
        monkeypatch.setattr("quarterback.cli.QUARTERBACK_HOME", qb_home)
        monkeypatch.setattr("quarterback.cli.DATA_DIR", qb_home / "data")
        monkeypatch.setattr("quarterback.cli.ORG_CONTEXT_DIR", qb_home / "org-context")
        monkeypatch.setattr("quarterback.cli.CONFIG_DIR", qb_home / "config")
        monkeypatch.setattr("quarterback.cli.DB_PATH", qb_home / "data" / "tasks.db")
        monkeypatch.setattr("quarterback.config.DB_PATH", qb_home / "data" / "tasks.db")

        from quarterback.cli import cmd_init

        cmd_init()

        assert (qb_home / "data").exists()
        assert (qb_home / "org-context").exists()
        assert (qb_home / "config").exists()
        assert (qb_home / "data" / "tasks.db").exists()


class TestMigrate:
    def test_migrate_nonexistent_source(self, tmp_path):
        from quarterback.cli import cmd_migrate

        with pytest.raises(SystemExit):
            cmd_migrate(str(tmp_path / "nonexistent"))

    def test_migrate_no_database(self, tmp_path):
        from quarterback.cli import cmd_migrate

        source = tmp_path / "source"
        source.mkdir()
        with pytest.raises(SystemExit):
            cmd_migrate(str(source))

    def test_migrate_copies_database(self, tmp_path, monkeypatch):
        source = tmp_path / "source"
        (source / "data").mkdir(parents=True)
        db_path = source / "data" / "tasks.db"

        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY, description TEXT)")
        conn.execute("INSERT INTO tasks (description) VALUES ('test task')")
        conn.execute("CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT)")
        conn.commit()
        conn.close()

        dest = tmp_path / ".quarterback"
        monkeypatch.setattr("quarterback.cli.QUARTERBACK_HOME", dest)
        monkeypatch.setattr("quarterback.cli.DATA_DIR", dest / "data")
        monkeypatch.setattr("quarterback.cli.ORG_CONTEXT_DIR", dest / "org-context")
        monkeypatch.setattr("quarterback.cli.CONFIG_DIR", dest / "config")
        monkeypatch.setattr("quarterback.cli.DB_PATH", dest / "data" / "tasks.db")
        monkeypatch.setattr("quarterback.config.DB_PATH", dest / "data" / "tasks.db")

        from quarterback.cli import cmd_migrate

        cmd_migrate(str(source))

        assert (dest / "data" / "tasks.db").exists()

        conn = sqlite3.connect(str(dest / "data" / "tasks.db"))
        count = conn.execute("SELECT count(*) FROM tasks").fetchone()[0]
        conn.close()
        assert count == 1


class TestCLIHelp:
    def test_help_exits_zero(self):
        result = subprocess.run(
            [sys.executable, "-m", "quarterback.cli", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "quarterback" in result.stdout.lower() or "strategic" in result.stdout.lower()

    def test_no_command_shows_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "quarterback.cli"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
