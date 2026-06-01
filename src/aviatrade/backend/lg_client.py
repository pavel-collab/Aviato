"""Тонкая обёртка над ``langgraph-sdk`` — связка backend ↔ граф агента.

Backend НЕ импортирует код графа для общения с агентом, а ходит к развёрнутому
LangGraph Server (сервис ``langgraph-server``) по сети через официальный SDK.
Сервер сам поднимает REST API над скомпилированным графом ``aviatrade_agent``,
а мы лишь создаём поток (thread) и запускаем run.

Это путь для ДИАЛОГА с агентом (POST /agent/chat). Прикладные же действия
(скрапинг, watchlist, мониторинг) backend выполняет напрямую через
``backend.actions`` — мимо графа.
"""

from __future__ import annotations

from functools import lru_cache

from langgraph_sdk import get_client
from langgraph_sdk.client import LangGraphClient

from .config import settings


@lru_cache(maxsize=1)
def _client() -> LangGraphClient:
    """Один экземпляр клиента на процесс (внутри — httpx.AsyncClient с пулом).

    Ленивое создание гарантирует, что httpx-клиент инициализируется уже внутри
    работающего event loop — и backend, и worker живут каждый в одном loop весь
    свой срок, поэтому один общий клиент безопасен.
    """
    return get_client(url=settings.langgraph_url)


async def aclose_client() -> None:
    """Закрыть внутренний httpx.AsyncClient. Зовётся на остановке процесса."""
    if _client.cache_info().currsize:  # клиент вообще создавали?
        await _client().http.client.aclose()
        _client.cache_clear()


# OpenAI-роли → роли сообщений LangChain/LangGraph. Прочие роли (tool и т.п.)
# в граф не передаём — он работает с диалогом human/ai.
_ROLE_MAP = {"system": "system", "user": "human", "assistant": "ai"}


def _coerce_content(content: object) -> str:
    """Привести content к строке: OpenAI допускает список частей (мультимодал)."""
    if isinstance(content, list):
        parts = [
            p.get("text", "")
            for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        ]
        return "\n".join(parts)
    return content if isinstance(content, str) else str(content)


def _last_content(result: object) -> str:
    """Достать текст финального сообщения из результата графа."""
    messages = result.get("messages", []) if isinstance(result, dict) else []
    if not messages:
        return ""
    last = messages[-1]
    return last.get("content", "") if isinstance(last, dict) else str(last)


async def run_graph_messages(messages: list[dict]) -> str:
    """Прогнать граф на ПОЛНОЙ истории диалога (OpenAI-формат) и вернуть ответ.

    Каждый прогон — новый thread: историю целиком присылает клиент (OpenWebUI), а
    не persistent-checkpointer сервера. Так нет загрязнения состояния между
    запросами и не нужен chat_id. Роутер графа смотрит только на последнее
    сообщение, субагенты получают весь контекст.
    """
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
        settings.graph_id,
        input={"messages": lc_messages},
    )
    return _last_content(result)


async def run_graph(message: str) -> str:
    """Прогнать граф агента на ОДНОМ сообщении (упрощённый путь /agent/chat, worker).

    ``runs.wait`` создаёт run и блокируется до его завершения — синхронный вызов
    с точки зрения backend. Внутри же LangGraph Server всё равно проводит run
    через свою Redis-очередь и Postgres-чекпоинты.
    """
    return await run_graph_messages([{"role": "user", "content": message}])
