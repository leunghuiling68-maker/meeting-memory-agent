"""SQLite connection and schema initialization."""

from pathlib import Path
import sqlite3


def get_connection(db_path: Path | str) -> sqlite3.Connection:
    """Return a SQLite connection configured for small MVP queries."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create or migrate MVP tables without destroying existing data."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            meeting_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            content TEXT,
            summary TEXT,
            decisions TEXT,
            risks TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS action_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id INTEGER,
            source_meeting_id INTEGER,
            project_id INTEGER NOT NULL,
            task TEXT NOT NULL,
            owner TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            deadline TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE SET NULL,
            FOREIGN KEY (source_meeting_id) REFERENCES meetings(id) ON DELETE SET NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS candidate_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            meeting_id INTEGER,
            source_meeting_id INTEGER,
            content TEXT NOT NULL,
            memory_text TEXT,
            memory_type TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            user_edited_content TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE SET NULL,
            FOREIGN KEY (source_meeting_id) REFERENCES meetings(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            source_meeting_id INTEGER,
            memory_text TEXT NOT NULL,
            memory_type TEXT,
            meeting_id INTEGER,
            content TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (source_meeting_id) REFERENCES meetings(id) ON DELETE SET NULL,
            FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE SET NULL
        );
        """
    )
    _migrate_existing_schema(conn)
    conn.commit()


def _migrate_existing_schema(conn: sqlite3.Connection) -> None:
    """Add columns required by the product model to older local databases."""
    memory_columns = _table_columns(conn, "memories")
    if "source_meeting_id" not in memory_columns:
        conn.execute("ALTER TABLE memories ADD COLUMN source_meeting_id INTEGER")
        conn.execute(
            """
            UPDATE memories
            SET source_meeting_id = meeting_id
            WHERE source_meeting_id IS NULL
              AND meeting_id IS NOT NULL
            """
        )

    memory_columns = _table_columns(conn, "memories")
    if "memory_text" not in memory_columns:
        conn.execute("ALTER TABLE memories ADD COLUMN memory_text TEXT")
        conn.execute(
            """
            UPDATE memories
            SET memory_text = content
            WHERE memory_text IS NULL
              AND content IS NOT NULL
            """
        )

    candidate_columns = _table_columns(conn, "candidate_memories")
    if "meeting_id" not in candidate_columns:
        conn.execute("ALTER TABLE candidate_memories ADD COLUMN meeting_id INTEGER")
    if "source_meeting_id" not in candidate_columns:
        conn.execute("ALTER TABLE candidate_memories ADD COLUMN source_meeting_id INTEGER")
        conn.execute(
            """
            UPDATE candidate_memories
            SET source_meeting_id = meeting_id
            WHERE source_meeting_id IS NULL
              AND meeting_id IS NOT NULL
            """
        )
    if "memory_text" not in candidate_columns:
        conn.execute("ALTER TABLE candidate_memories ADD COLUMN memory_text TEXT")
        conn.execute(
            """
            UPDATE candidate_memories
            SET memory_text = content
            WHERE memory_text IS NULL
              AND content IS NOT NULL
            """
        )
    if "memory_type" not in candidate_columns:
        conn.execute("ALTER TABLE candidate_memories ADD COLUMN memory_type TEXT")
    if "status" not in candidate_columns:
        conn.execute(
            "ALTER TABLE candidate_memories ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'"
        )

    memory_columns = _table_columns(conn, "memories")
    if "memory_type" not in memory_columns:
        conn.execute("ALTER TABLE memories ADD COLUMN memory_type TEXT")

    action_columns = _table_columns(conn, "action_items")
    if "source_meeting_id" not in action_columns:
        conn.execute("ALTER TABLE action_items ADD COLUMN source_meeting_id INTEGER")
        conn.execute(
            """
            UPDATE action_items
            SET source_meeting_id = meeting_id
            WHERE source_meeting_id IS NULL
              AND meeting_id IS NOT NULL
            """
        )


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    """Return existing column names for a SQLite table."""
    return {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
