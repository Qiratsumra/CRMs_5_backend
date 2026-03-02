"""
Web form handler for customer support submissions.
FastAPI router with endpoints for ticket submission and retrieval.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, EmailStr, field_validator

from database.queries import get_ticket_by_id, load_conversation_history, get_db_pool
from channels.resend_handler import get_resend_handler
import os

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/support", tags=["support"])

# Kafka is optional - if not available, we'll write directly to DB
KAFKA_ENABLED = os.getenv("KAFKA_ENABLED", "false").lower() == "true"

if KAFKA_ENABLED:
    from kafka_client import FTEKafkaProducer, TOPICS
    _producer: Optional[FTEKafkaProducer] = None

    async def get_producer():
        """Get or create Kafka producer."""
        global _producer
        if _producer is None:
            _producer = FTEKafkaProducer(
                bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
            )
            await _producer.start()
        return _producer


# ============================================================================
# Request/Response Models
# ============================================================================

class SupportSubmission(BaseModel):
    """Web form support submission."""
    name: str = Field(..., min_length=2, max_length=100, description="Customer name")
    email: EmailStr = Field(..., description="Customer email address")
    category: str = Field(..., description="Issue category")
    message: str = Field(..., min_length=10, max_length=5000, description="Support message")
    priority: Optional[str] = Field(default="medium", description="Priority level")

    @field_validator("category")
    @classmethod
    def validate_category(cls, v):
        valid_categories = ["general", "technical", "billing", "bug_report", "feedback"]
        if v not in valid_categories:
            raise ValueError(f"Category must be one of: {', '.join(valid_categories)}")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v):
        valid_priorities = ["low", "medium", "high", "urgent"]
        if v not in valid_priorities:
            raise ValueError(f"Priority must be one of: {', '.join(valid_priorities)}")
        return v


class SubmissionResponse(BaseModel):
    """Response after successful submission."""
    ticket_id: str
    message: str
    estimated_response_time: str


class TicketResponse(BaseModel):
    """Ticket details with messages."""
    ticket_id: str
    status: str
    category: str
    priority: str
    subject: str
    created_at: str
    messages: list[dict]


class TicketListItem(BaseModel):
    """Ticket list item."""
    ticket_id: str
    status: str
    category: str
    subject: str
    created_at: str


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/submit", response_model=SubmissionResponse)
async def submit_support_request(submission: SupportSubmission):
    """
    Submit a new support request via web form.
    Creates a ticket and either publishes to Kafka or writes directly to DB.
    """
    try:
        # Generate ticket ID
        ticket_id = str(uuid.uuid4())

        if KAFKA_ENABLED:
            # Normalize message for Kafka
            normalized_message = {
                "channel": "web_form",
                "channel_message_id": ticket_id,
                "customer_email": submission.email,
                "customer_name": submission.name,
                "content": submission.message,
                "category": submission.category,
                "priority": submission.priority,
                "received_at": datetime.now(timezone.utc).isoformat(),
                "metadata": {
                    "ticket_id": ticket_id,
                    "source": "web_form",
                }
            }

            # Publish to Kafka
            producer = await get_producer()
            await producer.publish(TOPICS["tickets_incoming"], normalized_message)
            logger.info(f"Web form submission published to Kafka: ticket {ticket_id}")
        else:
            # Write directly to database
            pool = await get_db_pool()

            # Get or create customer
            customer = await pool.fetchrow(
                "SELECT id FROM customers WHERE email = $1",
                submission.email
            )

            if not customer:
                customer = await pool.fetchrow(
                    """
                    INSERT INTO customers (email, name)
                    VALUES ($1, $2)
                    RETURNING id
                    """,
                    submission.email, submission.name
                )

            customer_id = customer["id"]

            # Create conversation
            conversation = await pool.fetchrow(
                """
                INSERT INTO conversations (customer_id, initial_channel, status)
                VALUES ($1, 'web_form', 'active')
                RETURNING id
                """,
                customer_id
            )

            conversation_id = conversation["id"]

            # Create ticket
            await pool.execute(
                """
                INSERT INTO tickets (id, customer_id, conversation_id, status, priority, category, subject, source_channel)
                VALUES ($1, $2, $3, 'open', $4, $5, $6, 'web_form')
                """,
                uuid.UUID(ticket_id), customer_id, conversation_id,
                submission.priority, submission.category,
                submission.message[:100]  # Use first 100 chars as subject
            )

            # Add customer message
            await pool.execute(
                """
                INSERT INTO messages (conversation_id, role, content, channel, direction)
                VALUES ($1, 'customer', $2, 'web_form', 'inbound')
                """,
                conversation_id, submission.message
            )

            logger.info(f"Web form submission saved directly to DB: ticket {ticket_id}")

            # Process with AI agent immediately (synchronous mode)
            try:
                from agent.customer_success_agent import run_agent

                # Build message for agent
                agent_message = {
                    "channel": "web_form",
                    "content": submission.message,
                    "customer_email": submission.email,
                    "customer_name": submission.name,
                    "conversation_id": conversation_id,  # Signal that message is already stored
                    "channel_message_id": ticket_id,
                    "metadata": {
                        "category": submission.category,
                        "priority": submission.priority,
                    }
                }

                ai_response = await run_agent(agent_message)

                # Update ticket status based on AI response
                if ai_response.get("status") == "success":
                    await pool.execute(
                        "UPDATE tickets SET status = 'resolved' WHERE id = $1",
                        uuid.UUID(ticket_id)
                    )
                    logger.info(f"AI processed ticket {ticket_id} successfully")
                else:
                    logger.warning(f"AI processing failed for ticket {ticket_id}: {ai_response.get('error')}")

            except Exception as e:
                logger.error(f"Failed to process ticket {ticket_id} with AI: {e}", exc_info=True)
                # Don't fail the request - ticket is still created

        # Send confirmation email asynchronously (non-blocking)
        import asyncio
        resend = get_resend_handler()
        if resend.enabled:
            email_subject = f"Support Request Received - Ticket #{ticket_id[:8]}"
            email_body = f"""
Hello {submission.name},

Thank you for contacting our support team. We have received your request and will respond shortly.

Ticket ID: {ticket_id}
Category: {submission.category}
Priority: {submission.priority}

Your message:
{submission.message}

You can check the status of your ticket at any time using your ticket ID.

Best regards,
Customer Support Team
            """.strip()

            # Send email in background task (non-blocking)
            asyncio.create_task(
                asyncio.to_thread(resend.send_email, submission.email, email_subject, email_body)
            )

        # Estimate response time based on priority
        response_times = {
            "urgent": "within 1 hour",
            "high": "within 4 hours",
            "medium": "within 24 hours",
            "low": "within 48 hours",
        }

        return SubmissionResponse(
            ticket_id=ticket_id,
            message="Your support request has been received. We'll respond shortly.",
            estimated_response_time=response_times.get(submission.priority, "within 24 hours")
        )

    except Exception as e:
        logger.error(f"Failed to submit support request: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to submit support request")


@router.get("/ticket/{ticket_id}", response_model=TicketResponse)
async def get_ticket(ticket_id: str):
    """
    Get ticket details and full message thread.
    """
    try:
        # Get ticket from database
        ticket = await get_ticket_by_id(ticket_id)

        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")

        # Get conversation messages
        messages = []
        if ticket.get("conversation_id"):
            msg_rows = await load_conversation_history(ticket["conversation_id"])
            messages = [
                {
                    "role": msg["role"],
                    "content": msg["content"],
                    "created_at": msg["created_at"].isoformat(),
                    "channel": msg["channel"],
                }
                for msg in msg_rows
            ]

        return TicketResponse(
            ticket_id=str(ticket["id"]),
            status=ticket["status"],
            category=ticket["category"] or "general",
            priority=ticket["priority"],
            subject=ticket["subject"] or "",
            created_at=ticket["created_at"].isoformat(),
            messages=messages
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get ticket {ticket_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve ticket")


@router.get("/tickets", response_model=list[TicketListItem])
async def list_tickets(email: Optional[str] = Query(None, description="Filter by customer email")):
    """
    List tickets, optionally filtered by customer email.
    """
    try:
        from database.queries import get_db_pool

        pool = await get_db_pool()

        if email:
            # Get tickets for specific customer
            rows = await pool.fetch(
                """
                SELECT t.id, t.status, t.category, t.subject, t.created_at
                FROM tickets t
                JOIN customers c ON t.customer_id = c.id
                WHERE c.email = $1
                ORDER BY t.created_at DESC
                LIMIT 50
                """,
                email
            )
        else:
            # Get recent tickets (limited for performance)
            rows = await pool.fetch(
                """
                SELECT id, status, category, subject, created_at
                FROM tickets
                ORDER BY created_at DESC
                LIMIT 50
                """
            )

        return [
            TicketListItem(
                ticket_id=str(row["id"]),
                status=row["status"],
                category=row["category"] or "general",
                subject=row["subject"] or "",
                created_at=row["created_at"].isoformat()
            )
            for row in rows
        ]

    except Exception as e:
        logger.error(f"Failed to list tickets: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list tickets")


@router.get("/health")
async def health_check():
    """Health check endpoint for web form service."""
    return {
        "status": "healthy",
        "service": "web_form",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
