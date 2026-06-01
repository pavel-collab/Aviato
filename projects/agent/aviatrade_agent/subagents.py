"""Субагенты-специалисты, собранные через create_agent.

``create_agent`` (LangChain 1.0) — фабрика готового ReAct-агента: модель + список
инструментов + системный промпт → скомпилированный граф (Runnable). Каждый
субагент принимает ``{"messages": [...]}`` и возвращает то же — поэтому в graph.py
он вставляется как обычный узел.

Модель берётся из YAML-конфига (``config.llm``) через ``make_model`` (раньше —
из os.getenv). Фабрики обёрнуты в lru_cache: одинаковые параметры → один агент.
"""

from __future__ import annotations

from functools import lru_cache

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from aviatrade_agent.config import config
from aviatrade_agent.tools import ANALYSIS_TOOLS, CHARTS_TOOLS, OPS_TOOLS


def make_model(model: str | None = None, temperature: float = 0.0) -> ChatOpenAI:
    """Создать клиент модели через OpenRouter из настроек ``config.llm``.

    ``model`` (из Context) переопределяет имя модели; иначе берётся config.llm.model.
    Ключ и base_url — из config.llm (YAML), не из переменных окружения.
    """
    return ChatOpenAI(
        model=model or config.llm.model,
        api_key=config.llm.api_key,
        base_url=config.llm.base_url,
        temperature=temperature,
    )


# --- Системные промпты по умолчанию -----------------------------------------
DEFAULT_ANALYSIS_SYSTEM = (
    "Ты — аналитик цен на авиабилеты. Твоя задача — анализировать собранные "
    "временные данные о ценах и делать на их основе выводы.\n"
    "Сначала вызови get_price_stats_tool для нужного маршрута и даты, затем "
    "интерпретируй полученную статистику для пользователя: оцени уровень цен, "
    "тренд (растут/падают/стабильны), разброс между авиакомпаниями, выгодность "
    "прямых рейсов против пересадок. Дай конкретную рекомендацию: покупать "
    "сейчас или подождать. Если данных нет — предложи сначала собрать их через "
    "ops (scrape_and_save_tool). Отвечай на русском, кратко и по делу."
)

DEFAULT_CHARTS_SYSTEM = (
    "Ты — помощник по визуализации цен на авиабилеты. По запросу пользователя "
    "строй диаграммы через visualize_prices_tool для указанного маршрута и даты. "
    "После генерации сообщи, что графики сохранены в каталог /charts, и коротко "
    "поясни, что на них видно. Отвечай на русском."
)

DEFAULT_OPS_SYSTEM = (
    "Ты — оператор системы мониторинга цен на авиабилеты. Ты управляешь "
    "внутренней функциональностью, доступной в CLI:\n"
    "- разовый сбор данных: scrape_and_save_tool;\n"
    "- список отслеживаемых маршрутов (watchlist): add_to_watchlist_tool, "
    "remove_from_watchlist_tool, list_watchlist_tool;\n"
    "- ФОНОВЫЙ непрерывный мониторинг: start_monitor_tool (один маршрут), "
    "start_watchlist_monitor_tool (весь watchlist), stop_monitor_tool, "
    "list_active_monitors_tool.\n"
    "Непрерывный мониторинг ВСЕГДА запускается в фоне и сразу возвращает "
    "управление — не обещай пользователю «бесконечный» вызов. Для остановки "
    "сначала покажи активные мониторы через list_active_monitors_tool, чтобы "
    "узнать ключ. Даты — в формате YYYY-MM-DD, коды городов — IATA (MOW, LED, "
    "AER, SVX, KZN, OVB). ОБЯЗАТЕЛЬНО вызывай инструменты, а не описывай их. "
    "Отвечай на русском."
)


# --- Фабрики субагентов ------------------------------------------------------
@lru_cache(maxsize=16)
def make_analysis_agent(
    model: str | None = None,
    temperature: float = 0.0,
    system_prompt: str = DEFAULT_ANALYSIS_SYSTEM,
):
    """Специалист 1: анализ временных рядов цен и выводы."""
    return create_agent(
        make_model(model, temperature),
        tools=ANALYSIS_TOOLS,
        system_prompt=system_prompt,
    )


@lru_cache(maxsize=16)
def make_charts_agent(
    model: str | None = None,
    temperature: float = 0.0,
    system_prompt: str = DEFAULT_CHARTS_SYSTEM,
):
    """Специалист 2: построение диаграмм."""
    return create_agent(
        make_model(model, temperature),
        tools=CHARTS_TOOLS,
        system_prompt=system_prompt,
    )


@lru_cache(maxsize=16)
def make_ops_agent(
    model: str | None = None,
    temperature: float = 0.0,
    system_prompt: str = DEFAULT_OPS_SYSTEM,
):
    """Специалист 3: внутренняя функциональность (scrape / watchlist / фоновый мониторинг)."""
    return create_agent(
        make_model(model, temperature),
        tools=OPS_TOOLS,
        system_prompt=system_prompt,
    )
