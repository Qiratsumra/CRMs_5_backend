"""
Message processor worker.
Polls database for new tickets and processes them with the agent.
"""

import sys
import os
from pathlib import Path

# Add parent directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from agent.customer_success_agent import run_agent
from database.queries import get_db_pool
from channels.smtp_handler import get_smtp_handler

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class MessageProcessor:
    """Processes incoming messages from all channels."""

    def __init__(self):
        self.smtp = get_smtp_handler()
        self.poll_interval = int(os.getenv("POLL_INTERVAL", "10"))

    async def start(self):
        """Start the message processor."""
        logger.info("Message processor started (database polling mode)")

        while True:
            try:
                await self.process_pending_tickets()
                await asyncio.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"Error in processor loop: {e}", exc_info=True)
                await asyncio.sleep(30)

    async def process_pending_tickets(self):
        """Find and process tickets that need responses."""
        pool = await get_db_pool()

        # Find tickets that need processing (open status, no agent response yet)
        tickets = await pool.fetch(
            """
            SELECT t.id, t.conversation_id, t.customer_id, t.category, t.priority,
                   c.email, c.name, m.content as customer_message
            FROM tickets t
            JOIN customers c ON t.customer_id = c.id
            JOIN conversations conv ON t.conversation_id = conv.id
            JOIN messages m ON m.conversation_id = conv.id AND m.role = 'customer'
            WHERE t.status = 'open'
            AND NOT EXISTS (
                SELECT 1 FROM messages m2
                WHERE m2.conversation_id = conv.id
                AND m2.role = 'agent'
            )
            ORDER BY t.created_at ASC
            LIMIT 10
            """
        )

        for ticket in tickets:
            await self.process_ticket(ticket)

    async def process_ticket(self, ticket):
        """Process a single ticket."""
        start_time = datetime.now(timezone.utc)
        logger.info(f"Processing ticket {ticket['id']}")

        try:
            pool = await get_db_pool()

            # Prepare message for agent
            message = {
                "channel": "web_form",
                "customer_id": str(ticket["customer_id"]),
                "customer_email": ticket["email"],
                "customer_name": ticket["name"],
                "content": ticket["customer_message"],
                "category": ticket["category"],
                "priority": ticket["priority"],
                "conversation_id": str(ticket["conversation_id"]),
            }

            # Run agent
            result = await run_agent(message)

            if result.get("status") == "success":
                agent_response = result.get("response", "")

                # Agent already saved the response to database, just send email
                # Send email response
                if self.smtp.enabled:
                    email_subject = f"Re: Support Request - Ticket #{str(ticket['id'])[:8]}"
                    email_body = f"""
Hello {ticket['name']},

Thank you for contacting us. Here's our response to your inquiry:

{agent_response}

If you have any further questions, please reply to this email or submit a new request.

Best regards,
Customer Support Team

---
Ticket ID: {ticket['id']}
                    """.strip()

                    self.smtp.send_email(ticket["email"], email_subject, email_body)

                # Update ticket status
                await pool.execute(
                    "UPDATE tickets SET status = 'in_progress' WHERE id = $1",
                    ticket["id"]
                )

                latency = (datetime.now(timezone.utc) - start_time).total_seconds()
                logger.info(f"Successfully processed ticket {ticket['id']} in {latency:.2f}s")

            else:
                logger.error(f"Agent failed for ticket {ticket['id']}: {result.get('error')}")
                await self.handle_error(ticket, Exception(result.get("error")))

        except Exception as e:
            logger.error(f"Failed to process ticket {ticket['id']}: {e}", exc_info=True)
            await self.handle_error(ticket, e)

    async def handle_error(self, ticket, error: Exception):
        """Handle processing errors."""
        try:
            pool = await get_db_pool()

            apology = (
                "We apologize, but we're experiencing technical difficulties. "
                "A team member will review your message and respond shortly."
            )

            # Save error response
            await pool.execute(
                """
                INSERT INTO messages (conversation_id, role, content, channel, direction, delivery_status)
                VALUES ($1, 'agent', $2, 'web_form', 'outbound', 'error')
                """,
                ticket["conversation_id"], apology
            )

            # Send apology email
            if self.smtp.enabled:
                email_subject = f"Re: Support Request - Ticket #{str(ticket['id'])[:8]}"
                self.smtp.send_email(ticket["email"], email_subject, apology)

            logger.info(f"Sent error apology for ticket {ticket['id']}")

        except Exception as apology_error:
            logger.error(f"Failed to send error apology: {apology_error}")


async def main():
    """Entry point for message processor."""
    processor = MessageProcessor()

    try:
        await processor.start()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")


if __name__ == "__main__":
    asyncio.run(main())
