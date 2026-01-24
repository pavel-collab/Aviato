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

SYSTEM_PROMPT = """You are an advanced AI assistant for flight price monitoring and analysis on Aviasales.ru.
You help users scrape, analyze, and visualize flight prices using available tools.

## Available Tools

1. **scrape_and_save_tool(origin, destination, departure_date)**
   - Scrapes current flight data from Aviasales and saves to database
   - Use when user wants to collect fresh price data

2. **visualize_prices_tool(origin, destination, departure_date)**
   - Generates visual price charts from stored data
   - Use when user wants to see graphs or visual representation

3. **monitor_prices_tool(origin, destination, departure_date, interval_minutes)**
   - Continuously monitors prices at specified intervals
   - Use only when user explicitly asks for continuous monitoring

4. **get_price_stats_tool(origin, destination, departure_date)**
   - Returns detailed price statistics: min/max/avg prices, airline breakdown, price trends
   - Use when user asks for analysis, statistics, or price recommendations
   - IMPORTANT: Returns structured data that you should analyze and explain to the user

## IATA City Codes (use these exactly)
- MOW = Moscow (all airports)
- LED = Saint-Petersburg
- AER = Sochi
- SVX = Yekaterinburg
- KZN = Kazan
- OVB = Novosibirsk

## How to Handle Complex Requests

When user asks for analysis or recommendations:
1. **First**, identify what data is needed (route, date)
2. **Then**, call get_price_stats_tool to get the statistics
3. **Finally**, analyze the returned data and provide insights:
   - Price trends (is it getting cheaper or more expensive?)
   - Best airlines by price
   - Recommendations on when to buy
   - Comparison of different options

## Important Rules
- Dates must be in YYYY-MM-DD format
- If no data exists in database, suggest using scrape_and_save_tool first
- When analyzing prices, consider: minimum price, average price, price variance, airline differences
- Provide actionable recommendations based on the data
- Answer in the same language as the user's question

## Example Reasoning

User: "Проанализируй цены на билеты Москва-Сочи на 15 июня 2025"

Your approach:
1. Extract parameters: origin=MOW, destination=AER, date=2025-06-15
2. Call get_price_stats_tool to get statistics
3. Analyze the returned data:
   - What is the minimum price?
   - What is the average? Is there high variance?
   - Which airlines are cheapest?
   - Are prices stable or changing?
4. Provide a clear recommendation with reasoning"""

def agent_node(state: AgentState, config: AgentConfig):
    """Main agent node that processes messages and decides on actions."""
    llm = config.llm
    llm_with_tools = llm.bind_tools(tools)

    messages = list(state["messages"])

    # Add system prompt if not already present
    if not any(isinstance(m, SystemMessage) for m in messages):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages

    # Invoke the LLM
    response = llm_with_tools.invoke(messages)

    # Check if we made tool calls (for tracking iterations)
    made_tool_calls = bool(response.tool_calls)

    return {
        "messages": [response],
        "need_reflection": made_tool_calls,
        "reflection_iterations": state.get("reflection_iterations", 0) + (1 if made_tool_calls else 0)
    }


def analysis_node(state: AgentState, config: AgentConfig):
    """Analysis node that interprets tool results and provides insights.

    This node is called after tools have been executed to help the agent
    synthesize the results into a coherent analysis for the user.
    """
    llm = config.llm
    messages = list(state["messages"])

    # Find the last tool message to understand what data we have
    tool_messages = [m for m in messages if isinstance(m, ToolMessage)]

    if not tool_messages:
        # No tool results to analyze, skip
        return {"messages": []}

    last_tool_result = tool_messages[-1].content

    # Add analysis guidance if we have substantial data
    if len(last_tool_result) > 500:  # Likely contains statistics
        analysis_prompt = HumanMessage(content="""Based on the data above, please provide:
1. A clear summary of the key findings
2. Specific recommendations for the user
3. Answer in the same language as the original user question

Be concise but insightful. Focus on actionable advice.""")

        messages.append(analysis_prompt)

        # Get analysis from LLM (without tools, pure analysis)
        response = llm.invoke(messages)

        return {
            "messages": [response],
            "need_reflection": False
        }

    return {"messages": []}


def router_node(state: AgentState):
    """Route to appropriate next node based on current state."""
    messages = state["messages"]

    if not messages:
        return "end"

    last_message = messages[-1]
    iteration_count = state.get("reflection_iterations", 0)
    max_iterations = state.get("max_reflection_iterations", 3)

    # Safety limit on iterations
    if iteration_count >= max_iterations:
        print(f"-- DEBUG: Max iterations ({max_iterations}) reached, ending --")
        return "end"

    # If last message is AI with tool calls, execute tools
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"

    # If last message is a tool result, go back to agent for analysis
    if isinstance(last_message, ToolMessage):
        return "agent"

    # AI message without tool calls = final answer
    if isinstance(last_message, AIMessage) and not last_message.tool_calls:
        return "end"

    return "end"
        

class AgentFactory:
    """Factory for building the AI agent graph."""

    @staticmethod
    def build_agent(model_name: str = "openai/gpt-4o-mini", api_key: Optional[str] = None):
        """Build and compile the agent graph.

        Args:
            model_name: OpenRouter model name (default: gpt-4o-mini for reliability)
            api_key: OpenRouter API key

        Returns:
            Compiled LangGraph agent ready for invocation
        """
        agent_config = AgentConfig(model_name=model_name, api_key=api_key)

        graph = StateGraph(AgentState)

        # Add nodes
        graph.add_node("agent", lambda state: agent_node(state, agent_config))
        graph.add_node("tools", ToolNode(tools))

        # Define edges
        # START -> agent: Begin with the agent
        graph.add_edge(START, "agent")

        # agent -> router: Decide what to do next
        graph.add_conditional_edges(
            "agent",
            router_node,
            {
                "tools": "tools",  # If tool calls, execute them
                "agent": "agent",  # Continue processing (after tool results)
                "end": END         # No more actions, end
            }
        )

        # tools -> router: After tools, check what to do
        graph.add_conditional_edges(
            "tools",
            router_node,
            {
                "agent": "agent",  # Go back to agent to analyze results
                "tools": "tools",  # More tools (rare)
                "end": END         # Done
            }
        )

        compiled_graph = graph.compile()
        return compiled_graph

    @staticmethod
    def draw_compiled_agent_schema(compiled_graph) -> None:
        """Draw and save the agent graph schema to a PNG file."""
        with open('agent_graph_schema.png', 'wb') as f:
            f.write(compiled_graph.get_graph().draw_mermaid_png())
