# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AviaTrade is a Python flight price monitoring system for Aviasales.ru. It scrapes flight prices, stores them in TimescaleDB (PostgreSQL + time-series extension), and generates statistical visualizations for price trend analysis. It also includes an AI agent built as a **LangGraph router + subagents graph** (runnable via `langgraph dev` / LangGraph Server) that exposes price analysis, visualization, and operational tools (scraping, watchlist management, background monitoring).

## Commands

### Database Setup
```bash
docker-compose up -d  # Start the TimescaleDB container
```

The container runs TimescaleDB. On first start (empty volume) `initdb/01-init-timescaledb.sql`
runs automatically: it creates the `flight_prices` hypertable, daily chunks, and a
compression policy. To re-run it, reset the volume: `docker-compose down -v && docker-compose up -d`.

### Installation
The project is managed with `uv` (there is no `requirements.txt`):
```bash
# Create the environment and install all dependencies
uv sync

# Include dev tools (pytest, mypy, ruff)
uv sync --extra dev
```

### Running the Application
```bash
# Run via uv (no manual activation needed)
uv run aviatrade --origin MOW --destination LED --date 2025-12-15 --action scrape

# Or using the run.py entry point (for development)
uv run python run.py --origin MOW --destination LED --date 2025-12-15 --action scrape

# Visualize collected data
uv run aviatrade --origin MOW --destination LED --date 2025-12-15 --action visualize

# Continuous monitoring (interval in minutes)
uv run aviatrade --origin MOW --destination LED --date 2025-12-15 --action monitor --interval 30

# Scrape and visualize together
uv run aviatrade --origin MOW --destination LED --date 2025-12-15 --action both

# Interactive AI agent (requires OPENROUTER_API_KEY)
uv run aviatrade --action agent

# Interactive TUI
uv run aviatrade --tui
```

### Running the Agent Graph (LangGraph)
```bash
# Local dev server + LangGraph Studio (needs the venv on Python 3.11–3.13)
uv run --extra langgraph langgraph dev

# Production: LangGraph Server in Docker (langgraph-server service)
docker-compose up -d --build
```
The graph entrypoint is declared in `langgraph.json` (`aviatrade_agent` →
`src/aviatrade/agent/graph.py:graph`). The Docker image (`Dockerfile`) installs
Chromium so the ops subagent can scrape inside the container; the
`langgraph-server` service gets its own Postgres (`langgraph-postgres`) + Redis
for run-state, separate from the TimescaleDB that stores prices.

### Running the Backend (FastAPI + worker)
```bash
# Local (needs RabbitMQ + Redis reachable; the LangGraph server for /agent/chat):
uv run --extra backend uvicorn aviatrade.backend.main:app --reload   # API on :8000
uv run --extra backend python -m aviatrade.backend.worker            # queue consumer

# Full stack in Docker (TimescaleDB + LangGraph Server + RabbitMQ + backend + worker):
docker-compose up -d --build
```
The backend is the external REST API. Endpoints (see `/docs`): agent chat
(`POST /agent/chat` sync via SDK, `POST /agent/chat/async` → `GET /jobs/{id}`),
scraping (`POST /scrape` → queue → worker), stats (`GET /stats`), charts
(`POST /charts`), watchlist CRUD (`/watchlist`), background monitors
(`/monitors`), plus the OpenAI-compatible pair `GET /v1/models` and
`POST /v1/chat/completions` (consumed by OpenWebUI). Heavy work (scraping, graph
runs) goes through RabbitMQ to the `worker`; light work (stats, watchlist,
monitors) runs in-process.

### Frontend (OpenWebUI)
`docker-compose up -d --build` also starts **OpenWebUI** on
`http://localhost:3000`. It is wired to the backend's OpenAI-compatible API
(`OPENAI_API_BASE_URL=http://backend:8000/v1`) and configured purely via env
vars in `docker-compose.yml` (`WEBUI_AUTH=false` for instant access,
`DEFAULT_MODELS=aviatrade-agent`). Background AI task features are turned off
(`ENABLE_TITLE_GENERATION`, `ENABLE_FOLLOW_UP_GENERATION`,
`ENABLE_SEARCH_QUERY_GENERATION`, `ENABLE_TAGS_GENERATION`,
`ENABLE_AUTOCOMPLETE_GENERATION` = `false`) so the UI never sends hidden
`### Task:` LLM calls to the agent.

**Key design rule:** the agent graph does NOT call the backend. Its ops subagent
invokes the underlying functions (`cli.lib` / `db` / `MONITORS`) **directly**, so
the agent runs in dev (`langgraph dev`) without the backend up. The backend is a
parallel path to the same functions for external clients (see `backend/actions.py`).

## Project Structure

```
aviatrade/
├── src/
│   └── aviatrade/              # Main package
│       ├── __init__.py         # Package exports
│       ├── cli/                # Command-line interface
│       │   ├── __init__.py
│       │   └── main.py         # CLI entry point and commands
│       ├── core/               # Core configuration
│       │   ├── __init__.py
│       │   └── config.py       # Environment configuration
│       ├── backend/            # FastAPI backend (external REST API)
│       │   ├── __init__.py
│       │   ├── config.py       # pydantic-settings (rabbitmq/redis/langgraph URLs)
│       │   ├── mq.py           # RabbitMQ publish + Redis job store
│       │   ├── lg_client.py    # langgraph-sdk wrapper (agent chat, full history)
│       │   ├── actions.py      # adapter over cli.lib / db / MONITORS (JSON dicts)
│       │   ├── openai_api.py   # OpenAI-compatible /v1 router for OpenWebUI frontend
│       │   ├── worker.py       # RabbitMQ consumer (scrape / run_graph)
│       │   └── main.py         # FastAPI app + endpoints (mounts openai_api)
│       ├── agent/              # AI agent (LangGraph router + subagents)
│       │   ├── __init__.py     # exports `graph` + AgentFactory
│       │   ├── graph.py        # router node + subagent nodes → compiled `graph`
│       │   ├── subagents.py    # make_model + analysis/charts/ops agent factories
│       │   ├── state.py        # State (messages+route) + Context (Runtime config)
│       │   ├── tools.py        # @tool functions grouped per subagent
│       │   ├── monitoring.py   # BackgroundMonitorManager (non-blocking monitors)
│       │   └── agent.py        # AgentFactory shim (compat for CLI/TUI)
│       ├── db/                 # Database layer
│       │   ├── __init__.py
│       │   ├── models.py       # SQLAlchemy ORM models
│       │   └── database.py     # Database session management
│       ├── scraper/            # Web scraping
│       │   ├── __init__.py
│       │   └── aviasales.py    # Aviasales.ru scraper
│       └── visualization/      # Data visualization
│           ├── __init__.py
│           └── visualizer.py   # Chart generation
├── initdb/                     # TimescaleDB init scripts (run on first DB start)
│   └── 01-init-timescaledb.sql
├── configs/
│   └── .env.example            # Environment variables template
├── charts/                     # Output directory for generated charts
├── docker-compose.yml          # TimescaleDB + LangGraph Server + RabbitMQ + backend + worker + openwebui
├── Dockerfile                  # LangGraph Server image (+ Chromium for scraping)
├── Dockerfile.backend          # FastAPI backend + worker image (aviatrade pkg + Chromium)
├── langgraph.json              # Graph entrypoint for langgraph dev / Server
├── pyproject.toml              # Project metadata + dependencies (uv)
├── run.py                      # Development entry point
├── README.md
└── CLAUDE.md
```

## Architecture

### Component Flow
```
cli/main.py (CLI/Orchestration)
    → scraper/aviasales.py (Botasaurus browser)
    → db/database.py + db/models.py (SQLAlchemy ORM)
    → TimescaleDB (PostgreSQL hypertable)

cli/main.py
    → visualization/visualizer.py (matplotlib/seaborn)
    → /charts/*.png

cli/lib.py run_agent / tui  →  agent/agent.py (AgentFactory shim)
langgraph dev / Server      →  langgraph.json
    → agent/graph.py (router node → analysis/charts/ops/chat subagent nodes)
        → agent/subagents.py (create_agent factories, model/prompts from Runtime[Context])
            → agent/tools.py (wraps cli/lib.py functions as @tool, grouped per subagent)
            → agent/monitoring.py (BackgroundMonitorManager for non-blocking monitors)

backend/main.py (external REST API)
    → backend/actions.py → cli/lib.py + db + agent/monitoring.MONITORS  (direct, light ops)
    → backend/mq.py (RabbitMQ publish) → backend/worker.py (heavy ops)
            → scrape: backend/actions.run_scrape (Botasaurus)
            → chat:   backend/lg_client.run_graph → LangGraph Server (SDK)
    → backend/mq.py (Redis) stores job status/result → GET /jobs/{id}

OpenWebUI (frontend, :3000)
    → backend/openai_api.py (GET /v1/models, POST /v1/chat/completions, SSE)
        → backend/lg_client.run_graph_messages → LangGraph Server (SDK)

NB: the agent path and the backend path are INDEPENDENT. The agent never calls
the backend; both reuse the same execution layer (cli/lib, db, MONITORS).
```

### Key Components

- **core/config.py**: Loads PostgreSQL connection from `.env` file (supports both root and configs/ directory)
- **db/models.py**: `FlightPrice` SQLAlchemy ORM model
- **db/database.py**: `Database` class for session management and CRUD operations
- **scraper/aviasales.py**: `AviasalesScraper` uses Botasaurus browser automation with multi-selector CSS approach
- **visualization/visualizer.py**: `FlightPriceVisualizer` generates 4-panel analysis charts
- **cli/main.py**: CLI entry point with modes: scrape, visualize, monitor, both, agent (plus `--tui`)
- **agent/graph.py**: `StateGraph(State, context_schema=Context)` — a `router` node (structured output → analysis/charts/ops/chat) with subagent nodes; exported as `graph` and invoked with `{"messages": [...]}`
- **agent/subagents.py**: `make_model` (OpenRouter via `ChatOpenAI`) + `lru_cache`d `create_agent` factories per subagent; model/temperature/system prompts come from `runtime.context` (`Runtime[Context]`) so they can be hot-swapped per invocation / in LangGraph Studio
- **agent/monitoring.py**: `BackgroundMonitorManager` runs continuous monitoring in daemon threads (non-blocking) so the graph never hangs; ops tools start/stop/list monitors
- **agent/agent.py**: `AgentFactory.build_agent` is a thin compat shim returning the compiled `graph` (keeps CLI `run_agent` and the TUI working unchanged)
- **backend/main.py**: FastAPI app exposing the actions (scrape/stats/charts/watchlist/monitors) and agent chat as REST endpoints; heavy work is enqueued to RabbitMQ, light work runs in-process via `run_in_threadpool`
- **backend/actions.py**: thin adapter calling the same execution layer as the agent (`cli.lib`, `db`, `MONITORS`) but returning JSON-friendly dicts — keeps the backend and agent paths independent
- **backend/worker.py**: RabbitMQ consumer; `scrape` jobs → `actions.run_scrape`, `chat` jobs → `lg_client.run_graph` (graph via langgraph-sdk); results stored in Redis under `job_id`
- **backend/openai_api.py**: OpenAI-compatible router (`GET /v1/models`, `POST /v1/chat/completions` with SSE streaming) so OpenWebUI can talk to the agent; proxies the full chat history into the graph via `run_graph_messages`; guards against OpenWebUI service requests (`### Task:` prefix) to avoid burning tokens
- **backend/mq.py / lg_client.py / config.py**: RabbitMQ+Redis job plumbing, langgraph-sdk client (`run_graph` / `run_graph_messages`), and pydantic-settings (mirrors the langgraph-research-assistant reference backend)
- **OpenWebUI (`openwebui` service)**: chat frontend on `:3000`; configured entirely via env vars (connects to `http://backend:8000/v1`, `WEBUI_AUTH=false`, `DEFAULT_MODELS=aviatrade-agent`). All background AI task features (title/follow-up/search-query/tags/autocomplete generation) are disabled so OpenWebUI does not send hidden LLM calls to the agent — see the `concepts/openwebui-service-message-isolation` note in the Obsidian KB

### Tech Stack
- **Botasaurus**: Selenium-like browser automation for web scraping
- **SQLAlchemy + psycopg2**: PostgreSQL ORM
- **matplotlib/seaborn/pandas**: Data visualization and analysis
- **LangGraph (`StateGraph` + `Runtime[Context]`) + LangChain `create_agent` + langchain-openai**: router/subagents agent over OpenRouter, runnable via `langgraph dev` / LangGraph Server
- **FastAPI + uvicorn + aio-pika (RabbitMQ) + redis + langgraph-sdk**: external REST backend with an async worker, talking to the agent graph over the SDK (installed via the `backend` extra)
- **Docker Compose**: TimescaleDB container (PostgreSQL 16 + time-series extension) + LangGraph Server (own Postgres/Redis) + RabbitMQ + backend + worker
- **uv**: dependency and environment management

### Database Schema
The `flight_prices` table stores: origin, destination, departure_date, airline, flight_number, departure_time, arrival_time, duration, price, currency, stops, scraped_at. Indexes exist on origin, destination, departure_date, and scraped_at. It is a TimescaleDB **hypertable** partitioned on `scraped_at` (daily chunks); `scraped_at` is part of the composite primary key `(id, scraped_at)` because the partition column must be in any PK/unique constraint.

## Development Notes

- Scraper uses multi-selector CSS queries to handle Aviasales UI changes
- Price extraction uses regex patterns for Russian ruble symbols
- Results are limited to first 20 flights per scrape
- Charts are saved to `/charts` directory with timestamps
- `flight_prices` is a TimescaleDB hypertable; chunking and compression are set up automatically by `initdb/01-init-timescaledb.sql` on first DB start
- The agent requires `OPENROUTER_API_KEY` (and optional `MODEL_NAME`, default `openai/gpt-4o-mini`) in the environment
- Configuration supports `.env` in both project root and `configs/` directory

## Common IATA Codes
MOW (Moscow), LED (Saint-Petersburg), SVX (Yekaterinburg), KZN (Kazan), OVB (Novosibirsk), AER (Sochi)
