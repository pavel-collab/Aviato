"""RabbitMQ consumer: задача scrape_tasks → сбор через botasaurus → запись в БД.

Масштабируется горизонтально: несколько реплик сервиса слушают одну durable-
очередь (competing consumers), prefetch_count=1 — по одной задаче на реплику за
раз (браузер тяжёлый). Если в задаче есть ``job_id`` — статус/результат пишется в
Redis (формат совместим с ``backend`` GET /jobs/{id}).
"""

from __future__ import annotations

import asyncio
import json

import aio_pika
import redis.asyncio as aioredis
from loguru import logger

from shared.scraper import ScrapeTask
from shared.services import get_database, scrape_and_save_local
from src.config import config


async def _set_job(redis: aioredis.Redis, job_id: str, payload: dict) -> None:
    await redis.set(f"job:{job_id}", json.dumps(payload, default=str), ex=3600)


class ScraperConsumer:
    """Потребитель очереди задач скрапинга с кооперативной остановкой."""

    def __init__(self) -> None:
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._redis = aioredis.from_url(config.redis.url, decode_responses=True)
        # Один Database на DSN (фабрика кэширует + создаёт таблицы).
        self._db = get_database(config.database)

    async def _handle(self, message: aio_pika.abc.AbstractIncomingMessage) -> None:
        # Подтверждаем (ack) при выходе из блока — ошибку скрапинга НЕ переотправляем
        # бесконечно: фиксируем её в статусе задачи и ack-аем.
        async with message.process(requeue=False):
            data = json.loads(message.body)
            task = ScrapeTask(**data)
            logger.info(f"[scraper] task: {task.origin}->{task.destination} {task.departure_date}")

            if task.job_id:
                await _set_job(self._redis, task.job_id, {"status": "running", "saved_count": 0})
            try:
                # Скрапинг блокирующий (браузер) — уводим в отдельный поток.
                saved = await asyncio.to_thread(
                    scrape_and_save_local,
                    task.origin,
                    task.destination,
                    task.departure_date,
                    self._db,
                )
                if task.job_id:
                    await _set_job(
                        self._redis, task.job_id, {"status": "done", "saved_count": saved}
                    )
                logger.info(f"[scraper] done: saved {saved} flights")
            except Exception as exc:  # noqa: BLE001 - фиксируем и ack-аем, без бесконечного requeue
                if task.job_id:
                    await _set_job(
                        self._redis,
                        task.job_id,
                        {"status": "error", "saved_count": 0, "error": str(exc)},
                    )
                logger.error(f"[scraper] error: {exc}")

    async def start(self) -> None:
        self._connection = await aio_pika.connect_robust(config.rabbitmq.url)
        channel = await self._connection.channel()
        await channel.set_qos(prefetch_count=config.prefetch_count)
        queue = await channel.declare_queue(config.rabbitmq.scrape_queue, durable=True)
        await queue.consume(self._handle)
        logger.info(f"[scraper] listening on queue '{config.rabbitmq.scrape_queue}'…")

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
        await self._redis.aclose()
