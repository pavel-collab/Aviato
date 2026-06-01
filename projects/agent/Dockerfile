# LangGraph Server образ агента AviaTrade. База — официальный langgraph-api,
# поверх неё в СИСТЕМНЫЙ python ставим пакет графа aviatrade_agent и его
# workspace-зависимости (shared.*). Контекст сборки — корень монорепо.
#
# Агент НЕ скрапит сам (Chromium не нужен) — он публикует задачи в очередь.

FROM langchain/langgraph-api:3.12

# uv для установки локальных пакетов.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Исходники общих библиотек и сервиса агента.
COPY shared/ shared/
COPY projects/agent/ projects/agent/

# Ставим всё в системный python образа (его использует langgraph-сервер).
# Локальные пакеты перечислены вместе — uv разрешает shared.* как пути,
# удовлетворяя зависимости aviatrade_agent.
RUN uv pip install --system --no-cache \
        ./shared/core ./shared/db ./shared/scraper ./shared/analytics ./shared/services \
        ./projects/agent

# Точка входа графа для langgraph-сервера.
ENV LANGSERVE_GRAPHS='{"aviatrade_agent": "/app/projects/agent/aviatrade_agent/graph.py:graph"}'

# Гарантируем целостность пакетов langgraph-api (как в исходном образе).
RUN mkdir -p /api/langgraph_api /api/langgraph_runtime /api/langgraph_license \
    && touch /api/langgraph_api/__init__.py /api/langgraph_runtime/__init__.py /api/langgraph_license/__init__.py

WORKDIR /app/projects/agent
