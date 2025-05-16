import asyncio
import json
import logging
from typing import Dict, List, Set, Optional, Callable

from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import TopicAlreadyExistsError, KafkaConnectionError

from shared.safe_naming import TopicNames, MessageType

logger = logging.getLogger(__name__)


class KafkaHandler:

    def __init__(self, *args, **kwargs):
        """
        Initializes the KafkaHandler with optional parameters.

        Sets up the bootstrap servers, producers, consumers, and initialized topics.
        """
        self._bootstrap_servers = f"{TopicNames.KAFKA_HOST.value}:9092"
        self._admin_client: Optional[AIOKafkaAdminClient] = None
        self._producers: Dict[str, AIOKafkaProducer] = {}
        self._consumers: Dict[str, AIOKafkaConsumer] = {}
        self._consumer_tasks: Dict[str, asyncio.Task] = {}
        self._initialized_topics: Set[str] = set()

    def validateInitialization(self, topic_name: Optional[str] = None) -> bool:
        """
        Validates the initialization of the Kafka connection, producers, and topics.

        Args:
            topic_name (str | None): The name of the topic to validate, if specified.

        Returns:
            bool: True if the producers and specified topic are initialized, False otherwise.
        """
        if not self._producers:
            logger.error("Kafka producers are not initialized.")
            return False
        if topic_name and topic_name not in self._producers:
            logger.error(f"Producer for topic '{topic_name}' is not initialized.")
            return False
        if topic_name and topic_name not in self._initialized_topics:
            logger.error(f"Topic '{topic_name}' is not initialized.")
            return False
        return True

    async def _initializeConnection(self, topic_names: List[str]) -> None:
        """
        Initializes the Kafka connection and creates the specified topics.

        Args:
            topic_names (List[str]): A list of topic names to initialize.
        """
        try:
            if not self._admin_client:
                self._admin_client = AIOKafkaAdminClient(
                    bootstrap_servers=self._bootstrap_servers,
                    client_id='admin-client'
                )
                await self._admin_client.start()
                logger.info(f"Admin client connected to {self._bootstrap_servers}")

            new_topics = []
            for topic_name in topic_names:
                if topic_name not in self._initialized_topics:
                    new_topics.append(NewTopic(
                        name=topic_name,
                        num_partitions=1,
                        replication_factor=1
                    ))

            if new_topics:
                try:
                    await self._admin_client.create_topics(new_topics)
                    logger.info(f"Created topics: {[t.name for t in new_topics]}")
                except TopicAlreadyExistsError:
                    logger.info("Some topics already exist")

            for topic_name in topic_names:
                if topic_name not in self._producers:
                    producer = AIOKafkaProducer(
                        bootstrap_servers=self._bootstrap_servers,
                        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                        key_serializer=lambda k: k.encode('utf-8') if k else None
                    )
                    await producer.start()
                    self._producers[topic_name] = producer
                self._initialized_topics.add(topic_name)
                logger.info(f"Initialized producer for topic '{topic_name}'")

        except Exception as e:
            logger.error(f"Failed to initialize Kafka connection: {e}")
            raise

    async def publishToTopic(self, topic_name: str, message: dict, message_type: Optional[MessageType] = None) -> None:
        """
        Sends a message to the specified Kafka topic.

        Args:
            topic_name (str): The name of the topic to send the message to.
            message (dict): The message to send.
            message_type (MessageType, optional): The type of the message.
        """
        if not self.validateInitialization(topic_name):
            return

        if topic_name not in self._producers:
            logger.error(f"Producer for topic '{topic_name}' does not exist.")
            return

        if message_type:
            message_with_header = message.copy()
            message_with_header['_message_type'] = message_type.value
        else:
            message_with_header = message

        try:
            await self._producers[topic_name].send_and_wait(
                topic_name,
                value=message_with_header,
                key=None
            )

            msg_type_info = f"{message_type.value} " if message_type else ""
            logger.info(f"Sent {msg_type_info}message to {topic_name}: {message}")
        except Exception as e:
            logger.error(f"Failed to send message to {topic_name}: {e}")

    async def consumeFromTopic(self, topic_name: str, callback: Callable) -> None:
        """
        Consumes messages from the specified Kafka topic and processes them with a callback.

        Args:
            topic_name (str): The name of the topic to consume messages from.
            callback (callable): The callback function to process each message.
        """
        if not self.validateInitialization(topic_name):
            return

        if topic_name in self._consumers:
            logger.warning(f"Already consuming from topic '{topic_name}'")
            return

        try:
            group_id = f"consumer-{topic_name}-{id(self)}"
            consumer = AIOKafkaConsumer(
                topic_name,
                bootstrap_servers=self._bootstrap_servers,
                group_id=group_id,
                auto_offset_reset='latest',
                enable_auto_commit=True,
                value_deserializer=lambda m: json.loads(m.decode('utf-8'))
            )

            await consumer.start()
            self._consumers[topic_name] = consumer

            task = asyncio.create_task(self._consumeLoop(topic_name, consumer, callback))
            self._consumer_tasks[topic_name] = task
            logger.info(f"Started consuming messages from {topic_name}...")

        except Exception as e:
            logger.error(f"Failed to create consumer for topic {topic_name}: {e}")

    async def _consumeLoop(self, topic_name: str, consumer: AIOKafkaConsumer, callback: Callable) -> None:
        """
        Internal method to continuously consume messages from a Kafka topic.

        Args:
            topic_name (str): The name of the topic being consumed.
            consumer (AIOKafkaConsumer): The consumer instance.
            callback (callable): The callback function to process each message.
        """
        try:
            async for message in consumer:
                try:
                    content = message.value
                    message_type = None
                    if isinstance(content, dict) and '_message_type' in content:
                        message_type = content.pop('_message_type')

                    if message_type:
                        logger.info(
                            f"Received message from topic '{topic_name}': {json.dumps(content, indent=2)}")
                    asyncio.create_task(callback(content))
                except Exception as e:
                    logger.error(f"Failed to process message: {e}")

        except asyncio.CancelledError:
            logger.info(f"Consumer loop for {topic_name} was cancelled")
        except Exception as e:
            logger.error(f"Error in consumer loop for {topic_name}: {e}")
        finally:
            await consumer.stop()
            if topic_name in self._consumers:
                del self._consumers[topic_name]
            if topic_name in self._consumer_tasks:
                del self._consumer_tasks[topic_name]

    async def shutdown(self) -> None:
        """
        Shuts down the Kafka connections, closing all producers and consumers.
        """
        for topic_name, task in list(self._consumer_tasks.items()):
            try:
                task.cancel()
                logger.info(f"Cancelled consumer task for topic '{topic_name}'")
            except Exception as e:
                logger.error(f"Error cancelling consumer task for topic '{topic_name}': {e}")

        for topic_name, consumer in list(self._consumers.items()):
            try:
                await consumer.stop()
                logger.info(f"Closed consumer for topic '{topic_name}'")
            except Exception as e:
                logger.error(f"Error closing consumer for topic '{topic_name}': {e}")

        for topic_name, producer in list(self._producers.items()):
            try:
                await producer.stop()
                logger.info(f"Closed producer for topic '{topic_name}'")
            except Exception as e:
                logger.error(f"Error closing producer for topic '{topic_name}': {e}")

        if self._admin_client:
            try:
                await self._admin_client.close()
                logger.info("Admin client closed")
            except Exception as e:
                logger.error(f"Error closing admin client: {e}")

        self._consumers.clear()
        self._producers.clear()
        self._consumer_tasks.clear()
        self._initialized_topics.clear()
        self._admin_client = None
        logger.info("Kafka connections closed and resources cleared.")

    async def healthCheck(self, topic_name: str) -> bool:
        """
        Checks the health of the Kafka connection and specified topic.

        Args:
            topic_name (str): The name of the topic to check.

        Returns:
            bool: True if the connection and topic are healthy, False otherwise.
        """
        if not self._producers or topic_name not in self._producers:
            logger.error(f"No active producer for topic '{topic_name}'.")
            return False

        try:
            producer = self._producers[topic_name]
            if not producer._sender.sender_task.done():
                return True
            else:
                logger.error(f"Producer for topic '{topic_name}' is disconnected")
                return False
        except Exception as e:
            logger.error(f"Health check failed for topic '{topic_name}': {e}")
            return False