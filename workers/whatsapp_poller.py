"""
WhatsApp Poller — replaces the Twilio webhook.
Polls every WHATSAPP_POLL_INTERVAL_SECONDS. Deploy as exactly 1 replica.
"""

import asyncio
import os
import logging
from channels.whatsapp_handler import WhatsAppMCPHandler
from kafka_client import FTEKafkaProducer, TOPICS
from database.queries import is_whatsapp_message_processed, mark_whatsapp_message_processed

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

POLL_INTERVAL = int(os.getenv("WHATSAPP_POLL_INTERVAL_SECONDS", "5"))
OWN_DIGITS = os.getenv("WHATSAPP_OWN_NUMBER", "").lstrip("+")


class WhatsAppPoller:
    """Polls WhatsApp for new messages and publishes to Kafka."""

    def __init__(self):
        self.handler = WhatsAppMCPHandler()
        self.producer = FTEKafkaProducer(
            bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        )

    async def start(self):
        """Start the polling loop."""
        await self.producer.start()
        logger.info(f"WhatsApp poller started — polling every {POLL_INTERVAL}s")

        while True:
            try:
                await self.poll_once()
            except Exception as e:
                logger.error(f"Poll error: {e}", exc_info=True)

            await asyncio.sleep(POLL_INTERVAL)

    async def poll_once(self):
        """Poll all chats for new messages."""
        chats = await self.handler.list_chats()

        for chat in chats:
            jid = chat.get("jid") or chat.get("id", "")

            # Skip groups
            if not jid or "@g.us" in jid:
                continue

            # Get recent messages
            messages = await self.handler.list_messages(jid, limit=10)

            for msg in messages:
                msg_id = msg.get("id", "")
                if not msg_id:
                    continue

                # Check if already processed
                if await is_whatsapp_message_processed(msg_id):
                    continue

                # Extract sender
                sender = msg.get("sender") or msg.get("from", "")
                sender_digits = sender.split("@")[0] if "@" in sender else sender

                # Skip our own messages
                if OWN_DIGITS and OWN_DIGITS in sender_digits:
                    await mark_whatsapp_message_processed(msg_id, jid)
                    continue

                # Normalize and publish
                normalized = self.handler.normalize_inbound(msg, f"+{sender_digits}")
                await self.producer.publish(TOPICS["tickets_incoming"], normalized)
                await mark_whatsapp_message_processed(msg_id, jid)

                logger.info(f"Published WhatsApp msg {msg_id} from {sender_digits}")


async def main():
    """Entry point for WhatsApp poller."""
    poller = WhatsAppPoller()
    await poller.start()


if __name__ == "__main__":
    asyncio.run(main())
