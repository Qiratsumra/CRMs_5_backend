"""
Agent tools for the Customer Success Agent.
All tools use @function_tool decorator and include error handling.
"""

import logging
import uuid
from typing import Optional
from pydantic import BaseModel, Field

import google.generativeai as genai
from agents import function_tool

from database.queries import (
    search_knowledge_base as db_search_kb,
    create_ticket_record,
    get_ticket_by_id,
    update_ticket_status,
    load_conversation_history,
    record_metric,
)
from kafka_client import FTEKafkaProducer, TOPICS
from channels.whatsapp_handler import WhatsAppMCPHandler
from channels.gmail_handler import GmailHandler
from agent.formatters import format_for_channel
import os

logger = logging.getLogger(__name__)

# Configure Gemini
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

# Initialize handlers (lazy loaded)
_whatsapp_handler = None
_gmail_handler = None
_kafka_producer = None


def get_whatsapp_handler():
    global _whatsapp_handler
    if _whatsapp_handler is None:
        _whatsapp_handler = WhatsAppMCPHandler()
    return _whatsapp_handler


def get_gmail_handler():
    global _gmail_handler
    if _gmail_handler is None:
        _gmail_handler = GmailHandler()
    return _gmail_handler


async def get_kafka_producer():
    global _kafka_producer
    if _kafka_producer is None:
        _kafka_producer = FTEKafkaProducer(
            bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        )
        await _kafka_producer.start()
    return _kafka_producer


# ============================================================================
# Tool Input Models
# ============================================================================

class SearchKnowledgeBaseInput(BaseModel):
    query: str = Field(description="Search query for knowledge base")
    max_results: int = Field(default=5, description="Maximum number of results")


class CreateTicketInput(BaseModel):
    customer_id: str = Field(description="Customer UUID")
    issue: str = Field(description="Description of the issue")
    priority: str = Field(description="Priority: low, medium, high, urgent")
    category: str = Field(description="Category: general, technical, billing, bug_report, feedback")
    channel: str = Field(description="Source channel: email, whatsapp, web_form")


class GetCustomerHistoryInput(BaseModel):
    customer_id: str = Field(description="Customer UUID")


class EscalateToHumanInput(BaseModel):
    ticket_id: str = Field(description="Ticket UUID")
    reason: str = Field(description="Reason for escalation")
    urgency: str = Field(default="normal", description="Urgency: normal, high, urgent")


class SendResponseInput(BaseModel):
    ticket_id: str = Field(description="Ticket UUID")
    message: str = Field(description="Response message to send")
    channel: str = Field(description="Channel: email, whatsapp, web_form")


class AnalyzeSentimentInput(BaseModel):
    text: str = Field(description="Text to analyze for sentiment")


# ============================================================================
# Tools
# ============================================================================

@function_tool
async def search_knowledge_base(query: str, max_results: int = 5) -> str:
    """
    Search the knowledge base for relevant articles.
    Returns formatted results with title, content snippet, and relevance score.
    """
    try:
        # Generate embedding for query
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=query
        )
        query_embedding = result["embedding"]

        # Search database
        results = await db_search_kb(query_embedding, max_results)

        if not results:
            return "No relevant articles found in knowledge base."

        # Format results
        formatted = []
        for i, article in enumerate(results, 1):
            score = article.get("similarity_score", 0)
            title = article.get("title", "Untitled")
            content = article.get("content", "")
            category = article.get("category", "general")

            # Truncate content to snippet
            snippet = content[:200] + "..." if len(content) > 200 else content

            formatted.append(
                f"{i}. [{category}] {title} (relevance: {score:.2f})\n"
                f"   {snippet}\n"
            )

        await record_metric("kb_search", len(results))
        return "\n".join(formatted)

    except Exception as e:
        logger.error(f"Knowledge base search failed: {e}", exc_info=True)
        return f"Error searching knowledge base: {str(e)}"


@function_tool
async def create_ticket(
    customer_id: str,
    issue: str,
    priority: str,
    category: str,
    channel: str
) -> str:
    """
    Create a support ticket. Always call this FIRST in every interaction.
    Returns the ticket ID.
    """
    try:
        ticket_id = str(uuid.uuid4())

        ticket_data = {
            "customer_id": customer_id,
            "source_channel": channel,
            "category": category,
            "priority": priority,
            "status": "open",
            "subject": issue[:200],  # Truncate to reasonable length
        }

        await create_ticket_record(ticket_id, ticket_data)
        await record_metric("ticket_created", 1, channel=channel)

        logger.info(f"Created ticket {ticket_id} for customer {customer_id}")
        return f"Ticket created successfully. Ticket ID: {ticket_id}"

    except Exception as e:
        logger.error(f"Failed to create ticket: {e}", exc_info=True)
        return f"Error creating ticket: {str(e)}"


@function_tool
async def get_customer_history(customer_id: str) -> str:
    """
    Get customer's conversation history across all channels.
    Returns last 20 messages with channel labels.
    """
    try:
        # This is simplified - in production, query across all conversations
        # For now, return a summary format
        from database.queries import get_db_pool

        pool = await get_db_pool()
        rows = await pool.fetch(
            """
            SELECT m.content, m.channel, m.role, m.created_at, c.initial_channel
            FROM messages m
            JOIN conversations c ON m.conversation_id = c.id
            WHERE c.customer_id = $1
            ORDER BY m.created_at DESC
            LIMIT 20
            """,
            customer_id
        )

        if not rows:
            return "No previous conversation history found for this customer."

        # Format history
        formatted = ["Customer History (most recent first):\n"]
        channels_used = set()

        for row in rows:
            channel = row["channel"]
            channels_used.add(channel)
            role = row["role"]
            content = row["content"][:100] + "..." if len(row["content"]) > 100 else row["content"]
            timestamp = row["created_at"].strftime("%Y-%m-%d %H:%M")

            formatted.append(f"[{channel}] {timestamp} - {role}: {content}")

        # Add cross-channel note
        if len(channels_used) > 1:
            formatted.insert(1, f"Note: Customer has used multiple channels: {', '.join(channels_used)}\n")

        return "\n".join(formatted)

    except Exception as e:
        logger.error(f"Failed to get customer history: {e}", exc_info=True)
        return f"Error retrieving customer history: {str(e)}"


@function_tool
async def escalate_to_human(ticket_id: str, reason: str, urgency: str = "normal") -> str:
    """
    Escalate ticket to human agent.
    Use when issue is beyond AI capabilities or customer explicitly requests human support.
    """
    try:
        # Update ticket status
        await update_ticket_status(ticket_id, "escalated", notes=f"Escalation reason: {reason}")

        # Publish to escalations topic
        producer = await get_kafka_producer()
        await producer.publish(TOPICS["escalations"], {
            "ticket_id": ticket_id,
            "reason": reason,
            "urgency": urgency,
            "escalated_at": "2026-02-28T15:09:10.504Z",
        })

        await record_metric("escalation", 1, dimensions={"reason": reason, "urgency": urgency})

        logger.info(f"Escalated ticket {ticket_id}: {reason}")
        return f"Ticket escalated to human agent. Urgency: {urgency}. A team member will respond shortly."

    except Exception as e:
        logger.error(f"Failed to escalate ticket: {e}", exc_info=True)
        return f"Error escalating ticket: {str(e)}"


@function_tool
async def send_response(ticket_id: str, message: str, channel: str) -> str:
    """
    Send response to customer via appropriate channel.
    Handles routing to email, WhatsApp, or web form.
    """
    try:
        # Get ticket details
        ticket = await get_ticket_by_id(ticket_id)
        if not ticket:
            return f"Error: Ticket {ticket_id} not found"

        # Format message for channel
        formatted = await format_for_channel(message, channel, ticket)

        # Route to appropriate channel
        if channel == "whatsapp":
            handler = get_whatsapp_handler()

            # Get customer phone from ticket
            from database.queries import get_db_pool
            pool = await get_db_pool()
            customer = await pool.fetchrow(
                "SELECT phone FROM customers WHERE id = $1",
                ticket["customer_id"]
            )

            if not customer or not customer["phone"]:
                return "Error: Customer phone number not found"

            # Split and send message
            parts = handler.split_message(formatted, max_len=1600)
            for part in parts:
                await handler.send_message(customer["phone"], part)

            logger.info(f"Sent WhatsApp response for ticket {ticket_id}")

        elif channel == "email":
            handler = get_gmail_handler()

            # Get customer email
            from database.queries import get_db_pool
            pool = await get_db_pool()
            customer = await pool.fetchrow(
                "SELECT email FROM customers WHERE id = $1",
                ticket["customer_id"]
            )

            if not customer or not customer["email"]:
                return "Error: Customer email not found"

            subject = f"Re: {ticket.get('subject', 'Your Support Request')}"
            await handler.send_reply(customer["email"], subject, formatted)

            logger.info(f"Sent email response for ticket {ticket_id}")

        else:  # web_form
            # Store response in database for web form retrieval
            from database.queries import store_message
            await store_message(
                conversation_id=ticket["conversation_id"],
                channel="web_form",
                direction="outbound",
                role="assistant",
                content=formatted,
                delivery_status="delivered"
            )

            logger.info(f"Stored web form response for ticket {ticket_id}")

        await record_metric("response_sent", 1, channel=channel)
        return f"Response sent successfully via {channel}"

    except Exception as e:
        logger.error(f"Failed to send response: {e}", exc_info=True)
        return f"Error sending response: {str(e)}"


@function_tool
async def analyze_sentiment(text: str) -> str:
    """
    Analyze sentiment of customer message.
    Returns score (0.0-1.0), label, and confidence.
    Scores < 0.3 trigger automatic escalation.
    """
    try:
        # Keyword-based sentiment analysis
        text_lower = text.lower()

        # Negative indicators
        negative_keywords = [
            "angry", "frustrated", "terrible", "awful", "horrible", "worst",
            "hate", "disappointed", "useless", "broken", "never", "always fails",
            "unacceptable", "ridiculous", "pathetic", "disgusted", "furious"
        ]

        # Positive indicators
        positive_keywords = [
            "thank", "thanks", "great", "excellent", "perfect", "love",
            "appreciate", "helpful", "amazing", "wonderful", "fantastic"
        ]

        # Legal/escalation keywords
        legal_keywords = [
            "lawyer", "attorney", "sue", "lawsuit", "legal action", "court"
        ]

        # Count matches
        negative_count = sum(1 for kw in negative_keywords if kw in text_lower)
        positive_count = sum(1 for kw in positive_keywords if kw in text_lower)
        legal_count = sum(1 for kw in legal_keywords if kw in text_lower)

        # Calculate score
        if legal_count > 0:
            score = 0.1
            label = "critical"
        elif negative_count > positive_count:
            score = max(0.2, 0.5 - (negative_count * 0.1))
            label = "negative"
        elif positive_count > negative_count:
            score = min(1.0, 0.7 + (positive_count * 0.1))
            label = "positive"
        else:
            score = 0.5
            label = "neutral"

        confidence = min(0.9, 0.5 + (abs(negative_count - positive_count) * 0.1))

        result = f"Sentiment: {label} (score: {score:.2f}, confidence: {confidence:.2f})"

        if score < 0.3:
            result += "\n⚠️ LOW SENTIMENT DETECTED - Consider escalation"

        await record_metric("sentiment_analyzed", score)
        return result

    except Exception as e:
        logger.error(f"Sentiment analysis failed: {e}", exc_info=True)
        return f"Error analyzing sentiment: {str(e)}"
