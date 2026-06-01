"""Тонкая обёртка над langgraph-sdk — связка backend ↔ граф агента."""

from __future__ import annotations

from functools import lru_cache

from langgraph_sdk import get_client
from langgraph_sdk.client import LangGraphClient

from src.config import config

_ROLE_MAP = {"system": "system", "user": "human", "assistant": "ai"}


@lru_cache(maxsize=1)
def _client() -> LangGraphClient:
    """Один экземпляр клиента на процесс (httpx.AsyncClient с пулом keep-alive)."""
    return get_client(url=config.langgraph.url)


async def aclose_client() -> None:
    if _client.cache_info().currsize:
        await _client().http.client.aclose()
        _client.cache_clear()


def _coerce_content(content: object) -> str:
    if isinstance(content, list):
        parts = [
            p.get("text", "")
            for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        ]
        return "\n".join(parts)
    return content if isinstance(content, str) else str(content)


def _last_content(result: object) -> str:
    messages = result.get("messages", []) if isinstance(result, dict) else []
    if not messages:
        return ""
    last = messages[-1]
    return last.get("content", "") if isinstance(last, dict) else str(last)


async def run_graph_messages(messages: list[dict]) -> str:
    """Прогнать граф на полной истории (OpenAI-формат) и вернуть финальный ответ."""
    lc_messages = []
    for m in messages:
        role = _ROLE_MAP.get(m.get("role", ""))
        if role is None:
            continue
        lc_messages.append({"role": role, "content": _coerce_content(m.get("content", ""))})

    if not lc_messages:
        return ""

    client = _client()
    thread = await client.threads.create()
    result = await client.runs.wait(
        thread["thread_id"],
        config.langgraph.graph_id,
        input={"messages": lc_messages},
    )
    return _last_content(result)


async def run_graph(message: str) -> str:
    """Прогнать граф на одном сообщении (упрощённый путь /agent/chat, worker)."""
    return await run_graph_messages([{"role": "user", "content": message}])
