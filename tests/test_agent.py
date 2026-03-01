"""
Tests for agent tools.
Tests each tool in isolation with mocked dependencies.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agent.tools import (
    search_knowledge_base,
    create_ticket,
    get_customer_history,
    escalate_to_human,
    send_response,
    analyze_sentiment,
)


@pytest.mark.asyncio
async def test_search_knowledge_base_success():
    """Test knowledge base search returns formatted results."""
    mock_results = [
        {
            "id": "1",
            "title": "Login Issues",
            "content": "To fix login issues, try resetting your password...",
            "category": "troubleshooting",
            "similarity_score": 0.92,
        },
        {
            "id": "2",
            "title": "Password Reset",
            "content": "You can reset your password by clicking...",
            "category": "account",
            "similarity_score": 0.85,
        },
    ]

    with patch("agent.tools.genai.embed_content") as mock_embed, \
         patch("agent.tools.db_search_kb", new_callable=AsyncMock) as mock_search:

        mock_embed.return_value = {"embedding": [0.1] * 768}
        mock_search.return_value = mock_results

        result = await search_knowledge_base("how to login")

        assert "Login Issues" in result
        assert "troubleshooting" in result
        assert "0.92" in result
        assert "Password Reset" in result


@pytest.mark.asyncio
async def test_search_knowledge_base_no_results():
    """Test knowledge base search with no results."""
    with patch("agent.tools.genai.embed_content") as mock_embed, \
         patch("agent.tools.db_search_kb", new_callable=AsyncMock) as mock_search:

        mock_embed.return_value = {"embedding": [0.1] * 768}
        mock_search.return_value = []

        result = await search_knowledge_base("nonexistent query")

        assert "No relevant articles found" in result


@pytest.mark.asyncio
async def test_create_ticket_success():
    """Test ticket creation."""
    with patch("agent.tools.create_ticket_record", new_callable=AsyncMock) as mock_create, \
         patch("agent.tools.record_metric", new_callable=AsyncMock):

        mock_create.return_value = "ticket-123"

        result = await create_ticket(
            customer_id="cust-123",
            issue="Cannot login",
            priority="high",
            category="technical",
            channel="email"
        )

        assert "Ticket created successfully" in result
        assert mock_create.called


@pytest.mark.asyncio
async def test_get_customer_history_with_cross_channel():
    """Test customer history retrieval shows cross-channel usage."""
    mock_rows = [
        {
            "content": "I need help with login",
            "channel": "email",
            "role": "user",
            "created_at": MagicMock(strftime=lambda x: "2026-02-28 10:00"),
            "initial_channel": "email"
        },
        {
            "content": "Here's how to reset your password",
            "channel": "email",
            "role": "assistant",
            "created_at": MagicMock(strftime=lambda x: "2026-02-28 10:05"),
            "initial_channel": "email"
        },
        {
            "content": "Still not working",
            "channel": "whatsapp",
            "role": "user",
            "created_at": MagicMock(strftime=lambda x: "2026-02-28 11:00"),
            "initial_channel": "whatsapp"
        },
    ]

    with patch("agent.tools.get_db_pool", new_callable=AsyncMock) as mock_pool:
        mock_pool.return_value.fetch = AsyncMock(return_value=mock_rows)

        result = await get_customer_history("cust-123")

        assert "email" in result
        assert "whatsapp" in result
        assert "multiple channels" in result


@pytest.mark.asyncio
async def test_escalate_to_human():
    """Test escalation to human agent."""
    with patch("agent.tools.update_ticket_status", new_callable=AsyncMock), \
         patch("agent.tools.get_kafka_producer", new_callable=AsyncMock) as mock_producer, \
         patch("agent.tools.record_metric", new_callable=AsyncMock):

        mock_producer.return_value.publish = AsyncMock()

        result = await escalate_to_human(
            ticket_id="ticket-123",
            reason="Customer mentioned lawyer",
            urgency="urgent"
        )

        assert "escalated" in result.lower()
        assert "urgent" in result.lower()


@pytest.mark.asyncio
async def test_analyze_sentiment_negative():
    """Test sentiment analysis detects negative sentiment."""
    result = await analyze_sentiment(
        "This is terrible and I'm very frustrated with your service"
    )

    assert "negative" in result.lower()
    assert "LOW SENTIMENT" in result or float(result.split("score: ")[1].split(",")[0]) < 0.3


@pytest.mark.asyncio
async def test_analyze_sentiment_positive():
    """Test sentiment analysis detects positive sentiment."""
    result = await analyze_sentiment(
        "Thank you so much! This is excellent and very helpful"
    )

    assert "positive" in result.lower()


@pytest.mark.asyncio
async def test_analyze_sentiment_legal_keywords():
    """Test sentiment analysis detects legal keywords."""
    result = await analyze_sentiment(
        "I'm going to contact my lawyer about this"
    )

    assert "critical" in result.lower() or "LOW SENTIMENT" in result


@pytest.mark.asyncio
async def test_send_response_whatsapp():
    """Test sending response via WhatsApp."""
    mock_ticket = {
        "id": "ticket-123",
        "customer_id": "cust-123",
        "subject": "Login issue",
    }

    mock_customer = {"phone": "+1234567890"}

    with patch("agent.tools.get_ticket_by_id", new_callable=AsyncMock) as mock_get_ticket, \
         patch("agent.tools.format_for_channel", new_callable=AsyncMock) as mock_format, \
         patch("agent.tools.get_whatsapp_handler") as mock_handler, \
         patch("agent.tools.get_db_pool", new_callable=AsyncMock) as mock_pool, \
         patch("agent.tools.record_metric", new_callable=AsyncMock):

        mock_get_ticket.return_value = mock_ticket
        mock_format.return_value = "Formatted response"
        mock_pool.return_value.fetchrow = AsyncMock(return_value=mock_customer)
        mock_handler.return_value.split_message = MagicMock(return_value=["Formatted response"])
        mock_handler.return_value.send_message = AsyncMock()

        result = await send_response(
            ticket_id="ticket-123",
            message="Here's the solution",
            channel="whatsapp"
        )

        assert "sent successfully" in result.lower()
        assert mock_handler.return_value.send_message.called


@pytest.mark.asyncio
async def test_send_response_email():
    """Test sending response via email."""
    mock_ticket = {
        "id": "ticket-123",
        "customer_id": "cust-123",
        "subject": "Login issue",
    }

    mock_customer = {"email": "customer@example.com"}

    with patch("agent.tools.get_ticket_by_id", new_callable=AsyncMock) as mock_get_ticket, \
         patch("agent.tools.format_for_channel", new_callable=AsyncMock) as mock_format, \
         patch("agent.tools.get_gmail_handler") as mock_handler, \
         patch("agent.tools.get_db_pool", new_callable=AsyncMock) as mock_pool, \
         patch("agent.tools.record_metric", new_callable=AsyncMock):

        mock_get_ticket.return_value = mock_ticket
        mock_format.return_value = "Formatted email response"
        mock_pool.return_value.fetchrow = AsyncMock(return_value=mock_customer)
        mock_handler.return_value.send_reply = AsyncMock()

        result = await send_response(
            ticket_id="ticket-123",
            message="Here's the solution",
            channel="email"
        )

        assert "sent successfully" in result.lower()
        assert mock_handler.return_value.send_reply.called
