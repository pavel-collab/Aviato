"""Worker — мост между RabbitMQ и тяжёлой работой.

Слушает прикладную очередь RabbitMQ и на каждую задачу делает одно из:

- ``type == "scrape"`` → ``actions.run_scrape`` (браузерный скрапинг Aviasales);
- ``type == "chat"``   → ``lg_client.run_graph`` (прогон графа агента через SDK).

Результат кладётся в Redis под ``job_id``. Это отдельный процесс/контейнер: так
HTTP-ручка backend развязывается с тяжёлой работой и не блокируется.

Запуск: ``python -m aviatrade.backend.worker``
"""

from __future__ import annotations

import asyncio
import json

import aio_pika
from starlette.concurrency import run_in_threadpool

from . import actions
from .config import settings
from .lg_client import aclose_client, run_graph
from .mq import aclose_mq, set_job


async def _execute(job_type: str, payload: dict) -> dict:
    """Выполнить одну задачу по её типу и вернуть полезную нагрузку результата."""
    if job_type == "scrape":
        # Скрапинг блокирующий (браузер) → уводим в пул потоков, чтобы не
        # держать event loop воркера.
        return await run_in_threadpool(
            actions.run_scrape,
            payload["origin"],
            payload["destination"],
            payload["departure_date"],
        )
    if job_type == "chat":
        answer = await run_graph(payload["message"])
        return {"answer": answer}
    raise ValueError(f"unknown job type: {job_type!r}")


async def _handle(message: aio_pika.abc.AbstractIncomingMessage) -> None:
    # message.process() подтвердит (ack) сообщение при успехе и вернёт в очередь
    # при исключении — задача не потеряется.
    async with message.process():
        data = json.loads(message.body)
        job_id = data["job_id"]
        job_type = data.get("type", "chat")
        payload = data.get("payload", {})
        await set_job(job_id, {"status": "running", "type": job_type, "result": None})
        try:
            result = await _execute(job_type, payload)
            await set_job(
                job_id, {"status": "done", "type": job_type, "result": result}
            )
        except Exception as exc:  # демо: фиксируем ошибку в статусе задачи
            await set_job(
                job_id,
                {"status": "error", "type": job_type, "result": None, "error": str(exc)},
            )


async def main() -> None:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    try:
        channel = await connection.channel()
        # Скрапинг тяжёлый (браузер) — не берём много задач разом.
        await channel.set_qos(prefetch_count=2)
        queue = await channel.declare_queue(settings.job_queue, durable=True)
        await queue.consume(_handle)
        print(f"[worker] слушаю очередь '{settings.job_queue}'…")
        await asyncio.Future()  # блокируемся навсегда
    finally:
        await aclose_client()
        await aclose_mq()
        await connection.close()


if __name__ == "__main__":
    asyncio.run(main())
