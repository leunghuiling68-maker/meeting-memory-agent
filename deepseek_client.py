"""Minimal DeepSeek JSON client with deterministic mock fallback."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any


DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"
ENV_FILE = Path(__file__).resolve().parent / ".env"

Message = Mapping[str, str]
MockFallback = Any | Callable[[], Any]


def call_deepseek_json(
    messages: str | Sequence[Message],
    *,
    mock_fallback: MockFallback = None,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    max_tokens: int = 1200,
    timeout_seconds: int = 30,
) -> Any:
    """Call DeepSeek and parse the assistant response as JSON.

    If DEEPSEEK_API_KEY is missing, the request fails, or the response cannot be
    parsed as JSON, return ``mock_fallback`` instead.
    """
    api_key = _get_deepseek_api_key()
    if not api_key:
        return _resolve_mock_fallback(mock_fallback)

    payload = {
        "model": model,
        "messages": _normalize_messages(messages),
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }

    try:
        response_data = _post_json(
            DEEPSEEK_API_URL,
            payload,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )
        content = response_data["choices"][0]["message"]["content"]
        return _parse_json_content(content)
    except (KeyError, IndexError, TypeError, ValueError, urllib.error.URLError):
        return _resolve_mock_fallback(mock_fallback)


def _get_deepseek_api_key() -> str:
    """Read DEEPSEEK_API_KEY from the process env, then from local .env."""
    env_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if env_key:
        return env_key

    for key, value in _read_dotenv(ENV_FILE).items():
        os.environ.setdefault(key, value)

    return os.getenv("DEEPSEEK_API_KEY", "").strip()


def _read_dotenv(path: Path) -> dict[str, str]:
    """Read simple KEY=VALUE entries from .env without extra dependencies."""
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _normalize_messages(messages: str | Sequence[Message]) -> list[dict[str, str]]:
    if isinstance(messages, str):
        return [{"role": "user", "content": messages}]
    return [
        {
            "role": str(message.get("role", "user")),
            "content": str(message.get("content", "")),
        }
        for message in messages
    ]


def _post_json(
    url: str,
    payload: Mapping[str, Any],
    *,
    api_key: str,
    timeout_seconds: int,
) -> Any:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _parse_json_content(content: str) -> Any:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)


def _resolve_mock_fallback(mock_fallback: MockFallback) -> Any:
    if callable(mock_fallback):
        return mock_fallback()
    return mock_fallback
