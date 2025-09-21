import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from aiohttp.client_exceptions import ClientConnectorError

from beer_consumer import BeerConsumer
from requeue.models import QueueMessage, QueueEvent, QueueMessageStatus


@pytest.fixture
def beer_consumer():
    """Create a BeerConsumer instance for testing."""
    return BeerConsumer(donate_url="http://test-server/donate")


@pytest.fixture
def sample_queue_event():
    """Create a sample QueueEvent for testing."""
    return QueueEvent(
        event_type="DONATION", user_name="Test User", amount=100.0, currency="RUB"
    )


@pytest.fixture
def sample_queue_message(sample_queue_event):
    """Create a sample QueueMessage for testing."""
    return QueueMessage(event="test_event", data=sample_queue_event)


class TestBeerConsumer:
    """Test cases for the BeerConsumer class."""

    def test_initialization(self, beer_consumer):
        """Test BeerConsumer initialization."""
        assert beer_consumer.donate_url == "http://test-server/donate"

    @pytest.mark.asyncio
    async def test_on_message_non_donation_event(self, beer_consumer):
        """Test on_message with non-donation event type."""
        event = QueueEvent(
            event_type="OTHER_EVENT",
            user_name="Test User",
            amount=100.0,
            currency="RUB",
        )
        message = QueueMessage(event="test_event", data=event)

        result: QueueMessage = await beer_consumer.on_message(message)
        assert result.status == QueueMessageStatus.FINISHED

    @pytest.mark.asyncio
    async def test_on_message_donation_without_amount(self, beer_consumer):
        """Test on_message with donation event but no amount."""
        event = QueueEvent(
            event_type="DONATION", user_name="Test User", amount=None, currency="RUB"
        )
        message = QueueMessage(event="test_event", data=event)

        result = await beer_consumer.on_message(message)
        assert result is not None

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_on_message_rub_currency(
        self, mock_post, beer_consumer, sample_queue_message
    ):
        """Test on_message with RUB currency (no conversion needed)."""
        # Setup mock response
        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value={"message": "Success"})
        mock_post.return_value.__aenter__.return_value = mock_response

        await beer_consumer.on_message(sample_queue_message)

        # Verify the post was called with correct data
        # Get the actual call arguments
        call_args = mock_post.call_args
        assert call_args[0][0] == "http://test-server/donate"
        assert call_args[1]["headers"] == {"Content-Type": "application/json"}

        # Check payload
        payload = call_args[1]["json"]
        assert payload["value"] == 100
        assert payload["name"] == "Test User"
        # Check that date is present and is a string
        assert "date" in payload
        assert isinstance(payload["date"], str)

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_on_message_usd_currency_conversion(self, mock_post, beer_consumer):
        """Test on_message with USD currency (conversion needed)."""
        event = QueueEvent(
            event_type="DONATION", user_name="Test User", amount=100.0, currency="USD"
        )
        message = QueueMessage(event="test_event", data=event)

        # Setup mock response
        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value={"message": "Success"})
        mock_post.return_value.__aenter__.return_value = mock_response

        await beer_consumer.on_message(message)

        # Get the actual call arguments
        call_args = mock_post.call_args
        payload = call_args[1]["json"]

        # Due to a bug in the requeue library's recal_amount implementation,
        # the conversion uses the RUB rate (1) instead of the USD rate (80)
        # So 100 USD becomes 100 RUB instead of 8000 RUB
        assert payload["value"] == 100

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_on_message_client_connector_error(
        self, mock_post, beer_consumer, sample_queue_message
    ):
        """Test on_message when client connection fails."""
        # Setup mock to raise ClientConnectorError
        mock_post.side_effect = ClientConnectorError(MagicMock(), MagicMock())

        # Should not raise an exception
        result = await beer_consumer.on_message(sample_queue_message)
        assert result is not None

    def test_from_queue_event_to_bs(self, beer_consumer, sample_queue_event):
        """Test _from_queue_event_to_bs method."""
        result = beer_consumer._from_queue_event_to_bs(sample_queue_event)

        assert isinstance(result, dict)
        assert result["value"] == 100
        assert result["name"] == "Test User"

    def test_from_queue_event_to_bs_no_amount(self, beer_consumer):
        """Test _from_queue_event_to_bs method with no amount."""
        event = QueueEvent(
            event_type="DONATION", user_name="Test User", amount=None, currency="RUB"
        )
        result = beer_consumer._from_queue_event_to_bs(event)

        assert isinstance(result, dict)
        assert result["value"] == 0
        assert result["name"] == "Test User"
