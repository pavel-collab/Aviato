from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from langgraph.prebuilt import ToolNode
from langgraph.graph import START, END, StateGraph, MessagesState
import os
from typing import Optional

from tool_wrappers import scrape_and_save_tool, visualize_prices_tool, monitor_prices_tool, get_price_stats_tool

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
        monitor_prices_tool
]

def agent_node(state: AgentState, config: AgentConfig):
    llm = config.llm
    llm_with_tools = llm.bind_tools(tools)
    
    messages = state["messages"]
    
    response = llm_with_tools.invoke(messages)
    
    model_reflection = bool(response.tool_calls)
    
    return {
            "messages": [response], # добавляем ответ модели в историю сообщений "messages
            "need_reflection": model_reflection,
            "reflection_iteration": state.get("reflection_iteration", 0) + 1
    }
        
def reflection_node(state: AgentState):
    messages = state["messages"]
    
    tool_messages = [message for message in messages if isinstance(message, ToolMessage)]
    print(f"-- DEBUG --\n\tTool messages {len(tool_messages)}")
    
    if tool_messages:
            last_tool_message = tool_messages[-1]
            print(f"-- DEBUG --\n\tLast tool message: {last_tool_message[:100]}...")
            
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
        agent_config = AgentConfig(model_name="openai/gpt-oss-120b:free", api_key=api_key)

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
        
        compiled_graph = graph.compile()
        return compiled_graph
    
    #! Нарушение принципа единой ответственности для класса
    @staticmethod
    def draw_compiled_agent_schema(compiled_graph) -> None:
        with open('determined_agent_scheme.png', 'wb') as f:
            f.write(compiled_graph.get_graph().draw_mermaid_png())

if __name__ == "__main__":
    load_dotenv()
    api_key = os.getenv("OPENROUTER_API_KEY")

    compiled_graph = AgentFactory.build_agent(
            model_name="openai/gpt-oss-120b:free",
            api_key=api_key
    )
    
    user_input = input(f"Input your prompt: ")
    initial_graph_state = AgentState(
            messages=[HumanMessage(content=user_input)],
            max_reflection_iterations=3,
            reflection_iterations=0
    )
    
    final_state = compiled_graph.invoke(initial_graph_state)
    for i, msg in enumerate(final_state["messages"]):
            print(f"-- Message {i} --\n{msg.content}")
