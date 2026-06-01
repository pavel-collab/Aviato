"""Фоновый мониторинг цен для агентного графа.

Зачем отдельный модуль: инструменты ``monitor_prices`` / ``monitor_watchlist``
из ``cli/lib.py`` — это БЕСКОНЕЧНЫЕ блокирующие циклы (``while True: ... sleep``).
В CLI это нормально (Ctrl+C останавливает), но внутри ``langgraph dev`` сервера
вызов такого инструмента из узла графа заблокировал бы прогон НАВСЕГДА — узел
никогда не вернёт управление, и Studio «зависнет».

Поэтому здесь живёт ``BackgroundMonitorManager``: он запускает мониторинг в
отдельном потоке-демоне и сразу возвращает управление. Поток кооперативно
останавливается через ``threading.Event``. Это даёт ops-субагенту инструменты
start/stop/status, не блокируя граф.

Менеджер — процесс-локальный синглтон (``MONITORS``). В режиме ``langgraph dev``
и в langgraph-server потоки живут внутри процесса сервера; при перезапуске
сервера мониторы, естественно, сбрасываются (состояние не персистентное —
для фонового сбора этого достаточно).
"""

from __future__ import annotations

import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class MonitorHandle:
    """Дескриптор одного фонового монитора."""

    key: str
    description: str
    interval_minutes: int
    thread: threading.Thread
    stop_event: threading.Event
    started_at: datetime
    cycles: int = 0
    last_run: datetime | None = None
    last_error: str | None = None
    # Внутреннее: мьютекс на обновление счётчиков из потока.
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


class BackgroundMonitorManager:
    """Реестр фоновых потоков мониторинга с кооперативной остановкой."""

    def __init__(self) -> None:
        self._monitors: dict[str, MonitorHandle] = {}
        self._lock = threading.Lock()

    # --- ключи ---------------------------------------------------------------
    @staticmethod
    def route_key(origin: str, destination: str, departure_date: str) -> str:
        return f"{origin.upper()}-{destination.upper()}-{departure_date}"

    WATCHLIST_KEY = "watchlist"

    # --- запуск --------------------------------------------------------------
    def start_route(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        interval_minutes: int,
    ) -> tuple[bool, str]:
        """Запустить фоновый мониторинг одного маршрута.

        Returns:
            (started, message). started=False, если монитор уже активен.
        """
        key = self.route_key(origin, destination, departure_date)
        with self._lock:
            if key in self._monitors and self._monitors[key].thread.is_alive():
                return False, f"Monitor for {key} is already running."

            stop_event = threading.Event()
            description = f"{origin.upper()} -> {destination.upper()} on {departure_date}"
            thread = threading.Thread(
                target=self._run_route_loop,
                args=(key, origin, destination, departure_date, interval_minutes, stop_event),
                name=f"monitor-{key}",
                daemon=True,
            )
            handle = MonitorHandle(
                key=key,
                description=description,
                interval_minutes=interval_minutes,
                thread=thread,
                stop_event=stop_event,
                started_at=datetime.now(),
            )
            self._monitors[key] = handle
            thread.start()
            return True, f"Started background monitor for {description} (every {interval_minutes} min)."

    def start_watchlist(self, default_interval_minutes: int) -> tuple[bool, str]:
        """Запустить фоновый мониторинг всего watchlist."""
        key = self.WATCHLIST_KEY
        with self._lock:
            if key in self._monitors and self._monitors[key].thread.is_alive():
                return False, "Watchlist monitor is already running."

            stop_event = threading.Event()
            thread = threading.Thread(
                target=self._run_watchlist_loop,
                args=(key, default_interval_minutes, stop_event),
                name="monitor-watchlist",
                daemon=True,
            )
            handle = MonitorHandle(
                key=key,
                description="all enabled watchlist routes",
                interval_minutes=default_interval_minutes,
                thread=thread,
                stop_event=stop_event,
                started_at=datetime.now(),
            )
            self._monitors[key] = handle
            thread.start()
            return True, (
                f"Started background watchlist monitor "
                f"(default interval {default_interval_minutes} min)."
            )

    # --- остановка / статус --------------------------------------------------
    def stop(self, key: str) -> tuple[bool, str]:
        """Остановить монитор по ключу (кооперативно, через Event)."""
        with self._lock:
            handle = self._monitors.get(key)
        if handle is None:
            return False, f"No active monitor with key '{key}'."
        handle.stop_event.set()
        handle.thread.join(timeout=10.0)
        with self._lock:
            self._monitors.pop(key, None)
        return True, f"Stopped monitor '{key}'."

    def stop_all(self) -> int:
        """Остановить все мониторы. Возвращает количество остановленных."""
        with self._lock:
            keys = list(self._monitors.keys())
        for key in keys:
            self.stop(key)
        return len(keys)

    def list_active(self) -> list[dict]:
        """Снимок активных мониторов для отображения пользователю."""
        with self._lock:
            handles = list(self._monitors.values())
        result = []
        for h in handles:
            with h._lock:
                result.append(
                    {
                        "key": h.key,
                        "description": h.description,
                        "interval_minutes": h.interval_minutes,
                        "alive": h.thread.is_alive(),
                        "started_at": h.started_at.strftime("%Y-%m-%d %H:%M:%S"),
                        "cycles": h.cycles,
                        "last_run": (
                            h.last_run.strftime("%Y-%m-%d %H:%M:%S") if h.last_run else None
                        ),
                        "last_error": h.last_error,
                    }
                )
        return result

    # --- циклы потоков -------------------------------------------------------
    def _sleep_interruptible(self, stop_event: threading.Event, minutes: int) -> bool:
        """Поспать ``minutes`` минут, периодически проверяя stop_event.

        Returns True, если нужно продолжать; False, если поступил сигнал стоп.
        """
        deadline = time.monotonic() + minutes * 60
        while time.monotonic() < deadline:
            if stop_event.wait(timeout=1.0):
                return False
        return not stop_event.is_set()

    def _run_route_loop(
        self,
        key: str,
        origin: str,
        destination: str,
        departure_date: str,
        interval_minutes: int,
        stop_event: threading.Event,
    ) -> None:
        # Локальные импорты: тяжёлые зависимости (БД, scraper) грузим в потоке,
        # а не на импорте модуля.
        from aviatrade.cli.lib import scrape_and_save
        from aviatrade.db import Database

        db = Database()
        db.create_tables()

        while not stop_event.is_set():
            try:
                scrape_and_save(origin, destination, departure_date, db)
                self._mark_cycle(key)
            except Exception as exc:  # noqa: BLE001 - фоновый поток не должен падать молча
                self._mark_error(key, f"{exc}")
                traceback.print_exc()
            if not self._sleep_interruptible(stop_event, interval_minutes):
                break

    def _run_watchlist_loop(
        self,
        key: str,
        default_interval_minutes: int,
        stop_event: threading.Event,
    ) -> None:
        from aviatrade.cli.lib import scrape_and_save
        from aviatrade.db import Database

        db = Database()
        db.create_tables()

        # next_due по ключу маршрута, чтобы уважать индивидуальные интервалы.
        next_due: dict[tuple[str, str, str], float] = {}

        while not stop_event.is_set():
            try:
                routes = db.get_watchlist(enabled_only=True)
                now = time.monotonic()
                for route in routes:
                    if stop_event.is_set():
                        break
                    rkey = (route.origin, route.destination, str(route.departure_date))
                    if next_due.get(rkey, 0.0) > now:
                        continue
                    interval = route.interval_min or default_interval_minutes
                    try:
                        scrape_and_save(
                            route.origin,
                            route.destination,
                            str(route.departure_date),
                            db,
                        )
                    except Exception as exc:  # noqa: BLE001
                        self._mark_error(key, f"{route.origin}-{route.destination}: {exc}")
                        traceback.print_exc()
                    next_due[rkey] = time.monotonic() + interval * 60
                self._mark_cycle(key)
            except Exception as exc:  # noqa: BLE001
                self._mark_error(key, f"{exc}")
                traceback.print_exc()
            # Спим короткими интервалами, чтобы быстро подхватывать новые маршруты
            # и реагировать на стоп.
            if not self._sleep_interruptible(stop_event, max(1, default_interval_minutes // 2)):
                break

    # --- учёт счётчиков ------------------------------------------------------
    def _mark_cycle(self, key: str) -> None:
        with self._lock:
            handle = self._monitors.get(key)
        if handle:
            with handle._lock:
                handle.cycles += 1
                handle.last_run = datetime.now()

    def _mark_error(self, key: str, message: str) -> None:
        with self._lock:
            handle = self._monitors.get(key)
        if handle:
            with handle._lock:
                handle.last_error = message


# Процесс-локальный синглтон, которым пользуются инструменты ops-субагента.
MONITORS = BackgroundMonitorManager()
