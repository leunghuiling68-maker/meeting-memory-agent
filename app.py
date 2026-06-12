"""Single-page Streamlit workspace for the Project Memory Agent MVP."""

from datetime import datetime
from html import escape
from pathlib import Path
import re

import streamlit as st

from deepseek_client import call_deepseek_json
from meeting_memory.action_items.service import (
    count_action_items_for_meeting,
    extract_action_items_placeholder,
    get_action_item,
    list_action_items,
    save_action_items,
    update_action_item_status,
)
from meeting_memory.db.connection import get_connection, init_db
from meeting_memory.db.seed import ensure_demo_project
from meeting_memory.meetings.service import create_meeting, list_meetings
from meeting_memory.memories.service import (
    build_memory_context,
    count_approved_memories_for_meeting,
    count_candidate_memories_for_meeting,
    generate_mock_candidate_memories,
    get_referenced_memories_for_meeting,
    get_recent_project_memories,
    infer_memory_category,
    list_candidate_memories,
    memory_like_exists,
    memory_category_from_type,
    memory_tag_class,
    meeting_used_memory,
    retrieve_project_memories,
    user_confirm_memory,
)
from meeting_memory.summaries.service import generate_summary_placeholder


DB_PATH = Path("data/meeting_memory.db")
VIEW_OPTIONS = ["工作台", "新建会议", "待确认记忆", "项目记忆", "待办中心", "会议详情", "Evaluation Dashboard", "设置"]
INTERNAL_VIEW_OPTIONS = VIEW_OPTIONS


def rerun_app() -> None:
    """Rerun across Streamlit versions."""
    if hasattr(st, "experimental_rerun"):
        st.experimental_rerun()
    else:
        st.rerun()


def navigate_to(view_name: str, **kwargs) -> None:
    """Queue a page change before active_view-backed content is rendered."""
    st.session_state.pending_active_view = view_name
    if kwargs:
        st.session_state.nav_payload = kwargs
    rerun_app()


def consume_pending_navigation() -> None:
    """Apply queued navigation during initialization, before active_view radio exists."""
    pending_view = st.session_state.pop("pending_active_view", None)
    if pending_view in INTERNAL_VIEW_OPTIONS:
        st.session_state["active_view"] = pending_view
    payload = st.session_state.pop("nav_payload", {})
    if payload:
        if "meeting_id" in payload:
            st.session_state["selected_meeting_id"] = payload["meeting_id"]
        if "selected_meeting_id" in payload:
            st.session_state["selected_meeting_id"] = payload["selected_meeting_id"]
        if "action_item_id" in payload:
            st.session_state["selected_action_item_id"] = payload["action_item_id"]


def handle_sidebar_navigation() -> None:
    """Convert the sidebar widget value into queued navigation."""
    selected_view = st.session_state.get("nav_choice", st.session_state.get("active_view", "工作台"))
    if selected_view != st.session_state.get("active_view"):
        st.session_state["active_view"] = selected_view


def bootstrap() -> None:
    """Create local SQLite database and demo project when needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection(DB_PATH) as conn:
        init_db(conn)
        ensure_demo_project(conn)


def ensure_ui_state(project_id: int) -> None:
    """Keep UI state stable while switching tabs and projects."""
    consume_pending_navigation()
    if "active_view" not in st.session_state:
        st.session_state.active_view = "工作台"
    if st.session_state.active_view not in INTERNAL_VIEW_OPTIONS:
        st.session_state.active_view = "工作台"
    if st.session_state.get("active_project_id") != project_id:
        st.session_state.active_project_id = project_id
        st.session_state.selected_action_item_id = None
        st.session_state.selected_meeting_id = None


def inject_styles() -> None:
    """Add a blue-white product workspace skin."""
    st.markdown(
        """
        <style>
        :root {
            --blue: #2f5bff;
            --blue-soft: #eef3ff;
            --ink: #172033;
            --muted: #6b7280;
            --line: #e5eaf3;
            --panel: #ffffff;
            --bg: #f5f7fb;
        }
        .stApp { background: var(--bg); }
        .block-container {
            padding: 30px 26px 34px;
            max-width: 1320px;
            overflow: visible;
        }
        [data-testid="stSidebar"] {
            background: #fbfcff;
            border-right: 1px solid var(--line);
        }
        [data-testid="stSidebar"] > div:first-child {
            padding-top: 28px;
        }
        h1, h2, h3 { letter-spacing: 0; color: var(--ink); }
        div[data-testid="stButton"] > button {
            border-radius: 8px;
            border: 1px solid #dbe3f2;
            box-shadow: none;
        }
        div[data-testid="stButton"] > button[kind="primary"] {
            background: linear-gradient(135deg, #4f6cff 0%, #2451ff 100%);
            border: 0;
        }
        .brand {
            display: flex;
            align-items: center;
            gap: 10px;
            font-weight: 760;
            color: #0f172a;
            margin: 0 0 24px;
        }
        .brand-mark {
            width: 30px;
            height: 30px;
            border-radius: 9px;
            background: linear-gradient(135deg, #6d7cff, #2f5bff);
            box-shadow: 0 8px 20px rgba(47, 91, 255, .22);
        }
        .sidebar-nav {
            margin-top: 18px;
            display: grid;
            gap: 7px;
        }
        .nav-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 10px 12px;
            border-radius: 8px;
            color: #43516b;
            text-decoration: none !important;
            font-size: .92rem;
        }
        .nav-item.active {
            background: #eef3ff;
            color: #2451ff;
            font-weight: 700;
        }
        .nav-item:hover { background: #f1f5ff; color: #2451ff; }
        .sidebar-card {
            border: 1px solid #dfe7f5;
            border-radius: 10px;
            padding: 14px;
            background: linear-gradient(180deg, #ffffff, #f7faff);
            margin-top: 18px;
        }
        .app-topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 18px;
            margin-bottom: 16px;
        }
        .project-name-line {
            display: flex;
            align-items: center;
            gap: 12px;
            min-height: 42px;
        }
        .project-icon {
            width: 30px;
            height: 30px;
            border-radius: 8px;
            background: linear-gradient(135deg, #7c8cff, #3d63ff);
            box-shadow: 0 8px 22px rgba(47, 91, 255, .22);
        }
        .project-title {
            font-size: 1.55rem;
            font-weight: 780;
            line-height: 1.25;
            color: var(--ink);
        }
        .search-box {
            min-width: 280px;
            border: 1px solid var(--line);
            background: #fff;
            border-radius: 10px;
            padding: 11px 14px;
            color: #8a94a6;
            box-shadow: 0 6px 18px rgba(15, 23, 42, .04);
        }
        .tabs {
            display: flex;
            gap: 30px;
            border-bottom: 1px solid var(--line);
            margin: 0 -26px 18px;
            padding: 0 26px;
            background: rgba(255,255,255,.54);
        }
        .tab {
            padding: 14px 0;
            color: #536179;
            font-weight: 650;
            border-bottom: 2px solid transparent;
        }
        .tab.active { color: #2451ff; border-bottom-color: #2451ff; }
        div[role="radiogroup"] {
            gap: 18px;
            border-bottom: 1px solid var(--line);
            margin: 0 -26px 18px;
            padding: 0 26px 8px;
            background: rgba(255,255,255,.54);
        }
        div[role="radiogroup"] label {
            padding: 8px 10px;
            border-radius: 8px;
        }
        .header-card {
            border: 1px solid var(--line);
            border-radius: 12px;
            background: var(--panel);
            box-shadow: 0 14px 36px rgba(31, 41, 55, .07);
            padding: 20px 22px;
            margin-bottom: 16px;
            overflow: visible;
        }
        .muted { color: var(--muted); font-size: .9rem; }
        .card {
            border: 1px solid var(--line);
            border-radius: 12px;
            background: var(--panel);
            box-shadow: 0 10px 26px rgba(31, 41, 55, .055);
            padding: 18px 20px;
            margin-bottom: 14px;
        }
        .main-card {
            border: 1px solid var(--line);
            border-radius: 12px;
            background: var(--panel);
            box-shadow: 0 16px 38px rgba(31, 41, 55, .075);
            padding: 22px;
            margin-bottom: 16px;
        }
        .right-card {
            border: 1px solid var(--line);
            border-radius: 12px;
            background: var(--panel);
            box-shadow: 0 10px 26px rgba(31, 41, 55, .055);
            padding: 17px 18px;
            margin-bottom: 14px;
        }
        .right-rail {
            position: sticky;
            top: 24px;
        }
        .work-surface {
            border: 1px solid var(--line);
            border-radius: 14px;
            background: rgba(255,255,255,.72);
            box-shadow: 0 18px 42px rgba(31, 41, 55, .07);
            padding: 16px;
            margin-bottom: 16px;
        }
        .scroll-panel {
            max-height: 430px;
            overflow-y: auto;
            padding-right: 4px;
        }
        .scroll-panel.small {
            max-height: 330px;
        }
        .scroll-panel::-webkit-scrollbar { width: 7px; }
        .scroll-panel::-webkit-scrollbar-thumb { background: #d9e2f3; border-radius: 999px; }
        .section-title {
            font-size: 1.05rem;
            font-weight: 760;
            color: var(--ink);
            margin: 6px 0 12px;
        }
        .stat-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin-top: 16px;
        }
        .stat-card {
            border: 1px solid #e2e8f8;
            border-radius: 10px;
            padding: 12px 14px;
            background: #f8faff;
        }
        .stat-label { color: var(--muted); font-size: .8rem; margin-bottom: 6px; }
        .stat-value { color: var(--ink); font-size: 1.45rem; font-weight: 780; }
        .stat-value.compact {
            font-size: .98rem;
            line-height: 1.32;
            min-height: 2.5rem;
        }
        .stat-note {
            color: var(--muted);
            font-size: .78rem;
            margin-top: 7px;
        }
        .agent-flow {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            align-items: center;
            margin: 10px 0 16px;
        }
        .flow-step {
            border: 1px solid #dbe3f2;
            border-radius: 999px;
            padding: 6px 10px;
            background: #ffffff;
            color: #344054;
            font-size: .84rem;
        }
        .flow-arrow {
            color: #94a3b8;
            font-size: .82rem;
        }
        .memory-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
        }
        .memory-card-title {
            font-weight: 720;
            color: var(--ink);
            margin-bottom: 8px;
        }
        .subtle-card {
            border: 1px solid #edf1f8;
            border-radius: 10px;
            background: #fbfcff;
            padding: 12px;
            margin-bottom: 10px;
        }
        .evidence-label {
            color: #475569;
            font-weight: 700;
            font-size: .84rem;
            margin-top: 8px;
        }
        .tag {
            display: inline-block;
            border-radius: 999px;
            padding: 2px 9px;
            font-size: .76rem;
            border: 1px solid #d5ddec;
            color: #41506a;
            background: #f8fafc;
            margin-right: 6px;
            margin-bottom: 5px;
            white-space: nowrap;
        }
        .tag-blue { background: #eef3ff; border-color: #cbd8ff; color: #2451ff; }
        .tag-green { background: #ecfdf5; border-color: #a7f3d0; color: #047857; }
        .tag-yellow { background: #fff7ed; border-color: #fed7aa; color: #b45309; }
        .tag-purple { background: #f5f3ff; border-color: #ddd6fe; color: #6d28d9; }
        .tag-red { background: #fff1f2; border-color: #fecdd3; color: #be123c; }
        .tag-orange { background: #fff7ed; border-color: #fed7aa; color: #c2410c; }
        .tag-slate { background: #f1f5f9; border-color: #cbd5e1; color: #475569; }
        .empty {
            border: 1px dashed #cfd9eb;
            border-radius: 10px;
            padding: 18px;
            background: #f9fbff;
            color: var(--muted);
            text-align: center;
            margin-bottom: 12px;
        }
        .meeting-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 18px;
            color: #667085;
            font-size: .9rem;
            margin: 10px 0 14px;
        }
        .divider {
            height: 1px;
            background: var(--line);
            margin: 15px 0;
        }
        .timeline {
            border-left: 2px solid #dfe7f5;
            padding-left: 14px;
            margin-left: 4px;
        }
        .timeline-scroll {
            overflow-x: auto;
            padding: 8px 2px 14px;
            margin: 8px 0 12px;
        }
        .timeline-track {
            display: flex;
            align-items: stretch;
            gap: 14px;
            min-width: max-content;
            position: relative;
        }
        .timeline-card {
            width: 190px;
            border: 1px solid #dfe7f5;
            border-radius: 8px;
            background: #fff;
            padding: 12px;
            box-shadow: 0 8px 22px rgba(15, 23, 42, .04);
            position: relative;
        }
        .timeline-card::before {
            content: "";
            position: absolute;
            left: -15px;
            right: -15px;
            top: 43px;
            height: 2px;
            background: #dbe5ff;
            z-index: 0;
        }
        .timeline-card:first-child::before { left: 50%; }
        .timeline-card:last-child::before { right: 50%; }
        .timeline-dot {
            width: 13px;
            height: 13px;
            border-radius: 999px;
            border: 3px solid #2f5bff;
            background: #fff;
            margin: 4px 0 10px;
            position: relative;
            z-index: 1;
        }
        .timeline-card.active {
            border-color: #2f5bff;
            background: linear-gradient(180deg, #f8fbff, #ffffff);
            box-shadow: 0 10px 26px rgba(47, 91, 255, .12);
        }
        .timeline-card.active .timeline-dot {
            background: #2f5bff;
            box-shadow: 0 0 0 5px #e6edff;
        }
        .timeline-title {
            color: #18233b;
            font-weight: 760;
            font-size: .92rem;
            line-height: 1.3;
            min-height: 38px;
        }
        .timeline-card.active .timeline-title { color: #2451ff; }
        .timeline-date {
            color: #64748b;
            font-size: .8rem;
            margin-bottom: 9px;
        }
        .timeline-stats {
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
        }
        .timeline-stat {
            border-radius: 999px;
            background: #f1f5ff;
            color: #3152c9;
            padding: 3px 8px;
            font-size: .72rem;
            white-space: nowrap;
        }
        .compact-p { margin: .45rem 0 0; }
        .clamp {
            display: -webkit-box;
            -webkit-line-clamp: 3;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }
        @media (max-width: 900px) {
            .stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .memory-grid { grid-template-columns: 1fr; }
            .app-topbar { display: block; }
            .search-box { margin-top: 12px; min-width: 0; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def create_project(name: str, description: str = "") -> int:
    """Create a new project topic."""
    with get_connection(DB_PATH) as conn:
        cursor = conn.execute(
            """
            INSERT INTO projects (name, description)
            VALUES (?, ?)
            """,
            (name.strip(), description.strip()),
        )
        conn.commit()
        return int(cursor.lastrowid)


def load_projects() -> list:
    """Read projects for the sidebar selector."""
    with get_connection(DB_PATH) as conn:
        return conn.execute(
            """
            SELECT id, name, description, created_at, updated_at
            FROM projects
            ORDER BY updated_at DESC, id DESC
            """
        ).fetchall()


def get_project(project_id: int):
    """Load one project."""
    with get_connection(DB_PATH) as conn:
        return conn.execute(
            """
            SELECT id, name, description, created_at, updated_at
            FROM projects
            WHERE id = ?
            """,
            (project_id,),
        ).fetchone()


def get_project_overview(project_id: int) -> dict:
    """Collect counters for the workspace header."""
    with get_connection(DB_PATH) as conn:
        return {
            "meeting_total": conn.execute(
                "SELECT COUNT(*) FROM meetings WHERE project_id = ?",
                (project_id,),
            ).fetchone()[0],
            "memory_total": conn.execute(
                "SELECT COUNT(*) FROM memories WHERE project_id = ?",
                (project_id,),
            ).fetchone()[0],
            "pending_total": conn.execute(
                """
                SELECT COUNT(*)
                FROM candidate_memories
                WHERE project_id = ? AND status = 'pending'
                """,
                (project_id,),
            ).fetchone()[0],
            "open_actions": conn.execute(
                """
                SELECT COUNT(*)
                FROM action_items
                WHERE project_id = ? AND status = 'open'
                """,
                (project_id,),
            ).fetchone()[0],
        }


def get_selected_or_latest_meeting(project_id: int):
    selected_meeting_id = st.session_state.get("selected_meeting_id")
    with get_connection(DB_PATH) as conn:
        if selected_meeting_id:
            row = conn.execute(
                """
                SELECT
                    id,
                    title,
                    COALESCE(meeting_date, created_at) AS meeting_time,
                    created_at,
                    summary,
                    content
                FROM meetings
                WHERE project_id = ?
                  AND id = ?
                """,
                (project_id, int(selected_meeting_id)),
            ).fetchone()
            if row:
                return row
        return conn.execute(
            """
            SELECT
                id,
                title,
                COALESCE(meeting_date, created_at) AS meeting_time,
                created_at,
                summary,
                content
            FROM meetings
            WHERE project_id = ?
            ORDER BY COALESCE(meeting_date, created_at) DESC, id DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()


def render_sidebar() -> int:
    """Render the fixed-feeling workspace sidebar."""
    st.sidebar.markdown("### 会议纪要 Agent")
    st.sidebar.caption("AI Meeting Memory Agent")

    projects = load_projects()
    if not projects:
        create_project("演示项目", "默认演示项目")
        projects = load_projects()

    options = {f"{row['name']} · #{row['id']}": row["id"] for row in projects}
    selected = st.sidebar.selectbox("当前 Project", list(options.keys()))
    project_id = int(options[selected])
    project = get_project(project_id)
    ensure_ui_state(project_id)

    if st.sidebar.button("+ 新建会议", type="primary", use_container_width=True):
        navigate_to("新建会议")

    with st.sidebar.expander("+ 新建 Project", expanded=True):
        name = st.text_input("Project 名称")
        description = st.text_area("Project 描述", height=80)
        if st.button("创建 Project"):
            if name.strip():
                create_project(name, description)
                st.success("Project 已创建")
                st.rerun()

    st.session_state["nav_choice"] = st.session_state.get("active_view", "工作台")
    st.sidebar.radio(
        "功能区",
        VIEW_OPTIONS,
        key="nav_choice",
        label_visibility="collapsed",
        on_change=handle_sidebar_navigation,
    )

    st.sidebar.divider()
    st.sidebar.caption("当前 Project")
    st.sidebar.markdown(f"**{project['name']}**")
    st.sidebar.caption(project["description"] or "暂无项目描述")
    st.sidebar.caption(f"project_id {project_id}")
    return project_id


def render_empty_state(title: str, body: str) -> None:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        st.caption(body)


def mock_memory_weight(text: str) -> float:
    """Deterministic display-only memory weight."""
    base = 0.62
    if text.startswith(("决策", "约束")):
        base += 0.18
    if text.startswith(("风险", "待办")):
        base += 0.12
    return min(base + min(len(text), 80) / 1000, 0.95)


def mock_memory_confidence(text: str) -> float:
    """Deterministic display-only confidence score."""
    if any(keyword in text for keyword in ("决定", "暂不", "下次", "需要", "风险")):
        return 0.88
    return 0.76


def short_text(text: str | None, limit: int = 34) -> str:
    """Keep metric cards readable without losing the signal."""
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean or "暂无"
    return clean[: limit - 1] + "…"


def memory_display_category(memory_type: str | None, memory_text: str) -> str:
    category = memory_category_from_type(memory_type, memory_text)
    return "后续关注" if category == "待办" else category


def memory_agent_reason(category: str, text: str) -> str:
    reasons = {
        "决策": "这会影响后续会议的方案选择与取舍。",
        "约束": "这是后续讨论必须遵守的项目边界。",
        "风险": "这是后续会议需要持续复查的风险信号。",
        "需求": "这是后续会议可能继续推进的产品变化。",
        "事实": "这是项目历史中的稳定背景信息。",
        "后续关注": "这是后续会议需要主动带回来的未解决事项。",
    }
    return reasons.get(category, "这条信息有复用价值，适合沉淀为项目记忆。")


def summary_influence(summary: str | None, memory_text: str) -> str:
    clean_summary = " ".join((summary or "").split())
    if not clean_summary:
        return "影响：本次会议暂无摘要，后续生成摘要时可作为上下文。"
    first_part = clean_summary.split("。", 1)[0].strip()
    if first_part:
        return f"影响摘要：{short_text(first_part, 58)}"
    return f"影响建议：围绕 {short_text(memory_text, 24)} 保持项目连续性。"


def get_recent_referenced_meeting(project_id: int):
    with get_connection(DB_PATH) as conn:
        return conn.execute(
            """
            SELECT title, COALESCE(meeting_date, created_at) AS meeting_time
            FROM meetings
            WHERE project_id = ?
              AND summary LIKE '%已参考当前项目记忆%'
            ORDER BY COALESCE(meeting_date, created_at) DESC, id DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()


def get_top_referenced_memory(project_id: int):
    with get_connection(DB_PATH) as conn:
        memories = retrieve_project_memories(conn, project_id, limit=80)
    if not memories:
        return None, 0
    ranked = [
        (memory, count_memory_references(project_id, memory["created_at"]))
        for memory in memories
    ]
    return max(ranked, key=lambda item: item[1])


def get_candidate_source_excerpt(project_id: int, candidate) -> str:
    source_meeting_id = candidate["source_meeting_id"] if "source_meeting_id" in candidate.keys() else candidate["meeting_id"]
    if not source_meeting_id:
        return candidate["content"]
    with get_connection(DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT content
            FROM meetings
            WHERE project_id = ?
              AND id = ?
            """,
            (project_id, source_meeting_id),
        ).fetchone()
    return row["content"] if row and row["content"] else candidate["content"]


def count_memory_references(project_id: int, created_at: str) -> int:
    """Mock reference count based on later meetings that used project memory."""
    with get_connection(DB_PATH) as conn:
        return int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM meetings
                WHERE project_id = ?
                  AND created_at >= ?
                  AND summary LIKE '%已参考当前项目记忆%'
                """,
                (project_id, created_at),
            ).fetchone()[0]
        )


def count_memory_references_for_memory(project_id: int, memory) -> int:
    base_count = count_memory_references(project_id, memory["created_at"])
    session_counts = st.session_state.get("memory_reference_counts", {}).get(int(project_id), {})
    return base_count + int(session_counts.get(int(memory["id"]), 0))


def render_topbar(project_id: int) -> None:
    return None


def render_project_header(
    project_id: int,
    title: str = "工作台",
    subtitle: str = "项目记忆总览，了解项目知识沉淀与 Agent 工作状态",
    show_metrics: bool = True,
) -> None:
    overview = get_project_overview(project_id)
    st.markdown(f"# {title}")
    st.caption(subtitle)
    if not show_metrics:
        return
    metric_cols = st.columns(4)
    metric_cols[0].metric("已确认记忆", overview["memory_total"], "条长期记忆")
    metric_cols[1].metric("待确认记忆", overview["pending_total"], "条候选记忆")
    metric_cols[2].metric("总会议数", overview["meeting_total"], "次会议记录")
    metric_cols[3].metric("附属待办数", overview["open_actions"], "条待办事项")


def get_latest_meeting_entry(project_id: int):
    with get_connection(DB_PATH) as conn:
        return conn.execute(
            """
            SELECT
                id,
                title,
                COALESCE(meeting_date, created_at) AS meeting_time
            FROM meetings
            WHERE project_id = ?
            ORDER BY COALESCE(meeting_date, created_at) DESC, id DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()


def render_workbench_entries(project_id: int) -> None:
    overview = get_project_overview(project_id)
    latest_meeting = get_latest_meeting_entry(project_id)
    left, right = st.columns(2, gap="large")

    with left.container(border=True):
        st.markdown("#### 最近会议入口")
        if latest_meeting is None:
            st.caption("暂无会议")
            if st.button("新建会议", key=f"entry_new_meeting_{project_id}"):
                navigate_to("新建会议")
        else:
            st.markdown(f"**{latest_meeting['title']}**")
            st.caption(latest_meeting["meeting_time"])
            if st.button("查看会议", key=f"entry_latest_meeting_{project_id}"):
                navigate_to("会议详情", meeting_id=latest_meeting["id"])

    with right.container(border=True):
        st.markdown("#### 待处理入口")
        st.caption(f"待确认候选记忆：{overview['pending_total']} 条")
        st.caption(f"会议附属待办：{overview['open_actions']} 条")
        pending_col, action_col = st.columns(2)
        with pending_col:
            if st.button("处理记忆", key=f"entry_pending_{project_id}"):
                navigate_to("待确认记忆")
        with action_col:
            if st.button("查看待办", key=f"entry_actions_{project_id}"):
                navigate_to("待办中心")


def render_workbench_recent_context(project_id: int) -> None:
    meeting = get_selected_or_latest_meeting(project_id)
    if meeting is None:
        render_empty_state("暂无最近会议", "新建会议后，工作台会展示最近会议摘要和引用记忆。")
        return

    with get_connection(DB_PATH) as conn:
        referenced = get_referenced_memories_for_meeting(conn, project_id, meeting["id"], limit=5)
        approved_count = count_approved_memories_for_meeting(conn, project_id, meeting["id"])
        action_count = count_action_items_for_meeting(conn, project_id, meeting["id"])

    left, right = st.columns(2, gap="large")
    with left.container(border=True):
        st.markdown("### 最近会议摘要")
        st.caption("AI 生成")
        st.markdown(f"**{meeting['title']}**")
        st.caption(meeting["meeting_time"])
        st.write(short_text(meeting["summary"], 180))
        metric_cols = st.columns(3)
        metric_cols[0].metric("引用历史记忆", len(referenced), "条")
        metric_cols[1].metric("新增长期记忆", approved_count, "条")
        metric_cols[2].metric("附属待办", action_count, "条")

    with right.container(border=True):
        st.markdown("### 本次会议引用的历史记忆")
        st.caption(f"查看全部（{len(referenced)}）")
        if not referenced:
            st.caption("暂无引用历史记忆")
        for memory in referenced[:3]:
            category = infer_memory_category(memory["memory_text"])
            source = memory["source_meeting_title"] or "未知历史会议"
            st.markdown(f"**{short_text(memory['memory_text'], 36)}**")
            st.caption(f"来源：{source} · {category}")
            st.divider()
        st.caption(f"共引用 {len(referenced)} 条历史记忆")


def render_workbench_recent_summary(project_id: int) -> None:
    meeting = get_selected_or_latest_meeting(project_id)
    with st.container(border=True):
        st.markdown("### 最近会议摘要")
        if meeting is None:
            st.caption("暂无会议摘要，新建会议后会在这里展示。")
            return
        st.markdown(f"**{meeting['title']}**")
        st.caption(meeting["meeting_time"])
        st.write(meeting["summary"] or "暂无摘要")


def render_workbench_memory_references(project_id: int) -> None:
    meeting = get_selected_or_latest_meeting(project_id)
    with st.container(border=True):
        st.markdown("### 本次 / 最近会议引用的历史记忆")
        if meeting is None:
            st.caption("暂无引用记录，后续会议引用历史记忆后会在这里展示。")
            return
        referenced = get_meeting_citation_data(project_id, meeting)["cited_memories"][:5]
        if not referenced:
            st.caption("暂无引用记录，后续会议引用历史记忆后会在这里展示。")
            return
        for memory in referenced:
            reference_count = count_memory_references_for_memory(project_id, memory)
            source = memory["source_meeting_title"] or "未知历史会议"
            memory_type = memory_category_from_type(memory["memory_type"], memory["memory_text"])
            st.markdown("**引用记忆**")
            st.write(memory["memory_text"])
            st.caption(f"来源：{source}")
            st.caption(f"类型：{memory_type}")
            st.caption(f"历史引用次数：{reference_count}")
            st.divider()


def render_quick_entries(project_id: int) -> None:
    overview = get_project_overview(project_id)
    st.markdown("### 快捷入口")
    cols = st.columns(3)
    entries = [
        ("新建会议", "开始记录新会议", "新建会议"),
        ("待确认记忆", f"审核候选记忆 {overview['pending_total']} 条", "待确认记忆"),
        ("项目长期记忆", "查看长期记忆", "项目记忆"),
    ]
    for col, (title, caption, target) in zip(cols, entries):
        with col.container(border=True):
            st.markdown(f"**{title}**")
            st.caption(caption)
            if st.button("进入", key=f"quick_{target}_{project_id}"):
                navigate_to(target)


def render_agent_metrics(project_id: int) -> None:
    log = st.session_state.get(f"latest_agent_run_log_{project_id}")
    if log is None:
        meeting = get_selected_or_latest_meeting(project_id)
        if meeting is not None:
            citation_data = get_meeting_citation_data(project_id, meeting)
            log = {
                "retrieved_memory_count": len(citation_data["injected_memories"]),
                "injected_memory_count": len(citation_data["injected_memories"]),
                "candidate_memory_count": 0,
                "citation_count": len(citation_data["referenced_memory_ids"]),
                "reference_count_updated": False,
                "conflict_checked_count": 0,
                "conflict_found_count": 0,
            }
    if log is None:
        return
    st.markdown("### Agent Metrics")
    cols = st.columns(7)
    cols[0].metric("Memory Retrieved", log["retrieved_memory_count"])
    cols[1].metric("Memory Injected", log["injected_memory_count"])
    cols[2].metric("Candidate Generated", log["candidate_memory_count"])
    cols[3].metric("Citation Triggered", log["citation_count"])
    cols[4].metric("Reference Updates", "Yes" if log["reference_count_updated"] else "No")
    cols[5].metric("Conflict Checked", log.get("conflict_checked_count", 0))
    cols[6].metric("Potential Conflict Found", log.get("conflict_found_count", 0))


def render_agent_activity_flow(
    project_id: int,
    candidate_count: int | None = None,
    action_count: int | None = None,
) -> None:
    with get_connection(DB_PATH) as conn:
        memory_count = len(get_recent_project_memories(conn, project_id, limit=5))
        if candidate_count is None:
            candidate_count = conn.execute(
                """
                SELECT COUNT(*)
                FROM candidate_memories
                WHERE project_id = ? AND status = 'pending'
                """,
                (project_id,),
            ).fetchone()[0]
        if action_count is None:
            action_count = conn.execute(
                """
                SELECT COUNT(*)
                FROM action_items
                WHERE project_id = ? AND status = 'open'
                """,
                (project_id,),
            ).fetchone()[0]
    steps = [
        f"读取 {memory_count} 条项目记忆",
        "生成会议摘要",
        f"提取 {candidate_count} 条候选记忆",
        f"提取 {action_count} 条待办",
        "等待人工确认",
        "后续会议可引用",
    ]
    with st.container(border=True):
        st.markdown("#### Agent 活动流")
        st.caption("这条链路展示 AI 如何把会议内容转成可复用的项目记忆。")
        st.markdown(" → ".join(steps))


def _retrieval_keywords(text: str) -> set[str]:
    return {
        item.lower()
        for item in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", text or "")
        if len(item.strip()) >= 2
    }


def _memory_recency_points(created_at: str | None) -> tuple[int, str]:
    if not created_at:
        return 0, "创建时间未知"
    try:
        created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    except ValueError:
        try:
            created = datetime.strptime(str(created_at), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return 0, "创建时间未知"
    age_days = max((datetime.now() - created.replace(tzinfo=None)).days, 0)
    if age_days <= 30:
        return 2, "最近30天创建"
    if age_days <= 90:
        return 1, "最近90天创建"
    return 0, "超过90天创建"


def get_top_k_memory_retrieval(conn, project_id: int, query_text: str, limit: int = 5) -> list[dict]:
    query_keywords = _retrieval_keywords(query_text)
    type_weights = {
        "decision": 4,
        "constraint": 4,
        "risk": 4,
        "requirement": 3,
        "fact": 2,
        "follow_up": 1,
        "action": 1,
    }
    memories = retrieve_project_memories(conn, project_id, limit=80)
    scored: list[dict] = []
    for memory in memories:
        memory_text = memory["memory_text"] or ""
        matched_keywords = sorted(_retrieval_keywords(memory_text) & query_keywords)
        keyword_score = 5 if matched_keywords else 0
        memory_type = memory["memory_type"] or "fact"
        type_score = type_weights.get(memory_type, 2)
        reference_count = count_memory_references_for_memory(project_id, memory)
        recency_score, recency_reason = _memory_recency_points(memory["created_at"])
        score = keyword_score + type_score + reference_count + recency_score
        reasons = []
        if matched_keywords:
            reasons.append(f"命中关键词：{'、'.join(matched_keywords[:5])}")
        reasons.append(f"类型权重：{memory_type} +{type_score}")
        reasons.append(f"历史引用次数：{reference_count}")
        reasons.append(recency_reason)
        scored.append(
            {
                "memory_id": int(memory["id"]),
                "type": memory_type,
                "content": memory_text,
                "created_at": memory["created_at"],
                "score": score,
                "matched_keywords": matched_keywords,
                "reference_count": reference_count,
                "recency_reason": recency_reason,
                "reasons": reasons,
                "row": memory,
            }
        )
    scored.sort(key=lambda item: (item["score"], item["created_at"], item["memory_id"]), reverse=True)
    return scored[:limit]


def build_top_k_memory_context(conn, project_id: int, meeting_content: str, limit: int = 5) -> tuple[str, list[dict]]:
    retrieved = get_top_k_memory_retrieval(conn, project_id, meeting_content, limit=limit)
    lines = ["[Project Memories]"]
    if retrieved:
        lines.extend(
            f"- [MEMORY_{item['memory_id']}] {item['content']}"
            for item in retrieved
        )
    else:
        lines.append("- 暂无已确认项目记忆")

    recent_meetings = conn.execute(
        """
        SELECT title, COALESCE(meeting_date, created_at) AS meeting_time, summary
        FROM meetings
        WHERE project_id = ?
        ORDER BY COALESCE(meeting_date, created_at) DESC, id DESC
        LIMIT 3
        """,
        (project_id,),
    ).fetchall()
    lines.append("")
    lines.append("[Recent Meetings]")
    if recent_meetings:
        lines.extend(
            f"- {row['title']} ({row['meeting_time']}): {row['summary'] or '暂无摘要'}"
            for row in recent_meetings
        )
    else:
        lines.append("- 暂无历史会议")

    open_actions = conn.execute(
        """
        SELECT task, owner, deadline
        FROM action_items
        WHERE project_id = ?
          AND status = 'open'
        ORDER BY updated_at DESC, id DESC
        LIMIT 5
        """,
        (project_id,),
    ).fetchall()
    lines.append("")
    lines.append("[Open Action Items]")
    if open_actions:
        lines.extend(
            f"- {row['task']} | owner={row['owner'] or '未指定'} | deadline={row['deadline'] or '未指定'}"
            for row in open_actions
        )
    else:
        lines.append("- 暂无未完成待办")
    return "\n".join(lines), retrieved


def _contains_conflict_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    normalized = re.sub(r"\s+", "", text or "").lower()
    return any(re.sub(r"\s+", "", phrase).lower() in normalized for phrase in phrases)


def _conflict_current_snippet(text: str, phrases: tuple[str, ...]) -> str:
    sentences = [
        item.strip()
        for item in re.split(r"[。！？!?；;\n]+", text or "")
        if item.strip()
    ]
    for sentence in sentences:
        if _contains_conflict_phrase(sentence, phrases):
            return sentence[:160]
    return short_text(text, 160)


def detect_memory_conflicts(conn, project_id: int, meeting_content: str) -> dict:
    high_history = ("必须人工", "人工审核", "人工确认", "人工复核", "人工介入", "不得由AI直接", "不得自动", "高风险不得由AI直接")
    high_current = ("无需人工", "取消人工", "取消人工审核", "不再需要人工", "AI自动通过", "自动通过", "直接发送给客户", "AI直接决策", "自动决策")
    medium_history = ("必须人工", "人工审核", "人工复核", "不得由AI直接")
    medium_current = ("自动处理", "自动回复", "自动执行", "自动流转")
    protective_terms = ("人工复核", "人工审核", "人工确认", "不得由AI直接", "高风险", "风险", "约束", "复核", "追溯")
    explicit_conflict_terms = ("取消人工", "无需人工", "自动通过", "直接发送", "AI直接决策")
    protective_negations = ("不得由AI直接", "高风险不得由AI直接")
    other_rules = [
        {
            "history": ("暂不接入", "暂不使用", "当前阶段不接入", "第一阶段不做"),
            "current": ("决定接入", "开始接入", "立即接入", "改为使用", "上线"),
            "confidence": "medium",
            "reason": "历史记忆要求暂不接入，但当前会议提出接入或上线。",
        },
        {
            "history": ("保留", "必须", "需要", "要求"),
            "current": ("取消", "移除", "不再需要", "废弃", "替换"),
            "confidence": "medium",
            "reason": "历史记忆要求保留或执行某项机制，但当前会议提出取消、替换或废弃。",
        },
    ]
    rows = conn.execute(
        """
        SELECT id, memory_text, memory_type
        FROM memories
        WHERE project_id = ?
          AND memory_type IN ('decision', 'constraint', 'risk', 'requirement')
        ORDER BY created_at DESC, id DESC
        """,
        (project_id,),
    ).fetchall()
    conflicts: list[dict] = []
    all_items: list[dict] = []
    for row in rows:
        memory_text = row["memory_text"] or ""
        item = None
        has_protective_negation = _contains_conflict_phrase(meeting_content, protective_negations)
        has_explicit_conflict = (
            _contains_conflict_phrase(meeting_content, explicit_conflict_terms)
            and not has_protective_negation
        )
        if (
            _contains_conflict_phrase(memory_text, protective_terms)
            and _contains_conflict_phrase(meeting_content, protective_terms)
            and not has_explicit_conflict
        ):
            item = {
                "confidence": "low",
                "is_conflict": False,
                "current_terms": protective_terms,
                "reason": "当前会议与历史记忆方向一致，属于保护性约束延续。",
            }
        elif _contains_conflict_phrase(memory_text, high_history) and _contains_conflict_phrase(meeting_content, high_current):
            item = {
                "confidence": "high",
                "is_conflict": True,
                "current_terms": high_current,
                "reason": "历史要求人工约束，但当前会议提出取消人工或自动执行。",
            }
        elif _contains_conflict_phrase(memory_text, medium_history) and _contains_conflict_phrase(meeting_content, medium_current):
            item = {
                "confidence": "medium",
                "is_conflict": True,
                "current_terms": medium_current,
                "reason": "当前会议出现自动化动作，可能需要确认是否违反人工复核约束。",
            }
        else:
            for rule in other_rules:
                if _contains_conflict_phrase(memory_text, rule["history"]) and _contains_conflict_phrase(meeting_content, rule["current"]):
                    item = {
                        "confidence": rule["confidence"],
                        "is_conflict": True,
                        "current_terms": rule["current"],
                        "reason": rule["reason"],
                    }
                    break
        if item is None:
            continue
        conflict_item = {
            "memory_id": int(row["id"]),
            "memory_type": row["memory_type"] or "fact",
            "memory_text": memory_text,
            "current_text": _conflict_current_snippet(meeting_content, item["current_terms"]),
            "reason": item["reason"],
            "suggestion": "请人工确认是否保留历史约束，或将本次会议内容作为新决策更新长期记忆。",
            "confidence": item["confidence"],
            "is_conflict": item["is_conflict"],
        }
        all_items.append(conflict_item)
        if conflict_item["is_conflict"]:
            conflicts.append(conflict_item)
    return {
        "checked_count": len(rows),
        "conflict_count": len(conflicts),
        "conflict_items": conflicts,
        "all_items": all_items,
    }


def load_retrieval_preview(project_id: int) -> tuple[list[dict], str]:
    meeting_content = st.session_state.get(f"content_{project_id}", "")
    with get_connection(DB_PATH) as conn:
        memory_context, memories = build_top_k_memory_context(conn, project_id, meeting_content)
    return memories, memory_context


def _get_injected_memory_rows(conn, project_id: int, meeting_content: str = "") -> list[dict]:
    return [
        {
            "memory_id": item["memory_id"],
            "type": item["type"],
            "content": item["content"],
            "score": item["score"],
            "reasons": item["reasons"],
        }
        for item in get_top_k_memory_retrieval(conn, project_id, meeting_content, limit=5)
    ]


def _record_injected_memories(meeting_id: int, injected_memories: list[dict]) -> None:
    injected_by_meeting = st.session_state.setdefault("injected_memories", {})
    injected_by_meeting[int(meeting_id)] = injected_memories


def _get_recorded_injected_memories(meeting_id: int) -> list[dict]:
    return st.session_state.get("injected_memories", {}).get(int(meeting_id), [])


def _record_referenced_memory_ids(meeting_id: int, referenced_memory_ids: list[int]) -> None:
    referenced_by_meeting = st.session_state.setdefault("referenced_memory_ids", {})
    referenced_by_meeting[int(meeting_id)] = referenced_memory_ids


def _get_recorded_referenced_memory_ids(meeting_id: int) -> list[int]:
    return st.session_state.get("referenced_memory_ids", {}).get(int(meeting_id), [])


def _record_agent_run_log(
    project_id: int,
    meeting_id: int,
    *,
    retrieved_memories: list[dict],
    injected_memories: list[dict],
    candidate_memory_count: int,
    action_item_count: int,
    referenced_memory_ids: list[int],
    reference_count_updated: bool,
    llm_mode: str,
    conflict_result: dict | None = None,
) -> None:
    conflict_result = conflict_result or {"checked_count": 0, "conflict_count": 0, "conflict_items": []}
    log = {
        "project_id": int(project_id),
        "meeting_id": int(meeting_id),
        "retrieved_memory_count": len(retrieved_memories),
        "retrieved_memory_ids": [int(item["memory_id"]) for item in retrieved_memories],
        "injected_memory_count": len(injected_memories),
        "injected_memory_ids": [int(item["memory_id"]) for item in injected_memories],
        "candidate_memory_count": int(candidate_memory_count),
        "action_item_count": int(action_item_count),
        "citation_count": len(referenced_memory_ids),
        "referenced_memory_ids": [int(memory_id) for memory_id in referenced_memory_ids],
        "reference_count_updated": bool(reference_count_updated),
        "llm_mode": llm_mode,
        "conflict_checked_count": int(conflict_result["checked_count"]),
        "conflict_found_count": int(conflict_result["conflict_count"]),
        "conflict_items": conflict_result["conflict_items"],
    }
    st.session_state.setdefault("agent_run_logs", {})[int(meeting_id)] = log
    st.session_state[f"latest_agent_run_log_{project_id}"] = log


def _get_agent_run_log(meeting_id: int) -> dict | None:
    return st.session_state.get("agent_run_logs", {}).get(int(meeting_id))


def get_meeting_citation_data(project_id: int, meeting) -> dict:
    meeting_id = int(meeting["id"])
    referenced_ids = extract_referenced_memory_ids(meeting["summary"] or "")
    if not referenced_ids:
        referenced_ids = _get_recorded_referenced_memory_ids(meeting_id)

    with get_connection(DB_PATH) as conn:
        injected_memories = _get_recorded_injected_memories(meeting_id)
        if not injected_memories:
            injected_memories = [
                {
                    "memory_id": row["id"],
                    "type": row["memory_type"] or "fact",
                    "content": row["memory_text"],
                }
                for row in conn.execute(
                    """
                    SELECT id, memory_text, memory_type
                    FROM memories
                    WHERE project_id = ?
                      AND created_at <= ?
                      AND (source_meeting_id IS NULL OR source_meeting_id != ?)
                    ORDER BY created_at DESC, id DESC
                    LIMIT 5
                    """,
                    (project_id, meeting["created_at"], meeting_id),
                ).fetchall()
            ]

        cited_memories = []
        for memory_id in referenced_ids:
            row = conn.execute(
                """
                SELECT
                    memories.id,
                    memories.memory_text,
                    memories.memory_type,
                    memories.created_at,
                    meetings.title AS source_meeting_title
                FROM memories
                LEFT JOIN meetings ON memories.source_meeting_id = meetings.id
                WHERE memories.project_id = ?
                  AND memories.id = ?
                """,
                (project_id, memory_id),
            ).fetchone()
            if row is not None:
                cited_memories.append(row)

    valid_referenced_ids = [int(memory["id"]) for memory in cited_memories]
    if valid_referenced_ids != _get_recorded_referenced_memory_ids(meeting_id):
        _record_referenced_memory_ids(meeting_id, valid_referenced_ids)
    if injected_memories and not _get_recorded_injected_memories(meeting_id):
        _record_injected_memories(meeting_id, injected_memories)

    return {
        "injected_memories": injected_memories,
        "referenced_memory_ids": valid_referenced_ids,
        "cited_memories": cited_memories,
    }


def extract_referenced_memory_ids(text: str) -> list[int]:
    referenced_ids: list[int] = []
    for match in re.finditer(r"\[MEMORY_(\d+)\]", text or ""):
        memory_id = int(match.group(1))
        if memory_id not in referenced_ids:
            referenced_ids.append(memory_id)
    return referenced_ids


def increment_memory_reference_counts(memory_ids: list[int], project_id: int, meeting_id: int | None = None) -> None:
    if meeting_id is not None:
        updated_meetings = st.session_state.setdefault("reference_count_updated_meetings", set())
        if int(meeting_id) in updated_meetings:
            return

    valid_ids: list[int] = []
    with get_connection(DB_PATH) as conn:
        for memory_id in memory_ids:
            row = conn.execute(
                """
                SELECT id
                FROM memories
                WHERE id = ?
                  AND project_id = ?
                """,
                (memory_id, project_id),
            ).fetchone()
            if row is not None:
                valid_ids.append(int(memory_id))

    if not valid_ids:
        if meeting_id is not None:
            st.session_state["reference_count_updated_meetings"].add(int(meeting_id))
        return

    counts_by_project = st.session_state.setdefault("memory_reference_counts", {})
    project_counts = counts_by_project.setdefault(int(project_id), {})
    for memory_id in valid_ids:
        project_counts[int(memory_id)] = int(project_counts.get(int(memory_id), 0)) + 1

    if meeting_id is not None:
        st.session_state["reference_count_updated_meetings"].add(int(meeting_id))


def _record_memory_impact_proof(
    meeting_id: int,
    without_memory_summary: str,
    with_memory_summary: str,
    referenced_memory_ids: list[int],
) -> None:
    without_words = set(re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", without_memory_summary or ""))
    with_words = set(re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", with_memory_summary or ""))
    proof_by_meeting = st.session_state.setdefault("memory_impact_proofs", {})
    proof_by_meeting[int(meeting_id)] = {
        "without_memory_summary": without_memory_summary,
        "with_memory_summary": with_memory_summary,
        "referenced_memory_count": len(referenced_memory_ids),
        "new_keyword_count": len(with_words - without_words),
        "has_memory_citation": bool(re.search(r"\[MEMORY_\d+\]", with_memory_summary or "")),
    }


def _get_recorded_memory_impact_proof(meeting_id: int) -> dict | None:
    return st.session_state.get("memory_impact_proofs", {}).get(int(meeting_id))


def _ensure_memory_impact_proof(project_id: int, meeting) -> None:
    if _get_recorded_memory_impact_proof(meeting["id"]):
        return
    content = meeting["content"] or ""
    with_memory_summary = meeting["summary"] or generate_summary_placeholder(content, "")
    without_memory_result = call_deepseek_json(
        _build_deepseek_meeting_messages(meeting["title"], content, "", []),
        mock_fallback=None,
        temperature=0.2,
    )
    without_memory_normalized = _normalize_deepseek_meeting_result(without_memory_result, meeting["title"])
    without_memory_summary = (
        without_memory_normalized["summary"]
        if without_memory_normalized is not None
        else generate_summary_placeholder(content, "")
    )
    referenced_memory_ids = _get_recorded_referenced_memory_ids(meeting["id"])
    if not referenced_memory_ids:
        referenced_memory_ids = extract_referenced_memory_ids(with_memory_summary)
    _record_memory_impact_proof(
        meeting["id"],
        without_memory_summary,
        with_memory_summary,
        referenced_memory_ids,
    )


LOW_VALUE_MEMORY_PHRASES = (
    "暂无历史记忆",
    "暂无可参考历史记忆",
    "暂无可参考历史项目记忆",
    "无可参考历史记忆",
    "没有可参考历史记忆",
    "当前会议暂无",
    "暂无内容",
    "无内容",
    "待补充",
    "示例会议",
    "测试会议",
    "DeepSeek 接入测试会议",
    "验证 DeepSeek 接入链路",
    "DS_PROBE",
    "本次会议暂无可参考",
    "可作为项目初始记忆候选",
)


def is_low_value_memory(memory: dict | str) -> bool:
    """低价值记忆过滤：避免无信息量内容污染长期记忆库。"""
    if isinstance(memory, dict):
        content = str(memory.get("content") or memory.get("memory_text") or "").strip()
    else:
        content = str(memory or "").strip()
    if not content:
        return True
    compact_content = re.sub(r"\s+", "", content)
    if len(compact_content) < 8:
        return True
    return any(phrase in content for phrase in LOW_VALUE_MEMORY_PHRASES)


def generate_meeting_outputs(
    conn,
    project_id: int,
    title: str,
    content: str,
    memory_context: str,
    retrieved_memories: list[dict] | None = None,
) -> tuple[int, list[int], list[int], str]:
    """Generate meeting artifacts with DeepSeek, falling back to local mocks."""
    injected_memories = [
        {
            "memory_id": item["memory_id"],
            "type": item["type"],
            "content": item["content"],
            "score": item.get("score", 0),
            "reasons": item.get("reasons", []),
        }
        for item in (retrieved_memories if retrieved_memories is not None else _get_injected_memory_rows(conn, project_id, content))
    ]
    conflict_result = detect_memory_conflicts(conn, project_id, content)
    deepseek_result = call_deepseek_json(
        _build_deepseek_meeting_messages(title, content, memory_context, injected_memories),
        mock_fallback=None,
        temperature=0.2,
    )
    normalized = _normalize_deepseek_meeting_result(deepseek_result, title)
    if normalized is None:
        return generate_mock_meeting_outputs(conn, project_id, title, content, memory_context, retrieved_memories, conflict_result)

    filtered_memories = [
        memory for memory in normalized["memories"]
        if not is_low_value_memory(memory)
    ]
    meeting_id = create_meeting(conn, project_id, title, content, normalized["summary"])
    candidate_ids = _save_deepseek_candidate_memories(
        conn,
        project_id=project_id,
        meeting_id=meeting_id,
        memories=filtered_memories,
    )
    action_ids = save_action_items(
        conn,
        project_id,
        meeting_id,
        normalized["action_items"],
    )
    referenced_memory_ids = _extract_referenced_memory_ids(normalized["summary"], injected_memories)
    without_memory_result = call_deepseek_json(
        _build_deepseek_meeting_messages(title, content, "", []),
        mock_fallback=None,
        temperature=0.2,
    )
    without_memory_normalized = _normalize_deepseek_meeting_result(without_memory_result, title)
    without_memory_summary = (
        without_memory_normalized["summary"]
        if without_memory_normalized is not None
        else generate_summary_placeholder(content, "")
    )
    _record_injected_memories(meeting_id, injected_memories)
    _record_referenced_memory_ids(meeting_id, referenced_memory_ids)
    increment_memory_reference_counts(referenced_memory_ids, project_id, meeting_id=meeting_id)
    _record_agent_run_log(
        project_id,
        meeting_id,
        retrieved_memories=retrieved_memories or injected_memories,
        injected_memories=injected_memories,
        candidate_memory_count=len(candidate_ids),
        action_item_count=len(action_ids),
        referenced_memory_ids=referenced_memory_ids,
        reference_count_updated=bool(referenced_memory_ids),
        llm_mode="deepseek",
        conflict_result=conflict_result,
    )
    _record_memory_impact_proof(
        meeting_id,
        without_memory_summary,
        normalized["summary"],
        referenced_memory_ids,
    )
    return meeting_id, candidate_ids, action_ids, "deepseek"


def generate_mock_meeting_outputs(
    conn,
    project_id: int,
    title: str,
    content: str,
    memory_context: str,
    retrieved_memories: list[dict] | None = None,
    conflict_result: dict | None = None,
) -> tuple[int, list[int], list[int], str]:
    """Run the original mock generation chain."""
    summary = generate_summary_placeholder(content, memory_context)
    meeting_id = create_meeting(conn, project_id, title, content, summary)
    candidate_ids = generate_mock_candidate_memories(
        conn,
        project_id=project_id,
        meeting_id=meeting_id,
        meeting_title=title,
        meeting_content=content,
        summary=summary,
        memory_context=memory_context,
    )
    candidate_ids = _filter_saved_candidate_memories(
        conn,
        project_id=project_id,
        meeting_id=meeting_id,
        candidate_ids=candidate_ids,
    )
    candidate_texts = [
        row["content"]
        for row in conn.execute(
            """
            SELECT content
            FROM candidate_memories
            WHERE project_id = ? AND meeting_id = ?
            """,
            (project_id, meeting_id),
        ).fetchall()
    ]
    action_items = extract_action_items_placeholder(content, *candidate_texts)
    action_ids = save_action_items(conn, project_id, meeting_id, action_items)
    injected_memories = [
        {
            "memory_id": item["memory_id"],
            "type": item["type"],
            "content": item["content"],
            "score": item.get("score", 0),
            "reasons": item.get("reasons", []),
        }
        for item in (retrieved_memories or _get_injected_memory_rows(conn, project_id, content))
    ]
    _record_injected_memories(meeting_id, injected_memories)
    _record_agent_run_log(
        project_id,
        meeting_id,
        retrieved_memories=retrieved_memories or injected_memories,
        injected_memories=injected_memories,
        candidate_memory_count=len(candidate_ids),
        action_item_count=len(action_ids),
        referenced_memory_ids=[],
        reference_count_updated=False,
        llm_mode="mock_fallback",
        conflict_result=conflict_result or detect_memory_conflicts(conn, project_id, content),
    )
    _record_memory_impact_proof(
        meeting_id,
        generate_summary_placeholder(content, ""),
        summary,
        [],
    )
    return meeting_id, candidate_ids, action_ids, "mock"


def _build_deepseek_meeting_messages(
    title: str,
    content: str,
    memory_context: str,
    injected_memories: list[dict],
) -> list[dict[str, str]]:
    cited_memory_context = _format_cited_memory_context(injected_memories)
    citation_rule = (
        "Memory citation rule: if a summary sentence uses or depends on an injected "
        "historical memory, append that memory marker after the related sentence, "
        "for example: Confirm continuing DeepSeek API integration. [MEMORY_8]\n"
        "Only cite markers from the injected memories below."
        if injected_memories
        else "Memory citation rule: there are no injected historical memories to cite."
    )
    return [
        {
            "role": "system",
            "content": (
                "You are a meeting memory agent. Return valid JSON only. "
                "Do not include markdown fences or prose outside JSON."
            ),
        },
        {
            "role": "user",
            "content": (
                "Generate structured meeting outputs from the meeting and project memory context.\n"
                "JSON schema:\n"
                "{\n"
                '  "summary": "string",\n'
                '  "memories": [\n'
                "    {\n"
                '      "type": "decision|constraint|requirement|risk|fact|action",\n'
                '      "content": "string",\n'
                '      "confidence": 0.0,\n'
                '      "importance": 0.0,\n'
                '      "source_meeting_title": "string"\n'
                "    }\n"
                "  ],\n"
                '  "action_items": [\n'
                "    {\n"
                '      "title": "string",\n'
                '      "owner": "string",\n'
                '      "deadline": "string",\n'
                '      "status": "open|doing|done|overdue"\n'
                "    }\n"
                "  ]\n"
                "}\n"
                "Keep memories durable and useful for future meetings. "
                "Use empty arrays when there are no valid memories or action items.\n\n"
                f"{citation_rule}\n\n"
                f"Meeting title: {title.strip() or 'Untitled meeting'}\n"
                f"Injected historical memories:\n{cited_memory_context}\n\n"
                f"Project memory context:\n{memory_context or 'None'}\n\n"
                f"Meeting content:\n{content or 'None'}"
            ),
        },
    ]


def _format_cited_memory_context(injected_memories: list[dict]) -> str:
    if not injected_memories:
        return "None"
    lines: list[str] = []
    for memory in injected_memories:
        lines.append(f"[MEMORY_{memory['memory_id']}]")
        lines.append(str(memory["content"]))
        lines.append("")
    return "\n".join(lines).strip()


def _extract_referenced_memory_ids(summary: str, injected_memories: list[dict]) -> list[int]:
    injected_ids = {int(memory["memory_id"]) for memory in injected_memories}
    referenced_ids: list[int] = []
    for memory_id in extract_referenced_memory_ids(summary):
        if memory_id in injected_ids and memory_id not in referenced_ids:
            referenced_ids.append(memory_id)
    return referenced_ids


def _normalize_deepseek_meeting_result(result, meeting_title: str) -> dict | None:
    if not isinstance(result, dict):
        return None
    summary = str(result.get("summary", "")).strip()
    memories = result.get("memories")
    action_items = result.get("action_items")
    if not summary or not isinstance(memories, list) or not isinstance(action_items, list):
        return None

    normalized_memories = []
    for item in memories:
        normalized = _normalize_deepseek_memory(item, meeting_title)
        if normalized is None:
            return None
        if normalized["content"]:
            normalized_memories.append(normalized)

    normalized_actions = []
    for item in action_items:
        normalized = _normalize_deepseek_action_item(item)
        if normalized is None:
            return None
        if normalized["task"]:
            normalized_actions.append(normalized)

    return {
        "summary": summary,
        "memories": normalized_memories,
        "action_items": normalized_actions,
    }


def _normalize_deepseek_memory(item, meeting_title: str) -> dict | None:
    if not isinstance(item, dict):
        return None
    required_fields = ("type", "content", "confidence", "importance", "source_meeting_title")
    if any(field not in item for field in required_fields):
        return None
    memory_type = _normalize_memory_type(item.get("type"))
    content = str(item.get("content", "")).strip()
    source_title = str(item.get("source_meeting_title") or meeting_title).strip()
    try:
        confidence = float(item.get("confidence"))
        importance = float(item.get("importance"))
    except (TypeError, ValueError):
        return None
    if not memory_type:
        return None
    return {
        "type": memory_type,
        "content": content,
        "confidence": confidence,
        "importance": importance,
        "source_meeting_title": source_title or meeting_title,
    }


def _normalize_deepseek_action_item(item) -> dict | None:
    if not isinstance(item, dict):
        return None
    required_fields = ("title", "owner", "deadline", "status")
    if any(field not in item for field in required_fields):
        return None
    status = str(item.get("status") or "open").strip().lower()
    if status not in {"open", "doing", "done", "overdue"}:
        status = "open"
    return {
        "task": str(item.get("title", "")).strip(),
        "owner": str(item.get("owner", "")).strip(),
        "deadline": str(item.get("deadline", "")).strip(),
        "status": status,
    }


def _normalize_memory_type(value) -> str | None:
    text = str(value or "").strip().lower()
    return {
        "decision": "decision",
        "constraint": "constraint",
        "requirement": "requirement",
        "risk": "risk",
        "fact": "fact",
        "action": "action",
        "decisions": "decision",
        "constraints": "constraint",
        "requirements": "requirement",
        "risks": "risk",
        "facts": "fact",
        "actions": "action",
        "todo": "action",
        "task": "action",
    }.get(text)


def _filter_saved_candidate_memories(
    conn,
    project_id: int,
    meeting_id: int,
    candidate_ids: list[int],
) -> list[int]:
    if not candidate_ids:
        return []
    rows = conn.execute(
        """
        SELECT id, content, memory_text
        FROM candidate_memories
        WHERE project_id = ?
          AND meeting_id = ?
          AND status = 'pending'
        """,
        (project_id, meeting_id),
    ).fetchall()
    low_value_ids = [
        int(row["id"])
        for row in rows
        if row["id"] in candidate_ids and is_low_value_memory(row)
    ]
    if low_value_ids:
        placeholders = ",".join("?" for _ in low_value_ids)
        conn.execute(
            f"DELETE FROM candidate_memories WHERE id IN ({placeholders})",
            low_value_ids,
        )
        conn.commit()
    return [candidate_id for candidate_id in candidate_ids if candidate_id not in low_value_ids]


def _save_deepseek_candidate_memories(
    conn,
    project_id: int,
    meeting_id: int,
    memories: list[dict],
) -> list[int]:
    ids: list[int] = []
    for memory in memories:
        content = memory["content"].strip()
        if is_low_value_memory(memory) or memory_like_exists(conn, project_id, content):
            continue
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
            (
                project_id,
                meeting_id,
                meeting_id,
                content,
                content,
                memory["type"],
            ),
        )
        ids.append(int(cursor.lastrowid))
    conn.commit()
    return ids


def render_new_meeting(project_id: int) -> None:
    last_flow = st.session_state.get("last_agent_flow")
    if last_flow and last_flow.get("project_id") == project_id:
        render_agent_activity_flow(
            project_id,
            candidate_count=last_flow.get("candidate_count"),
            action_count=last_flow.get("action_count"),
        )
    st.markdown("### 新建会议")
    st.caption("Agent 会先带入已确认项目记忆，再生成摘要和候选记忆。")
    title = st.text_input("会议标题", value="项目例会", key=f"title_{project_id}")
    content = st.text_area("会议内容", height=190, key=f"content_{project_id}")
    if st.button("生成纪要与候选记忆", type="primary"):
        with get_connection(DB_PATH) as conn:
            memory_context, retrieved_memories = build_top_k_memory_context(conn, project_id, content)
            meeting_id, candidate_ids, action_ids, generation_mode = generate_meeting_outputs(
                conn,
                project_id,
                title,
                content,
                memory_context,
                retrieved_memories,
            )
        st.session_state.last_agent_flow = {
            "project_id": project_id,
            "meeting_id": meeting_id,
            "candidate_count": len(candidate_ids),
            "action_count": len(action_ids),
            "generation_mode": generation_mode,
        }
        st.success(
            f"已生成会议 #{meeting_id}：候选记忆 {len(candidate_ids)} 条，"
            f"Action Items {len(action_ids)} 条。"
        )
        st.rerun()


def render_retrieval_preview(project_id: int) -> None:
    memories, memory_context = load_retrieval_preview(project_id)
    meeting_content = st.session_state.get(f"content_{project_id}", "")
    st.markdown("### Agent 将带入本次会议的历史上下文")
    st.caption(f"AI 不是普通摘要器；它会带着 {len(memories)} 条已确认项目记忆进入本次会议。")
    if not memories:
        render_empty_state("当前项目暂无可参考记忆", "确认候选记忆后，新会议会自动参考这些项目记忆。")
    else:
        for memory in memories:
            with st.container(border=True):
                st.markdown(f"**Memory #{memory['memory_id']}**")
                st.caption(f"类型：{memory['type']} · 最终得分：{memory['score']}")
                st.write(short_text(memory["content"], 140))
                st.markdown("**Why Selected**")
                for reason in memory["reasons"]:
                    st.caption(f"✓ {reason}")
    with st.expander("查看完整关联上下文", expanded=False):
        st.text_area("完整关联上下文", value=memory_context, height=180, disabled=True)
    render_memory_conflict_check(project_id, meeting_content)


def render_conflict_items(conflict_items: list[dict]) -> None:
    for item in [entry for entry in conflict_items if entry.get("is_conflict", True)]:
        with st.container(border=True):
            st.markdown("**⚠️ Potential Memory Conflict**")
            confidence_label = "High" if item.get("confidence") == "high" else "Medium"
            st.caption(f"Confidence: {confidence_label}")
            st.markdown("**历史记忆：**")
            st.write(f"[MEMORY_{item['memory_id']}] {item['memory_text']}")
            st.markdown("**当前会议片段：**")
            st.write(item["current_text"])
            st.markdown("**冲突原因：**")
            st.caption(item["reason"])
            if item.get("confidence") == "medium":
                st.caption("疑似冲突，建议人工确认。")
            elif item.get("confidence") == "high":
                st.caption("高置信冲突，建议优先复核。")
            st.markdown("**建议动作：**")
            st.caption(item["suggestion"])


def render_memory_conflict_check(project_id: int, meeting_content: str) -> dict:
    with get_connection(DB_PATH) as conn:
        result = detect_memory_conflicts(conn, project_id, meeting_content)
    st.markdown("### Memory Conflict Check")
    if result["conflict_count"] == 0:
        st.caption("未发现明显历史记忆冲突。")
        return result
    st.caption(f"发现 {result['conflict_count']} 条潜在历史记忆冲突。")
    render_conflict_items(result["conflict_items"])
    return result


def render_current_meeting_detail(project_id: int) -> None:
    meeting = get_selected_or_latest_meeting(project_id)
    if meeting is None:
        render_empty_state("暂无当前会议", "新建会议后，这里会显示最近一次会议详情。")
        return

    with get_connection(DB_PATH) as conn:
        candidate_count = count_candidate_memories_for_meeting(conn, project_id, meeting["id"])
        approved_count = count_approved_memories_for_meeting(conn, project_id, meeting["id"])
        action_count = count_action_items_for_meeting(conn, project_id, meeting["id"])
        meeting_memories = conn.execute(
            """
            SELECT memory_text, memory_type, created_at
            FROM memories
            WHERE project_id = ?
              AND source_meeting_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (project_id, meeting["id"]),
        ).fetchall()
        meeting_actions = list_action_items(conn, project_id)

    _ensure_memory_impact_proof(project_id, meeting)
    citation_data = get_meeting_citation_data(project_id, meeting)
    referenced_memories = citation_data["cited_memories"][:4]

    used_memory = "已引用" if meeting_used_memory(meeting["summary"]) else "未引用"
    with st.container(border=True):
        st.markdown(f"## {meeting['title']}")
        st.caption(
            f"{meeting['meeting_time']} · 历史记忆状态：{used_memory} · "
            f"候选记忆 {candidate_count} · 已确认记忆 {approved_count} · 附属待办 {action_count}"
        )
        nav_col, export_col, more_col = st.columns([1, 1, 1])
        with nav_col:
            if st.button("返回工作台", key=f"back_workbench_{meeting['id']}"):
                navigate_to("工作台")
        with export_col:
            st.button("导出", disabled=True, key=f"export_meeting_{meeting['id']}")
        with more_col:
            st.button("更多", disabled=True, key=f"more_meeting_{meeting['id']}")

    tabs = st.tabs([
        "会议摘要",
        f"引用历史记忆（{len(referenced_memories)}）",
        f"新增记忆（{approved_count}）",
        f"附属待办（{action_count}）",
        "原始内容",
    ])
    with tabs[0]:
        with st.container(border=True):
            st.markdown("#### 会议摘要")
            st.caption("AI 生成")
            st.write(meeting["summary"] or "暂无摘要")
        render_injected_memories(project_id, meeting)
        render_cited_memories(project_id, meeting)
        render_agent_run_log(project_id, meeting, candidate_count, action_count)
        render_memory_conflict_detection(project_id, meeting)
        render_memory_impact_proof(meeting["id"])
        render_memory_group("核心结论", meeting_memories, {"决策", "风险", "需求", "约束"})
    with tabs[1]:
        render_summary_memory_references(meeting, referenced_memories)
    with tabs[2]:
        render_memory_group("新增记忆", meeting_memories, {"决策", "风险", "需求", "约束", "事实", "待办"})
    with tabs[3]:
        render_meeting_action_summary(project_id, meeting["id"], meeting_actions)
    with tabs[4]:
        with st.container(border=True):
            st.write(meeting["content"] or "暂无原始内容")


def render_injected_memories(project_id: int, meeting) -> None:
    st.markdown("### 本次实际注入的历史记忆")
    injected_memories = get_meeting_citation_data(project_id, meeting)["injected_memories"]
    if not injected_memories:
        render_empty_state("暂无注入记录", "本次会议没有可展示的 DeepSeek 历史记忆注入记录。")
        return
    for memory in injected_memories:
        with st.container(border=True):
            st.caption(f"memory_id: {memory['memory_id']} · type: {memory['type']}")
            st.write(memory["content"])


def render_cited_memories(project_id: int, meeting) -> None:
    st.markdown("### 本次摘要引用的历史记忆")
    cited_rows = get_meeting_citation_data(project_id, meeting)["cited_memories"]
    cited_memories = [
        {
            "memory_id": row["id"],
            "type": row["memory_type"] or "fact",
            "content": row["memory_text"],
        }
        for row in cited_rows
    ]
    if not cited_memories:
        render_empty_state("暂无引用记录", "摘要中没有解析到 MEMORY 引用标记。")
        return
    for memory in cited_memories:
        with st.container(border=True):
            st.caption(f"memory_id: {memory['memory_id']} · type: {memory['type']}")
            st.write(memory["content"])


def render_agent_run_log(project_id: int, meeting, candidate_count: int, action_count: int) -> None:
    log = _get_agent_run_log(meeting["id"])
    if log is None:
        citation_data = get_meeting_citation_data(project_id, meeting)
        with get_connection(DB_PATH) as conn:
            conflict_result = detect_memory_conflicts(conn, project_id, meeting["content"] or "")
        log = {
            "retrieved_memory_count": len(citation_data["injected_memories"]),
            "retrieved_memory_ids": [item["memory_id"] for item in citation_data["injected_memories"]],
            "injected_memory_count": len(citation_data["injected_memories"]),
            "injected_memory_ids": [item["memory_id"] for item in citation_data["injected_memories"]],
            "candidate_memory_count": candidate_count,
            "action_item_count": action_count,
            "citation_count": len(citation_data["referenced_memory_ids"]),
            "referenced_memory_ids": citation_data["referenced_memory_ids"],
            "reference_count_updated": False,
            "llm_mode": "session_recovered",
            "conflict_checked_count": conflict_result["checked_count"],
            "conflict_found_count": conflict_result["conflict_count"],
            "conflict_items": conflict_result["conflict_items"],
        }
    st.markdown("### Agent Execution Trace")
    with st.container(border=True):
        st.caption(f"llm_mode: {log['llm_mode']}")
        st.markdown(f"Step 1 Memory Retrieval  \n✓ 检索长期记忆 {log['retrieved_memory_count']} 条")
        st.caption(f"retrieved_memory_ids: {log['retrieved_memory_ids'] or []}")
        st.markdown(f"Step 2 Memory Injection  \n✓ 注入 {log['injected_memory_count']} 条历史记忆")
        st.caption(f"injected_memory_ids: {log['injected_memory_ids'] or []}")
        st.markdown("Step 3 Summary Generation  \n✓ 生成会议摘要")
        st.markdown(f"Step 4 Action Extraction  \n✓ 生成 {log['action_item_count']} 条待办事项")
        st.markdown(f"Step 5 Memory Extraction  \n✓ 生成 {log['candidate_memory_count']} 条候选记忆")
        st.markdown(f"Step 6 Citation Tracking  \n✓ 检测到 {log['citation_count']} 条历史记忆被引用")
        st.caption(f"referenced_memory_ids: {log['referenced_memory_ids'] or []}")
        status = "已更新" if log["reference_count_updated"] else "未触发"
        st.markdown(f"Step 7 Reference Count Update  \n✓ {status}")
        st.markdown(
            f"Step 8 Memory Conflict Detection  \n"
            f"✓ 检测 {log.get('conflict_checked_count', 0)} 条历史记忆"
        )
        if log.get("conflict_found_count", 0):
            st.caption(f"发现 {log['conflict_found_count']} 条潜在冲突")
        else:
            st.caption("未发现明显历史记忆冲突")


def render_memory_conflict_detection(project_id: int, meeting) -> None:
    log = _get_agent_run_log(meeting["id"])
    if log is not None:
        checked_count = log.get("conflict_checked_count", 0)
        conflict_count = log.get("conflict_found_count", 0)
        conflict_items = log.get("conflict_items", [])
    else:
        with get_connection(DB_PATH) as conn:
            result = detect_memory_conflicts(conn, project_id, meeting["content"] or "")
        checked_count = result["checked_count"]
        conflict_count = result["conflict_count"]
        conflict_items = result["conflict_items"]

    st.markdown("### Memory Conflict Detection")
    st.caption(f"Checked memories: {checked_count}")
    st.caption(f"Potential conflicts found: {conflict_count}")
    if conflict_count:
        render_conflict_items(conflict_items)
    else:
        st.caption("未发现明显历史记忆冲突。")


def render_memory_impact_proof(meeting_id: int) -> None:
    proof = _get_recorded_memory_impact_proof(meeting_id)
    st.markdown("### 记忆影响验证")
    if not proof:
        render_empty_state("暂无影响验证", "本次会议暂无可展示的记忆影响对照结果。")
        return
    st.markdown("#### 无记忆版本摘要")
    st.write(proof["without_memory_summary"] or "暂无摘要")
    st.markdown("#### 有记忆版本摘要")
    st.write(proof["with_memory_summary"] or "暂无摘要")
    st.markdown("#### 差异分析")
    st.caption(
        f"引用历史记忆数量：{proof['referenced_memory_count']} · "
        f"新增关键词数量：{proof['new_keyword_count']} · "
        f"是否出现 Memory Citation：{'是' if proof['has_memory_citation'] else '否'}"
    )


def render_summary_memory_references(meeting, referenced_memories: list) -> None:
    st.markdown("### 本次摘要引用的历史记忆")
    if not referenced_memories:
        render_empty_state("暂无历史记忆引用", "当会议摘要带入已确认项目记忆后，这里会展示来源、内容和影响。")
        return
    for memory in referenced_memories:
        source = memory["source_meeting_title"] or "未知历史会议"
        with st.container(border=True):
            st.markdown("**AI 引用**")
            st.caption(f"来源会议：{source} · {memory['created_at']}")
            st.markdown("**记忆内容**")
            st.markdown(memory["memory_text"])
            st.markdown("**影响了哪段摘要/建议**")
            st.caption(summary_influence(meeting["summary"], memory["memory_text"]))
            st.markdown("**Agent 引用原因**")
            st.caption("当前会议主题与该历史记忆相关")
            st.caption("该记忆属于同一 Project 下的已确认项目记忆")
            st.caption("该记忆可能影响本次摘要、建议或后续决策")


def render_memory_group(title: str, memories: list, categories: set[str]) -> None:
    st.markdown(f"### {title}")
    rows = [
        row for row in memories
        if memory_category_from_type(row["memory_type"], row["memory_text"]) in categories
    ]
    if not rows:
        render_empty_state("暂无内容", f"当前会议暂无{title}。")
        return
    for index, row in enumerate(rows[:5], start=1):
        category = memory_category_from_type(row["memory_type"], row["memory_text"])
        with st.container(border=True):
            st.caption(category)
            st.markdown(f"**{index}. {row['memory_text']}**")


def render_meeting_action_summary(project_id: int, meeting_id: int, action_items: list) -> None:
    st.markdown("### 待办事项")
    rows = [row for row in action_items if row["source_meeting_id"] == meeting_id]
    if not rows:
        render_empty_state("暂无待办", "当前会议暂无 Action Items。")
        return
    for row in rows[:5]:
        with st.container(border=True):
            st.caption(row["status"])
            st.markdown(f"**{row['task']}**")
            st.caption(f"Owner：{row['owner'] or '未指定'} · Deadline：{row['deadline'] or '未指定'}")


def render_candidate_memories(project_id: int) -> None:
    st.caption("确认这些候选记忆，就是在训练这个项目的长期记忆；只有人工确认后，后续会议才会引用。")
    with get_connection(DB_PATH) as conn:
        candidates = list_candidate_memories(conn, project_id)

    if not candidates:
        render_empty_state("暂无待确认候选记忆", "新建会议后，候选记忆会出现在这里。")
        return

    categories = ["全部", "决策", "需求", "约束", "风险", "事实", "后续关注"]
    grouped: dict[str, list] = {category: [] for category in categories}
    for candidate in candidates:
        text = candidate["memory_text"] if "memory_text" in candidate.keys() else candidate["content"]
        category = memory_category_from_type(candidate["memory_type"], text) if "memory_type" in candidate.keys() else infer_memory_category(text)
        display_category = "后续关注" if category == "待办" else category
        grouped["全部"].append(candidate)
        grouped.setdefault(display_category, []).append(candidate)

    tabs = st.tabs([f"{category} {len(grouped.get(category, []))}" for category in categories])
    for tab, tab_category in zip(tabs, categories):
        with tab:
            for idx, candidate in enumerate(grouped.get(tab_category, []), start=1):
                render_candidate_memory_card(project_id, candidate, idx, tab_category)


def render_candidate_memory_card(project_id: int, candidate, idx: int, scope: str) -> None:
    text = candidate["memory_text"] if "memory_text" in candidate.keys() else candidate["content"]
    category = memory_category_from_type(candidate["memory_type"], text) if "memory_type" in candidate.keys() else infer_memory_category(text)
    display_category = "后续关注" if category == "待办" else category
    weight = mock_memory_weight(text)
    confidence = mock_memory_confidence(text)
    source_excerpt = get_candidate_source_excerpt(project_id, candidate)
    candidate_id = int(candidate["id"])
    key_scope = f"{project_id}_{scope}_{candidate_id}_{idx}"
    future_effect = "会影响后续会议上下文" if category in {"决策", "约束", "风险", "需求", "待办"} else "可作为后续会议背景事实"
    with st.container(border=True):
        duplicate_label = " · 可能重复" if candidate["possible_duplicate"] else ""
        st.caption(f"pending · {display_category}{duplicate_label}")
        st.caption(f"来源：{candidate['meeting_title'] or '未知会议'} · {candidate['created_at']}")
        st.caption(f"记忆类型：{display_category} · 权重：{weight:.2f} · 置信度：{confidence:.2f}")
        st.markdown("**来源原文**")
        st.markdown(source_excerpt)
        st.markdown("**Agent 提取理由**")
        st.caption(memory_agent_reason(display_category, text))
        st.markdown("**是否会影响后续会议**")
        st.caption(future_effect)
        st.markdown("**候选记忆**")
        st.markdown(text)
    edited_text = st.text_area(
        "编辑候选记忆",
        value=text,
        key=f"edit_candidate_{key_scope}",
        height=78,
        label_visibility="collapsed",
    )
    approve_col, merge_col, reject_col, _ = st.columns([1, 1, 1, 4])
    with approve_col:
        if st.button("确认", key=f"confirm_candidate_{key_scope}"):
            with get_connection(DB_PATH) as conn:
                user_confirm_memory(conn, candidate["id"], "approved", edited_content=edited_text)
            st.rerun()
    with merge_col:
        if st.button("合并", key=f"merge_candidate_{key_scope}"):
            with get_connection(DB_PATH) as conn:
                user_confirm_memory(conn, candidate["id"], "merged")
            st.rerun()
    with reject_col:
        if st.button("拒绝", key=f"reject_candidate_{key_scope}"):
            with get_connection(DB_PATH) as conn:
                user_confirm_memory(conn, candidate["id"], "rejected")
            st.rerun()


def render_project_memories(project_id: int) -> None:
    st.caption("这些是已经通过人工确认的项目记忆，会被 Agent 带入后续会议。")
    with get_connection(DB_PATH) as conn:
        memories = retrieve_project_memories(conn, project_id)

    render_low_value_memory_scanner(project_id)

    if not memories:
        render_empty_state("项目记忆为空", "确认候选记忆后，正式记忆会沉淀到这里。")
        return

    search_col, filter_col, sort_col = st.columns([2, 1, 1])
    with search_col:
        query = st.text_input("搜索记忆内容、关键词……", key=f"memory_search_{project_id}")
    with filter_col:
        type_filter = st.selectbox("类型筛选", ["全部", "决策", "需求", "约束", "风险", "事实", "后续关注"])
    with sort_col:
        sort_mode = st.selectbox("排序", ["按引用次数", "最近更新时间", "权重"])

    filtered = []
    for memory in memories:
        display_category = memory_display_category(memory["memory_type"], memory["memory_text"])
        if type_filter != "全部" and display_category != type_filter:
            continue
        if query.strip() and query.strip().lower() not in memory["memory_text"].lower():
            continue
        filtered.append(memory)
    if sort_mode == "按引用次数":
        filtered.sort(key=lambda item: count_memory_references_for_memory(project_id, item), reverse=True)
    elif sort_mode == "权重":
        filtered.sort(key=lambda item: mock_memory_weight(item["memory_text"]), reverse=True)

    groups = ["全部", "决策", "约束", "风险", "需求", "事实", "后续关注"]
    tabs = st.tabs(groups)
    for tab, group in zip(tabs, groups):
        with tab:
            rows = [
                memory for memory in filtered
                if group == "全部" or memory_display_category(memory["memory_type"], memory["memory_text"]) == group
            ]
            if not rows:
                render_empty_state(f"暂无{group}记忆", "当候选记忆被确认后，会沉淀到对应分类。")
                continue
            for memory in rows:
                category = memory_category_from_type(memory["memory_type"], memory["memory_text"]) if "memory_type" in memory.keys() else infer_memory_category(memory["memory_text"])
                source = memory["source_meeting_title"] or f"会议 #{memory['source_meeting_id']}"
                weight = mock_memory_weight(memory["memory_text"])
                confidence = mock_memory_confidence(memory["memory_text"])
                reference_count = count_memory_references_for_memory(project_id, memory)
                asset_label = " · 核心资产" if reference_count >= 3 else ""
                with st.container(border=True):
                    st.caption(f"记忆类型：{group}{asset_label}")
                    st.markdown(f"**{short_text(memory['memory_text'], 90)}**")
                    st.caption(
                        f"来源：{source} · 引用 {reference_count} 次 · "
                        f"权重 {weight:.2f} · 置信度 {confidence:.2f}"
                    )


def render_low_value_memory_scanner(project_id: int) -> None:
    if st.button("扫描历史垃圾记忆", key=f"scan_low_value_memories_{project_id}"):
        with get_connection(DB_PATH) as conn:
            st.session_state[f"low_value_memory_scan_{project_id}"] = scan_low_value_project_memories(
                conn,
                project_id,
            )

    scan_results = st.session_state.get(f"low_value_memory_scan_{project_id}", [])
    if not scan_results:
        return

    st.markdown("### 疑似历史垃圾记忆")
    for memory in scan_results:
        with st.container(border=True):
            st.caption(f"memory_id: {memory['memory_id']} · type: {memory['type']}")
            st.write(memory["content"])
            if st.button(
                "删除",
                key=f"delete_low_value_memory_{project_id}_{memory['memory_id']}",
            ):
                with get_connection(DB_PATH) as conn:
                    delete_project_memory(conn, project_id, memory["memory_id"])
                st.session_state.pop(f"low_value_memory_scan_{project_id}", None)
                st.rerun()


def scan_low_value_project_memories(conn, project_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, memory_type, memory_text
        FROM memories
        WHERE project_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (project_id,),
    ).fetchall()
    return [
        {
            "memory_id": int(row["id"]),
            "type": row["memory_type"] or "fact",
            "content": row["memory_text"] or "",
        }
        for row in rows
        if is_low_value_memory(row["memory_text"] or "")
    ]


def delete_project_memory(conn, project_id: int, memory_id: int) -> None:
    conn.execute(
        """
        DELETE FROM memories
        WHERE project_id = ?
          AND id = ?
        """,
        (project_id, memory_id),
    )
    conn.commit()


def render_action_items(project_id: int) -> None:
    st.caption("Action Items 来自会议提取结果，用于提醒后续关注；它不是项目记忆 Agent 的主工作区。")
    with get_connection(DB_PATH) as conn:
        rows = list_action_items(conn, project_id)

    if not rows:
        render_empty_state("暂无 Action Items", "会议内容出现“下次、待讨论、需要、负责人、TODO、待办”时会生成待办。")
        return

    tab_defs = [
        ("全部", rows),
        ("进行中", [row for row in rows if row["status"] == "doing"]),
        ("已完成", [row for row in rows if row["status"] == "done"]),
        ("已逾期", [row for row in rows if row["status"] == "overdue"]),
    ]
    tabs = st.tabs([f"{title} {len(items)}" for title, items in tab_defs])
    for tab, (title, items) in zip(tabs, tab_defs):
        with tab:
            if not items:
                st.caption("暂无记录")
                continue
            for row in items:
                render_action_item_row(project_id, row, title)
            st.caption(f"共 {len(items)} 条")


def render_action_item_row(project_id: int, row, scope: str) -> None:
    source = row["source_meeting_title"] or f"会议 #{row['source_meeting_id']}"
    with st.container(border=True):
        st.caption(row["status"])
        st.markdown(f"**{row['task']}**")
        st.caption(
            f"来源：{source} · Owner：{row['owner'] or '未指定'} · "
            f"Deadline：{row['deadline'] or '未指定'} · {row['created_at']}"
        )
    detail_col, doing_col, done_col, overdue_col, _ = st.columns([1, 1, 1, 1, 3])
    with detail_col:
        if st.button("详情", key=f"select_action_{scope}_{row['id']}"):
            st.session_state.selected_action_item_id = row["id"]
            st.rerun()
    with doing_col:
        if st.button("进行中", key=f"doing_action_{scope}_{row['id']}"):
            with get_connection(DB_PATH) as conn:
                update_action_item_status(conn, project_id, row["id"], "doing")
            st.rerun()
    with done_col:
        if st.button("已完成", key=f"done_action_{scope}_{row['id']}"):
            with get_connection(DB_PATH) as conn:
                update_action_item_status(conn, project_id, row["id"], "done")
            st.rerun()
    with overdue_col:
        if st.button("逾期", key=f"overdue_action_{scope}_{row['id']}"):
            with get_connection(DB_PATH) as conn:
                update_action_item_status(conn, project_id, row["id"], "overdue")
            st.rerun()


def render_meeting_timeline(project_id: int) -> None:
    st.markdown("### 会议时间线")
    with get_connection(DB_PATH) as conn:
        meetings = list_meetings(conn, project_id)
        counts = {
            row["id"]: {
                "candidates": count_candidate_memories_for_meeting(conn, project_id, row["id"]),
                "approved": count_approved_memories_for_meeting(conn, project_id, row["id"]),
                "actions": count_action_items_for_meeting(conn, project_id, row["id"]),
                "references": get_referenced_memories_for_meeting(conn, project_id, row["id"]),
            }
            for row in meetings
        }

    if not meetings:
        render_empty_state("暂无会议", "新建会议后会在这里形成项目时间线。")
        return

    for meeting in meetings[:8]:
        count = counts[meeting["id"]]
        used_memory = "是" if meeting_used_memory(meeting["summary"]) else "否"
        with st.container(border=True):
            st.markdown(f"**{meeting['title']}**")
            st.caption(meeting["meeting_time"])
            st.caption(
                f"候选记忆 {count['candidates']} · 已确认记忆 {count['approved']} · "
                f"附属待办 {count['actions']} · 引用历史记忆：{used_memory}"
            )


def render_horizontal_meeting_timeline(project_id: int) -> None:
    with get_connection(DB_PATH) as conn:
        meetings = list_meetings(conn, project_id)
        counts = {
            row["id"]: {
                "approved": count_approved_memories_for_meeting(conn, project_id, row["id"]),
                "references": len(get_referenced_memories_for_meeting(conn, project_id, row["id"])),
            }
            for row in meetings
        }
    st.markdown("### 项目演化时间线")
    st.caption("项目会议演化过程，点击节点查看详情")
    if not meetings:
        render_empty_state("暂无会议", "新建会议后会在这里形成项目时间线。")
        return
    shown = list(reversed(meetings[:10]))
    active_id = st.session_state.get("selected_meeting_id") or meetings[0]["id"]
    cards = []
    for meeting in shown:
        selected = active_id == meeting["id"]
        cards.append(
            f"""
            <div class="timeline-card {'active' if selected else ''}">
                <div class="timeline-dot"></div>
                <div class="timeline-title">{escape(short_text(meeting['title'], 28))}</div>
                <div class="timeline-date">{escape(str(meeting['meeting_time']))}</div>
                <div class="timeline-stats">
                    <span class="timeline-stat">新增 {counts[meeting['id']]['approved']}</span>
                    <span class="timeline-stat">引用 {counts[meeting['id']]['references']}</span>
                </div>
            </div>
            """
        )
    st.markdown(
        f"""
        <div class="timeline-scroll">
            <div class="timeline-track">
                {''.join(cards)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    cols = st.columns(min(len(shown), 5))
    for index, meeting in enumerate(shown):
        col = cols[index % len(cols)]
        with col:
            if st.button(short_text(meeting["title"], 14), key=f"timeline_open_{meeting['id']}", use_container_width=True):
                navigate_to("会议详情", meeting_id=meeting["id"])


def render_related_meetings(project_id: int) -> None:
    with get_connection(DB_PATH) as conn:
        meetings = list_meetings(conn, project_id)
    st.markdown("### 关联历史会议")
    if not meetings:
        st.caption("暂无历史会议")
    else:
        for meeting in meetings[:5]:
            st.divider()
            st.markdown(f"**{meeting['title']}**")
            st.caption(meeting["meeting_time"])
            if st.button("查看会议", key=f"select_meeting_{meeting['id']}"):
                navigate_to("会议详情", meeting_id=meeting["id"])


def render_action_overview(project_id: int) -> None:
    with get_connection(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM action_items
            WHERE project_id = ?
            GROUP BY status
            """,
            (project_id,),
        ).fetchall()
    counts = {row["status"]: row["count"] for row in rows}
    open_count = counts.get("open", 0)
    doing_count = counts.get("doing", 0)
    done_count = counts.get("done", 0)
    overdue_count = counts.get("overdue", 0)
    total = open_count + doing_count + done_count + overdue_count
    with st.container(border=True):
        st.markdown("### 附属待办")
        st.caption("会议中顺手提取的提醒项，不作为产品主线。")
        st.divider()
        st.caption(f"open {open_count} · doing {doing_count} · done {done_count} · overdue {overdue_count}")
        st.caption(f"合计 {total} 条")


def _percent(numerator: int, denominator: int) -> float:
    return (numerator / denominator * 100) if denominator else 0.0


def collect_evaluation_metrics(project_id: int) -> dict:
    with get_connection(DB_PATH) as conn:
        meetings = conn.execute(
            """
            SELECT id, title, summary, content, created_at
            FROM meetings
            WHERE project_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (project_id,),
        ).fetchall()
        memories = retrieve_project_memories(conn, project_id, limit=200)
        candidate_total = int(
            conn.execute(
                "SELECT COUNT(*) FROM candidate_memories WHERE project_id = ?",
                (project_id,),
            ).fetchone()[0]
        )
        action_rows = conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM action_items
            WHERE project_id = ?
            GROUP BY status
            """,
            (project_id,),
        ).fetchall()
        memory_type_rows = conn.execute(
            """
            SELECT COALESCE(memory_type, 'fact') AS type, COUNT(*) AS count
            FROM memories
            WHERE project_id = ?
            GROUP BY COALESCE(memory_type, 'fact')
            ORDER BY count DESC
            """,
            (project_id,),
        ).fetchall()

    total_meetings = len(meetings)
    citation_meetings = [
        meeting for meeting in meetings
        if extract_referenced_memory_ids(meeting["summary"] or "")
    ]
    reused_memories = [
        memory for memory in memories
        if count_memory_references_for_memory(project_id, memory) > 0
    ]
    confirmed_total = len(memories)
    approval_denominator = confirmed_total + candidate_total

    conflict_meeting_ids: set[int] = set()
    with get_connection(DB_PATH) as conn:
        for meeting in meetings:
            result = detect_memory_conflicts(conn, project_id, meeting["content"] or "")
            if result["conflict_count"] > 0:
                conflict_meeting_ids.add(int(meeting["id"]))

    impact_proofs = st.session_state.get("memory_impact_proofs", {})
    impact_meeting_ids = {
        int(meeting["id"])
        for meeting in meetings
        if int(meeting["id"]) in impact_proofs
    }

    action_counts = {row["status"]: int(row["count"]) for row in action_rows}
    done_actions = action_counts.get("done", 0)
    total_actions = sum(action_counts.values())

    top_memories = sorted(
        [
            {
                "memory_id": int(memory["id"]),
                "content": memory["memory_text"],
                "reference_count": count_memory_references_for_memory(project_id, memory),
                "source_meeting_title": memory["source_meeting_title"] or f"会议 #{memory['source_meeting_id']}",
            }
            for memory in memories
        ],
        key=lambda item: item["reference_count"],
        reverse=True,
    )[:5]

    events = build_recent_evaluation_events(meetings, conflict_meeting_ids, impact_meeting_ids)

    return {
        "total_meetings": total_meetings,
        "citation_meetings": len(citation_meetings),
        "citation_rate": _percent(len(citation_meetings), total_meetings),
        "memory_reuse_count": len(reused_memories),
        "confirmed_total": confirmed_total,
        "candidate_total": candidate_total,
        "approval_rate": _percent(confirmed_total, approval_denominator),
        "conflict_meetings": len(conflict_meeting_ids),
        "conflict_rate": _percent(len(conflict_meeting_ids), total_meetings),
        "impact_meetings": len(impact_meeting_ids),
        "impact_coverage": _percent(len(impact_meeting_ids), total_meetings),
        "done_actions": done_actions,
        "total_actions": total_actions,
        "completion_rate": _percent(done_actions, total_actions),
        "memory_distribution": [
            {"type": row["type"], "count": int(row["count"])}
            for row in memory_type_rows
        ],
        "top_memories": top_memories,
        "events": events,
    }


def build_recent_evaluation_events(meetings: list, conflict_meeting_ids: set[int], impact_meeting_ids: set[int]) -> list[dict]:
    events: list[dict] = []
    for meeting in meetings:
        event_date = str(meeting["created_at"]).split(" ", 1)[0]
        meeting_id = int(meeting["id"])
        if extract_referenced_memory_ids(meeting["summary"] or ""):
            events.append({"date": event_date, "title": "Memory Citation Triggered", "detail": meeting["title"]})
        if meeting_id in impact_meeting_ids:
            events.append({"date": event_date, "title": "Impact Validation Generated", "detail": meeting["title"]})
        if meeting_id in conflict_meeting_ids:
            events.append({"date": event_date, "title": "Potential Memory Conflict Found", "detail": meeting["title"]})
        else:
            events.append({"date": event_date, "title": "Conflict Check Passed", "detail": meeting["title"]})
    return events[:8]


def render_evaluation_dashboard_view(project_id: int) -> None:
    render_project_header(
        project_id,
        title="Evaluation Dashboard",
        subtitle="评估 Long-term Memory Agent 是否形成记忆使用、引用验证和业务闭环",
        show_metrics=False,
    )
    metrics = collect_evaluation_metrics(project_id)

    kpi_cols = st.columns(3)
    with kpi_cols[0].container(border=True):
        st.metric("Citation Rate", f"{metrics['citation_rate']:.1f}%")
        st.caption(f"{metrics['citation_meetings']} / {metrics['total_meetings']} · 历史记忆被引用的会议占比")
    with kpi_cols[1].container(border=True):
        st.metric("Memory Reuse", metrics["memory_reuse_count"])
        st.caption("被后续会议实际复用的长期记忆数量")
    with kpi_cols[2].container(border=True):
        st.metric("Approval Rate", f"{metrics['approval_rate']:.0f}%")
        st.caption(f"{metrics['confirmed_total']} / {metrics['confirmed_total'] + metrics['candidate_total']} · 候选记忆进入长期记忆库比例")

    kpi_cols = st.columns(3)
    with kpi_cols[0].container(border=True):
        st.metric("Conflict Rate", f"{metrics['conflict_rate']:.0f}%")
        st.caption(f"{metrics['conflict_meetings']} / {metrics['total_meetings']} · 发现潜在历史冲突的会议占比")
    with kpi_cols[1].container(border=True):
        st.metric("Impact Coverage", f"{metrics['impact_coverage']:.0f}%")
        st.caption(f"{metrics['impact_meetings']} / {metrics['total_meetings']} · 完成有记忆 vs 无记忆对比验证的会议占比")
    with kpi_cols[2].container(border=True):
        st.metric("Completion Rate", f"{metrics['completion_rate']:.0f}%")
        st.caption(f"{metrics['done_actions']} / {metrics['total_actions']} · 会议行动项完成率")

    left_col, right_col = st.columns([1, 1], gap="large")
    with left_col.container(border=True):
        st.markdown("### Memory Usage Distribution")
        if metrics["memory_distribution"]:
            st.bar_chart(metrics["memory_distribution"], x="type", y="count")
        else:
            st.caption("暂无长期记忆数据")

    with right_col.container(border=True):
        st.markdown("### Top Referenced Memories")
        if not metrics["top_memories"]:
            st.caption("暂无长期记忆")
        for item in metrics["top_memories"]:
            st.markdown(f"**MEMORY_{item['memory_id']}**")
            st.write(short_text(item["content"], 90))
            st.caption(f"引用 {item['reference_count']} 次 · 来源：{item['source_meeting_title']}")
            st.divider()

    with st.container(border=True):
        st.markdown("### Recent Evaluation Events")
        if not metrics["events"]:
            st.caption("暂无评估事件")
        for event in metrics["events"]:
            st.caption(f"[{event['date']}]")
            st.markdown(f"**{event['title']}**")
            st.caption(event["detail"])
            st.divider()


def render_agent_side_summary(project_id: int) -> None:
    overview = get_project_overview(project_id)
    recent_meeting = get_recent_referenced_meeting(project_id)
    top_memory, top_reference_count = get_top_referenced_memory(project_id)
    with st.container(border=True):
        st.markdown("### Agent 记忆状态")
        st.caption(f"已确认项目记忆：{overview['memory_total']} 条可被后续会议引用")
        st.caption(f"待人工确认：{overview['pending_total']} 条候选记忆等待训练")
        st.caption(f"最近带入历史的会议：{short_text(recent_meeting['title'], 42) if recent_meeting else '暂无'}")
        st.caption(f"被引用最多的记忆：{short_text(top_memory['memory_text'], 42) if top_memory else '暂无'}")
        st.caption(f"引用 {top_reference_count} 次")


def render_selected_action_detail(project_id: int) -> None:
    selected_id = st.session_state.get("selected_action_item_id")
    st.markdown("### 任务详情")
    if not selected_id:
        render_empty_state("未选择任务", "在待办中心点击“查看详情”。")
        return

    with get_connection(DB_PATH) as conn:
        item = get_action_item(conn, project_id, int(selected_id))
    if item is None:
        st.session_state.selected_action_item_id = None
        render_empty_state("任务不存在", "该任务不属于当前 Project 或已被移除。")
        return

    source = item["source_meeting_title"] or f"会议 #{item['source_meeting_id']}"
    st.divider()
    st.caption(item["status"])
    st.markdown(f"**{item['task']}**")
    st.caption(f"来源：{source}")
    st.caption(f"Owner：{item['owner'] or '未指定'}")
    st.caption(f"Deadline：{item['deadline'] or '未指定'}")
    st.caption(f"Created：{item['created_at']}")


def render_project_info(project_id: int) -> None:
    project = get_project(project_id)
    overview = get_project_overview(project_id)
    with st.container(border=True):
        st.markdown("### 项目信息")
        st.caption(f"项目描述：{project['description'] or '暂无项目描述'}")
        st.caption(f"创建时间：{project['created_at']}")
        st.caption(f"项目资产：{overview['meeting_total']} 场会议 · {overview['memory_total']} 条记忆")


def render_recent_confirmed_memories(project_id: int) -> None:
    with get_connection(DB_PATH) as conn:
        memories = retrieve_project_memories(conn, project_id, limit=4)
    st.markdown("### 最近确认记忆")
    if not memories:
        st.caption("暂无已确认记忆")
    else:
        for memory in memories:
            category = memory_category_from_type(memory["memory_type"], memory["memory_text"]) if "memory_type" in memory.keys() else infer_memory_category(memory["memory_text"])
            source = memory["source_meeting_title"] or f"会议 #{memory['source_meeting_id']}"
            st.divider()
            st.caption(category)
            st.markdown(memory["memory_text"])
            st.caption(source)


def render_right_panel(project_id: int) -> None:
    try:
        render_agent_side_summary(project_id)
        render_project_info(project_id)
        render_recent_confirmed_memories(project_id)
    except Exception as e:
        st.error(f"右侧面板渲染异常: {e}")


def render_workbench_view(project_id: int) -> None:
    render_project_header(project_id)
    render_workbench_recent_summary(project_id)
    render_workbench_memory_references(project_id)
    render_quick_entries(project_id)
    render_agent_metrics(project_id)
    render_agent_side_summary(project_id)
    render_project_info(project_id)
    render_recent_confirmed_memories(project_id)


def render_new_meeting_view(project_id: int) -> None:
    render_project_header(
        project_id,
        title="新建会议",
        subtitle="输入会议内容，Agent 将自动读取历史记忆，生成纪要并提取候选记忆和待办事项",
        show_metrics=False,
    )
    form_col, context_col = st.columns([1, 1.25], gap="large")
    with form_col:
        render_new_meeting(project_id)
    with context_col:
        render_retrieval_preview(project_id)


def render_pending_memory_view(project_id: int) -> None:
    render_project_header(
        project_id,
        title="待确认记忆",
        subtitle="Agent 从会议中提取的候选记忆，需要人工确认后才会进入长期记忆库",
        show_metrics=False,
    )
    render_candidate_memories(project_id)


def render_project_memory_view(project_id: int) -> None:
    render_project_header(
        project_id,
        title="项目长期记忆",
        subtitle="持续沉淀项目知识，Agent 会在后续会议中自动引用",
        show_metrics=False,
    )
    render_project_memories(project_id)


def render_action_center_view(project_id: int) -> None:
    render_project_header(
        project_id,
        title="待办中心",
        subtitle="会议中生成的行动项，用于跟踪执行进度",
        show_metrics=False,
    )
    render_action_items(project_id)


def render_meeting_detail_view(project_id: int) -> None:
    render_project_header(
        project_id,
        title="会议详情",
        subtitle="查看会议摘要、引用历史记忆、新增记忆、附属待办和原始内容",
        show_metrics=False,
    )
    render_current_meeting_detail(project_id)


def render_docs_tab(project_id: int) -> None:
    render_project_header(project_id)
    st.markdown("### 项目文档")
    st.write("MVP 暂未接入文档系统。当前可沉淀为文档素材的内容来自已确认项目记忆。")
    with get_connection(DB_PATH) as conn:
        memories = retrieve_project_memories(conn, project_id, limit=80)
    if not memories:
        render_empty_state("暂无文档素材", "确认候选记忆后，这里会按类型组织项目文档素材。")
    else:
        for category in ["决策", "需求", "风险", "约束", "事实", "待办"]:
            rows = [
                row for row in memories
                if memory_category_from_type(row["memory_type"], row["memory_text"]) == category
            ]
            if not rows:
                continue
            st.markdown(f"#### {category}")
            for row in rows[:5]:
                source = row["source_meeting_title"] or f"会议 #{row['source_meeting_id']}"
                with st.container(border=True):
                    st.caption(f"来源：{source} · {row['created_at']}")
                    st.markdown(row["memory_text"])


def render_settings_tab(project_id: int) -> None:
    project = get_project(project_id)
    render_project_header(
        project_id,
        title="设置",
        subtitle="配置项目和 Agent 的基础参数",
        show_metrics=False,
    )
    menu_col, content_col, icon_col = st.columns([0.9, 2.1, 1], gap="large")
    with menu_col:
        selected = st.radio(
            "设置菜单",
            ["项目设置", "模型设置", "记忆配置", "引用配置", "显示设置"],
            label_visibility="collapsed",
            key=f"settings_menu_{project_id}",
        )
    with content_col:
        if selected == "项目设置":
            with st.container(border=True):
                st.markdown("### 项目设置")
                st.text_input("项目名称", value=project["name"], disabled=True)
                st.text_area("项目描述", value=project["description"] or "", disabled=True)
                st.caption(f"创建时间：{project['created_at']}")
                st.caption(f"项目 ID：{project_id}")
                st.selectbox("时区设置", ["(GMT+8) Asia/Shanghai"], disabled=True)
                st.button("保存设置", disabled=True)
        elif selected == "模型设置":
            with st.container(border=True):
                st.markdown("### 模型设置")
                st.caption("会议摘要与候选记忆生成会优先尝试真实 LLM 调用；不可用时自动使用本地 fallback 保证流程可用。")
                st.caption("当前页面仅展示配置占位，暂不提供在线切换。")
        elif selected == "记忆配置":
            with st.container(border=True):
                st.markdown("### 记忆配置")
                st.caption("可提取记忆类型：决策、需求、约束、风险、事实、后续关注")
                st.checkbox("候选记忆必须人工确认后入库", value=True, disabled=True)
                st.checkbox("重复记忆检测", value=True, disabled=True)
        elif selected == "引用配置":
            with st.container(border=True):
                st.markdown("### 引用配置")
                st.slider("新会议最多带入历史记忆数", min_value=1, max_value=10, value=5, disabled=True)
                st.caption("优先引用类型：决策、风险、约束")
                st.checkbox("展示引用原因", value=True, disabled=True)
                st.checkbox("展示影响了哪段摘要", value=True, disabled=True)
        else:
            with st.container(border=True):
                st.markdown("### 显示设置")
                st.checkbox("显示右侧信息栏", value=True, disabled=True)
                st.checkbox("显示最近确认记忆", value=True, disabled=True)
                st.checkbox("显示 Mock/LLM 状态", value=True, disabled=True)
                st.checkbox("显示快捷入口", value=True, disabled=True)
    with icon_col:
        with st.container(border=True):
            st.markdown("### 项目图标")
            st.markdown("◎")
            st.button("更换图标", disabled=True)
            st.caption("更换图标仅代表更换当前项目 / Agent 的视觉 Logo，不影响业务逻辑。")
        with st.container(border=True):
            st.markdown("### 危险操作")
            st.caption("删除项目为危险操作，MVP 暂不执行真实删除。")
            st.button("删除项目", disabled=True)


def render_active_view(active_view: str, project_id: int) -> None:
    if active_view == "工作台":
        render_workbench_view(project_id)
    elif active_view == "新建会议":
        render_new_meeting_view(project_id)
    elif active_view == "待确认记忆":
        render_pending_memory_view(project_id)
    elif active_view == "项目记忆":
        render_project_memory_view(project_id)
    elif active_view == "待办中心":
        render_action_center_view(project_id)
    elif active_view == "会议详情":
        render_meeting_detail_view(project_id)
    elif active_view == "Evaluation Dashboard":
        render_evaluation_dashboard_view(project_id)
    elif active_view == "设置":
        render_settings_tab(project_id)
    else:
        render_workbench_view(project_id)


def main() -> None:
    st.set_page_config(page_title="Project Memory Agent", layout="wide")
    bootstrap()
    inject_styles()

    project_id = render_sidebar()
    ensure_ui_state(project_id)
    render_topbar(project_id)

    main_col, side_col = st.columns([2.7, 0.9], gap="large")
    with main_col:
        try:
            render_active_view(st.session_state.active_view, project_id)
        except Exception as e:
            st.error(f"主内容渲染异常: {e}")
    with side_col:
        render_right_panel(project_id)
        if st.session_state.active_view == "待办中心":
            render_action_overview(project_id)
            render_selected_action_detail(project_id)
        elif st.session_state.active_view == "会议详情":
            render_related_meetings(project_id)


if __name__ == "__main__":
    main()

