#!/usr/bin/env python3
"""Migration: Add cost column to tasks table."""

import sqlite3

from quarterback.config import DB_PATH


def run_migration(db_path: str = None):
    if db_path is None:
        db_path = str(DB_PATH)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"Running migration on {db_path}...")

    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN cost REAL")
        print("  Added tasks.cost")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("  tasks.cost already exists, skipping")
        else:
            raise

    conn.commit()
    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    run_migration()
