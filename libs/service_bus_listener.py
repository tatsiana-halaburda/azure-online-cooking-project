"""Background Service Bus queue reader for Inventory (Practice 3)."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from typing import Any

from libs import service_bus as sb

logger = logging.getLogger(__name__)


def _message_body_to_bytes(body: Any) -> bytes:
    if isinstance(body, (bytes, bytearray)):
        return bytes(body)
    if isinstance(body, memoryview):
        return body.tobytes()
    return b"".join(bytes(chunk) if isinstance(chunk, (bytes, bytearray)) else memoryview(chunk).tobytes() for chunk in body)


# Last events for quick verification (e.g. GET /service-bus/recent-events)
_recent: deque[dict[str, Any]] = deque(maxlen=50)


def recent_events() -> list[dict[str, Any]]:
    return list(_recent)


async def _receive_batch() -> None:
    conn = sb.listen_connection_string()
    q = sb.queue_name()
    if not conn or not q:
        return

    from azure.servicebus.aio import ServiceBusClient

    async with ServiceBusClient.from_connection_string(conn) as client:
        async with client.get_queue_receiver(queue_name=q, max_wait_time=8) as receiver:
            async for msg in receiver:
                try:
                    raw = _message_body_to_bytes(msg.body)
                    text = raw.decode("utf-8")
                    data = json.loads(text)
                    _recent.append({"message": data})
                    logger.info("Service Bus message received: %s", data)
                    await receiver.complete_message(msg)
                except Exception:
                    logger.exception("Service Bus message handling failed; abandoning message")
                    await receiver.abandon_message(msg)


async def poll_queue_forever(stop: asyncio.Event) -> None:
    conn = sb.listen_connection_string()
    q = sb.queue_name()
    if not conn or not q:
        logger.info(
            "Service Bus listener not started: set AZURE_SERVICEBUS_LISTEN_CONNECTION_STRING "
            "and AZURE_SERVICEBUS_QUEUE_NAME (same queue name as the sender)"
        )
        await stop.wait()
        return

    interval = sb.poll_interval_seconds()
    logger.info("Service Bus listener started (queue=%s, poll interval=%ss)", q, interval)
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            break
        except TimeoutError:
            pass
        if stop.is_set():
            break
        try:
            await _receive_batch()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Service Bus receive cycle failed")
    logger.info("Service Bus listener stopped")
