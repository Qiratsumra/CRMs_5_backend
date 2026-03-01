"""
Kafka client for event streaming.
Provides producer and consumer classes with automatic reconnection and structured logging.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from aiokafka.errors import KafkaError

logger = logging.getLogger(__name__)

# Topic definitions
TOPICS = {
    "tickets_incoming": "fte.tickets.incoming",
    "email_inbound": "fte.channels.email.inbound",
    "whatsapp_inbound": "fte.channels.whatsapp.inbound",
    "webform_inbound": "fte.channels.webform.inbound",
    "escalations": "fte.escalations",
    "metrics": "fte.metrics",
    "dlq": "fte.dlq",
}


class FTEKafkaProducer:
    """Kafka producer for publishing messages to topics."""

    def __init__(self, bootstrap_servers: str = "localhost:9092"):
        self.bootstrap_servers = bootstrap_servers
        self.producer: Optional[AIOKafkaProducer] = None

    async def start(self):
        """Start the Kafka producer."""
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                compression_type="gzip",
            )
            await self.producer.start()
            logger.info(f"Kafka producer started: {self.bootstrap_servers}")
        except KafkaError as e:
            logger.error(f"Failed to start Kafka producer: {e}")
            raise

    async def stop(self):
        """Stop the Kafka producer."""
        if self.producer:
            await self.producer.stop()
            logger.info("Kafka producer stopped")

    async def publish(self, topic: str, message: dict):
        """
        Publish a message to a topic.
        Automatically adds timestamp if not present.
        """
        if not self.producer:
            raise RuntimeError("Producer not started. Call start() first.")

        # Add timestamp if not present
        if "timestamp" not in message:
            message["timestamp"] = datetime.now(timezone.utc).isoformat()

        try:
            await self.producer.send_and_wait(topic, message)
            logger.debug(f"Published to {topic}: {message.get('channel_message_id', 'N/A')}")
        except KafkaError as e:
            logger.error(f"Failed to publish to {topic}: {e}", exc_info=True)
            # Publish to DLQ
            try:
                dlq_message = {
                    "original_topic": topic,
                    "error": str(e),
                    "message": message,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                await self.producer.send_and_wait(TOPICS["dlq"], dlq_message)
            except Exception as dlq_error:
                logger.error(f"Failed to publish to DLQ: {dlq_error}")


class FTEKafkaConsumer:
    """Kafka consumer for processing messages from topics."""

    def __init__(
        self,
        topics: list[str],
        group_id: str,
        bootstrap_servers: str = "localhost:9092",
    ):
        self.topics = topics
        self.group_id = group_id
        self.bootstrap_servers = bootstrap_servers
        self.consumer: Optional[AIOKafkaConsumer] = None
        self._running = False

    async def start(self):
        """Start the Kafka consumer."""
        try:
            self.consumer = AIOKafkaConsumer(
                *self.topics,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                auto_offset_reset="earliest",
                enable_auto_commit=True,
            )
            await self.consumer.start()
            logger.info(f"Kafka consumer started: {self.group_id} on {self.topics}")
        except KafkaError as e:
            logger.error(f"Failed to start Kafka consumer: {e}")
            raise

    async def stop(self):
        """Stop the Kafka consumer."""
        self._running = False
        if self.consumer:
            await self.consumer.stop()
            logger.info("Kafka consumer stopped")

    async def consume(self, handler: Callable):
        """
        Consume messages and pass them to the handler coroutine.
        Runs until stop() is called.
        """
        if not self.consumer:
            raise RuntimeError("Consumer not started. Call start() first.")

        self._running = True
        logger.info(f"Starting message consumption for {self.group_id}")

        try:
            async for msg in self.consumer:
                if not self._running:
                    break

                try:
                    logger.debug(f"Received message from {msg.topic}: offset {msg.offset}")
                    await handler(msg.value)
                except Exception as e:
                    logger.error(
                        f"Error processing message from {msg.topic}: {e}",
                        exc_info=True,
                    )
                    # Continue processing other messages

        except KafkaError as e:
            logger.error(f"Kafka consumer error: {e}", exc_info=True)
            # Attempt reconnection
            await asyncio.sleep(5)
            if self._running:
                logger.info("Attempting to reconnect consumer...")
                await self.start()
                await self.consume(handler)
