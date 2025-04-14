import asyncio
import json
import logging
import aio_pika
from .safe_naming import QueueNames, MessageType

logger = logging.getLogger(__name__)



class RabbitMQHandler:


    def __init__(self, *args, **kwargs):
        """
        Initializes the RabbitMQHandler with optional parameters.

        Sets up the connection, channels, and queues as None or empty dictionaries.
        """
        self._connection: aio_pika.Connection | None = None
        self._channels: dict[str, aio_pika.Channel] = {}
        self._queues: dict[str, aio_pika.Queue] = {}


    def validateInitialization(self, queue_name: str | None = None) -> bool:
        """
        Validates the initialization of the RabbitMQ connection, channels, and queues.

        Args:
            queue_name (str | None): The name of the queue to validate, if specified.

        Returns:
            bool: True if the connection and specified queue are initialized, False otherwise.
        """
        if not self._connection:
            logger.error("Connection is not initialized.")
            return False
        if queue_name and queue_name not in self._channels:
            logger.error(f"Channel for queue '{queue_name}' is not initialized.")
            return False
        if queue_name and queue_name not in self._queues:
            logger.error(f"Queue '{queue_name}' is not initialized.")
            return False
        return True
    
    async def _initializeConnection(self, queue_names: list[QueueNames]) -> None:
        """
        Initializes the RabbitMQ connection and declares the specified queues.

        Args:
            queue_names (list[QueueNames]): A list of queue names to initialize.
        """
        if not self._connection:
            self._connection = await aio_pika.connect_robust(f"amqp://{QueueNames.RABBITMQ_HOST.value}")
        for queue_name in queue_names:
            try:
                channel = await self._connection.channel()
                queue = await channel.declare_queue(queue_name, durable=True)
                self._channels[queue_name] = channel
                self._queues[queue_name] = queue
                logger.info(f"Initialized channel and queue for '{queue_name}'")
            except Exception as e:
                logger.error(f"Failed to initialize queue '{queue_name}': {e}")

    
    async def sendToQueue(self, queue_name: str, message: dict, message_type: MessageType = None) -> None:
        """
        Sends a message to the specified RabbitMQ queue.

        Args:
            queue_name (str): The name of the queue to send the message to.
            message (dict): The message to send.
            message_type (MessageType, optional): The type of the message.
        """
        if not self.validateInitialization(queue_name):
            return
        if queue_name not in self._channels:
            logger.error(f"Channel for queue '{queue_name}' does not exist.")
            return
        await self._channels[queue_name].default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(message).encode(),
                headers={'message_type': message_type.value} if message_type else {}
            ),
            routing_key=queue_name
            #fix enum routing key
        )
        msg_type_info = f"{message_type.value} " if message_type else ""
        logger.info(f"Sent {msg_type_info}message to {queue_name}: {message}")


    async def consumeFromQueue(self, queue_name: str, callback) -> None:
        """
        Consumes messages from the specified RabbitMQ queue and processes them with a callback.

        Args:
            queue_name (str): The name of the queue to consume messages from.
            callback (callable): The callback function to process each message.
        """
        if not self.validateInitialization(queue_name):
            return  

        queue = self._queues.get(queue_name)
        if not queue:
            logger.error(f"Queue '{queue_name}' not found.")
            return
        
        async def onMessage(message):
            async with message.process():
                try:
                    decoded_message = json.loads(message.body.decode())
                    message_type = message.headers.get('message_type')
                    if message_type:
                        # decoded_message['error'] = message_type
                        logger.info(f"Received message from queue '{queue_name}': {json.dumps(decoded_message, indent=2)}")
                    asyncio.create_task(callback(decoded_message))
                except Exception as e:
                    logger.error(f"Failed to process message: {e}")

        await queue.consume(onMessage)
        logger.info(f"Started consuming messages from {queue_name}...")



    async def shutdown(self) -> None:
        """
        Shuts down the RabbitMQ connection and clears channels and queues.
        """
        if self._connection:
            await self._connection.close()
            logger.info("RabbitMQ connection closed.")
        self._channels.clear()
        self._queues.clear()
        logger.info("Channels and queues cleared.")


    def healthCheck(self, queue_name: str) -> bool:
        """
        Checks the health of the RabbitMQ connection and specified queue.

        Args:
            queue_name (str): The name of the queue to check.

        Returns:
            bool: True if the connection and queue are healthy, False otherwise.
        """
        if not self._connection or queue_name not in self._channels:
            logger.error(f"No active connection or channel for queue '{queue_name}'.")
            return False
        return True