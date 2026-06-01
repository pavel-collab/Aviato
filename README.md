# AviaTrade

Flight price monitoring system for Aviasales.ru

## Quick Start

### 1. Start the database (TimescaleDB)
```bash
docker-compose up -d
```

The container runs **TimescaleDB** (a PostgreSQL extension for time-series data).
On the first start (empty volume) the script in `initdb/` runs automatically and
sets everything up: the `flight_prices` hypertable, daily chunks (time buckets),
and a chunk compression policy. No manual SQL is required for the Docker setup.

> If you recreate the database and want the init script to run again, reset the
> volume: `docker-compose down -v && docker-compose up -d`.

### 2. Install dependencies
The project is managed with [uv](https://docs.astral.sh/uv/):
```bash
# Create the virtual environment and install all dependencies
uv sync

# Run commands inside the environment
uv run aviatrade --origin MOW --destination LED --date 2025-12-15 --action scrape
```

### 3. Configure environment
```bash
cp configs/.env.example .env
# Edit .env with your database credentials
```

### 4. Run the application
```bash
# Scrape flight prices
aviatrade --origin MOW --destination LED --date 2025-12-15 --action scrape

# Track several routes at once (multi-direction watchlist)
aviatrade --origin MOW --destination LED --date 2025-12-15 --action watch-add --interval 30
aviatrade --origin MOW --destination AER --date 2025-12-20 --action watch-add
aviatrade --action monitor-all --interval 60
```

> Prefer a chat UI? Run the full stack with `docker-compose up -d --build` and
> open **OpenWebUI** at `http://localhost:3000` to talk to the agent. See
> `CLAUDE.md` for the backend/frontend details.

## Command-Line Usage

For scripting or automated pipelines, use the CLI mode directly:

### Scrape flight prices
```bash
aviatrade --origin MOW --destination LED --date 2025-12-15 --action scrape
```

### Visualize collected data
```bash
aviatrade --origin MOW --destination LED --date 2025-12-15 --action visualize
```

### Continuous monitoring
```bash
aviatrade --origin MOW --destination LED --date 2025-12-15 --action monitor --interval 30
```

### Scrape and visualize together
```bash
aviatrade --origin MOW --destination LED --date 2025-12-15 --action both
```

## Multi-Direction Monitoring (Watchlist)

Instead of monitoring a single route, you can maintain a **watchlist** of routes
and monitor all of them with one command. The watchlist is stored in the database
(a plain `watchlist` table, not a hypertable), so it persists across restarts and
can be managed from the CLI or the AI agent. Price history itself still lives in
`flight_prices`.

### Add a route to the watchlist
```bash
aviatrade --origin MOW --destination LED --date 2025-12-15 --action watch-add --interval 30
```
- `--interval` sets the **per-route** collection interval in minutes (default: 60).
- Adding a route that already exists **updates its interval** and re-enables it
  (routes are unique by origin + destination + date).

### Show the watchlist
```bash
aviatrade --action watch-list
```

### Remove a route from the watchlist
```bash
aviatrade --origin MOW --destination AER --date 2025-12-20 --action watch-remove
```

### Monitor every route in the watchlist
```bash
aviatrade --action monitor-all --interval 60
```
Routes are scraped **sequentially** (gentle on Aviasales — no parallel browser
sessions). Each route is re-scraped only after its own interval elapses; routes
without one fall back to the `--interval` value. The watchlist is re-read at the
start of every cycle, so routes you add or remove are picked up **without
restarting** the monitor.

> Manage the watchlist from the AI agent too: just ask it in natural language,
> e.g. *"add Moscow–Sochi on 2025-12-20 to tracking, check every 30 minutes"* or
> *"show the watchlist"*. See the agent tools below.

## AI Agent

AviaTrade includes an interactive AI agent (LangChain `create_agent`, OpenRouter)
that exposes scraping, visualization, statistics, and watchlist management as
tools. Talk to it in natural language and it calls the right tool for you.

```bash
# Requires OPENROUTER_API_KEY in the environment (and optional MODEL_NAME,
# default: openai/gpt-4o-mini)
export OPENROUTER_API_KEY=your_key
aviatrade --action agent
```

Example session:
```
Agent> analyze Moscow–Sochi prices for 2025-12-20
Agent> add Moscow–Saint-Petersburg on 2025-12-15 to tracking, every 30 minutes
Agent> show the watchlist
Agent> remove Moscow–Sochi
```

Available agent tools:

| Tool | Purpose |
|------|---------|
| `scrape_and_save_tool` | Scrape current prices for a route and save them |
| `visualize_prices_tool` | Generate price charts for a route |
| `monitor_prices_tool` | Continuously monitor a single route |
| `get_price_stats_tool` | Detailed price statistics & recommendations |
| `add_to_watchlist_tool` | Add a route to the multi-direction watchlist |
| `remove_from_watchlist_tool` | Remove a route from the watchlist |
| `list_watchlist_tool` | List all watched routes |
| `monitor_watchlist_tool` | Continuously monitor every watched route |

## Common IATA Codes

| Code | City |
|------|------|
| MOW | Moscow |
| LED | Saint-Petersburg |
| SVX | Yekaterinburg |
| KZN | Kazan |
| OVB | Novosibirsk |
| AER | Sochi |

## Docker Commands

Start the TimescaleDB container:
```bash
docker-compose up -d
```

Connect to container:
```bash
docker exec -it <container-id> /bin/bash
```

## Project Structure

AviaTrade is a **`uv` workspace monorepo**: shared libraries in `shared/*`,
deployable services in `projects/*`, and a thin CLI at the root. Configuration is
pydantic-settings loaded from YAML (`config.yaml`, gitignored; see
`config.example.yaml`). See `CLAUDE.md` for the full architecture.

```
aviatrade/
├── src/aviatrade/       # CLI tool (root package): cli/{main,lib}.py, config.py
├── shared/              # installable libraries (shared.<name>)
│   ├── core/            # pydantic-settings YAML base + config models
│   ├── db/              # SYNC SQLAlchemy models (FlightPrice, Watchlist) + Database
│   ├── scraper/         # Botasaurus scraper + ScrapeTask/FlightRecord schemas
│   ├── analytics/       # matplotlib charts + price stats
│   └── services/        # use-cases: scraping (local/queue), monitoring, db factory
├── projects/            # deployable services
│   ├── scraper/         # RabbitMQ consumer (the only Chromium image) — scalable
│   ├── agent/           # LangGraph Server graph (aviatrade_agent) + langgraph.json
│   └── backend/         # FastAPI REST + OpenAI API (OpenWebUI) + worker
├── initdb/              # TimescaleDB init scripts (run on first DB start)
├── docker-compose.yml   # full stack (+ OpenWebUI on :3000)
├── config.example.yaml  # CLI config template
└── run.py               # CLI dev entry point
```

## For Developers

### Setup development environment
```bash
# Create the environment and install runtime + dev dependencies
uv sync --extra dev

# Run a command inside the environment
uv run aviatrade --origin MOW --destination LED --date 2025-12-15 --action scrape

# Or activate the environment manually
source .venv/bin/activate  # Linux/macOS
# or: .venv\Scripts\activate  # Windows
```

### Running via run.py
For debugging you can use the `run.py` entry point instead of the installed command:

```bash
# Using the installed command
aviatrade --origin MOW --destination LED --date 2025-12-15 --action scrape

# Or using run.py entry point (useful for debugging)
python run.py --origin MOW --destination LED --date 2025-12-15 --action scrape
```

### Available CLI arguments
| Argument | Description | Required |
|----------|-------------|----------|
| `--origin` | Origin airport IATA code | Yes (route-specific actions) |
| `--destination` | Destination airport IATA code | Yes (route-specific actions) |
| `--date` | Departure date (YYYY-MM-DD) | Yes (route-specific actions) |
| `--action` | Action: `scrape`, `visualize`, `monitor`, `both`, `agent`, `watch-add`, `watch-remove`, `watch-list`, `monitor-all` | No (default: both) |
| `--interval` | Collection interval in minutes (for `monitor`/`monitor-all`; per-route interval for `watch-add`) | No (default: 60) |

> `watch-list`, `monitor-all`, and `agent` do **not** require `--origin/--destination/--date`.

### How to set up the Timescale extension for PostgreSQL

> **Note:** with the bundled `docker-compose` setup this is done **automatically** by
> `initdb/01-init-timescaledb.sql` on first start — you do not need any of the steps
> below. This section is only for an **external / self-hosted** PostgreSQL where you
> add the extension to an existing server by hand.

If you're using your PostgreSQL database service not in docker, but as a real hosted servise, you may want to set up an
addition extension TimescaleDB for time data. This extension allow to separate time data through the separated time chunks, 
using optimal data saving on the disk, automate statistics aggregation and zip the old data to reduce data disk space.

Use the following commands to set up the TimescaleDB extension.

#### Build from scratch

Firstly you need to download the Timescaledb code and build the extension as a shared lib object (.so file).
```
# clone the timescale source code
git clone https://github.com/timescale/timescaledb.git
cd timescaledb

# configure the project (use it without OpenSSL)
./bootstrap -DUSE_OPENSSL=0

# build the extension
cd ./build && make

# install the extension
sudo make install
```

#### Setings for the postgresql server

When you have installed the timescaledb extension you need to add this extension to the postgresql shared libraries.
Open the postgresql.conf configuration file and add 'timescaledb' to 'shared_preload_libraries' parameter.
```
vim postgresql.conf

# set: shared_preload_libraries = 'timescaledb'
```

After you change parameters in postgresql.conf you need to restart the postgresql server:
```
pg_ctl restart
```

#### Setting the timescaledb features

First of all check if your postgresql server is working correct
```
pg_ctl status
```

If all is ok, attach your psql session and connect to your database with table 'flight_prices'
```
psql

# in the psql session
\c flight prices
```

You need to add the extension to your database:
```
CREATE EXTENSION IF NOT EXISTS timescaledb;
```

Now you're ready to modify your existing table with content and set timescaledb feature.

Before set up the hypertable we need the partitioning column `scraped_at` to be part
of the primary key (TimescaleDB requires it). The ORM model uses a composite PK
`(id, scraped_at)`; if your existing table still has `id` as the only key, fix it:
```
ALTER TABLE flight_prices DROP CONSTRAINT flight_prices_pkey;
ALTER TABLE flight_prices ADD PRIMARY KEY (id, scraped_at);
```

First of all make the content table to gypertable:
```
SELECT create_hypertable('flight_prices', by_range('scraped_at'), migrate_data => true);
```

After that we need to set up the chunk time interval
```
SELECT set_chunk_time_interval('flight_prices', INTERVAL '1 day');
```

And the last but not the least: we will st up a compression policy.
Set the compression
```
ALTER TABLE flight_prices
    SET (timescaledb.compress,
         timescaledb.compress_orderby='scraped_at');
```

and autocompress policy
```
SELECT add_compression_policy(
  'flight_prices',
  compress_after => INTERVAL '2 day');
```

#### Check the timescaledb settings

After you have successful set the timescaledb extension, you can check how your table was changed.
Firstly check the time partitions -- chunks:
```
SELECT show_chunks('flight_prices');
```

Check the compresed partitions:
```
SELECT compress_chunk(c) FROM show_chunks('flight_prices') c;
```

Check the chunks compression metadata:
```
SELECT chunk_name, compression_status, before_compression_total_bytes, after_compression_total_bytes FROM chunk_compression_stats('flight_prices');
```
