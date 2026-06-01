"""AI Agent module for flight price monitoring.

Router + субагенты на LangGraph. ``graph`` — скомпилированный граф (точка входа
для ``langgraph dev`` и LangGraph Server). ``AgentFactory`` — совместимость со
старым CLI/TUI.
"""

from aviatrade.agent.agent import AgentFactory
from aviatrade.agent.graph import graph

__all__ = ["AgentFactory", "graph"]
