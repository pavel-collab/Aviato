"""Worker — мост между RabbitMQ (job_queue) и графом агента.

После выноса скрапинга в отдельный сервис worker обрабатывает ТОЛЬКО chat-задачи
(асинхронный путь /agent/chat/async): прогоняет граф через SDK и кладёт ответ в
Redis. Скрапинг-задачи идут в отдельную очередь scrape_queue → сервис scraper.

Запуск: python -m src.worker
"""

from __future__ import annotations

import asyncio
import json

import aio_pika

from src.config import config
from src.lg_client import aclose_client, run_graph
from src.mq import aclose_mq, set_job


async def _execute(job_type: str, payload: dict) -> dict:
    if job_type == "chat":
        answer = await run_graph(payload["message"])
        return {"answer": answer}
    raise ValueError(f"unknown job type: {job_type!r}")


async def _handle(message: aio_pika.abc.AbstractIncomingMessage) -> None:
    async with message.process():
        data = json.loads(message.body)
        job_id = data["job_id"]
        job_type = data.get("type", "chat")
        payload = data.get("payload", {})
        await set_job(job_id, {"status": "running", "type": job_type, "result": None})
        try:
            result = await _execute(job_type, payload)
            await set_job(job_id, {"status": "done", "type": job_type, "result": result})
        except Exception as exc:  # демо: фиксируем ошибку в статусе задачи
            await set_job(
                job_id,
                {"status": "error", "type": job_type, "result": None, "error": str(exc)},
            )


async def main() -> None:
    connection = await aio_pika.connect_robust(config.rabbitmq.url)
    try:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=4)
        queue = await channel.declare_queue(config.rabbitmq.job_queue, durable=True)
        await queue.consume(_handle)
        print(f"[worker] слушаю очередь '{config.rabbitmq.job_queue}'…")
        await asyncio.Future()
    finally:
        await aclose_client()
        await aclose_mq()
        await connection.close()


if __name__ == "__main__":
    asyncio.run(main())
