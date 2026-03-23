#!/usr/bin/env python3
"""
Migration: Add advisory_documents and advisory_recommendations tables.
"""

import asyncio
from sqlalchemy import text
from quarterback.database import init_db, get_session
from quarterback.config import DB_PATH


async def run_migration():
    print("Starting migration: add_advisory_tables")
    print("=" * 80)

    engine = await init_db(str(DB_PATH))

    async with await get_session(engine) as session:
        result = await session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='advisory_documents'")
        )
        if result.fetchone():
            print("Tables already exist, skipping migration")
            return

        print("Creating advisory_documents table...")
        await session.execute(
            text("""
            CREATE TABLE advisory_documents (
                id INTEGER PRIMARY KEY,
                workflow_id INTEGER,
                project_id INTEGER,
                title VARCHAR(512) NOT NULL,
                source VARCHAR(512),
                source_type VARCHAR(50),
                content TEXT NOT NULL,
                status VARCHAR(50) DEFAULT 'pending_review' NOT NULL,
                analysis_result TEXT,
                adoption_notes TEXT,
                adopted_recommendations TEXT,
                rejected_recommendations TEXT,
                tags TEXT,
                priority INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                reviewed_at DATETIME,
                adopted_at DATETIME,
                FOREIGN KEY(workflow_id) REFERENCES workflows (id),
                FOREIGN KEY(project_id) REFERENCES projects (id)
            )
        """)
        )

        print("Creating advisory_recommendations table...")
        await session.execute(
            text("""
            CREATE TABLE advisory_recommendations (
                id INTEGER PRIMARY KEY,
                advisory_document_id INTEGER NOT NULL,
                recommendation_text TEXT NOT NULL,
                category VARCHAR(100),
                status VARCHAR(50) DEFAULT 'pending' NOT NULL,
                decision_rationale TEXT,
                conflicts_with TEXT,
                aligns_with TEXT,
                estimated_effort_hours FLOAT,
                estimated_impact INTEGER,
                implemented_as_task_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                decided_at DATETIME,
                FOREIGN KEY(advisory_document_id) REFERENCES advisory_documents (id),
                FOREIGN KEY(implemented_as_task_id) REFERENCES tasks (id)
            )
        """)
        )

        print("Creating indexes...")
        for idx_sql in [
            "CREATE INDEX idx_advisory_docs_status ON advisory_documents(status)",
            "CREATE INDEX idx_advisory_docs_project ON advisory_documents(project_id)",
            "CREATE INDEX idx_advisory_recs_document ON advisory_recommendations(advisory_document_id)",
            "CREATE INDEX idx_advisory_recs_status ON advisory_recommendations(status)",
        ]:
            await session.execute(text(idx_sql))

        await session.commit()
        print("Migration completed successfully")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_migration())
