"""Совместимость со старым API сборки агента.

Раньше здесь жил плоский ReAct-агент (create_agent с общим списком инструментов).
Теперь агент переработан в полноценный граф router + субагенты (см. graph.py).

Этот модуль оставлен тонким shim'ом, чтобы не ломать существующие точки вызова
в CLI (cli/lib.py:run_agent) и TUI (cli/tui/app.py): они вызывают
``AgentFactory.build_agent(...)`` и затем ``graph.invoke({"messages": [...]})``.
Скомпилированный граф имеет тот же интерфейс {"messages": [...]} →
{"messages": [...]}, поэтому достаточно вернуть его.

Модель и ключ API теперь берутся из окружения (OPENROUTER_API_KEY, MODEL_NAME)
внутри узлов графа через Context/make_model, поэтому аргументы build_agent
сохранены лишь для обратной совместимости и игнорируются.
"""

from aviatrade.agent.graph import graph


class AgentFactory:
    """Factory for building the AI agent graph (compat wrapper)."""

    @staticmethod
    def build_agent(model_name: str | None = None, api_key: str | None = None):
        """Вернуть скомпилированный граф router + субагенты.

        Args:
            model_name: игнорируется (модель берётся из MODEL_NAME/Context).
            api_key: игнорируется (ключ берётся из OPENROUTER_API_KEY).

        Returns:
            Скомпилированный LangGraph-граф, совместимый с .invoke/.ainvoke
            по интерфейсу {"messages": [...]}.
        """
        return graph

    @staticmethod
    def draw_compiled_agent_schema(compiled_graph=None) -> None:
        """Draw and save the agent graph schema to a PNG file."""
        target = compiled_graph if compiled_graph is not None else graph
        with open("agent_graph_schema.png", "wb") as f:
            f.write(target.get_graph().draw_mermaid_png())
