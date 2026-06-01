"""Точка запуска сервиса-скрапера: старт consumer + graceful shutdown."""

from __future__ import annotations

import asyncio
import signal

from src.consumer import ScraperConsumer


async def main() -> None:
    consumer = ScraperConsumer()
    await consumer.start()

    loop = asyncio.get_running_loop()
    shutdown = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, shutdown.set)
        except NotImplementedError:  # на некоторых платформах (Windows)
            pass

    try:
        await shutdown.wait()
    finally:
        print("[scraper] shutting down…")
        await consumer.close()


if __name__ == "__main__":
    asyncio.run(main())
