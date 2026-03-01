"""
WhatsApp handler using whatsapp-mcp (not Twilio).

The Go bridge writes messages to SQLite.
This handler calls the Python MCP server via stdio using the `mcp` library.
"""

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import os
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class WhatsAppMCPHandler:
    """Handler for WhatsApp communication via whatsapp-mcp."""

    def __init__(self):
        self.server_path = os.getenv(
            "WHATSAPP_MCP_SERVER_PATH",
            "../whatsapp-mcp/whatsapp-mcp-server"
        )
        self.own_number = os.getenv("WHATSAPP_OWN_NUMBER", "").lstrip("+")

    def _server_params(self):
        """Get server parameters for stdio connection."""
        return StdioServerParameters(
            command="uv",
            args=["--directory", self.server_path, "run", "main.py"],
        )

    async def _call_tool(self, name: str, params: dict):
        """Call an MCP tool and return the result."""
        async with stdio_client(self._server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, params)
                return self._parse(result)

    def _parse(self, result):
        """Parse MCP tool result."""
        if result and result.content:
            for item in result.content:
                if hasattr(item, "text"):
                    try:
                        return json.loads(item.text)
                    except (json.JSONDecodeError, TypeError):
                        return item.text
        return None

    async def list_chats(self) -> list[dict]:
        """List all available WhatsApp chats."""
        try:
            r = await self._call_tool("list_chats", {})
            return r if isinstance(r, list) else []
        except Exception as e:
            logger.error(f"Failed to list chats: {e}")
            return []

    async def list_messages(self, chat_jid: str, limit: int = 20) -> list[dict]:
        """List messages from a specific chat."""
        try:
            r = await self._call_tool("list_messages", {
                "chat_jid": chat_jid,
                "limit": limit,
                "include_context": False
            })
            return r if isinstance(r, list) else []
        except Exception as e:
            logger.error(f"Failed to list messages for {chat_jid}: {e}")
            return []

    async def send_message(self, phone_or_jid: str, body: str) -> dict:
        """Send a WhatsApp message."""
        try:
            recipient = self._to_jid(phone_or_jid)
            await self._call_tool("send_message", {
                "recipient": recipient,
                "message": body
            })
            logger.info(f"WhatsApp sent to {recipient}")
            return {"delivery_status": "sent", "recipient": recipient}
        except Exception as e:
            logger.error(f"Failed to send WhatsApp message: {e}")
            return {"delivery_status": "failed", "error": str(e)}

    def _to_jid(self, phone_or_jid: str) -> str:
        """Convert phone number to WhatsApp JID format."""
        if "@" in phone_or_jid:
            return phone_or_jid
        digits = phone_or_jid.lstrip("+").replace(" ", "").replace("-", "")
        return f"{digits}@s.whatsapp.net"

    def normalize_inbound(self, raw: dict, sender_phone: str) -> dict:
        """Normalize raw WhatsApp message to standard format."""
        return {
            "channel": "whatsapp",
            "channel_message_id": raw.get("id", ""),
            "customer_phone": sender_phone,
            "content": raw.get("content") or raw.get("text", ""),
            "received_at": raw.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "metadata": {
                "chat_jid": raw.get("chat_jid", ""),
                "sender_name": raw.get("sender_name", ""),
                "is_group": "@g.us" in raw.get("chat_jid", ""),
            },
        }

    def split_message(self, text: str, max_len: int = 1600) -> list[str]:
        """
        Split long messages into chunks for WhatsApp.
        WhatsApp has a 4096 char limit, but we use 1600 for better UX.
        """
        if len(text) <= max_len:
            return [text]

        parts = []
        remaining = text

        while remaining:
            if len(remaining) <= max_len:
                parts.append(remaining)
                break

            # Try to split at sentence boundary
            cut = remaining.rfind(". ", 0, max_len)
            if cut == -1:
                # Try to split at word boundary
                cut = remaining.rfind(" ", 0, max_len)
            if cut == -1:
                # Force split at max_len
                cut = max_len

            parts.append(remaining[:cut + 1].strip())
            remaining = remaining[cut + 1:].strip()

        return parts
