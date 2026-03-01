"""
Database queries layer using asyncpg.
All functions use a shared connection pool for efficient database access.
"""

import asyncpg
import os
import logging
from typing import Optional
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def get_db_pool() -> asyncpg.Pool:
    """Get or create the database connection pool."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=os.environ["DATABASE_URL"],
            ssl="require",
            min_size=1,
            max_size=10,
        )
        logger.info("Database connection pool created")
    return _pool


# ============================================================================
# Customers
# ============================================================================

async def get_customer_by_email(email: str) -> Optional[dict]:
    """Get customer by email address."""
    pool = await get_db_pool()
    row = await pool.fetchrow(
        "SELECT * FROM customers WHERE email = $1",
        email
    )
    return dict(row) if row else None


async def get_customer_by_phone(phone: str) -> Optional[dict]:
    """Get customer by phone number."""
    pool = await get_db_pool()
    row = await pool.fetchrow(
        "SELECT * FROM customers WHERE phone = $1",
        phone
    )
    return dict(row) if row else None


async def create_customer(email: Optional[str] = None, phone: Optional[str] = None, name: Optional[str] = None) -> str:
    """Create a new customer and return their ID."""
    pool = await get_db_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO customers (email, phone, name)
        VALUES ($1, $2, $3)
        RETURNING id
        """,
        email, phone, name
    )
    customer_id = str(row["id"])
    logger.info(f"Created customer {customer_id}")
    return customer_id


async def get_or_create_customer(message: dict) -> str:
    """
    Get or create customer based on message channel.
    WhatsApp → match by phone
    Email/web_form → match by email
    """
    channel = message.get("channel", "")

    if channel == "whatsapp":
        phone = message.get("customer_phone")
        if phone:
            customer = await get_customer_by_phone(phone)
            if customer:
                return str(customer["id"])
            return await create_customer(phone=phone, name=message.get("customer_name"))

    else:  # email or web_form
        email = message.get("customer_email")
        if email:
            customer = await get_customer_by_email(email)
            if customer:
                return str(customer["id"])
            return await create_customer(email=email, name=message.get("customer_name"))

    raise ValueError("Cannot resolve customer: missing email or phone")


# ============================================================================
# Conversations
# ============================================================================

async def create_conversation(customer_id: str, channel: str) -> str:
    """Create a new conversation and return its ID."""
    pool = await get_db_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO conversations (customer_id, initial_channel, status)
        VALUES ($1, $2, 'active')
        RETURNING id
        """,
        customer_id, channel
    )
    conversation_id = str(row["id"])
    logger.info(f"Created conversation {conversation_id} for customer {customer_id}")
    return conversation_id


async def get_active_conversation(customer_id: str) -> Optional[dict]:
    """
    Get active conversation for customer.
    Active = status='active' AND started within last 24 hours.
    """
    pool = await get_db_pool()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    row = await pool.fetchrow(
        """
        SELECT * FROM conversations
        WHERE customer_id = $1
          AND status = 'active'
          AND started_at > $2
        ORDER BY started_at DESC
        LIMIT 1
        """,
        customer_id, cutoff
    )
    return dict(row) if row else None


async def close_conversation(conversation_id: str, resolution_type: str):
    """Close a conversation with resolution type."""
    pool = await get_db_pool()
    await pool.execute(
        """
        UPDATE conversations
        SET status = 'closed', ended_at = NOW(), resolution_type = $2
        WHERE id = $1
        """,
        conversation_id, resolution_type
    )
    logger.info(f"Closed conversation {conversation_id} with resolution: {resolution_type}")


async def update_conversation_sentiment(conversation_id: str, score: float):
    """Update conversation sentiment score."""
    pool = await get_db_pool()
    await pool.execute(
        "UPDATE conversations SET sentiment_score = $2 WHERE id = $1",
        conversation_id, score
    )


# ============================================================================
# Messages
# ============================================================================

async def store_message(
    conversation_id: str,
    channel: str,
    direction: str,
    role: str,
    content: str,
    **kwargs
) -> str:
    """Store a message and return its ID."""
    import json

    pool = await get_db_pool()

    # Convert tool_calls list to JSON string if present
    tool_calls = kwargs.get("tool_calls", [])
    if isinstance(tool_calls, list):
        tool_calls = json.dumps(tool_calls)

    row = await pool.fetchrow(
        """
        INSERT INTO messages (
            conversation_id, channel, direction, role, content,
            tokens_used, latency_ms, tool_calls, channel_message_id, delivery_status
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10)
        RETURNING id
        """,
        conversation_id,
        channel,
        direction,
        role,
        content,
        kwargs.get("tokens_used"),
        kwargs.get("latency_ms"),
        tool_calls,
        kwargs.get("channel_message_id"),
        kwargs.get("delivery_status", "pending")
    )
    message_id = str(row["id"])
    logger.debug(f"Stored message {message_id}")
    return message_id


async def load_conversation_history(conversation_id: str) -> list[dict]:
    """Load all messages for a conversation."""
    pool = await get_db_pool()
    rows = await pool.fetch(
        """
        SELECT * FROM messages
        WHERE conversation_id = $1
        ORDER BY created_at ASC
        """,
        conversation_id
    )
    return [dict(row) for row in rows]


# ============================================================================
# Tickets
# ============================================================================

async def create_ticket_record(ticket_id: str, data: dict) -> str:
    """Create a ticket record."""
    pool = await get_db_pool()
    await pool.execute(
        """
        INSERT INTO tickets (id, conversation_id, customer_id, source_channel, category, priority, status, subject)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """,
        ticket_id,
        data.get("conversation_id"),
        data.get("customer_id"),
        data.get("source_channel"),
        data.get("category"),
        data.get("priority", "medium"),
        data.get("status", "open"),
        data.get("subject")
    )
    logger.info(f"Created ticket {ticket_id}")
    return ticket_id


async def get_ticket_by_id(ticket_id: str) -> Optional[dict]:
    """Get ticket by ID."""
    pool = await get_db_pool()
    row = await pool.fetchrow(
        "SELECT * FROM tickets WHERE id = $1",
        ticket_id
    )
    return dict(row) if row else None


async def update_ticket_status(ticket_id: str, status: str, notes: Optional[str] = None):
    """Update ticket status and optionally add resolution notes."""
    pool = await get_db_pool()
    if status == "resolved":
        await pool.execute(
            """
            UPDATE tickets
            SET status = $2, resolved_at = NOW(), resolution_notes = $3
            WHERE id = $1
            """,
            ticket_id, status, notes
        )
    else:
        await pool.execute(
            "UPDATE tickets SET status = $2 WHERE id = $1",
            ticket_id, status
        )
    logger.info(f"Updated ticket {ticket_id} status to {status}")


# ============================================================================
# Knowledge Base
# ============================================================================

async def search_knowledge_base(query_embedding: list, max_results: int = 5) -> list[dict]:
    """Search knowledge base using vector similarity."""
    pool = await get_db_pool()
    rows = await pool.fetch(
        """
        SELECT id, title, content, category,
               1 - (embedding <=> $1::vector) AS similarity_score
        FROM knowledge_base
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> $1::vector
        LIMIT $2
        """,
        query_embedding,
        max_results
    )
    return [dict(row) for row in rows]


# ============================================================================
# Metrics
# ============================================================================

async def record_metric(name: str, value: float, channel: Optional[str] = None, dimensions: Optional[dict] = None):
    """Record an agent metric."""
    import json

    pool = await get_db_pool()

    # Convert dimensions dict to JSON string
    dimensions_json = json.dumps(dimensions or {})

    await pool.execute(
        """
        INSERT INTO agent_metrics (metric_name, metric_value, channel, dimensions)
        VALUES ($1, $2, $3, $4::jsonb)
        """,
        name, value, channel, dimensions_json
    )


async def get_channel_metrics(hours: int = 24) -> dict:
    """Get metrics per channel for the last N hours."""
    pool = await get_db_pool()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = await pool.fetch(
        """
        SELECT channel, metric_name, AVG(metric_value) as avg_value, COUNT(*) as count
        FROM agent_metrics
        WHERE recorded_at > $1 AND channel IS NOT NULL
        GROUP BY channel, metric_name
        ORDER BY channel, metric_name
        """,
        cutoff
    )

    result = {}
    for row in rows:
        channel = row["channel"]
        if channel not in result:
            result[channel] = {}
        result[channel][row["metric_name"]] = {
            "avg": float(row["avg_value"]),
            "count": row["count"]
        }
    return result


# ============================================================================
# WhatsApp Deduplication
# ============================================================================

async def is_whatsapp_message_processed(message_id: str) -> bool:
    """Check if WhatsApp message has already been processed."""
    pool = await get_db_pool()
    row = await pool.fetchrow(
        "SELECT 1 FROM whatsapp_processed_messages WHERE message_id = $1",
        message_id
    )
    return row is not None


async def mark_whatsapp_message_processed(message_id: str, chat_jid: str) -> None:
    """Mark WhatsApp message as processed."""
    pool = await get_db_pool()
    await pool.execute(
        """
        INSERT INTO whatsapp_processed_messages (message_id, chat_jid)
        VALUES ($1, $2)
        ON CONFLICT (message_id) DO NOTHING
        """,
        message_id, chat_jid
    )
