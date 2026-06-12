"""Summary generation placeholders."""


def generate_summary_placeholder(
    meeting_content: str,
    memory_context: str = "",
) -> str:
    """Create a deterministic mock summary without calling an LLM."""
    clean_content = meeting_content.strip()
    has_memory = bool(memory_context) and "暂无已确认项目记忆" not in memory_context
    context_note = "已参考当前项目记忆。" if has_memory else "未引用历史项目记忆。"
    if not clean_content:
        return f"本次会议暂无内容，待补充纪要。{context_note}"
    return f"Mock 会议纪要：{clean_content[:120]} {context_note}"
