"""Единое логирование AviaTrade на loguru (по образцу retrieval-experiments).

`setup_logging()` настраивает единый sink loguru на stdout и перехватывает весь
стандартный `logging` (включая SQLAlchemy/uvicorn/aio_pika) через
`InterceptHandler`, чтобы всё шло в одном формате. Библиотеки (`shared.*`) просто
импортируют `from loguru import logger` и пишут логи; сервисы (`projects/*`,
`scripts/`) один раз в точке входа вызывают `setup_logging(...)`.

`LogLevel` — pydantic-совместимый enum: его можно использовать как тип поля в
настройках (принимает строку `"INFO"`/`"debug"` или число из YAML).
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Iterable
from enum import Enum
from pathlib import Path
from types import NoneType
from typing import Any

from loguru import logger
from pydantic_core import CoreSchema, PydanticCustomError, core_schema


class LogLevel(Enum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50

    @classmethod
    def validate_log_level(cls, value: str | int | LogLevel) -> LogLevel:
        if isinstance(value, LogLevel):
            return value
        if isinstance(value, str):
            try:
                return cls[value.upper()]
            except KeyError as e:
                raise PydanticCustomError(
                    "log_level_invalid",
                    f"Invalid log level string '{value}', expected one of: "
                    f"{', '.join([e.name for e in cls])}",  # pyright: ignore [reportArgumentType]
                ) from e
        elif isinstance(value, int):
            for level in cls:
                if level.value == value:
                    return level
            raise PydanticCustomError(
                "log_level_invalid",
                f"Invalid log level integer '{value}', expected one of: "
                f"{', '.join([str(e.value) for e in cls])}",  # pyright: ignore [reportArgumentType]
            )

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: type, handler) -> CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls.validate_log_level,
            core_schema.union_schema([core_schema.str_schema(), core_schema.int_schema()]),
        )


class InterceptHandler(logging.Handler):
    """Перенаправляет записи стандартного `logging` в loguru."""

    def __init__(self, level: int = logging.NOTSET, excluded_loggers_set: set[str] | None = None):
        super().__init__(level)
        self.excluded_loggers = excluded_loggers_set or set()

    def emit(self, record: logging.LogRecord):
        if record.name in self.excluded_loggers:
            return

        # Шумные INFO-сообщения SQLAlchemy понижаем до DEBUG.
        if record.name.startswith("sqlalchemy") and record.levelno == logging.INFO:
            record.levelno = logging.DEBUG
            record.levelname = "DEBUG"

        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelname

        _frame = logging.currentframe()
        _depth = 1

        if _frame:
            _caller_frame = _frame.f_back
            while _caller_frame and _caller_frame.f_code.co_filename == logging.__file__:
                _caller_frame = _caller_frame.f_back
                _depth += 1

        # rel_path / _formatted_params обязательны, иначе формат sink-а упадёт с KeyError.
        extra = {"original_std_record": record, "rel_path": "intercepted_log", "_formatted_params": ""}
        logger.opt(depth=_depth, exception=record.exc_info, lazy=True).bind(**extra).log(
            level, record.getMessage()
        )


def format_value_for_log(value: Any) -> str:
    if isinstance(value, (int, float, bool, NoneType)):
        return str(value)
    if isinstance(value, str):
        return f"'{value}'"
    if isinstance(value, (list, tuple, set)):
        if isinstance(value, list):
            opening_bracket = "["
            closing_bracket = "]"
        elif isinstance(value, tuple):
            opening_bracket = "("
            closing_bracket = ")"
        else:  # set
            opening_bracket = "{"
            closing_bracket = "}"
        formatted_items = [format_value_for_log(item) for item in value]
        items_str = ",".join(formatted_items)
        return f"{opening_bracket}{items_str}{closing_bracket}"
    if isinstance(value, dict):
        formatted_pairs = []
        for k, v in value.items():
            formatted_key = k if isinstance(k, str) else str(k)
            formatted_value = format_value_for_log(v)
            formatted_pairs.append(f"'{formatted_key}':{formatted_value}")
        pairs_str = ",".join(formatted_pairs)
        return f"{{{pairs_str}}}"
    return str(value)


def format_extra_params(extra: dict[str, Any]) -> str:
    skip_keys = {"framework", "rel_path", "logger_name", "original_std_record"}
    params = []
    for key, value in extra.items():
        if key not in skip_keys and not key.startswith("_"):
            formatted_value = format_value_for_log(value)
            params.append(f"{key}={formatted_value}")
    return " | " + " | ".join(params) if params else ""


def setup_logging(
    log_level: LogLevel | None = None,
    excluded_loggers: Iterable[str] | None = None,
) -> None:
    """Настроить loguru-sink на stdout и перехватить стандартный logging.

    `log_level` — уровень; если None, берётся из переменной окружения
    ``LOG_LEVEL`` (по умолчанию INFO). Сервисы AviaTrade передают сюда
    ``config.logging.level`` из YAML.
    """
    if log_level is None:
        env_log_level = os.environ.get("LOG_LEVEL", "INFO")
        log_level = LogLevel.validate_log_level(env_log_level)

    logger.remove()
    project_root = str(Path(os.getcwd()).absolute())

    excluded_set_for_handler = set(excluded_loggers) if excluded_loggers else set()

    the_intercept_handler = InterceptHandler(excluded_loggers_set=excluded_set_for_handler)

    @logger.catch(message="Error in loguru patcher function:")
    def universal_patcher(record_dict):
        if not record_dict["message"] or not str(record_dict["message"]).strip():
            return False

        original_std_record: logging.LogRecord | None = record_dict["extra"].get(
            "original_std_record"
        )
        is_intercepted_std_log = original_std_record is not None

        if is_intercepted_std_log:
            record_dict["extra"]["framework"] = original_std_record.name
        else:
            loguru_file_info = record_dict.get("file")
            if loguru_file_info and loguru_file_info.path:
                filepath = loguru_file_info.path
                if filepath.startswith(project_root):
                    record_dict["extra"]["rel_path"] = filepath[len(project_root) + 1 :]
                else:
                    record_dict["extra"]["rel_path"] = filepath
            else:
                record_dict["extra"]["rel_path"] = "unknown_file"

            record_dict["extra"].setdefault("rel_path", "unknown_path")
            record_dict["extra"]["_formatted_params"] = format_extra_params(record_dict["extra"])

        return True

    logger.configure(patcher=universal_patcher)  # pyright: ignore [reportArgumentType]

    common_sink_kwargs = {
        "level": log_level.value,
        "colorize": True,
        "enqueue": False,  # без межпроцессной очереди — избегаем проблем с pickling
    }

    logger.add(
        sys.stdout,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level}</level> | "
            "<cyan>{extra[rel_path]}:{line}</cyan> <cyan>{function}</cyan> | "
            "<level>{message}</level>"
            "{extra[_formatted_params]}"
        ),
        filter=lambda record: "framework" not in record["extra"],
        **common_sink_kwargs,
    )

    logger.add(
        sys.stdout,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level}</level> | "
            "<cyan>{extra[framework]}</cyan> <level>{message}</level>"
        ),
        filter=lambda record: bool(record["extra"].get("framework")),
        **common_sink_kwargs,
    )

    # Перехват стандартного logging.
    logging.captureWarnings(True)
    logging.basicConfig(handlers=[the_intercept_handler], level=log_level.value, force=True)
    all_stdlib_logger_names = list(logging.root.manager.loggerDict.keys())

    for name in all_stdlib_logger_names:
        if name == "" or name == "loguru":
            continue

        logger_obj = logging.getLogger(name)

        current_level_for_logger = log_level.value
        if name == "py.warnings":
            current_level_for_logger = max(logging.WARNING, log_level.value)
        logger_obj.setLevel(current_level_for_logger)

        if name in excluded_set_for_handler:
            logger_obj.handlers = [
                h for h in logger_obj.handlers if not isinstance(h, InterceptHandler)
            ]
            if not logger_obj.handlers:
                logger_obj.propagate = True
        else:
            logger_obj.handlers = [the_intercept_handler]
            logger_obj.propagate = False
