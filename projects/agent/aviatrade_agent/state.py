"""Состояние и контекст агентного графа AviaTrade.

В LangGraph «состояние» (State) — это словарь, который путешествует между
узлами. Каждый узел получает его на вход и возвращает частичное обновление
(patch), которое LangGraph применяет к общему состоянию. Поле ``messages``
помечено редьюсером ``add_messages``: новые сообщения не затирают историю, а
аккуратно добавляются к ней (с дедупликацией по id).

«Контекст» (Context) — это НЕИЗМЕНЯЕМАЯ на время прогона конфигурация, которую
передают на этапе ВЫЗОВА графа (а не копят в State). Узлы получают её как
``runtime.context`` благодаря тому, что граф скомпилирован с
``context_schema=Context``. Так один и тот же скомпилированный граф можно
вызывать с разными системными промптами/моделью без перезапуска процесса —
конфиг едет рядом с запросом.
"""

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import Field

# Куда роутер может направить запрос. Эти же строки служат именами узлов в графе.
Route = Literal["analysis", "charts", "ops", "chat"]


class State(TypedDict):
    """Состояние, общее для всего агентного графа AviaTrade."""

    # История сообщений диалога. add_messages — редьюсер: добавляет, а не заменяет.
    messages: Annotated[list[AnyMessage], add_messages]

    # Решение роутера: имя ветки, в которую уйдёт запрос на этом шаге.
    # Поле всегда выставляет узел router.
    route: Route


class Context(TypedDict, total=False):
    """Конфигурация графа, передаваемая на этапе ВЫЗОВА (а не в State).

    State — изменяемая «память» (копится через узлы), а Context — неизменяемые
    на время прогона параметры: системные промпты, имя модели, температуры.
    Узлы получают его как ``runtime.context`` (см. graph.py).

    Все поля опциональны (total=False): если поле не задано, узел берёт
    встроенный дефолт.

    Пример вызова:
        graph.ainvoke(
            {"messages": [...]},
            context={"chat_system": "Ты — строгий аналитик.", "model": "openai/gpt-4o"},
        )
    """

    # Имя модели; None/нет ключа → берётся из config.llm.model (YAML).
    # Метка __template_metadata__ kind=llm подсказывает Studio показать селектор
    # модели для этого поля.
    #
    # ВАЖНО: метаданные обязательно через pydantic.Field(json_schema_extra=...).
    # Схему контекста из TypedDict строит Pydantic, и плоский dict внутри
    # Annotated он игнорирует — ключи не попадут в JSON-схему, и Studio их не
    # увидит. Только json_schema_extra доезжает.
    model: Annotated[
        str, Field(json_schema_extra={"__template_metadata__": {"kind": "llm"}})
    ]

    # Температуры по веткам (у роутера нужна стабильность, у чата — «живость»).
    router_temperature: float
    chat_temperature: float
    subagent_temperature: float

    # Системные промпты по веткам. Это и есть «горячая» подмена поведения.
    #
    # Метаданные включают вкладку Prompts в LangGraph Studio:
    #   - langgraph_type="prompt" — поле редактируется как промпт в UI;
    #   - langgraph_nodes=[...]   — какие узлы графа используют этот промпт.
    # Имена узлов должны совпадать с add_node(...) в graph.py.
    router_system: Annotated[
        str,
        Field(
            json_schema_extra={"langgraph_type": "prompt", "langgraph_nodes": ["router"]}
        ),
    ]
    chat_system: Annotated[
        str,
        Field(
            json_schema_extra={"langgraph_type": "prompt", "langgraph_nodes": ["chat"]}
        ),
    ]
    analysis_system: Annotated[
        str,
        Field(
            json_schema_extra={
                "langgraph_type": "prompt",
                "langgraph_nodes": ["analysis"],
            }
        ),
    ]
    charts_system: Annotated[
        str,
        Field(
            json_schema_extra={"langgraph_type": "prompt", "langgraph_nodes": ["charts"]}
        ),
    ]
    ops_system: Annotated[
        str,
        Field(
            json_schema_extra={"langgraph_type": "prompt", "langgraph_nodes": ["ops"]}
        ),
    ]
