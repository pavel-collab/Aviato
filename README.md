# AviaTrade

Flight price monitoring system for Aviasales.ru

## Quick Start

### 1. Start PostgreSQL
```bash
docker-compose up -d
```

### 2. Install dependencies
```bash
# Option A: Install as package (recommended)
pip install -e .

# Option B: Install dependencies only
pip install -r requirements.txt
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

Start PostgreSQL container:
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
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows

# Install in editable mode
pip install -e .
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
