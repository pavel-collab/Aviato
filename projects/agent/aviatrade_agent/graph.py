"""Агентный граф AviaTrade: router + субагенты.

Запрос пользователя попадает в узел ``router``, который через ChatOpenAI решает,
в какую ветку его направить. Ветки — самостоятельные субагенты из subagents.py,
вставленные в граф как узлы.

    START → router ──┬──→ analysis ─→ END   (анализ временных данных цен)
                     ├──→ charts   ─→ END   (построение диаграмм)
                     ├──→ ops      ─→ END   (scrape / watchlist / фоновый мониторинг)
                     └──→ chat     ─→ END   (общий вопрос, приветствие, уточнение)

Runtime[Context]: граф скомпилирован с context_schema=Context, поэтому системные
промпты/модель/температуры берутся из ``runtime.context`` (с откатом на дефолты)
и подменяются на лету при вызове графа.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from aviatrade_agent.config import config
from aviatrade_agent.state import Context, State
from aviatrade_agent.subagents import (
    DEFAULT_ANALYSIS_SYSTEM,
    DEFAULT_CHARTS_SYSTEM,
    DEFAULT_OPS_SYSTEM,
    make_analysis_agent,
    make_charts_agent,
    make_model,
    make_ops_agent,
)
from shared.core import setup_logging

# Граф импортируется langgraph-api при старте — настраиваем логирование здесь,
# чтобы логи инструментов (shared.* через loguru) были видны в контейнере агента.
setup_logging(config.logging.level)


class RouterDecision(BaseModel):
    """Решение роутера: в какую ветку направить запрос."""

    destination: str = Field(
        description=(
            "Куда направить запрос. Одно из: "
            "'analysis' — проанализировать собранные цены, сделать выводы/рекомендацию; "
            "'charts' — построить график/диаграмму по ценам; "
            "'ops' — собрать данные (scrape), управлять отслеживаемыми маршрутами "
            "(watchlist) или запустить/остановить фоновый мониторинг; "
            "'chat' — всё остальное (общий вопрос, приветствие, уточнение)."
        )
    )


DEFAULT_ROUTER_SYSTEM = (
    "Ты — маршрутизатор ассистента по мониторингу цен на авиабилеты. По "
    "последнему сообщению пользователя определи нужную ветку и верни её в поле "
    "destination. Ничего не выполняй сам — только классифицируй."
)

DEFAULT_CHAT_SYSTEM = (
    "Ты — дружелюбный ассистент по мониторингу цен на авиабилеты (Aviasales). "
    "Отвечай кратко и по делу на русском. Если для ответа явно нужен сбор "
    "данных, анализ цен, график или управление отслеживанием — подскажи "
    "пользователю переформулировать запрос."
)


def _ctx(runtime: Runtime[Context]) -> Context:
    """Безопасно достать context: при вызове без него runtime.context == None."""
    return runtime.context or {}


async def router_node(state: State, runtime: Runtime[Context]) -> dict:
    """Классифицирует последнее сообщение и кладёт решение в state['route']."""
    ctx = _ctx(runtime)

    llm = make_model(ctx.get("model"), ctx.get("router_temperature", 0.0))

    router_llm = llm.with_structured_output(RouterDecision)
    system = ctx.get("router_system") or DEFAULT_ROUTER_SYSTEM

    last_message = state["messages"][-1]
    decision: RouterDecision = await router_llm.ainvoke(
        [SystemMessage(content=system), last_message]
    )
    route = (
        decision.destination
        if decision.destination in {"analysis", "charts", "ops", "chat"}
        else "chat"
    )
    return {"route": route}


def pick_route(state: State) -> str:
    """Функция-выбор для условного ребра: просто читает решение роутера."""
    return state["route"]


async def _run_subagent(agent, state: State) -> dict:
    incoming = state["messages"]
    result = await agent.ainvoke({"messages": incoming})
    new_messages = result["messages"][len(incoming):]
    return {"messages": new_messages}


async def analysis_node(state: State, runtime: Runtime[Context]) -> dict:
    ctx = _ctx(runtime)
    agent = make_analysis_agent(
        ctx.get("model"),
        ctx.get("subagent_temperature", 0.0),
        ctx.get("analysis_system") or DEFAULT_ANALYSIS_SYSTEM,
    )
    return await _run_subagent(agent, state)


async def charts_node(state: State, runtime: Runtime[Context]) -> dict:
    ctx = _ctx(runtime)
    agent = make_charts_agent(
        ctx.get("model"),
        ctx.get("subagent_temperature", 0.0),
        ctx.get("charts_system") or DEFAULT_CHARTS_SYSTEM,
    )
    return await _run_subagent(agent, state)


async def ops_node(state: State, runtime: Runtime[Context]) -> dict:
    ctx = _ctx(runtime)
    agent = make_ops_agent(
        ctx.get("model"),
        ctx.get("subagent_temperature", 0.0),
        ctx.get("ops_system") or DEFAULT_OPS_SYSTEM,
    )
    return await _run_subagent(agent, state)


async def chat_node(state: State, runtime: Runtime[Context]) -> dict:
    ctx = _ctx(runtime)
    chat_llm = make_model(ctx.get("model"), ctx.get("chat_temperature", 0.7))
    system = ctx.get("chat_system") or DEFAULT_CHAT_SYSTEM
    response: AIMessage = await chat_llm.ainvoke(
        [SystemMessage(content=system), *state["messages"]]
    )
    return {"messages": [response]}


# --- Сборка графа -----------------------------------------------------------
_builder = StateGraph(State, context_schema=Context)

_builder.add_node("router", router_node)
_builder.add_node("analysis", analysis_node)
_builder.add_node("charts", charts_node)
_builder.add_node("ops", ops_node)
_builder.add_node("chat", chat_node)

_builder.add_edge(START, "router")
_builder.add_conditional_edges(
    "router",
    pick_route,
    {
        "analysis": "analysis",
        "charts": "charts",
        "ops": "ops",
        "chat": "chat",
    },
)
_builder.add_edge("analysis", END)
_builder.add_edge("charts", END)
_builder.add_edge("ops", END)
_builder.add_edge("chat", END)

# Имя графа видно в LangGraph Studio и LangSmith.
graph = _builder.compile(name="AviaTrade Agent")
