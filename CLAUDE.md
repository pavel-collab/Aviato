# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AviaTrade is a Python flight price monitoring system for Aviasales.ru. It scrapes flight prices, stores them in TimescaleDB (PostgreSQL + time-series extension), and generates statistical visualizations for price trend analysis. It also includes an AI agent (LangChain `create_agent`) that exposes scraping/visualization/stats as tools.

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
│       ├── agent/              # AI agent (LangChain create_agent)
│       │   ├── __init__.py
│       │   ├── agent.py        # AgentFactory.build_agent + system prompt
│       │   └── tool_wrappers.py # Scrape/visualize/monitor/stats tools
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
├── docker-compose.yml          # TimescaleDB container configuration
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

cli/lib.py run_agent / tui
    → agent/agent.py (LangChain create_agent)
    → agent/tool_wrappers.py (wraps cli/lib.py functions as tools)
```

### Key Components

- **core/config.py**: Loads PostgreSQL connection from `.env` file (supports both root and configs/ directory)
- **db/models.py**: `FlightPrice` SQLAlchemy ORM model
- **db/database.py**: `Database` class for session management and CRUD operations
- **scraper/aviasales.py**: `AviasalesScraper` uses Botasaurus browser automation with multi-selector CSS approach
- **visualization/visualizer.py**: `FlightPriceVisualizer` generates 4-panel analysis charts
- **cli/main.py**: CLI entry point with modes: scrape, visualize, monitor, both, agent (plus `--tui`)
- **agent/agent.py**: `AgentFactory.build_agent` builds a LangChain `create_agent` ReAct agent (OpenRouter via `ChatOpenAI`); invoke with `{"messages": [...]}`

### Tech Stack
- **Botasaurus**: Selenium-like browser automation for web scraping
- **SQLAlchemy + psycopg2**: PostgreSQL ORM
- **matplotlib/seaborn/pandas**: Data visualization and analysis
- **LangChain (`create_agent`) + langchain-openai**: AI agent over OpenRouter
- **Docker Compose**: TimescaleDB container (PostgreSQL 16 + time-series extension)
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
