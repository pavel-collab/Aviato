# FastAPI backend + worker AviaTrade. Без браузера — скрапинг вынесен в сервис
# scraper. Контекст сборки — корень монорепо.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY shared/ shared/
COPY projects/backend/pyproject.toml projects/backend/pyproject.toml
RUN uv sync --project projects/backend --frozen --no-install-project --no-dev

COPY projects/backend/ projects/backend/
RUN uv sync --project projects/backend --frozen --no-dev


FROM python:3.12-slim-bookworm
COPY --from=builder /app /app
WORKDIR /app/projects/backend
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
# По умолчанию — API; сервис worker переопределяет команду на: python -m src.worker
CMD ["python", "-m", "src"]
