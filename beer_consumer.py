import asyncio
import datetime
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp
from faststream import AckPolicy, FastStream
from faststream.rabbit import RabbitBroker, RabbitQueue
from faststream.rabbit.annotations import RabbitMessage
from pydantic import BaseModel

from app import settings

logger = logging.getLogger(__name__)


class QueueEvent(BaseModel):
    event_type: str
    billing_system: str | None = None
    user_name: str | None = None
    amount: float | None = None
    currency: str | None = None
    message: str | None = None
    raw_payload: dict[str, Any] | None = None


class QueueMessage(BaseModel):
    event: str
    data: QueueEvent
    source: str = ""


class BeerConsumer:
    def __init__(self, donate_url: str) -> None:
        self.donate_url = donate_url

    async def on_message(self, message: QueueMessage) -> None:
        logger.debug("%s process %s", __name__, message.data)
        if message.data.event_type != "DONATION" or not message.data.amount:
            return

        stat_data = self._from_queue_event_to_bs(message.data)

        payload = {
            "date": datetime.datetime.now(datetime.UTC).isoformat(),
            "value": stat_data.get("value", 0),
            "name": stat_data.get("name", ""),
        }
        headers = {
            "Content-Type": "application/json",
        }
        async with (
            aiohttp.ClientSession() as session,
            session.post(self.donate_url, json=payload, headers=headers) as response,
        ):
            response.raise_for_status()
            await response.json()

    def _from_queue_event_to_bs(self, event: QueueEvent) -> dict[str, int | str | None]:
        message: dict[str, int | str | None] = {
            "value": round(event.amount) if event.amount else 0,
            "name": event.user_name,
        }
        return message


async def process_message(
    on_message: Callable[[QueueMessage], Awaitable[None]],
    message: QueueMessage,
    msg: RabbitMessage,
) -> None:
    try:
        await on_message(message)
    except Exception:
        logger.exception("worker function failed")
        await msg.reject()
    else:
        await msg.ack()


async def main() -> None:
    broker = RabbitBroker(settings.rabbit_url, virtualhost="gunlinux_bot")
    app = FastStream(broker)
    consumer = BeerConsumer(donate_url=settings.BEER_URL)

    @broker.subscriber(
        queue=RabbitQueue(
            settings.BEER_STAT,
            auto_delete=False,
            durable=True,
            arguments={
                "x-dead-letter-exchange": "dlq",
                "x-dead-letter-routing-key": f"{settings.BEER_STAT}.dlq",
            },
        ),
        ack_policy=AckPolicy.MANUAL,
    )
    async def handler(message: QueueMessage, msg: RabbitMessage) -> None:
        await process_message(consumer.on_message, message, msg)

    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
