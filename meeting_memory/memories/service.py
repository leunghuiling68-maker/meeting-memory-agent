"""Project-scoped Memory Retrieval and Memory Update services."""

import re
import sqlite3


MEMORY_PREFIXES = ("决策", "约束", "待讨论", "需求", "风险", "事实", "待办")
LOW_VALUE_PATTERNS = (
    "暂无可参考",
    "暂无可用历史记忆",
    "当前项目暂无",
    "本次会议暂无",
    "会议形成的新项目记忆",
    "Mock 会议纪要",
    "后续需要人工确认",
)


def generate_candidate_memory(
    conn: sqlite3.Connection,
    project_id: int,
    meeting_id: int | None,
    source_text: str,
) -> int | None:
    """Create one valuable, deduped candidate memory for later human review."""
    content = source_text.strip()
    if not _is_valuable_candidate(content):
        return None
    if memory_like_exists(conn, project_id, content):
        return None
    memory_type = memory_type_from_text(content)
    cursor = conn.execute(
        """
        INSERT INTO candidate_memories (
            project_id,
            meeting_id,
            source_meeting_id,
            content,
            memory_text,
            memory_type,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, 'pending')
        """,
        (project_id, meeting_id, meeting_id, content, content, memory_type),
    )
    conn.commit()
    return int(cursor.lastrowid)


def generate_mock_candidate_memories(
    conn: sqlite3.Connection,
    project_id: int,
    meeting_id: int,
    meeting_title: str,
    meeting_content: str,
    summary: str,
    memory_context: str,
) -> list[int]:
    """Generate structured candidate memories without a real LLM."""
    candidates = _extract_structured_candidates(meeting_content)
    if not candidates:
        candidates = [
            f"事实：会议《{meeting_title.strip() or '未命名会议'}》记录了新的项目讨论内容。"
        ]

    ids: list[int] = []
    for candidate in candidates:
        candidate_id = generate_candidate_memory(
            conn,
            project_id=project_id,
            meeting_id=meeting_id,
            source_text=candidate,
        )
        if candidate_id is not None:
            ids.append(candidate_id)
    return ids


def list_candidate_memories(
    conn: sqlite3.Connection,
    project_id: int,
) -> list[sqlite3.Row]:
    """List pending candidate memories for the active project only."""
    return conn.execute(
        """
        SELECT
            candidate_memories.id,
            candidate_memories.project_id,
            candidate_memories.meeting_id,
            COALESCE(candidate_memories.source_meeting_id, candidate_memories.meeting_id) AS source_meeting_id,
            candidate_memories.content,
            COALESCE(candidate_memories.memory_text, candidate_memories.content) AS memory_text,
            candidate_memories.memory_type,
            candidate_memories.status,
            candidate_memories.created_at,
            meetings.title AS meeting_title,
            EXISTS (
                SELECT 1
                FROM memories
                WHERE memories.project_id = candidate_memories.project_id
                  AND (
                      memories.memory_text = COALESCE(candidate_memories.memory_text, candidate_memories.content)
                      OR instr(
                          replace(replace(replace(memories.memory_text, ' ', ''), '，', ''), '。', ''),
                          replace(replace(replace(COALESCE(candidate_memories.memory_text, candidate_memories.content), ' ', ''), '，', ''), '。', '')
                      ) > 0
                      OR instr(
                          replace(replace(replace(COALESCE(candidate_memories.memory_text, candidate_memories.content), ' ', ''), '，', ''), '。', ''),
                          replace(replace(replace(memories.memory_text, ' ', ''), '，', ''), '。', '')
                      ) > 0
                  )
            ) AS possible_duplicate
        FROM candidate_memories
        LEFT JOIN meetings ON candidate_memories.meeting_id = meetings.id
        WHERE candidate_memories.project_id = ?
          AND candidate_memories.status = 'pending'
        ORDER BY candidate_memories.created_at DESC, candidate_memories.id DESC
        """,
        (project_id,),
    ).fetchall()


def user_confirm_memory(
    conn: sqlite3.Connection,
    candidate_id: int,
    decision: str,
    edited_content: str | None = None,
) -> int | None:
    """Approve or reject a candidate memory, deduping formal memories."""
    if decision not in {"approved", "rejected", "merged"}:
        raise ValueError("decision must be approved, rejected, or merged")

    candidate = conn.execute(
        """
        SELECT
            id,
            project_id,
            meeting_id,
            COALESCE(source_meeting_id, meeting_id) AS source_meeting_id,
            COALESCE(memory_text, content) AS memory_text,
            COALESCE(memory_type, ?) AS memory_type,
            content,
            status
        FROM candidate_memories
        WHERE id = ?
        """,
        ("fact", candidate_id),
    ).fetchone()
    if candidate is None:
        raise ValueError(f"candidate memory not found: {candidate_id}")
    if candidate["status"] != "pending":
        raise ValueError("candidate memory has already been reviewed")

    if decision in {"rejected", "merged"}:
        conn.execute(
            """
            UPDATE candidate_memories
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (decision, candidate_id),
        )
        conn.commit()
        return None

    memory_id = None
    final_text = (edited_content or candidate["memory_text"]).strip()
    final_type = candidate["memory_type"] or memory_type_from_text(final_text)
    if not formal_memory_exists(conn, candidate["project_id"], final_text):
        cursor = conn.execute(
            """
            INSERT INTO memories (
                project_id,
                source_meeting_id,
                memory_text,
                memory_type,
                meeting_id,
                content
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                candidate["project_id"],
                candidate["source_meeting_id"],
                final_text,
                final_type,
                candidate["meeting_id"],
                final_text,
            ),
        )
        memory_id = int(cursor.lastrowid)

    conn.execute(
        """
        UPDATE candidate_memories
        SET status = 'approved', updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (candidate_id,),
    )
    conn.commit()
    return memory_id


def retrieve_project_memories(
    conn: sqlite3.Connection,
    project_id: int,
    limit: int = 50,
) -> list[sqlite3.Row]:
    """Retrieve high-quality formal memories scoped to one project."""
    return conn.execute(
        """
        SELECT
            memories.id,
            memories.memory_text,
            memories.memory_type,
            memories.source_meeting_id,
            memories.created_at,
            meetings.title AS source_meeting_title
        FROM memories
        LEFT JOIN meetings ON memories.source_meeting_id = meetings.id
        WHERE memories.project_id = ?
        ORDER BY memories.created_at DESC, memories.id DESC
        LIMIT ?
        """,
        (project_id, limit),
    ).fetchall()


def get_recent_project_memories(
    conn: sqlite3.Connection,
    project_id: int,
    limit: int = 5,
) -> list[sqlite3.Row]:
    """Return recent formal memories for Memory Retrieval."""
    return retrieve_project_memories(conn, project_id, limit=limit)


def get_recent_project_meetings(
    conn: sqlite3.Connection,
    project_id: int,
    limit: int = 3,
) -> list[sqlite3.Row]:
    """Return recent meetings for Memory Retrieval."""
    return conn.execute(
        """
        SELECT
            id,
            title,
            COALESCE(meeting_date, created_at) AS meeting_time,
            summary
        FROM meetings
        WHERE project_id = ?
        ORDER BY COALESCE(meeting_date, created_at) DESC, id DESC
        LIMIT ?
        """,
        (project_id, limit),
    ).fetchall()


def get_open_action_items(
    conn: sqlite3.Connection,
    project_id: int,
    limit: int = 5,
) -> list[sqlite3.Row]:
    """Return open action items for Memory Retrieval."""
    return conn.execute(
        """
        SELECT task, owner, deadline
        FROM action_items
        WHERE project_id = ?
          AND status = 'open'
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        (project_id, limit),
    ).fetchall()


def count_candidate_memories_for_meeting(
    conn: sqlite3.Connection,
    project_id: int,
    meeting_id: int,
) -> int:
    """Count candidate memories generated for one project meeting."""
    return int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM candidate_memories
            WHERE project_id = ?
              AND meeting_id = ?
            """,
            (project_id, meeting_id),
        ).fetchone()[0]
    )


def count_approved_memories_for_meeting(
    conn: sqlite3.Connection,
    project_id: int,
    meeting_id: int,
) -> int:
    """Count approved formal memories generated from one project meeting."""
    return int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM memories
            WHERE project_id = ?
              AND source_meeting_id = ?
            """,
            (project_id, meeting_id),
        ).fetchone()[0]
    )


def get_referenced_memories_for_meeting(
    conn: sqlite3.Connection,
    project_id: int,
    meeting_id: int,
    limit: int = 3,
) -> list[sqlite3.Row]:
    """Infer a simple cross-meeting reference chain for a meeting."""
    meeting = conn.execute(
        """
        SELECT created_at, summary
        FROM meetings
        WHERE project_id = ?
          AND id = ?
        """,
        (project_id, meeting_id),
    ).fetchone()
    if meeting is None or not meeting_used_memory(meeting["summary"]):
        return []

    return conn.execute(
        """
        SELECT
            memories.memory_text,
            memories.created_at,
            meetings.title AS source_meeting_title
        FROM memories
        LEFT JOIN meetings ON memories.source_meeting_id = meetings.id
        WHERE memories.project_id = ?
          AND memories.created_at <= ?
          AND (memories.source_meeting_id IS NULL OR memories.source_meeting_id != ?)
        ORDER BY memories.created_at DESC, memories.id DESC
        LIMIT ?
        """,
        (project_id, meeting["created_at"], meeting_id, limit),
    ).fetchall()


def build_memory_context(
    conn: sqlite3.Connection,
    project_id: int,
    memory_limit: int = 5,
    meeting_limit: int = 3,
    action_limit: int = 5,
) -> str:
    """Build structured project context for mock generation."""
    memories = get_recent_project_memories(conn, project_id, limit=memory_limit)
    meetings = get_recent_project_meetings(conn, project_id, limit=meeting_limit)
    action_items = get_open_action_items(conn, project_id, limit=action_limit)

    lines = ["[Project Memories]"]
    if memories:
        lines.extend(f"- {row['memory_text']}" for row in memories)
    else:
        lines.append("- 暂无已确认项目记忆")

    lines.append("")
    lines.append("[Recent Meetings]")
    if meetings:
        lines.extend(
            f"- {row['title']} ({row['meeting_time']}): {row['summary'] or '暂无摘要'}"
            for row in meetings
        )
    else:
        lines.append("- 暂无历史会议")

    lines.append("")
    lines.append("[Open Action Items]")
    if action_items:
        lines.extend(
            f"- {row['task']} | owner={row['owner'] or '未指定'} | deadline={row['deadline'] or '未指定'}"
            for row in action_items
        )
    else:
        lines.append("- 暂无未完成待办")

    return "\n".join(lines)


def infer_memory_category(memory_text: str) -> str:
    """Infer display category using mock keyword rules."""
    text = memory_text or ""
    prefix = text.split("：", 1)[0].strip()
    if prefix in {"决策", "需求", "风险", "待办", "事实", "约束"}:
        return prefix
    if prefix == "待讨论":
        return "待办"

    if any(word in text for word in ("决定", "采用", "使用", "确认", "选择")):
        return "决策"
    if any(word in text for word in ("需求", "新增", "优化", "支持", "添加")):
        return "需求"
    if any(word in text for word in ("风险", "问题", "不稳定", "失败", "无法验证")):
        return "风险"
    if any(word in text for word in ("下次", "待讨论", "TODO", "待办", "需要")):
        return "待办"
    if any(word in text for word in ("不接入", "暂不", "限制", "约束")):
        return "约束"
    return "事实"


def memory_tag_class(category: str) -> str:
    """Return CSS tag class for a memory category."""
    return {
        "决策": "tag-blue",
        "需求": "tag-purple",
        "风险": "tag-red",
        "待办": "tag-orange",
        "约束": "tag-slate",
        "事实": "tag-green",
    }.get(category, "tag-green")


def memory_type_from_text(memory_text: str) -> str:
    """Return stable English memory type for storage."""
    return {
        "决策": "decision",
        "需求": "requirement",
        "风险": "risk",
        "待办": "action",
        "约束": "constraint",
        "事实": "fact",
    }.get(infer_memory_category(memory_text), "fact")


def memory_category_from_type(memory_type: str | None, fallback_text: str = "") -> str:
    """Return display category from stored memory type."""
    if memory_type:
        return {
            "decision": "决策",
            "requirement": "需求",
            "risk": "风险",
            "action": "待办",
            "constraint": "约束",
            "fact": "事实",
        }.get(memory_type, infer_memory_category(fallback_text))
    return infer_memory_category(fallback_text)


def meeting_used_memory(summary: str | None) -> bool:
    """Infer whether a stored meeting used historical project memory."""
    return bool(summary and "已参考当前项目记忆" in summary)


def memory_like_exists(conn: sqlite3.Connection, project_id: int, text: str) -> bool:
    """Check duplicate candidate/formal memories in one project."""
    existing_texts = [
        row["memory_text"]
        for row in conn.execute(
            "SELECT memory_text FROM memories WHERE project_id = ?",
            (project_id,),
        ).fetchall()
    ]
    existing_texts.extend(
        row["content"]
        for row in conn.execute(
            """
            SELECT content
            FROM candidate_memories
            WHERE project_id = ?
              AND status = 'pending'
            """,
            (project_id,),
        ).fetchall()
    )
    return any(_is_similar_memory(text, existing) for existing in existing_texts)


def formal_memory_exists(conn: sqlite3.Connection, project_id: int, text: str) -> bool:
    """Check duplicate formal memories in one project."""
    rows = conn.execute(
        "SELECT memory_text FROM memories WHERE project_id = ?",
        (project_id,),
    ).fetchall()
    return any(_is_similar_memory(text, row["memory_text"]) for row in rows)


def _extract_structured_candidates(meeting_content: str) -> list[str]:
    sentences = _split_sentences(meeting_content)
    text = "\n".join(sentences)
    candidates: list[str] = []

    if "Streamlit" in text and "SQLite" in text:
        candidates.append("决策：MVP 阶段继续使用 Streamlit + SQLite")
    if "向量数据库" in text and any(word in text for word in ("不接入", "暂不", "不引入")):
        candidates.append("约束：暂不接入向量数据库")
    if "DeepSeek API" in text and any(word in text for word in ("下次", "待讨论", "讨论")):
        candidates.append("待办：讨论 DeepSeek API 接入方案")
    if "候选记忆" in text and any(word in text for word in ("优化", "展示", "改进")):
        candidates.append("需求：优化候选记忆展示")
    if "真实 LLM" in text or "摘要质量" in text:
        candidates.append("风险：真实 LLM 接入前无法验证摘要质量")

    for sentence in sentences:
        if _covered_by_canonical_rule(sentence):
            continue
        if any(word in sentence for word in ("决定", "采用", "使用", "确认", "选择", "继续使用")):
            candidates.append(f"决策：{_clean_memory_body(sentence)}")
        if any(word in sentence for word in ("不接入", "暂不", "限制", "约束", "不引入")):
            candidates.append(f"约束：{_clean_memory_body(sentence)}")
        if any(word in sentence for word in ("待讨论", "下次", "TODO", "待办")):
            candidates.append(f"待办：{_clean_memory_body(sentence)}")
        if any(word in sentence for word in ("需求", "新增", "优化", "支持", "添加", "需要")):
            candidates.append(f"需求：{_clean_memory_body(sentence)}")
        if any(word in sentence for word in ("风险", "问题", "不稳定", "失败", "无法验证")):
            candidates.append(f"风险：{_clean_memory_body(sentence)}")

    return _dedupe_candidates(candidates)


def _covered_by_canonical_rule(sentence: str) -> bool:
    return (
        ("Streamlit" in sentence and "SQLite" in sentence)
        or ("向量数据库" in sentence and any(word in sentence for word in ("不接入", "暂不", "不引入")))
        or ("DeepSeek API" in sentence and any(word in sentence for word in ("下次", "待讨论", "讨论")))
    )


def _split_sentences(text: str) -> list[str]:
    return [
        item.strip(" -\t，,。.")
        for item in re.split(r"[。！？!?\n]+", text or "")
        if item.strip(" -\t，,。.")
    ]


def _clean_memory_body(text: str) -> str:
    body = re.sub(r"^(TODO[:：]?|待办[:：]?)", "", text, flags=re.I).strip()
    return body[:80].strip(" ，,。.")


def _is_valuable_candidate(content: str) -> bool:
    if not content:
        return False
    if any(pattern in content for pattern in LOW_VALUE_PATTERNS):
        return False
    if not content.startswith(MEMORY_PREFIXES):
        return False
    body = content.split("：", 1)[-1].strip()
    return 4 <= len(body) <= 120


def _dedupe_candidates(candidates: list[str]) -> list[str]:
    result: list[str] = []
    seen: list[str] = []
    for candidate in candidates:
        if not _is_valuable_candidate(candidate):
            continue
        if any(_is_similar_memory(candidate, old) for old in seen):
            continue
        seen.append(candidate)
        result.append(candidate)
    return result[:6]


def _is_similar_memory(new_text: str, old_text: str) -> bool:
    new_norm = _normalize_memory_text(new_text)
    old_norm = _normalize_memory_text(old_text)
    if not new_norm or not old_norm:
        return False
    return (
        new_norm == old_norm
        or new_norm in old_norm
        or old_norm in new_norm
    )


def _normalize_memory_text(text: str) -> str:
    return re.sub(r"[\s，,。.!！？?:：；;、\-+]+", "", text or "").lower()
