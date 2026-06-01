# Сервис-скрапер AviaTrade. ЕДИНСТВЕННЫЙ образ с браузером (Chromium) —
# остальные сервисы скрапинг не делают, а ставят задачи в очередь.
# Контекст сборки — корень монорепо (нужны pyproject.toml/uv.lock + shared/).

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Сначала только метаданные workspace + shared — кешируем установку зависимостей.
COPY pyproject.toml uv.lock ./
COPY shared/ shared/
COPY projects/scraper/pyproject.toml projects/scraper/pyproject.toml
RUN uv sync --project projects/scraper --frozen --no-install-project --no-dev

# Затем исходники сервиса.
COPY projects/scraper/ projects/scraper/
RUN uv sync --project projects/scraper --frozen --no-dev


FROM python:3.12-slim-bookworm

# Chromium + драйвер для botasaurus/Selenium.
RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app /app
WORKDIR /app/projects/scraper
ENV PATH="/app/.venv/bin:$PATH"

# Воркер очереди (без портов). Масштабируется: docker compose up --scale scraper=N
CMD ["python", "-m", "src"]
