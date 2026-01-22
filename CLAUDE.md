# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AviaTrade is a Python flight price monitoring system for Aviasales.ru. It scrapes flight prices, stores them in PostgreSQL, and generates statistical visualizations for price trend analysis.

## Commands

### Database Setup
```bash
docker-compose up -d  # Start PostgreSQL container
```

### Installation
```bash
# Install in development mode
pip install -e .

# Or install dependencies only
pip install -r requirements.txt
```

### Running the Application
```bash
# Using the installed command (after pip install -e .)
aviatrade --origin MOW --destination LED --date 2025-12-15 --action scrape

# Or using the run.py entry point (for development)
python run.py --origin MOW --destination LED --date 2025-12-15 --action scrape

# Visualize collected data
python run.py --origin MOW --destination LED --date 2025-12-15 --action visualize

# Continuous monitoring (interval in minutes)
python run.py --origin MOW --destination LED --date 2025-12-15 --action monitor --interval 30

# Scrape and visualize together
python run.py --origin MOW --destination LED --date 2025-12-15 --action both
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
├── configs/
│   └── .env.example            # Environment variables template
├── charts/                     # Output directory for generated charts
├── docker-compose.yml          # PostgreSQL container configuration
├── pyproject.toml              # Modern Python packaging configuration
├── requirements.txt            # Dependencies
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
    → PostgreSQL

cli/main.py
    → visualization/visualizer.py (matplotlib/seaborn)
    → /charts/*.png
```

### Key Components

- **core/config.py**: Loads PostgreSQL connection from `.env` file (supports both root and configs/ directory)
- **db/models.py**: `FlightPrice` SQLAlchemy ORM model
- **db/database.py**: `Database` class for session management and CRUD operations
- **scraper/aviasales.py**: `AviasalesScraper` uses Botasaurus browser automation with multi-selector CSS approach
- **visualization/visualizer.py**: `FlightPriceVisualizer` generates 4-panel analysis charts
- **cli/main.py**: CLI entry point with four modes: scrape, visualize, monitor, both

### Tech Stack
- **Botasaurus**: Selenium-like browser automation for web scraping
- **SQLAlchemy + psycopg2**: PostgreSQL ORM
- **matplotlib/seaborn/pandas**: Data visualization and analysis
- **Docker Compose**: PostgreSQL 16 container

### Database Schema
The `flight_prices` table stores: origin, destination, departure_date, airline, flight_number, departure_time, arrival_time, duration, price, currency, stops, scraped_at. Indexes exist on origin, destination, departure_date, and scraped_at.

## Development Notes

- Scraper uses multi-selector CSS queries to handle Aviasales UI changes
- Price extraction uses regex patterns for Russian ruble symbols
- Results are limited to first 20 flights per scrape
- Charts are saved to `/charts` directory with timestamps
- UUID-based IDs are used for TimescaleDB compatibility
- Configuration supports `.env` in both project root and `configs/` directory

## Common IATA Codes
MOW (Moscow), LED (Saint-Petersburg), SVX (Yekaterinburg), KZN (Kazan), OVB (Novosibirsk), AER (Sochi)
