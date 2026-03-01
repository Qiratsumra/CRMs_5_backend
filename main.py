"""
FastAPI main application.
Provides REST API endpoints for the Customer Success FTE system.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from channels.web_form_handler import router as support_router
from channels.gmail_handler import GmailHandler
from channels.whatsapp_handler import WhatsAppMCPHandler
from database.queries import (
    get_db_pool,
    load_conversation_history,
    get_channel_metrics,
)

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Customer Success FTE API",
    description="Multi-channel customer support system with AI agent",
    version="1.0.0"
)

# Configure CORS
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(support_router)

# Initialize handlers
gmail_handler = GmailHandler() if os.getenv("GMAIL_ENABLED", "true") == "true" else None
whatsapp_handler = WhatsAppMCPHandler() if os.getenv("WHATSAPP_ENABLED", "true") == "true" else None


# ============================================================================
# Models
# ============================================================================

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    channels: dict


class ConversationMessage(BaseModel):
    role: str
    content: str
    channel: str
    created_at: str


class CustomerLookup(BaseModel):
    customer_id: str
    email: Optional[str]
    phone: Optional[str]
    name: Optional[str]
    created_at: str


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    System health check with per-channel status.
    Checks database, Gmail, and WhatsApp connectivity.
    """
    channels = {
        "email": "unknown",
        "whatsapp": "unknown",
        "web_form": "active"  # Always active if API is running
    }

    # Check email
    if gmail_handler and os.getenv("GMAIL_ENABLED", "true") == "true":
        try:
            if gmail_handler.service:
                channels["email"] = "active"
            else:
                channels["email"] = "degraded"
        except Exception as e:
            logger.error(f"Gmail health check failed: {e}")
            channels["email"] = "degraded"
    else:
        channels["email"] = "disabled"

    # Check WhatsApp
    if whatsapp_handler and os.getenv("WHATSAPP_ENABLED", "true") == "true":
        try:
            import asyncio
            chats = await asyncio.wait_for(
                whatsapp_handler.list_chats(),
                timeout=3.0
            )
            channels["whatsapp"] = "active" if chats is not None else "degraded"
        except asyncio.TimeoutError:
            logger.warning("WhatsApp health check timed out")
            channels["whatsapp"] = "degraded"
        except Exception as e:
            logger.error(f"WhatsApp health check failed: {e}")
            channels["whatsapp"] = "degraded"
    else:
        channels["whatsapp"] = "disabled"

    # Overall status
    status = "healthy"
    if any(v == "degraded" for v in channels.values()):
        status = "degraded"

    return HealthResponse(
        status=status,
        timestamp=datetime.now(timezone.utc).isoformat(),
        channels=channels
    )


@app.post("/webhooks/gmail")
async def gmail_webhook(request: Request):
    """
    Gmail Pub/Sub push notification webhook.
    Processes new email messages.
    """
    if not gmail_handler:
        raise HTTPException(status_code=503, detail="Gmail not enabled")

    try:
        body = await request.json()

        # Process the notification
        messages = await gmail_handler.process_notification(body.get("message", {}))

        # Publish to Kafka
        from kafka_client import FTEKafkaProducer, TOPICS
        producer = FTEKafkaProducer(
            bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        )
        await producer.start()

        for msg in messages:
            await producer.publish(TOPICS["tickets_incoming"], msg)

        await producer.stop()

        logger.info(f"Processed Gmail webhook: {len(messages)} messages")
        return {"status": "ok", "messages_processed": len(messages)}

    except Exception as e:
        logger.error(f"Gmail webhook failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process Gmail webhook")


@app.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """
    Get full conversation history with all messages.
    """
    try:
        messages = await load_conversation_history(conversation_id)

        if not messages:
            raise HTTPException(status_code=404, detail="Conversation not found")

        return {
            "conversation_id": conversation_id,
            "message_count": len(messages),
            "messages": [
                ConversationMessage(
                    role=msg["role"],
                    content=msg["content"],
                    channel=msg["channel"],
                    created_at=msg["created_at"].isoformat()
                )
                for msg in messages
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get conversation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve conversation")


@app.get("/customers/lookup")
async def lookup_customer(email: Optional[str] = None, phone: Optional[str] = None):
    """
    Look up customer by email or phone number.
    """
    if not email and not phone:
        raise HTTPException(status_code=400, detail="Must provide email or phone")

    try:
        from database.queries import get_customer_by_email, get_customer_by_phone

        customer = None
        if email:
            customer = await get_customer_by_email(email)
        elif phone:
            customer = await get_customer_by_phone(phone)

        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        return CustomerLookup(
            customer_id=str(customer["id"]),
            email=customer.get("email"),
            phone=customer.get("phone"),
            name=customer.get("name"),
            created_at=customer["created_at"].isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Customer lookup failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to lookup customer")


@app.get("/metrics/channels")
async def get_metrics():
    """
    Get 24-hour metrics per channel.
    """
    try:
        metrics = await get_channel_metrics(hours=24)

        return {
            "period": "24h",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "channels": metrics
        }

    except Exception as e:
        logger.error(f"Failed to get metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve metrics")


@app.get("/metrics/summary")
async def get_metrics_summary():
    """
    Get overall system metrics summary.
    """
    try:
        pool = await get_db_pool()

        # Get counts
        ticket_count = await pool.fetchval("SELECT COUNT(*) FROM tickets WHERE created_at > NOW() - INTERVAL '24 hours'")
        conversation_count = await pool.fetchval("SELECT COUNT(*) FROM conversations WHERE started_at > NOW() - INTERVAL '24 hours'")
        escalation_count = await pool.fetchval("SELECT COUNT(*) FROM tickets WHERE status = 'escalated' AND created_at > NOW() - INTERVAL '24 hours'")

        # Get average sentiment
        avg_sentiment = await pool.fetchval(
            "SELECT AVG(sentiment_score) FROM conversations WHERE sentiment_score IS NOT NULL AND started_at > NOW() - INTERVAL '24 hours'"
        )

        return {
            "period": "24h",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tickets_created": ticket_count or 0,
            "conversations": conversation_count or 0,
            "escalations": escalation_count or 0,
            "average_sentiment": float(avg_sentiment) if avg_sentiment else None,
        }

    except Exception as e:
        logger.error(f"Failed to get summary metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve metrics summary")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Customer Success FTE API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }


# ============================================================================
# Startup/Shutdown
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize connections on startup."""
    logger.info("Starting Customer Success FTE API")

    # Initialize database pool
    await get_db_pool()
    logger.info("Database connection pool initialized")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown."""
    logger.info("Shutting down Customer Success FTE API")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=os.getenv("ENVIRONMENT") == "development"
    )
