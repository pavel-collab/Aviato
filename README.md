# AviaTrade

Система мониторинга цен на авиабилеты (Aviasales.ru): собирает цены, хранит их в
TimescaleDB и даёт AI-агента, который умеет собирать данные, считать статистику,
строить графики и вести список отслеживаемых маршрутов.

> Это **Quick Start**. Архитектура, потоки данных и детали реализации — в `CLAUDE.md`.

---

## Что нужно

- **Docker** + **Docker Compose** (профили запуска ниже).
- **[uv](https://docs.astral.sh/uv/)** — для скриптов ручного тестирования и запуска агента на хосте (`langgraph dev`).
- Ключ **OpenRouter** — только для AI-агента (сбор/аналитика/графики работают без него).

```bash
uv sync                 # окружение workspace: общие библиотеки + зависимости скриптов
```

---

## Конфигурация (один раз)

Конфиги — это YAML. Есть два набора, отличаются только адресами хостов:

| Файл | Кто читает | Хосты |
|------|------------|-------|
| `config.yaml` | инструменты на **хосте**: CLI, `langgraph dev` | `localhost` |
| `config.docker.yaml` | **контейнеры** docker-compose | имена сервисов (`postgres`, …) |

Скопируйте примеры (реальные `*.yaml` — в `.gitignore`, секреты только в них):

```bash
# Хостовые инструменты (localhost):
cp config.example.yaml                         config.yaml
cp projects/agent/config.example.yaml          projects/agent/config.yaml        # впишите llm.api_key

# Контейнеры (docker-хосты):
cp projects/agent/config.docker.example.yaml   projects/agent/config.docker.yaml # впишите llm.api_key
cp projects/backend/config.docker.example.yaml projects/backend/config.docker.yaml
cp projects/scraper/config.docker.example.yaml projects/scraper/config.docker.yaml
```

### Трейсинг агента (LangSmith) — опционально

Переменные `LANGSMITH_*` читаются SDK `langsmith`/`langgraph` **напрямую из
окружения процесса** (не нашим кодом и не из YAML), поэтому живут в корневом
`.env` — единственном источнике правды для них:

```bash
cp .env.example .env          # затем впишите LANGSMITH_API_KEY (smith.langchain.com)
```

| Где | Откуда берутся переменные |
|-----|---------------------------|
| контейнер `agent` | docker-compose подставляет `${LANGSMITH_*}` из корневого `.env` |
| `langgraph dev` (хост) | тот же `.env` через `"env"` в `projects/agent/langgraph.json` |

Трейсинг выполняется в процессе LangGraph Server (сервис `agent`), который
изолирует каждый run через `contextvars` — параллельные запуски не мешают друг
другу. Без `LANGSMITH_API_KEY` трейсинг просто выключен (`LANGSMITH_TRACING=false`).

Профили запуска:

| Профиль | Что поднимает |
|---------|---------------|
| `infra` | TimescaleDB, Redis, RabbitMQ, **scraper** (служебные сервисы) |
| `agent` | `infra` + LangGraph Server (граф агента) + его run-state БД |
| `app`   | всё приложение: `infra` + `agent` + backend + worker + OpenWebUI |

---

## Сценарий 1 — только служебные сервисы (проверка скрапера)

Поднять инфраструктуру и проверить сбор данных скриптом (скрапер крутится в
контейнере и забирает задачи из очереди):

```bash
docker compose --profile infra up -d           # postgres, redis, rabbitmq, scraper

# В config.yaml выставьте scraper.mode: rabbitmq, затем поставьте задачу в очередь:
uv run python scripts/cli.py --origin MOW --destination LED --date 2026-09-15 --action scrape

docker compose logs -f scraper                  # видно, как задача обрабатывается
docker compose exec postgres \
  psql -U flight_user -d flight_prices -c "select count(*) from flight_prices;"
```

Масштабировать сбор (несколько конкурирующих воркеров):

```bash
docker compose --profile infra up -d --scale scraper=3
```

---

## Сценарий 2 — служебные сервисы + агент через `langgraph dev`

Инфраструктура — в Docker (порты проброшены на `localhost`), а граф агента
запускается на хосте в режиме отладки и при этом имеет доступ к БД и к скраперу
(публикует задачи в RabbitMQ, их собирает контейнер `scraper`):

```bash
docker compose --profile infra up -d

uv sync --project projects/agent --extra langgraph
uv run --project projects/agent --extra langgraph langgraph dev
```

Откроется LangGraph Studio с графом `aviatrade_agent`. Агент читает
`projects/agent/config.yaml` (`localhost`, `scraper.mode: rabbitmq`). Правки в
`*.py` подхватываются на лету.

---

## Сценарий 3 — полное приложение

```bash
docker compose --profile app up -d --build
# при необходимости больше скраперов:
docker compose --profile app up -d --scale scraper=3
```

Точки входа:

| Что | Адрес |
|-----|-------|
| Чат с агентом (OpenWebUI) | http://localhost:3000 (модель `aviatrade-agent`) |
| Backend REST + Swagger | http://localhost:8000/docs |
| RabbitMQ Management | http://localhost:15672 |

Остановить (с `-v` — сбросить тома и данные БД):

```bash
docker compose --profile app down          # или: down -v
```

---

## Чек-лист первого полного запуска

После `--profile app` проверьте через **OpenWebUI** (http://localhost:3000) или
через **`/docs`**, что агент реально вызывает инструменты и сценарии работают
сквозь все сервисы. Даты — будущие, коды городов — IATA (MOW, LED, AER, SVX, KZN, OVB).

Сбор и анализ:

- [ ] **Сбор данных** — «собери цены MOW → AER на 2026-09-15» → задача уходит в очередь, в логах `scraper` видно обработку, в БД появляются строки.
- [ ] **Аналитика** — «проанализируй цены MOW → AER на 2026-09-15» → отчёт: минимум/среднее/медиана, тренд, рекомендация.
- [ ] **Графики** — «построй график цен MOW → AER на 2026-09-15» → PNG появляется в `./charts`.

Отслеживаемые маршруты (watchlist):

- [ ] **Добавить** — «добавь MOW → LED на 2026-10-01 в отслеживание, каждые 30 минут».
- [ ] **Список** — «покажи список отслеживаемых маршрутов» (новый маршрут в списке).
- [ ] **Удалить** — «удали MOW → LED на 2026-10-01 из отслеживания» (маршрут исчез из списка).

Фоновый мониторинг:

- [ ] **Запуск** — «запусти фоновый мониторинг всех отслеживаемых маршрутов».
- [ ] **Статус** — «покажи активные мониторы» (монитор `alive`, счётчик циклов растёт).
- [ ] **Остановка** — «останови монитор watchlist».

Сервисы и асинхронные задачи:

- [ ] **Масштаб скрапера** — `docker compose --profile app up -d --scale scraper=3`, `docker compose ps` показывает 3 реплики, задачи расходятся между ними.
- [ ] **Асинхронный scrape-job** — `POST /scrape` → `job_id`; `GET /jobs/{job_id}` → `status: done`, `saved_count > 0`.
- [ ] **Рост БД** — при активном мониторинге `select count(*) from flight_prices` со временем увеличивается.
- [ ] **OpenWebUI** — диалог отвечает только по существу (служебные AI-запросы выключены, токены не тратятся впустую).

---

## Скрипты ручного тестирования (`scripts/`)

Самодостаточные скрипты поверх `shared.*` для ручной проверки сбора/аналитики/
мониторинга без backend и OpenWebUI. Не входят в docker-compose и не собираются в
пакет — запускаются напрямую из окружения workspace (см. `scripts/README.md`).

```bash
uv run python scripts/cli.py --origin MOW --destination LED --date 2026-09-15 --action scrape
uv run python scripts/cli.py --action watch-list
uv run python scripts/cli.py --action monitor-all --interval 60
uv run python scripts/cli.py --action agent        # интерактивный чат через LangGraph Server
```

Действия `--action`: `scrape`, `visualize`, `monitor`, `both`, `agent`,
`watch-add`, `watch-list`, `watch-remove`, `monitor-all`. Для `watch-list`,
`monitor-all` и `agent` маршрут (`--origin/--destination/--date`) не нужен.
