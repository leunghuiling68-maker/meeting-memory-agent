"""Project-scoped action item mock extraction and display helpers."""

import re
import sqlite3


ACTION_KEYWORDS = ("下次", "待讨论", "需要", "负责人", "TODO", "待办", "截止", "讨论", "推进", "完成")


def extract_action_items_placeholder(*texts: str) -> list[dict[str, str]]:
    """Extract mock action items from meeting text or candidate memories."""
    items: list[dict[str, str]] = []
    for text in texts:
        for sentence in _split_sentences(text or ""):
            if not any(keyword in sentence for keyword in ACTION_KEYWORDS):
                continue
            task = _normalize_task(sentence)
            if not task:
                continue
            items.append(
                {
                    "task": task,
                    "owner": _extract_owner(sentence),
                    "status": "open",
                    "deadline": _extract_deadline(sentence),
                }
            )
    return _dedupe_items(items)


def save_action_items(
    conn: sqlite3.Connection,
    project_id: int,
    meeting_id: int,
    action_items: list[dict[str, str]],
) -> list[int]:
    """Persist mock action items for the active project and meeting."""
    ids: list[int] = []
    for item in action_items:
        if _action_exists(conn, project_id, meeting_id, item["task"]):
            continue
        cursor = conn.execute(
            """
            INSERT INTO action_items (
                meeting_id,
                source_meeting_id,
                project_id,
                task,
                owner,
                status,
                deadline
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                meeting_id,
                meeting_id,
                project_id,
                item["task"],
                item.get("owner") or None,
                item.get("status") or "open",
                item.get("deadline") or None,
            ),
        )
        ids.append(int(cursor.lastrowid))
    conn.commit()
    return ids


def list_action_items(
    conn: sqlite3.Connection,
    project_id: int,
) -> list[sqlite3.Row]:
    """List action items for the active project only."""
    return conn.execute(
        """
        SELECT
            action_items.id,
            action_items.task,
            action_items.owner,
            action_items.status,
            action_items.deadline,
            action_items.created_at,
            action_items.source_meeting_id,
            meetings.title AS source_meeting_title
        FROM action_items
        LEFT JOIN meetings ON action_items.source_meeting_id = meetings.id
        WHERE action_items.project_id = ?
        ORDER BY action_items.updated_at DESC, action_items.id DESC
        """,
        (project_id,),
    ).fetchall()


def update_action_item_status(
    conn: sqlite3.Connection,
    project_id: int,
    action_item_id: int,
    status: str,
) -> None:
    """Update action item status in the active project."""
    if status not in {"open", "doing", "done", "overdue"}:
        raise ValueError("unsupported action item status")
    conn.execute(
        """
        UPDATE action_items
        SET status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE project_id = ?
          AND id = ?
        """,
        (status, project_id, action_item_id),
    )
    conn.commit()


def get_action_item(
    conn: sqlite3.Connection,
    project_id: int,
    action_item_id: int,
) -> sqlite3.Row | None:
    """Load one open action item scoped to the active project."""
    return conn.execute(
        """
        SELECT
            action_items.id,
            action_items.task,
            action_items.owner,
            action_items.status,
            action_items.deadline,
            action_items.created_at,
            action_items.source_meeting_id,
            meetings.title AS source_meeting_title,
            meetings.summary AS source_meeting_summary
        FROM action_items
        LEFT JOIN meetings ON action_items.source_meeting_id = meetings.id
        WHERE action_items.project_id = ?
          AND action_items.id = ?
        """,
        (project_id, action_item_id),
    ).fetchone()


def count_action_items_for_meeting(
    conn: sqlite3.Connection,
    project_id: int,
    meeting_id: int,
) -> int:
    """Count action items generated for one project meeting."""
    return int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM action_items
            WHERE project_id = ?
              AND source_meeting_id = ?
            """,
            (project_id, meeting_id),
        ).fetchone()[0]
    )


def detect_action_item_conflicts(
    conn: sqlite3.Connection,
    project_id: int,
    proposed_task: str,
) -> list[sqlite3.Row]:
    """Find simple conflicts with existing open action items in a project."""
    if not proposed_task.strip():
        return []
    return conn.execute(
        """
        SELECT id, task, owner, deadline
        FROM action_items
        WHERE project_id = ?
          AND status = 'open'
          AND task LIKE ?
        ORDER BY updated_at DESC
        """,
        (project_id, f"%{proposed_task.strip()}%"),
    ).fetchall()


def _split_sentences(text: str) -> list[str]:
    return [
        item.strip(" -\t，,。.")
        for item in re.split(r"[。！？!?\n]+", text)
        if item.strip(" -\t，,。.")
    ]


def _normalize_task(sentence: str) -> str:
    """Turn a matching sentence into a compact mock task."""
    text = _focus_action_phrase(sentence)

    if text.startswith("下次会议讨论"):
        text = "讨论 " + text.removeprefix("下次会议讨论").strip()
    elif text.startswith("下次讨论"):
        text = "讨论 " + text.removeprefix("下次讨论").strip()
    elif text.startswith("待讨论"):
        text = "讨论 " + text.removeprefix("待讨论").strip(" ：:")
    elif text.startswith("需要"):
        text = "处理 " + text.removeprefix("需要").strip(" ：:")
    elif text.startswith("讨论"):
        text = "讨论 " + text.removeprefix("讨论").strip(" ：:")
    elif text.startswith("推进"):
        text = "推进 " + text.removeprefix("推进").strip(" ：:")
    elif text.startswith("完成"):
        text = "完成 " + text.removeprefix("完成").strip(" ：:")
    elif text.upper().startswith("TODO"):
        text = text[4:].strip(" ：:")
    elif text.startswith("待办"):
        text = text.removeprefix("待办").strip(" ：:")
    else:
        text = text.replace("下次会议", "").replace("下次", "").strip(" ，,。.")

    text = re.sub(r"负责人[:：]\s*[\w\u4e00-\u9fff]+", "", text).strip(" ，,。.")
    text = re.sub(r"\s+", " ", text)
    if "DeepSeek API 接入" in text and "方案" not in text:
        text = text.replace("讨论 DeepSeek API 接入", "讨论 DeepSeek API 接入方案")
    return text[:120]


def _focus_action_phrase(sentence: str) -> str:
    """Keep the action-looking part when a sentence contains multiple clauses."""
    for marker in ("下次会议讨论", "下次讨论", "待讨论", "TODO", "待办", "需要", "讨论", "推进", "完成", "下次"):
        if marker in sentence:
            return sentence[sentence.index(marker) :]
    return sentence


def _extract_owner(sentence: str) -> str:
    """Extract a simple owner marker like 负责人：张三."""
    match = re.search(r"负责人[:：]\s*([\w\u4e00-\u9fff]+)", sentence)
    return match.group(1) if match else ""


def _extract_deadline(sentence: str) -> str:
    """Extract a simple deadline marker like 截止：周五."""
    match = re.search(r"截止(?:日期)?[:：]?\s*([\w\u4e00-\u9fff\-月日号/]+)", sentence)
    return match.group(1)[:30] if match else ""


def _dedupe_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for item in items:
        key = _normalize_for_compare(item["task"])
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _action_exists(
    conn: sqlite3.Connection,
    project_id: int,
    meeting_id: int,
    task: str,
) -> bool:
    key = _normalize_for_compare(task)
    rows = conn.execute(
        """
        SELECT task
        FROM action_items
        WHERE project_id = ?
          AND source_meeting_id = ?
          AND status = 'open'
        """,
        (project_id, meeting_id),
    ).fetchall()
    return any(_normalize_for_compare(row["task"]) == key for row in rows)


def _normalize_for_compare(text: str) -> str:
    return re.sub(r"[\s，,。.!！？?:：；;、\-]+", "", text or "").lower()
