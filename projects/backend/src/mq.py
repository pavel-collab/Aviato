"""RabbitMQ (публикация chat-job) + Redis (статусы/результаты задач).

Поток chat-задач:
    POST /agent/chat/async → publish_job() → RabbitMQ (job_queue) → worker
        → run_graph() → set_job()
    GET  /jobs/{id}        → get_job() (Redis)

Задачи скрапинга идут в ОТДЕЛЬНУЮ очередь (scrape_queue) и публикуются через
``shared.services.publish_scrape`` прямо из ручки /scrape — здесь не дублируется.
Статус скрап-задач пишет сам сервис-скрапер (тот же формат job:{id} в Redis).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import aio_pika
import redis.asyncio as aioredis

from src.config import config

_amqp_connection: aio_pika.abc.AbstractRobustConnection | None = None
_amqp_channel: aio_pika.abc.AbstractChannel | None = None
_amqp_lock = asyncio.Lock()


async def _channel() -> aio_pika.abc.AbstractChannel:
    global _amqp_connection, _amqp_channel
    if _amqp_channel is not None and not _amqp_channel.is_closed:
        return _amqp_channel
    async with _amqp_lock:
        if _amqp_channel is not None and not _amqp_channel.is_closed:
            return _amqp_channel
        _amqp_connection = await aio_pika.connect_robust(config.rabbitmq.url)
        _amqp_channel = await _amqp_connection.channel()
        await _amqp_channel.declare_queue(config.rabbitmq.job_queue, durable=True)
    return _amqp_channel


async def publish_job(job_id: str, job_type: str, payload: dict[str, Any]) -> None:
    """Положить chat-задачу в durable-очередь job_queue (persistent-сообщение)."""
    channel = await _channel()
    await channel.default_exchange.publish(
        aio_pika.Message(
            body=json.dumps(
                {"job_id": job_id, "type": job_type, "payload": payload}
            ).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        ),
        routing_key=config.rabbitmq.job_queue,
    )


# --- Redis ------------------------------------------------------------------
_redis_client: aioredis.Redis | None = None


def _redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(config.redis.url, decode_responses=True)
    return _redis_client


async def set_job(job_id: str, payload: dict) -> None:
    await _redis().set(f"job:{job_id}", json.dumps(payload, default=str), ex=3600)


async def get_job(job_id: str) -> dict | None:
    raw = await _redis().get(f"job:{job_id}")
    return json.loads(raw) if raw else None


async def aclose_mq() -> None:
    global _amqp_connection, _amqp_channel, _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
    if _amqp_connection is not None:
        await _amqp_connection.close()
        _amqp_connection = None
        _amqp_channel = None
