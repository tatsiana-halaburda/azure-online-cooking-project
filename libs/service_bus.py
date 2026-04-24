"""Azure Service Bus queue helpers (Practice 3)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def queue_name() -> str:
    return os.getenv("AZURE_SERVICEBUS_QUEUE_NAME", "").strip()


def send_connection_string() -> str:
    return os.getenv("AZURE_SERVICEBUS_SEND_CONNECTION_STRING", "").strip()


def listen_connection_string() -> str:
    return os.getenv("AZURE_SERVICEBUS_LISTEN_CONNECTION_STRING", "").strip()


def poll_interval_seconds() -> float:
    raw = os.getenv("AZURE_SERVICEBUS_POLL_INTERVAL_SECONDS", "5").strip() or "5"
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 5.0


def send_json_message(payload: dict[str, Any]) -> bool:
    """
    Send one JSON message to the queue. Returns True if sent, False if skipped (missing config) or on failure.
    """
    conn = send_connection_string()
    q = queue_name()
    if not conn or not q:
        logger.debug("Service Bus send skipped: set AZURE_SERVICEBUS_SEND_CONNECTION_STRING and AZURE_SERVICEBUS_QUEUE_NAME")
        return False
    try:
        from azure.servicebus import ServiceBusClient, ServiceBusMessage

        body = json.dumps(payload, default=str)
        with ServiceBusClient.from_connection_string(conn) as client:
            with client.get_queue_sender(q) as sender:
                sender.send_messages(ServiceBusMessage(body))
        return True
    except Exception:
        logger.exception("Service Bus send failed; order was still persisted")
        return False
