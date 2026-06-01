"""OpenAI-совместимый API для фронтенда OpenWebUI.

OpenWebUI берёт ``OPENAI_API_BASE_URL`` и дёргает ``GET /v1/models`` и
``POST /v1/chat/completions`` (со стримингом). Здесь мы их реализуем и проксируем
диалог в граф агента через ``lg_client`` (LangGraph SDK).

Граф не стримит токены, поэтому ответ формируется целиком и отдаётся одним SSE-
чанком. Служебные запросы OpenWebUI (``### Task:``) до агента не доходят (чтобы не
жечь токены) — их фичи также выключены через env сервиса openwebui.
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

from src.lg_client import run_graph_messages

router = APIRouter(tags=["openai"])

MODEL_ID = "aviatrade-agent"
_TASK_PREFIX = "### Task:"


class ChatMessage(BaseModel):
    role: str
    content: Any = ""
    model_config = ConfigDict(extra="ignore")


class ChatCompletionRequest(BaseModel):
    model: str = MODEL_ID
    messages: list[ChatMessage] = Field(default_factory=list)
    stream: bool = False
    model_config = ConfigDict(extra="ignore")


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


def _is_service_request(messages: list[ChatMessage]) -> bool:
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
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _stream_response(answer: str, model: str) -> AsyncIterator[str]:
    cid = f"chatcmpl-{uuid4().hex}"
    created = int(time.time())
    base = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": model}

    yield _sse({**base, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]})
    if answer:
        yield _sse({**base, "choices": [{"index": 0, "delta": {"content": answer}, "finish_reason": None}]})
    yield _sse({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
    yield "data: [DONE]\n\n"


@router.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
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
