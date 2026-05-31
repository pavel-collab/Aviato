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
uv run aviatrade --tui
```

### 3. Configure environment
```bash
cp configs/.env.example .env
# Edit .env with your database credentials
```

### 4. Run the application
```bash
# Launch interactive TUI (recommended for most users)
aviatrade --tui

# Or use command-line mode
aviatrade --origin MOW --destination LED --date 2025-12-15 --action scrape
```

## Interactive TUI

AviaTrade includes an interactive terminal user interface (TUI) for convenient operation.

### Launch TUI
```bash
aviatrade --tui
# or
aviatrade-tui
```

### TUI Features
- **Input form**: Enter origin, destination, departure date, and monitoring interval
- **Action selector**: Choose between Scrape, Visualize, Monitor, or Both
- **Live log panel**: View application messages and progress in real-time
- **Keyboard shortcuts**: `q` - quit, `Escape` - cancel running operation

### TUI Layout
```
+----------------------------------------------------------+
|  AviaTrade - Flight Price Monitor                        |
+------------------+---------------------------------------+
| Flight Search    |  [●] Ready                            |
|                  |                                       |
| Origin (IATA):   |  Application Log                      |
| [MOW          ]  | +---------------------------------+   |
|                  | | 10:30:15 AviaTrade TUI started  |   |
| Destination:     | | 10:30:16 Database connected     |   |
| [LED          ]  | | 10:30:45 Scraping flights...    |   |
|                  | | 10:30:52 Found 15 flights       |   |
| Departure Date:  | |                                 |   |
| [2025-12-15   ]  | |                                 |   |
|                  | |                                 |   |
| Interval (min):  | |                                 |   |
| [60           ]  | |                                 |   |
|                  | |                                 |   |
| Action:          | |                                 |   |
| [Scrape + Viz ▼] | |                                 |   |
|                  | +---------------------------------+   |
| [Execute][Cancel]|                                       |
+------------------+---------------------------------------+
```

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

```
aviatrade/
├── src/aviatrade/       # Main package
│   ├── cli/             # Command-line interface
│   │   ├── main.py      # CLI entry point
│   │   └── tui/         # Interactive TUI application
│   ├── core/            # Configuration
│   ├── db/              # Database models and operations
│   ├── scraper/         # Web scraping (Botasaurus)
│   └── visualization/   # Chart generation (matplotlib)
├── configs/             # Configuration files
├── charts/              # Generated charts output
└── run.py               # Development entry point
```

## For Developers

### Setup development environment
```bash
# Create the environment and install runtime + dev dependencies
uv sync --extra dev

# Run a command inside the environment
uv run aviatrade --tui

# Or activate the environment manually
source .venv/bin/activate  # Linux/macOS
# or: .venv\Scripts\activate  # Windows
```

### Running without TUI
For development and debugging, you can bypass the TUI and use CLI directly:

```bash
# Using the installed command
aviatrade --origin MOW --destination LED --date 2025-12-15 --action scrape

# Or using run.py entry point (useful for debugging)
python run.py --origin MOW --destination LED --date 2025-12-15 --action scrape
```

### Available CLI arguments
| Argument | Description | Required |
|----------|-------------|----------|
| `--tui` | Launch interactive TUI | No |
| `--origin` | Origin airport IATA code | Yes (CLI mode) |
| `--destination` | Destination airport IATA code | Yes (CLI mode) |
| `--date` | Departure date (YYYY-MM-DD) | Yes (CLI mode) |
| `--action` | Action: scrape, visualize, monitor, both | No (default: both) |
| `--interval` | Monitor interval in minutes | No (default: 60) |

### TUI Architecture
The TUI is built with [Textual](https://textual.textualize.io/) framework:
- `tui/app.py` - Main application class with workers for async operations
- `tui/widgets.py` - Custom widgets (StatusIndicator, LogPanel)
- `tui/workers.py` - Output redirection utilities
- `tui/styles.tcss` - Textual CSS styles

Workers run in separate threads to keep the UI responsive during scraping operations.

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
