"""Project-scoped meeting record operations."""

import sqlite3


def create_meeting(
    conn: sqlite3.Connection,
    project_id: int,
    title: str,
    content: str,
    summary: str | None = None,
) -> int:
    """Persist one meeting under the active project."""
    cursor = conn.execute(
        """
        INSERT INTO meetings (project_id, title, content, summary)
        VALUES (?, ?, ?, ?)
        """,
        (project_id, title.strip() or "未命名会议", content.strip(), summary),
    )
    conn.commit()
    return int(cursor.lastrowid)


def list_meetings(conn: sqlite3.Connection, project_id: int) -> list[sqlite3.Row]:
    """List meetings for the active project only, newest first."""
    return conn.execute(
        """
        SELECT
            id,
            title,
            COALESCE(meeting_date, created_at) AS meeting_time,
            summary,
            CASE
                WHEN length(COALESCE(content, '')) > 100
                THEN substr(content, 1, 100) || '...'
                ELSE COALESCE(content, '')
            END AS content_excerpt
        FROM meetings
        WHERE project_id = ?
        ORDER BY COALESCE(meeting_date, created_at) DESC, id DESC
        """,
        (project_id,),
    ).fetchall()
