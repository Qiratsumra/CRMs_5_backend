"""
Channel-specific message formatters.
Formats agent responses according to channel requirements and constraints.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def format_for_channel(response: str, channel: str, ticket_data: dict) -> str:
    """
    Format response text for specific channel.

    Args:
        response: Raw agent response text
        channel: Target channel (email, whatsapp, web_form)
        ticket_data: Ticket information for context

    Returns:
        Formatted response string
    """
    if channel == "email":
        return _format_email(response, ticket_data)
    elif channel == "whatsapp":
        return _format_whatsapp(response, ticket_data)
    elif channel == "web_form":
        return _format_web_form(response, ticket_data)
    else:
        logger.warning(f"Unknown channel: {channel}, using default formatting")
        return response


def _format_email(response: str, ticket_data: dict) -> str:
    """
    Format for email channel.
    - Formal greeting with customer name
    - Structured paragraphs
    - TechCorp signature
    - Ticket reference footer
    - Max 500 words
    """
    customer_name = ticket_data.get("customer_name", "Valued Customer")
    ticket_id = ticket_data.get("id", "N/A")

    # Truncate to ~500 words if needed
    words = response.split()
    if len(words) > 500:
        response = " ".join(words[:500]) + "..."
        logger.warning(f"Email response truncated to 500 words for ticket {ticket_id}")

    # Build formatted email
    formatted = f"""Dear {customer_name},

{response}

If you have any further questions, please don't hesitate to reach out.

Best regards,
TechCorp Customer Success Team

---
Ticket Reference: {ticket_id}
Need immediate assistance? Visit https://support.techcorp.com
"""

    return formatted


def _format_whatsapp(response: str, ticket_data: dict) -> str:
    """
    Format for WhatsApp channel.
    - Strip ALL markdown symbols (**, *, #, -, _)
    - Plain text only
    - Conversational tone
    - Append support footer
    - Prefer under 300 chars but allow longer
    """
    # Remove all markdown formatting
    formatted = response

    # Remove bold (**text** or __text__)
    formatted = re.sub(r'\*\*(.+?)\*\*', r'\1', formatted)
    formatted = re.sub(r'__(.+?)__', r'\1', formatted)

    # Remove italic (*text* or _text_)
    formatted = re.sub(r'\*(.+?)\*', r'\1', formatted)
    formatted = re.sub(r'_(.+?)_', r'\1', formatted)

    # Remove headers (# text)
    formatted = re.sub(r'^#+\s+', '', formatted, flags=re.MULTILINE)

    # Remove list markers (- item or * item)
    formatted = re.sub(r'^[\*\-]\s+', '', formatted, flags=re.MULTILINE)

    # Remove code blocks (```text```)
    formatted = re.sub(r'```.*?```', '', formatted, flags=re.DOTALL)
    formatted = re.sub(r'`(.+?)`', r'\1', formatted)

    # Clean up extra whitespace
    formatted = re.sub(r'\n{3,}', '\n\n', formatted)
    formatted = formatted.strip()

    # Append support footer
    formatted += "\n\n💬 Reply 'human' for live support."

    return formatted


def _format_web_form(response: str, ticket_data: dict) -> str:
    """
    Format for web form channel.
    - Professional but approachable
    - Light markdown OK (bold, lists)
    - Max 300 words
    - Append help footer
    """
    ticket_id = ticket_data.get("id", "N/A")

    # Truncate to ~300 words if needed
    words = response.split()
    if len(words) > 300:
        response = " ".join(words[:300]) + "..."
        logger.warning(f"Web form response truncated to 300 words for ticket {ticket_id}")

    # Truncate to 1000 chars max
    if len(response) > 1000:
        response = response[:997] + "..."

    # Append footer
    formatted = f"""{response}

---
Need more help? Reply below.

Ticket ID: {ticket_id}
"""

    return formatted


def strip_markdown(text: str) -> str:
    """
    Utility function to strip all markdown formatting from text.
    Used primarily for WhatsApp but available for other channels.
    """
    # Remove bold
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)

    # Remove italic
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)

    # Remove headers
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)

    # Remove list markers
    text = re.sub(r'^[\*\-]\s+', '', text, flags=re.MULTILINE)

    # Remove code blocks
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'`(.+?)`', r'\1', text)

    # Remove links [text](url)
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)

    # Clean up whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def truncate_words(text: str, max_words: int) -> str:
    """Truncate text to maximum number of words."""
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "..."


def truncate_chars(text: str, max_chars: int) -> str:
    """Truncate text to maximum number of characters."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 3] + "..."
