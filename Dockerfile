# Прод-образ графа AviaTrade для LangGraph Server.
#
# База langchain/langgraph-api уже содержит сам сервер LangGraph (REST API,
# очередь run-ов, интеграцию с Postgres/Redis). Мы доустанавливаем сюда наш
# пакет aviatrade и указываем граф через LANGSERVE_GRAPHS.
#
# ОТЛИЧИЕ от «лёгких» графов: ops-субагент через botasaurus запускает РЕАЛЬНЫЙ
# браузер для скрапинга Aviasales, поэтому в образ нужно доставить Chromium и
# его системные зависимости (в базовом образе их нет).

FROM langchain/langgraph-api:3.12

# --- Системные зависимости: Chromium для скрапинга внутри контейнера --------
RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium \
        chromium-driver \
        fonts-liberation \
        libnss3 \
        libxss1 \
        libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Botasaurus/Selenium подхватывают системный Chromium по этим путям.
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# -- Adding local package . --
ADD . /deps/aviatrade
# -- End of local package . --

# -- Installing all local dependencies --
RUN PYTHONDONTWRITEBYTECODE=1 uv pip install --system --no-cache-dir \
        -c /api/constraints.txt -e /deps/aviatrade
# -- End of local dependencies install --

ENV LANGSERVE_GRAPHS='{"aviatrade_agent": "/deps/aviatrade/src/aviatrade/agent/graph.py:graph"}'

# -- Ensure user deps didn't inadvertently overwrite langgraph-api --
RUN mkdir -p /api/langgraph_api /api/langgraph_runtime /api/langgraph_license \
    && touch /api/langgraph_api/__init__.py /api/langgraph_runtime/__init__.py /api/langgraph_license/__init__.py
RUN PYTHONDONTWRITEBYTECODE=1 uv pip install --system --no-cache-dir --no-deps -e /api
# -- End of ensuring user deps didn't inadvertently overwrite langgraph-api --

WORKDIR /deps/aviatrade
