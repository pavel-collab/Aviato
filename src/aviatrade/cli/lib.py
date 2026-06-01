"""Интерактивный режим CLI: диалог с агентом через LangGraph Server.

Скрапинг/визуализация/мониторинг вызываются в ``cli/main.py`` напрямую из
``shared.*``; здесь — только клиент агента (langgraph-sdk).
"""

__all__ = ["run_agent"]


def run_agent() -> None:
    """Run the AI agent interactively via the LangGraph server (langgraph-sdk).

    The CLI is a client of the agent service: it sends each message to the
    deployed graph over the SDK and prints the final answer. Start the server
    first (``uv run --project projects/agent --extra langgraph langgraph dev`` for
    local dev, or the ``agent`` docker service) and point ``langgraph.url`` in
    config.yaml at it.
    """
    from langgraph_sdk import get_sync_client

    from aviatrade.config import config

    print(f"\n{'=' * 60}")
    print("AI AGENT MODE")
    print(f"LangGraph server: {config.langgraph.url} (graph: {config.langgraph.graph_id})")
    print("Type 'exit' or 'quit' to leave agent mode")
    print(f"{'=' * 60}\n")

    try:
        client = get_sync_client(url=config.langgraph.url)
    except Exception as e:
        print(f"Error connecting to LangGraph server: {e}")
        return

    while True:
        try:
            user_input = input("Agent> ").strip()

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit"):
                print("Exiting agent mode")
                break

            thread = client.threads.create()
            result = client.runs.wait(
                thread["thread_id"],
                config.langgraph.graph_id,
                input={"messages": [{"role": "human", "content": user_input}]},
            )

            messages = result.get("messages", []) if isinstance(result, dict) else []
            if messages:
                last = messages[-1]
                content = last.get("content", "") if isinstance(last, dict) else str(last)
                print(f"\n{content}\n")
            else:
                print("\n(no response)\n")

        except KeyboardInterrupt:
            print("\n\nAgent mode interrupted")
            break
        except Exception as e:
            print(f"Error: {e}")
