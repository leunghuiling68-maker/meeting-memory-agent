"""Development seed data for the MVP skeleton."""

import sqlite3


def ensure_demo_project(conn: sqlite3.Connection) -> int:
    """Create a default project so the Streamlit shell can run immediately."""
    row = conn.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
    if row:
        return int(row["id"])

    cursor = conn.execute(
        """
        INSERT INTO projects (name, description)
        VALUES (?, ?)
        """,
        ("演示项目", "Project-based Meeting Memory Agent MVP demo project."),
    )
    conn.commit()
    return int(cursor.lastrowid)
