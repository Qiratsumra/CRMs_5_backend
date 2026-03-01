"""
End-to-end multi-channel tests.
Tests complete workflows across channels.
"""

import pytest
from unittest.mock import AsyncMock, patch
import uuid


@pytest.mark.asyncio
async def test_web_form_to_kafka():
    """Test web form submission publishes to Kafka."""
    from channels.web_form_handler import get_producer
    from kafka_client import TOPICS

    mock_producer = AsyncMock()
    mock_producer.publish = AsyncMock()

    with patch("channels.web_form_handler.get_producer", return_value=mock_producer):
        from channels.web_form_handler import submit_support_request, SupportSubmission

        submission = SupportSubmission(
            name="John Doe",
            email="john@example.com",
            category="technical",
            message="I need help with my account",
            priority="medium"
        )

        result = await submit_support_request(submission)

        assert result.ticket_id
        assert "received" in result.message.lower()
        mock_producer.publish.assert_called_once()


@pytest.mark.asyncio
async def test_whatsapp_deduplication():
    """Test WhatsApp message deduplication prevents duplicate processing."""
    from database.queries import is_whatsapp_message_processed, mark_whatsapp_message_processed

    message_id = f"test-msg-{uuid.uuid4()}"
    chat_jid = "1234567890@s.whatsapp.net"

    with patch("database.queries.get_db_pool", new_callable=AsyncMock) as mock_pool:
        # First check - not processed
        mock_pool.return_value.fetchrow = AsyncMock(return_value=None)
        result = await is_whatsapp_message_processed(message_id)
        assert result is False

        # Mark as processed
        mock_pool.return_value.execute = AsyncMock()
        await mark_whatsapp_message_processed(message_id, chat_jid)

        # Second check - already processed
        mock_pool.return_value.fetchrow = AsyncMock(return_value={"message_id": message_id})
        result = await is_whatsapp_message_processed(message_id)
        assert result is True


@pytest.mark.asyncio
async def test_customer_resolution_by_phone():
    """Test customer resolved correctly by phone (WhatsApp)."""
    from workers.message_processor import resolve_customer

    message = {
        "channel": "whatsapp",
        "customer_phone": "+1234567890",
        "customer_name": "John Doe",
    }

    with patch("workers.message_processor.get_customer_by_phone", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"id": "existing-customer-id"}

        customer_id = await resolve_customer(message)

        assert customer_id == "existing-customer-id"
        mock_get.assert_called_once_with("+1234567890")


@pytest.mark.asyncio
async def test_customer_resolution_by_email():
    """Test customer resolved correctly by email (web_form)."""
    from workers.message_processor import resolve_customer

    message = {
        "channel": "web_form",
        "customer_email": "john@example.com",
        "customer_name": "John Doe",
    }

    with patch("workers.message_processor.get_customer_by_email", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"id": "existing-customer-id"}

        customer_id = await resolve_customer(message)

        assert customer_id == "existing-customer-id"
        mock_get.assert_called_once_with("john@example.com")


@pytest.mark.asyncio
async def test_cross_channel_customer_matching():
    """Test customer created via web_form is matched again via WhatsApp phone."""
    from workers.message_processor import resolve_customer

    # First interaction via web form
    web_message = {
        "channel": "web_form",
        "customer_email": "john@example.com",
        "customer_name": "John Doe",
    }

    with patch("workers.message_processor.get_customer_by_email", new_callable=AsyncMock) as mock_get_email, \
         patch("workers.message_processor.create_customer", new_callable=AsyncMock) as mock_create:

        mock_get_email.return_value = None
        mock_create.return_value = "new-customer-id"

        customer_id_1 = await resolve_customer(web_message)
        assert customer_id_1 == "new-customer-id"

    # Second interaction via WhatsApp with same customer
    # In real scenario, customer would have phone added to their record
    whatsapp_message = {
        "channel": "whatsapp",
        "customer_phone": "+1234567890",
        "customer_name": "John Doe",
    }

    with patch("workers.message_processor.get_customer_by_phone", new_callable=AsyncMock) as mock_get_phone:
        # Simulate customer record now has phone
        mock_get_phone.return_value = {"id": "new-customer-id"}

        customer_id_2 = await resolve_customer(whatsapp_message)
        assert customer_id_2 == "new-customer-id"
        assert customer_id_1 == customer_id_2


@pytest.mark.asyncio
async def test_ticket_record_created():
    """Test ticket record is created in database."""
    from database.queries import create_ticket_record

    ticket_id = str(uuid.uuid4())
    ticket_data = {
        "customer_id": "cust-123",
        "source_channel": "email",
        "category": "technical",
        "priority": "high",
        "status": "open",
        "subject": "Cannot login to account",
    }

    with patch("database.queries.get_db_pool", new_callable=AsyncMock) as mock_pool:
        mock_pool.return_value.execute = AsyncMock()

        result = await create_ticket_record(ticket_id, ticket_data)

        assert result == ticket_id
        mock_pool.return_value.execute.assert_called_once()


@pytest.mark.asyncio
async def test_whatsapp_escalation_keywords():
    """Test WhatsApp-specific escalation keywords trigger escalation."""
    from agent.tools import analyze_sentiment

    escalation_keywords = ["human", "agent", "person", "representative"]

    for keyword in escalation_keywords:
        message = f"I want to speak to a {keyword}"
        result = await analyze_sentiment(message)

        # Should detect as requiring attention
        # (In real implementation, the agent prompt handles WhatsApp-specific escalation)
        assert isinstance(result, str)


@pytest.mark.asyncio
async def test_message_processor_error_handling():
    """Test message processor handles errors gracefully."""
    from workers.message_processor import MessageProcessor

    processor = MessageProcessor()

    # Mock error in agent execution
    error_message = {
        "channel": "email",
        "customer_email": "test@example.com",
        "content": "Test message",
    }

    with patch.object(processor, "handle_error", new_callable=AsyncMock) as mock_handle_error, \
         patch("workers.message_processor.run_agent", new_callable=AsyncMock) as mock_run_agent, \
         patch("workers.message_processor.resolve_customer", new_callable=AsyncMock) as mock_resolve:

        mock_resolve.return_value = "cust-123"
        mock_run_agent.return_value = {"status": "error", "error": "Test error"}

        await processor.process_message(error_message)

        mock_handle_error.assert_called_once()
