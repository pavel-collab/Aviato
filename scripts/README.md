# scripts/

Самодостаточные скрипты для **ручного тестирования** AviaTrade поверх общих
библиотек `shared.*`. Это инструменты разработчика, а не деплой-сервисы: они не
участвуют в docker-compose и не собираются в пакет. Запускаются напрямую из
окружения workspace.

Конфигурацию берут из корневого `config.yaml` (или пути в `SETTINGS_PATH`); без
файла действуют дефолты (localhost, `scraper.mode=local`).

## `cli.py`

Ручной прогон скрапинга/визуализации/мониторинга/watchlist и интерактивный чат с
агентом (через LangGraph Server). Раньше это была консольная команда `aviatrade`.

```bash
uv run python scripts/cli.py --origin MOW --destination LED --date 2026-09-15 --action scrape
uv run python scripts/cli.py --action watch-list
uv run python scripts/cli.py --action monitor-all --interval 60
uv run python scripts/cli.py --action agent        # интерактивный чат через LangGraph Server
uv run python scripts/cli.py --help
```

Действия `--action`: `scrape`, `visualize`, `monitor`, `both`, `agent`,
`watch-add`, `watch-list`, `watch-remove`, `monitor-all`. Для `watch-list`,
`monitor-all` и `agent` маршрут (`--origin/--destination/--date`) не нужен.

## `_settings.py`

Вспомогательный модуль (не запускается напрямую): общий конфиг скриптов поверх
`shared.core`.
