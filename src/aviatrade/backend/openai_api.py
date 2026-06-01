"""OpenAI-совместимый API для фронтенда OpenWebUI.

OpenWebUI умеет общаться с любым backend, который реализует «OpenAI-интерфейс»:
он берёт ``OPENAI_API_BASE_URL`` и дёргает у него ``GET /v1/models`` (список
моделей для выпадашки) и ``POST /v1/chat/completions`` (сам диалог, обычно со
стримингом). Здесь мы реализуем ровно эти две ручки и проксируем диалог в граф
агента AviaTrade через ``lg_client`` (LangGraph SDK).

Схема (см. базу знаний — Architect Copilot):

    OpenWebUI → POST /v1/chat/completions → run_graph_messages (SDK) → граф
              ← SSE-стрим (chat.completion.chunk) ←

Граф у нас не стримит токены (router → субагент → ответ), поэтому ответ
формируется целиком, а затем отдаётся одним SSE-чанком контента. Для OpenWebUI
этого достаточно.

Защита токенов: служебные AI-запросы OpenWebUI (авто-тайтл, follow-up, web-search
query, теги) ОТКЛЮЧЕНЫ через переменные окружения сервиса openwebui (см.
docker-compose). На случай, если что-то всё же просочится, здесь есть страховка:
сообщения с префиксом ``### Task:`` не доходят до агента (возвращаем пустой ответ),
чтобы не жечь токены и не засорять сессию.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from .lg_client import run_graph_messages

router = APIRouter(tags=["openai"])

# Единственная «модель», которую видит OpenWebUI, — это весь агентный граф.
MODEL_ID = "aviatrade-agent"

# Префикс служебных запросов OpenWebUI (title/follow-up/tags/search query).
_TASK_PREFIX = "### Task:"


# ===========================================================================
# Модели запроса/ответа (OpenAI Chat Completions)
# ===========================================================================
class ChatMessage(BaseModel):
    role: str
    # content бывает строкой или списком частей (мультимодальный формат) —
    # приведём к строке в lg_client._coerce_content.
    content: Any = ""
    model_config = ConfigDict(extra="ignore")


class ChatCompletionRequest(BaseModel):
    model: str = MODEL_ID
    messages: list[ChatMessage] = Field(default_factory=list)
    stream: bool = False
    # OpenWebUI шлёт кучу доп-полей (chat_id, session_id, tool_ids, files…) —
    # игнорируем их, чтобы валидация не падала.
    model_config = ConfigDict(extra="ignore")


# ===========================================================================
# GET /v1/models — список моделей для выпадашки OpenWebUI
# ===========================================================================
@router.get("/v1/models")
async def list_models() -> dict:
    return {
        "object": "list",
        "data": [
            {
                "id": MODEL_ID,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "aviatrade",
            }
        ],
    }


# ===========================================================================
# POST /v1/chat/completions — диалог с агентом
# ===========================================================================
def _is_service_request(messages: list[ChatMessage]) -> bool:
    """True, если последний запрос — служебный (### Task:) от OpenWebUI."""
    if not messages:
        return True
    last = messages[-1]
    content = last.content if isinstance(last.content, str) else ""
    return content.lstrip().startswith(_TASK_PREFIX)


def _completion_response(answer: str, model: str) -> dict:
    return {
        "id": f"chatcmpl-{uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": answer},
                "finish_reason": "stop",
            }
        ],
        # Токены не считаем (граф ходит через OpenRouter сам) — отдаём нули.
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _stream_response(answer: str, model: str) -> AsyncIterator[str]:
    """Отдать готовый ответ в формате потоковых chat.completion.chunk."""
    cid = f"chatcmpl-{uuid4().hex}"
    created = int(time.time())
    base = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": model}

    # 1) чанк с ролью, 2) чанк с контентом, 3) финальный чанк, 4) [DONE].
    yield _sse({**base, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]})
    if answer:
        yield _sse({**base, "choices": [{"index": 0, "delta": {"content": answer}, "finish_reason": None}]})
    yield _sse({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
    yield "data: [DONE]\n\n"


@router.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    # Страховка от служебных запросов OpenWebUI: не дёргаем агента, не жжём токены.
    if _is_service_request(req.messages):
        answer = ""
    else:
        answer = await run_graph_messages([m.model_dump() for m in req.messages])

    if req.stream:
        return StreamingResponse(
            _stream_response(answer, req.model),
            media_type="text/event-stream",
        )
    return _completion_response(answer, req.model)
