#!/usr/bin/env python3
"""
Migration: Add agent execution and webhook tables.
"""

import sqlite3
from quarterback.config import DB_PATH


def run_migration(db_path: str = None):
    if db_path is None:
        db_path = str(DB_PATH)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"Running migration on {db_path}...")

    agent_columns = [
        ("agent_config", "TEXT"),
        ("agent_ready", "BOOLEAN DEFAULT 0"),
        ("agent_status", "VARCHAR(50)"),
        ("agent_output", "TEXT"),
        ("agent_started_at", "DATETIME"),
        ("agent_completed_at", "DATETIME"),
    ]

    for col_name, col_type in agent_columns:
        try:
            cursor.execute(f"ALTER TABLE tasks ADD COLUMN {col_name} {col_type}")
            print(f"  Added tasks.{col_name}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print(f"  tasks.{col_name} already exists, skipping")
            else:
                raise

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS webhooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(255) NOT NULL,
            url VARCHAR(1024) NOT NULL,
            secret VARCHAR(255),
            events TEXT NOT NULL,
            active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_triggered_at DATETIME,
            failure_count INTEGER DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS webhook_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            webhook_id INTEGER NOT NULL,
            event_type VARCHAR(100) NOT NULL,
            payload TEXT NOT NULL,
            status VARCHAR(50) NOT NULL,
            response_code INTEGER,
            response_body TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            sent_at DATETIME,
            FOREIGN KEY (webhook_id) REFERENCES webhooks(id)
        )
    """)

    indexes = [
        ("idx_tasks_agent_ready", "tasks", "agent_ready"),
        ("idx_tasks_agent_status", "tasks", "agent_status"),
        ("idx_webhooks_active", "webhooks", "active"),
        ("idx_webhook_events_status", "webhook_events", "status"),
        ("idx_webhook_events_webhook_id", "webhook_events", "webhook_id"),
    ]

    for idx_name, table, column in indexes:
        try:
            cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({column})")
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()
    print("Migration completed successfully!")


if __name__ == "__main__":
    run_migration()
