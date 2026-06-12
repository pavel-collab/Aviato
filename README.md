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

# Пути к графу в langgraph.json резолвятся относительно рабочей директории,
# поэтому запускать нужно с CWD = projects/agent (флаг uv --directory), а не из
# корня репозитория — иначе ./aviatrade_agent/graph.py не найдётся.
uv run --directory projects/agent --extra langgraph langgraph dev
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

## Сценарий 4 — раздельный деплой (Raspberry Pi 24/7 + ноутбук по требованию)

Тяжёлый интерактивный слой (LangGraph Server жрёт ресурсы) не тянется на ARM Pi,
но и держать его постоянно на рабочем ноутбуке нельзя — а скрапинг должен идти
круглосуточно. Решение: **сбор данных живёт на Pi 24/7, а агент + UI поднимаются
на ноутбуке по требованию** и ходят за данными на Pi по локальной сети.

```
┌─────────── Raspberry Pi (24/7) ───────────┐      ┌──── Ноутбук (по требованию) ────┐
│  TimescaleDB :5432   RabbitMQ :5672        │      │  agent (LangGraph Server)       │
│  Redis :6379                               │      │  langgraph-postgres + redis     │
│  scraper (Chromium, consumer scrape_tasks) │ LAN  │  backend + worker + openwebui   │
│  cron → cli.py --action scrape (publish)   │◄────►│  :3000                          │
│  = docker compose --profile infra          │      │  = docker-compose.laptop.yml    │
└────────────────────────────────────────────┘      └─────────────────────────────────┘
```

Развязка — через очередь `scrape_tasks` на Pi: задачи, уже попавшие в очередь,
скрапер на Pi отрабатывает **независимо** от того, включён ли ноутбук. Поэтому
ритм сбора задаёт **планировщик на Pi** (cron), а не фоновые мониторы агента
(их потоки живут в процессе агента — на ноутбуке, и гаснут вместе с ним).

### Часть A — Raspberry Pi (служебный слой + планировщик)

**A1. Поднять инфраструктуру** (как в Сценарии 1; конфиги контейнеров — на именах
сервисов compose, менять не нужно):

```bash
docker compose --profile infra up -d           # postgres, redis, rabbitmq, scraper
hostname -I                                     # узнать IP Pi (понадобится ноутбуку)
```

**A2. Открыть RabbitMQ для ноутбука.** Пользователь `guest/guest` работает только
с localhost — подключение ноутбук→Pi он отклонит. Создать отдельного пользователя
(один раз):

```bash
docker compose exec rabbitmq rabbitmqctl add_user aviatrade <пароль>
docker compose exec rabbitmq rabbitmqctl set_user_tags aviatrade administrator
docker compose exec rabbitmq rabbitmqctl set_permissions -p / aviatrade ".*" ".*" ".*"
```

> БД и Redis пускают по LAN как есть (пароль БД задан; Redis без пароля — при
> необходимости закройте firewall'ом/`requirepass`).

**A3. Планировщик на хосте Pi.** В режиме `rabbitmq` действие `scrape` только
**публикует** задачу в очередь и выходит — идеально для cron. Нужен `uv` и копия
репозитория на Pi:

```bash
uv sync                                         # окружение workspace на Pi
cp config.example.yaml config.yaml              # localhost (порты Pi проброшены), scraper.mode: rabbitmq
```

cli.py на хосте Pi ходит на `localhost`, где `guest/guest` работает (loopback) —
менять учётку в `config.yaml` Pi не нужно. Пример `/etc/cron.d/aviatrade`
(одна строка = один маршрут):

```cron
# каждые 30 минут публиковать задачу на сбор MOW → LED на 2026-09-15
*/30 * * * * pi cd /home/pi/AviaTrade && SETTINGS_PATH=$PWD/config.yaml \
  uv run python scripts/cli.py --origin MOW --destination LED --date 2026-09-15 --action scrape \
  >> /var/log/aviatrade-cron.log 2>&1
```

> Альтернатива cron — один долгоживущий `cli.py --action monitor-all --interval 60`
> под `systemd` (расписание берётся из таблицы `watchlist` в БД, а не из crontab).

### Часть B — Ноутбук (агент + UI по требованию)

Верхний слой вынесен в отдельный `docker-compose.laptop.yml` (только `agent` +
его локальные `langgraph-postgres`/`redis` для run-state + `backend` + `worker` +
`openwebui`; служебных сервисов в нём нет — они на Pi).

**B1. Конфиги ноутбука** (уже есть готовые `config.laptop.yaml`, в `.gitignore`):

```bash
# при первой настройке — из шаблонов:
cp projects/agent/config.laptop.example.yaml   projects/agent/config.laptop.yaml
cp projects/backend/config.laptop.example.yaml projects/backend/config.laptop.yaml
```

В обоих файлах заменить `192.168.1.50` на **IP Pi** (все поля `host`), вписать
`rabbitmq.user/password` = `aviatrade/<пароль>` из шага A2 и `llm.api_key`
(OpenRouter) в конфиге агента. Логика адресов:

| Что | Куда смотрит | Почему |
|-----|--------------|--------|
| `database` / `rabbitmq` (оба конфига) | **Pi** | данные и очереди живут на Pi |
| `redis` (backend) | **Pi** | статусы `job:{id}` пишет скрапер на Pi |
| `DATABASE_URI` / `REDIS_URI` контейнера `agent` | **локально** | run-state LangGraph — чтобы граф не бегал по сети |
| `langgraph.url` (backend) | **локально** (`agent:8000`) | сервер агента — в сети compose ноутбука |

**B2. Запуск:**

```bash
docker compose -f docker-compose.laptop.yml up -d --build
```

Точки входа (всё на ноутбуке):

| Что | Адрес |
|-----|-------|
| Чат с агентом (OpenWebUI) | http://localhost:3000 |
| Backend REST + Swagger | http://localhost:8000/docs |

**B3. Остановить, когда ноутбук не нужен** (Pi продолжает собирать данные):

```bash
docker compose -f docker-compose.laptop.yml down
```

### Что переживает выключение ноутбука

| Состояние на момент остановки ноута | Продолжится на Pi? |
|-------------------------------------|--------------------|
| Задача уже в очереди / уже скрапится | ✅ да (развязка через `scrape_tasks`) |
| Публикация по cron на Pi | ✅ да (планировщик на Pi) |
| Следующий цикл фонового монитора агента | ❌ нет (поток жил на ноутбуке) |
| Ручной запрос через OpenWebUI | ❌ нет (нужен включённый ноутбук) |

> На ноутбуке запускайте **только** `docker-compose.laptop.yml`. Обычный
> `docker-compose.yml` поднял бы собственную инфраструктуру и продублировал Pi.

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
