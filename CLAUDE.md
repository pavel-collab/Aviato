# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AviaTrade is a flight price monitoring system for Aviasales.ru. It scrapes flight
prices, stores them in TimescaleDB (PostgreSQL + time-series extension), and
generates statistical visualizations. It includes an AI agent (a **LangGraph
router + subagents graph**) exposing price analysis, charts, and operational
tools (scraping, watchlist, background monitoring), and a **FastAPI backend** with
an OpenAI-compatible API consumed by an **OpenWebUI** frontend.

The repo is a **`uv` workspace monorepo** (modeled on `retrieval-experiments`):
shared libraries in `shared/*`, deployable services in `projects/*`, and
self-contained manual-testing scripts in `scripts/`. The workspace root is a
non-package (`package = false`) — it ships no code of its own.

## Layout

```
AviaTrade/
├── pyproject.toml            # workspace root (package = false; deps for scripts/)
├── uv.lock                   # committed (Dockerfiles build with --frozen)
├── config.example.yaml       # config template (copy to config.yaml; gitignored)
├── docker-compose.yml
├── initdb/01-init-timescaledb.sql
├── scripts/                  # self-contained manual-testing scripts: cli.py, _settings.py
│
├── shared/                   # installable libraries (package name shared.<name>)
│   ├── core/      shared/core/{settings.py, logging.py}      # pydantic-settings YAML base + models
│   ├── db/        shared/db/{models.py, database.py}         # SYNC SQLAlchemy (FlightPrice, Watchlist, Database)
│   ├── scraper/   shared/scraper/{aviasales.py, schemas.py}  # botasaurus scraper + ScrapeTask
│   ├── analytics/ shared/analytics/{visualizer.py, stats.py, charts.py}  # matplotlib + stats
│   └── services/  shared/services/{scraping.py, monitoring.py, db_factory.py}  # use-cases (no matplotlib)
│
└── projects/                 # deployable services
    ├── scraper/  src/{__main__,app,consumer,config}.py + Dockerfile   # RabbitMQ consumer (the only Chromium image)
    ├── agent/    aviatrade_agent/{graph,subagents,tools,state,config}.py + langgraph.json + Dockerfile
    └── backend/  src/{__main__,app,worker,actions,openai_api,lg_client,mq,config}.py + Dockerfile
```

Each `shared/*` lib is a hatchling wheel; services declare them via
`[tool.uv.sources] {name = {workspace = true}}`. `projects/scraper` and
`projects/backend` are `package = false` (run via `python -m src`);
`projects/agent` is an installable package `aviatrade_agent` (so the graph imports
cleanly under `langgraph dev` and in the langgraph-api image).

## Configuration (pydantic-settings + YAML)

All config is pydantic-settings loaded **from YAML only** (no `.env`). The base
`shared.core.settings.BaseServiceSettings` reads a single YAML file via
`YamlConfigSettingsSource`; each service (and `scripts/_settings.py`) subclasses it
(`SettingsConfigDict(yaml_file=...)`) and selects the sections it needs. Override
the path with `SETTINGS_PATH`.

- Shared models: `DatabaseSettings` (sync `dsn`), `RabbitMQSettings` (`scrape_queue`,
  `job_queue`, `url`), `RedisSettings`, `LLMSettings` (OpenRouter), `LangGraphSettings`,
  `ScraperSettings` (`mode: local|rabbitmq`).
- **Two config files per service, differing only in hostnames** (both gitignored;
  commit only the `*.example.yaml`): `config.yaml` (localhost — host tools:
  `scripts/`, `langgraph dev`) and `config.docker.yaml` (compose service names — containers).
  docker-compose mounts `projects/<svc>/config.docker.yaml` and sets `SETTINGS_PATH`
  to it. The path is resolved via `shared.core.settings.resolve_settings_path(fallback)`.
  Without a YAML file, defaults apply (localhost, `scraper.mode=local`).
- `make_model` (agent) and the `Database` DSN come from settings, not `os.getenv`.

## Commands

```bash
# Environment (uv workspace)
uv sync                         # shared libs + scripts deps (root is package = false)
uv sync --extra dev             # + pytest/mypy/ruff
uv sync --project projects/agent --extra langgraph   # agent service deps

# Database only (TimescaleDB; initdb runs on first empty volume)
docker compose up -d postgres

# Manual-testing scripts (scripts/). scraper.mode=local scrapes in-process; rabbitmq publishes a task.
uv run python scripts/cli.py --origin MOW --destination LED --date 2025-12-15 --action scrape
uv run python scripts/cli.py --action watch-list
uv run python scripts/cli.py --action agent          # talks to the LangGraph server via SDK

# Agent graph locally (LangGraph Studio)
uv run --project projects/agent --extra langgraph langgraph dev

# Backend + worker locally (need RabbitMQ/Redis up; agent for chat)
uv run --project projects/backend python -m src           # API on :8000
uv run --project projects/backend python -m src.worker    # chat-job consumer

# Scraper service locally
uv run --project projects/scraper python -m src

# Compose profiles: infra (db/redis/rabbitmq/scraper) ⊂ agent (+langgraph server)
#   ⊂ app (+backend/worker/openwebui). Infra services belong to all three profiles,
#   so each profile is self-sufficient.
docker compose --profile infra up -d                 # just the service infra (+ scraper)
docker compose --profile app up -d --build           # full stack (OpenWebUI on :3000)
docker compose --profile app up -d --scale scraper=3 # scale the scraper (competing consumers)
```

OpenWebUI runs on `http://localhost:3000` (configured entirely via env in
docker-compose; AI task features disabled so it doesn't send hidden `### Task:`
LLM calls). Backend REST + OpenAI API on `:8000` (`/docs`).

## Architecture (data flow)

```
scripts/cli.py                 → shared.services.dispatch_scrape (local|rabbitmq) → shared.db
                                → shared.analytics (charts/stats); agent via langgraph-sdk

OpenWebUI → backend /v1/chat/completions (openai_api) → lg_client → LangGraph Server (agent)
backend  /scrape  → publish ScrapeTask → RabbitMQ(scrape_tasks) ─┐
backend  /agent/chat/async → RabbitMQ(aviatrade_jobs) → worker → graph (SDK)
agent ops tools / monitors → publish ScrapeTask ─────────────────┤
                                                                  ▼
                          scraper service (consumer, Chromium) → shared.services.scrape_and_save_local → TimescaleDB
                          (writes job status to Redis if job_id; backend GET /jobs/{id} reads it)

backend light ops (/stats,/charts,/watchlist,/monitors) → shared.* directly (run_in_threadpool)
```

Two RabbitMQ queues: `scrape_tasks` (→ scalable scraper service) and
`aviatrade_jobs` (→ backend worker for async chat). Background monitors
(`shared.services.monitoring.MONITORS`) run as daemon threads in whatever process
hosts them (agent/backend) and **publish** scrape tasks each cycle.

## Key Components

- **shared.core.settings**: `BaseServiceSettings` (YAML-only) + all config models.
- **shared.db**: `FlightPrice`/`Watchlist` ORM + sync `Database(dsn)`. Schema unchanged
  (hypertable, composite PK `(id, scraped_at)`); `initdb/01-init-timescaledb.sql` still applies.
- **shared.scraper**: `AviasalesScraper` (botasaurus) + `ScrapeTask` schema (queue contract).
- **shared.analytics**: `FlightPriceVisualizer`, `compute_price_stats` (dict),
  `render_stats_report` (text), `visualize_prices`.
- **shared.services**: `scrape_and_save_local`, `publish_scrape`, `dispatch_scrape`
  (mode switch), `monitor_route`/`monitor_watchlist`, `BackgroundMonitorManager`/`MONITORS`,
  `get_database` (cached per DSN). No matplotlib dep → scraper image stays lean.
- **projects/scraper**: aio-pika consumer of `scrape_tasks` (prefetch 1), scrapes in a
  threadpool, writes to DB, records job status in Redis. Only image with Chromium.
- **projects/agent**: LangGraph graph `aviatrade_agent` (router → analysis/charts/ops/chat).
  `make_model` reads `config.llm`; tools use `shared.*` + `config`. Dockerfile uses the
  `langchain/langgraph-api` base + `uv pip install --system` of the local packages.
- **projects/backend**: FastAPI REST + OpenAI-compatible `/v1/*` (OpenWebUI). `/scrape`
  publishes to `scrape_tasks`; worker handles chat jobs only.

## Tech Stack
- **uv workspace** (root + `shared/*` libs + `projects/*` services)
- **pydantic-settings + PyYAML** for YAML config
- **Botasaurus** (scraper service only), **SQLAlchemy + psycopg2** (sync), **matplotlib/seaborn/pandas**
- **LangGraph + LangChain `create_agent` + langchain-openai** over OpenRouter; **langgraph-sdk** (backend/CLI clients)
- **FastAPI + uvicorn + aio-pika (RabbitMQ) + redis**
- **OpenWebUI** frontend
- **Docker Compose**: TimescaleDB + LangGraph run-state Postgres + Redis + RabbitMQ + scraper + agent + backend + worker + openwebui

## Database Schema
`flight_prices` (TimescaleDB hypertable, daily chunks, compression) and a plain
`watchlist` table. `scraped_at` is part of the composite PK `(id, scraped_at)`
because the partition column must be in the PK. Defined in `shared/db/.../models.py`;
created by `initdb/01-init-timescaledb.sql` on first DB start.

## Development Notes
- Each phase of the monorepo migration is verified; the DB schema and existing data are unchanged.
- Scraping is **asynchronous** in `rabbitmq` mode: agent/scripts submit a task and don't get a
  synchronous saved-count (status is recoverable via Redis `job:{id}` / `GET /jobs/{id}`).
  Use `scraper.mode: local` for in-process scraping in dev (needs Chromium, no broker).
- The agent requires `llm.api_key` (OpenRouter) in its `config.yaml`.
- The scraper is the only service needing Chromium; scale it with `docker compose up --scale scraper=N`.
