"""Субагенты-специалисты, собранные через create_agent.

``create_agent`` (LangChain 1.0) — это «фабрика» готового ReAct-агента: ты даёшь
модель, список инструментов и системный промпт, а на выходе получаешь
СКОМПИЛИРОВАННЫЙ граф (Runnable). Внутри он сам гоняет цикл
    модель → (вызвать инструмент?) → инструмент → модель → … → ответ,
поэтому отдельный StateGraph под каждого специалиста писать не нужно.

Каждый субагент принимает на вход {"messages": [...]} и возвращает
{"messages": [...]} — тот же интерфейс, что и у узла обычного графа. Благодаря
этому в graph.py мы вставляем субагентов как обычные узлы.

Три специалиста, у каждого СУЖЕННЫЙ набор инструментов:
- analysis_agent — анализ временных рядов цен и выводы (ANALYSIS_TOOLS);
- charts_agent   — построение диаграмм (CHARTS_TOOLS);
- ops_agent      — внутренняя функциональность: скрапинг, watchlist,
                   фоновый мониторинг (OPS_TOOLS).

ВАЖНО про Runtime[Context]: субагенты НЕ создаются как глобалы на импорте.
Вместо этого здесь лежат фабрики make_*_agent(model, temperature, system_prompt).
Узлы графа вызывают их с параметрами из ``runtime.context``, поэтому системный
промпт и модель можно подменять на лету, без перезапуска процесса. Фабрики
обёрнуты в lru_cache: при одинаковых параметрах агент собирается один раз и
переиспользуется (агенты не хранят состояние между вызовами).
"""

from __future__ import annotations

import os
from functools import lru_cache

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from aviatrade.agent.tools import ANALYSIS_TOOLS, CHARTS_TOOLS, OPS_TOOLS


def make_model(model: str | None = None, temperature: float = 0.0) -> ChatOpenAI:
    """Создать клиент модели через OpenRouter (как в текущем проекте AviaTrade).

    api_key берётся из OPENROUTER_API_KEY, base_url указывает на портал
    OpenRouter. Имя модели можно переопределить аргументом ``model`` (приходит
    из Context); если он не задан — берётся MODEL_NAME из окружения, по
    умолчанию ``openai/gpt-4o-mini``.
    """
    return ChatOpenAI(
        model=model or os.getenv("MODEL_NAME", "openai/gpt-4o-mini"),
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1",
        temperature=temperature,
    )


# --- Системные промпты по умолчанию -----------------------------------------
# Вынесены в константы, чтобы служить дефолтом, когда Context их не переопределяет.

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
# lru_cache: одинаковые (model, temperature, system_prompt) → тот же агент.
# Аргументы хэшируемы (строки/число/None), поэтому кэш работает корректно.


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
