"""
Customer Success Agent definition and runner.
Uses Google Genai (new package).
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional
from google import genai

from dotenv import load_dotenv

from agent.prompts import CUSTOMER_SUCCESS_SYSTEM_PROMPT
from database.queries import (
    get_or_create_customer,
    get_active_conversation,
    create_conversation,
    store_message,
)

load_dotenv()
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configure Gemini with new package
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


async def run_agent(message: dict) -> dict:
    """
    Run the agent for a customer message.

    Full lifecycle:
    1. Resolve/create customer
    2. Get or create active conversation
    3. Store inbound message
    4. Build conversation history
    5. Run agent
    6. Store outbound message
    7. Return result

    Args:
        message: Normalized message dict with keys:
            - channel: email, whatsapp, web_form
            - content: message text
            - customer_email or customer_phone
            - customer_name (optional)
            - metadata (optional)

    Returns:
        Result dict with status, conversation_id, message_id, etc.
    """
    start_time = datetime.now(timezone.utc)

    try:
        # 1. Resolve or create customer
        logger.info(f"Processing message from {message.get('channel')}")
        customer_id = await get_or_create_customer(message)

        # 2. Get or create active conversation
        conversation = await get_active_conversation(customer_id)
        if not conversation:
            conversation_id = await create_conversation(
                customer_id,
                message.get("channel", "unknown")
            )
        else:
            conversation_id = str(conversation["id"])

        # 3. Check if message already exists (web form already stores it)
        # Only store if conversation_id is provided (meaning message not yet stored)
        inbound_msg_id = None
        if not message.get("conversation_id"):
            inbound_msg_id = await store_message(
                conversation_id=conversation_id,
                channel=message.get("channel"),
                direction="inbound",
                role="user",
                content=message.get("content", ""),
                channel_message_id=message.get("channel_message_id"),
                delivery_status="received"
            )

        # 4. Build conversation history for context
        from database.queries import load_conversation_history
        history = await load_conversation_history(conversation_id)

        # Format history for agent context
        history_text = "\n".join([
            f"{msg['role']}: {msg['content']}"
            for msg in history[-10:]  # Last 10 messages
        ])

        # 5. Prepare agent input
        context_parts = [
            CUSTOMER_SUCCESS_SYSTEM_PROMPT,
            f"\nChannel: {message.get('channel')}",
            f"Customer name: {message.get('customer_name', 'Unknown')}",
            f"Customer message: {message.get('content', '')}",
        ]

        if history_text:
            context_parts.append(f"\nConversation history:\n{history_text}")

        agent_prompt = "\n\n".join(context_parts)

        # 6. Run Gemini
        logger.info(f"Running Gemini for conversation {conversation_id}")

        response = client.models.generate_content(
            model='gemini-2.0-flash-exp',
            contents=agent_prompt
        )

        # Handle response safely
        if response.text:
            response_text = response.text
        else:
            # Fallback if Gemini blocks or fails
            logger.warning(f"Gemini response blocked or empty")
            response_text = "Thank you for contacting us. We've received your message and our team will review it shortly. We'll get back to you as soon as possible."

        # 7. Store outbound message
        outbound_msg_id = await store_message(
            conversation_id=conversation_id,
            channel=message.get("channel"),
            direction="outbound",
            role="agent",
            content=response_text,
            delivery_status="sent"
        )

        # 8. Calculate metrics
        end_time = datetime.now(timezone.utc)
        latency_ms = int((end_time - start_time).total_seconds() * 1000)

        # Record latency metric
        from database.queries import record_metric
        await record_metric(
            "response_latency_ms",
            latency_ms,
            channel=message.get("channel")
        )

        logger.info(
            f"Agent completed for conversation {conversation_id} "
            f"in {latency_ms}ms"
        )

        return {
            "status": "success",
            "customer_id": customer_id,
            "conversation_id": conversation_id,
            "inbound_message_id": inbound_msg_id,
            "outbound_message_id": outbound_msg_id,
            "response": response_text,
            "latency_ms": latency_ms,
        }

    except Exception as e:
        logger.error(f"Agent execution failed: {e}", exc_info=True)

        return {
            "status": "error",
            "error": str(e),
            "message": message,
        }
