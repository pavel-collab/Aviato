"""Совместимость: оркестрация переехала в shared.* (фаза 4).

Этот модуль оставлен тонким шимом до фазы 9. Функции скрапинга/визуализации/
мониторинга теперь живут в ``shared.services`` и ``shared.analytics``; здесь —
их ре-экспорт со старыми сигнатурами, плюс интерактивный ``run_agent`` (переедет
в projects/cli на фазе 5).
"""

from shared.core.settings import RabbitMQSettings, ScraperSettings

from shared.analytics import visualize_prices
from shared.services import monitor_route
from shared.services import monitor_watchlist as _monitor_watchlist
from shared.services import scrape_and_save_local as scrape_and_save

__all__ = [
    "scrape_and_save",
    "visualize_prices",
    "monitor_prices",
    "monitor_watchlist",
    "run_agent",
]


def monitor_prices(origin, destination, departure_date, db, interval_minutes=60):
    """Старая сигнатура CLI: один маршрут, блокирующий мониторинг (через shared)."""
    monitor_route(
        origin,
        destination,
        departure_date,
        db,
        scraper=ScraperSettings(),
        rabbitmq=RabbitMQSettings(),
        interval_minutes=interval_minutes,
    )


def monitor_watchlist(db, default_interval_minutes=60, pause_between_routes=5):
    """Старая сигнатура CLI: блокирующий мониторинг watchlist (через shared)."""
    _monitor_watchlist(
        db,
        scraper=ScraperSettings(),
        rabbitmq=RabbitMQSettings(),
        default_interval_minutes=default_interval_minutes,
        pause_between_routes=pause_between_routes,
    )


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
