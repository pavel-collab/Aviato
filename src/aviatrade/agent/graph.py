"""Агентный граф AviaTrade: router + субагенты.

Идея (по мотивам research-ассистента на LangGraph Server): запрос пользователя
сначала попадает в узел ``router``, который на базе ChatOpenAI решает, в какую
ветку его направить. Ветки — это не «голые» узлы, а самостоятельные субагенты
из subagents.py, собранные через create_agent. Мы вставляем их в граф как
обычные узлы и склеиваем условным ребром.

    START → router ──┬──→ analysis ─→ END   (анализ временных данных цен)
                     ├──→ charts   ─→ END   (построение диаграмм)
                     ├──→ ops      ─→ END   (scrape / watchlist / фоновый мониторинг)
                     └──→ chat     ─→ END   (общий вопрос, приветствие, уточнение)

Так получается «граф из агентов»: верхний уровень — ручная маршрутизация,
нижний — готовые ReAct-циклы внутри каждого субагента.

Runtime[Context]: граф скомпилирован с context_schema=Context, поэтому каждый
узел получает второй аргумент ``runtime: Runtime[Context]``. Системные промпты,
имя модели и температуры берутся из ``runtime.context`` (с откатом на дефолты).
Это позволяет подменять поведение (например, системный промпт) НА ЛЕТУ при
вызове графа, без перезапуска процесса.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from aviatrade.agent.state import Context, State
from aviatrade.agent.subagents import (
    DEFAULT_ANALYSIS_SYSTEM,
    DEFAULT_CHARTS_SYSTEM,
    DEFAULT_OPS_SYSTEM,
    make_analysis_agent,
    make_charts_agent,
    make_model,
    make_ops_agent,
)

# --- Узел router ------------------------------------------------------------
# Роутер использует structured output: модель обязана вернуть ровно одно из
# допустимых значений destination, а не свободный текст. Это надёжнее парсинга.


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


# --- Системные промпты по умолчанию (router и chat) -------------------------
# Дефолты для веток, которыми graph.py управляет напрямую. Любой можно
# переопределить через Context, не трогая код.

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

    # temperature=0 по умолчанию — классификация должна быть стабильной.
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


# --- Узлы-субагенты ---------------------------------------------------------
# Субагент возвращает ВСЮ историю (вход + новые сообщения). Чтобы не плодить
# дубликаты и вернуть в общий граф только то, что субагент добавил, отрезаем
# первые len(входных) сообщений. add_messages затем подмержит их в общую ленту.


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
    # temperature=0.7 по умолчанию — для чата нужна «живость».
    chat_llm = make_model(ctx.get("model"), ctx.get("chat_temperature", 0.7))
    system = ctx.get("chat_system") or DEFAULT_CHAT_SYSTEM
    response: AIMessage = await chat_llm.ainvoke(
        [SystemMessage(content=system), *state["messages"]]
    )
    return {"messages": [response]}


# --- Сборка графа -----------------------------------------------------------
# context_schema=Context включает Runtime[Context] для всех узлов.
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
