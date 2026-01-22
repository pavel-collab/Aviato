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
# Using installed command (after pip install -e .)
aviatrade --origin MOW --destination LED --date 2025-12-15 --action scrape

# Or using run.py (for development)
python run.py --origin MOW --destination LED --date 2025-12-15 --action scrape
```

## Usage

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
│   ├── core/            # Configuration
│   ├── db/              # Database models and operations
│   ├── scraper/         # Web scraping
│   └── visualization/   # Chart generation
├── configs/             # Configuration files
├── charts/              # Generated charts output
└── run.py               # Development entry point
```
