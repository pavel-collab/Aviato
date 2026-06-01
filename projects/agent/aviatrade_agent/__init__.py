"""aviatrade_agent — агентный граф AviaTrade (router + субагенты).

``graph`` — скомпилированный граф, точка входа для ``langgraph dev`` и
LangGraph Server (см. langgraph.json).
"""

from aviatrade_agent.graph import graph

__all__ = ["graph"]
