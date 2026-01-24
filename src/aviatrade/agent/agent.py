from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import ToolNode
from langgraph.graph import START, END, StateGraph, MessagesState
from typing import Optional

from aviatrade.agent.tool_wrappers import (
    scrape_and_save_tool,
    visualize_prices_tool,
    monitor_prices_tool,
    get_price_stats_tool
)

class AgentConfig:
    def __init__(self, model_name: str, api_key: str):
            try:
                    self.llm = ChatOpenAI(
                            model=model_name,
                            api_key=api_key,
                            base_url="https://openrouter.ai/api/v1", # using OpenRouter portal
                            temperature=0.0 # use temperature=0 for max determinate output
                    )
                    
                    self.supervisor = ChatOpenAI(
                            model=model_name,
                            api_key=api_key,
                            base_url="https://openrouter.ai/api/v1", # using OpenRouter portal
                            temperature=0.0 # use temperature=0 for max determinate output
                    )
            except Exception as ex:
                    print(f"-- ERROR!!! --\n{ex}")
                
                
class AgentState(MessagesState):
    '''
    Наследуем состояние агента из MessageState, которое автоматически содержит историб сообщений
    и функции для работы с ним.
    '''
    
    # дополнительно добавим максимальное количество итераций рефлексии и счетчик итераций
    max_reflection_iterations: int = 3
    reflection_iterations: int = 0
    need_reflection: bool = False
   
tools = [
        scrape_and_save_tool,
        visualize_prices_tool,
        monitor_prices_tool,
        get_price_stats_tool
]

SYSTEM_PROMPT = """You are an AI assistant for flight price monitoring on Aviasales.ru.
You help users scrape, analyze, and visualize flight prices.

Available tools:
- scrape_and_save_tool: Scrape flight data from Aviasales and save to database
- visualize_prices_tool: Generate price visualization charts
- monitor_prices_tool: Monitor prices at specified intervals (in minutes)
- get_price_stats_tool: Get price statistics for a specific route and date

Important:
- Always use IATA airport codes (e.g., MOW for Moscow, LED for Saint-Petersburg, AER for Sochi)
- Dates must be in YYYY-MM-DD format
- When the user asks about flight prices, use the appropriate tool based on their request

Answer in the same language as the user's question."""

def agent_node(state: AgentState, config: AgentConfig):
    llm = config.llm
    llm_with_tools = llm.bind_tools(tools)

    messages = state["messages"]

    # Add system prompt if not already present
    if not any(isinstance(m, SystemMessage) for m in messages):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)

    response = llm_with_tools.invoke(messages)
    
    model_reflection = bool(response.tool_calls)
    
    return {
            "messages": [response], # добавляем ответ модели в историю сообщений "messages
            "need_reflection": model_reflection,
            "reflection_iterations": state.get("reflection_iterations", 0) + 1
    }
        
def reflection_node(state: AgentState):
    messages = state["messages"]
    
    tool_messages = [message for message in messages if isinstance(message, ToolMessage)]
    print(f"-- DEBUG --\n\tTool messages {len(tool_messages)}")
    
    if tool_messages:
            last_tool_message = tool_messages[-1]
            print(f"-- DEBUG --\n\tLast tool message: {last_tool_message.content[:100]}...")
            
    reflection_message = HumanMessage(content="Проанализируй результаты работы модели, составь summary и дай ответ пользователю")
    return {
            "messages": [reflection_message]
    }

def supervisor_node(state: AgentState, config: AgentConfig):
    supervisor = config.supervisor
    messages = state["messages"]
    response = supervisor.invoke(messages)
    
    return {
            "messages": [response],
            "need_reflection": False # сбрасываем флаг рефлексии, если модель решила что-то сделать
    }
        
def router_node(state: AgentState):
    messages = state["messages"]
    last_message = messages[-1]
    
    iteration_count = state.get("reflection_iterations", 0)
    
    if iteration_count > state.max_reflection_iterations:
            return "end"
    
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
            return "tools"
    
    if state.get("need_reflection", False):
            return "reflection"
    
    return "end"
        

class AgentFactory:
    @staticmethod
    def build_agent(model_name: str="openai/gpt-oss-120b:free", api_key: Optional[str]=None):
        agent_config = AgentConfig(model_name=model_name, api_key=api_key)

        graph = StateGraph(AgentState)

        graph.add_node("agent", lambda state: agent_node(state, agent_config))
        graph.add_node("tools", ToolNode(tools))
        graph.add_node("reflection", reflection_node)
        graph.add_node("supervisor", lambda state: supervisor_node(state, agent_config))
        
        graph.add_edge(START, "agent")
        graph.add_conditional_edges(
                "agent",
                router_node,
                {
                        "tools": "tools",
                        "reflection": "reflection",
                        "end": END
                }
        )
        graph.add_edge("tools", "agent")
        graph.add_edge("reflection", "supervisor")
        graph.add_edge("supervisor", END)

        compiled_graph = graph.compile()
        return compiled_graph
    
    @staticmethod
    def draw_compiled_agent_schema(compiled_graph) -> None:
        """Draw and save the agent graph schema to a PNG file."""
        with open('determined_agent_scheme.png', 'wb') as f:
            f.write(compiled_graph.get_graph().draw_mermaid_png())
