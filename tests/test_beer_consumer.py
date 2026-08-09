from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import pytest

from beer_consumer import (
    BeerConsumer,
    QueueEvent,
    QueueMessage,
    process_message,
)


class TestFromQueueEventToBs:
    def test_converts_amount_to_int(self) -> None:
        consumer = BeerConsumer(donate_url="http://example.com/donate")
        event = QueueEvent(event_type="DONATION", user_name="test_user", amount=100.5)
        result = consumer._from_queue_event_to_bs(event)
        assert result == {"value": 100, "name": "test_user"}

    def test_rounds_fractional_amount(self) -> None:
        consumer = BeerConsumer(donate_url="http://example.com/donate")
        event = QueueEvent(event_type="DONATION", amount=100.6)
        result = consumer._from_queue_event_to_bs(event)
        assert result == {"value": 101, "name": None}

    def test_handles_none_amount(self) -> None:
        consumer = BeerConsumer(donate_url="http://example.com/donate")
        event = QueueEvent(event_type="DONATION", amount=None)
        result = consumer._from_queue_event_to_bs(event)
        assert result == {"value": 0, "name": None}

    def test_handles_none_user_name(self) -> None:
        consumer = BeerConsumer(donate_url="http://example.com/donate")
        event = QueueEvent(event_type="DONATION", amount=50.0, user_name=None)
        result = consumer._from_queue_event_to_bs(event)
        assert result == {"value": 50, "name": None}

    def test_handles_zero_amount(self) -> None:
        consumer = BeerConsumer(donate_url="http://example.com/donate")
        event = QueueEvent(event_type="DONATION", amount=0)
        result = consumer._from_queue_event_to_bs(event)
        assert result == {"value": 0, "name": None}


class TestOnMessage:
    @pytest.mark.asyncio
    async def test_skips_non_donation_event_type(self) -> None:
        consumer = BeerConsumer(donate_url="http://example.com/donate")
        event = QueueEvent(event_type="SUBSCRIBE", amount=100.0)
        message = QueueMessage(event="test_event", data=event)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            await consumer.on_message(message)
            mock_session_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_missing_amount(self) -> None:
        consumer = BeerConsumer(donate_url="http://example.com/donate")
        event = QueueEvent(event_type="DONATION", amount=None)
        message = QueueMessage(event="test_event", data=event)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            await consumer.on_message(message)
            mock_session_cls.assert_not_called()

    def _make_mock_post_response(
        self, json_return: dict[str, Any] | None = None
    ) -> Mock:
        mock_response = Mock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_response.raise_for_status = Mock(return_value=None)
        mock_response.json = AsyncMock(
            return_value=(
                json_return if json_return is not None else {"message": "Success"}
            )
        )
        return mock_response

    def _make_mock_session(self, post_return: Mock) -> Mock:
        mock_session = Mock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.post = Mock(return_value=post_return)
        return mock_session

    @pytest.mark.asyncio
    async def test_posts_to_donate_url_on_valid_donation(self) -> None:
        consumer = BeerConsumer(donate_url="http://example.com/donate")
        event = QueueEvent(event_type="DONATION", user_name="Cher_cash", amount=100.5)
        message = QueueMessage(event="test_event", data=event)

        mock_response = self._make_mock_post_response()
        mock_session = self._make_mock_session(mock_response)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            await consumer.on_message(message)

        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert call_args[0][0] == "http://example.com/donate"
        payload = call_args[1]["json"]
        assert payload["value"] == 100
        assert payload["name"] == "Cher_cash"
        assert "date" in payload

    @pytest.mark.asyncio
    async def test_raises_on_http_error_status(self) -> None:
        consumer = BeerConsumer(donate_url="http://example.com/donate")
        event = QueueEvent(event_type="DONATION", amount=100.0)
        message = QueueMessage(event="test_event", data=event)

        mock_response = self._make_mock_post_response()
        mock_response.raise_for_status = Mock(
            side_effect=aiohttp.ClientResponseError(
                request_info=Mock(), history=(), status=500
            )
        )
        mock_session = self._make_mock_session(mock_response)

        with (
            patch("aiohttp.ClientSession", return_value=mock_session),
            pytest.raises(aiohttp.ClientResponseError),
        ):
            await consumer.on_message(message)

        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_zero_amount(self) -> None:
        consumer = BeerConsumer(donate_url="http://example.com/donate")
        event = QueueEvent(event_type="DONATION", amount=0.0)
        message = QueueMessage(event="test_event", data=event)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            await consumer.on_message(message)
            mock_session_cls.assert_not_called()


class StubWorker:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.processed: list[QueueMessage] = []

    async def on_message(self, message: QueueMessage) -> None:
        self.processed.append(message)
        if self.error is not None:
            raise self.error


class TestProcessMessage:
    @pytest.mark.asyncio
    async def test_acks_on_success(self) -> None:
        message = QueueMessage(event="DONATION", data=QueueEvent(event_type="DONATION"))
        worker = StubWorker()
        msg = Mock()
        msg.ack = AsyncMock()
        msg.reject = AsyncMock()

        await process_message(worker.on_message, message, msg)

        assert worker.processed == [message]
        msg.ack.assert_awaited_once()
        msg.reject.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rejects_on_worker_error(self) -> None:
        message = QueueMessage(event="DONATION", data=QueueEvent(event_type="DONATION"))
        worker = StubWorker(error=RuntimeError("boom"))
        msg = Mock()
        msg.ack = AsyncMock()
        msg.reject = AsyncMock()

        await process_message(worker.on_message, message, msg)

        msg.reject.assert_awaited_once()
        msg.ack.assert_not_awaited()


class TestQueueEventModel:
    def test_parses_minimal_valid_event(self) -> None:
        data: dict[str, Any] = {"event_type": "DONATION"}
        event = QueueEvent(**data)
        assert event.event_type == "DONATION"
        assert event.amount is None
        assert event.user_name is None

    def test_parses_full_event_with_raw_payload(self) -> None:
        data = {
            "event_type": "DONATION",
            "billing_system": "stripe",
            "user_name": "test_user",
            "amount": 50.0,
            "currency": "USD",
            "message": "thanks!",
            "raw_payload": {"nested": "data"},
        }
        event = QueueEvent(**data)
        assert event.billing_system == "stripe"
        assert event.raw_payload == {"nested": "data"}

    def test_tolerates_producer_event_key(self) -> None:
        # newdonats (the producer) always emits `data.event: null`; the renamed
        # model drops the legacy key without failing validation.
        data: dict[str, Any] = {
            "event_type": "DONATION",
            "amount": 100.0,
            "event": None,
        }
        event = QueueEvent(**data)
        assert event.raw_payload is None


class TestQueueMessageModel:
    def test_parses_queue_message(self) -> None:
        data = {
            "event": "test_event",
            "data": {"event_type": "DONATION", "amount": 100.0},
            "source": "test_source",
        }
        message = QueueMessage(**data)
        assert message.event == "test_event"
        assert isinstance(message.data, QueueEvent)
        assert message.data.event_type == "DONATION"
        assert message.source == "test_source"

    def test_default_source_is_empty(self) -> None:
        data = {
            "event": "test_event",
            "data": {"event_type": "DONATION"},
        }
        message = QueueMessage(**data)
        assert message.source == ""
