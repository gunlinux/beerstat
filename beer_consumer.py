import asyncio
import datetime
import logging

import aiohttp
from aiohttp.client_exceptions import ClientConnectorError

from requeue.requeue import Queue
from requeue.rredis import RedisConnection
from requeue.models import QueueMessage, QueueEvent

from app import settings

logger = logging.getLogger(__name__)


class BeerConsumer:
    def __init__(self, donate_url: str) -> None:
        self.donate_url = donate_url

    async def on_message(self, message: QueueMessage) -> QueueMessage:
        logger.debug("%s process %s", __name__, message.data)
        if message.data.event_type != "DONATION" or not message.data.amount:
            message.finish()
            return message

        if message.data.currency != "RUB":
            message.data.recal_amount(currencies=settings.currencies)

        stat_data = self._from_queue_event_to_bs(message.data)

        payload = {
            "date": datetime.datetime.now().isoformat(),
            "value": stat_data.get("value", 0),
            "name": stat_data.get("name", ""),
        }
        headers = {
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    self.donate_url, json=payload, headers=headers
                ) as response:
                    await response.json()
                    message.finish()
                    return message
            except ClientConnectorError:
                logger.warning("cant connect to bs service")
        return message

    def _from_queue_event_to_bs(self, event: QueueEvent) -> dict[str, int | str | None]:
        message: dict[str, int | str | None] = {
            "value": int(event.amount) if event.amount else 0,
            "name": event.user_name,
        }
        return message


async def main() -> None:
    beer_consumer: BeerConsumer = BeerConsumer(donate_url=settings.BEER_URL)
    async with RedisConnection(settings.redis_url) as redis_connection:
        queue: Queue = Queue(name=settings.BEER_STAT, connection=redis_connection)
        await queue.consumer(on_message=beer_consumer.on_message)


if __name__ == "__main__":
    asyncio.run(main())
