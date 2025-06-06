"""
Client Response Microservice

This microservice handles sending responses back to users via WhatsApp.
It performs the following functions:
1. Consumes messages from the Kafka response topic
2. Sends messages to users via the Twilio API
3. Handles retries and error cases for message delivery
4. Updates user session states in Redis after message delivery

The service is designed to work asynchronously as part of a larger
microservice architecture for invoice processing and data retrieval.
"""

from shared.kafka_manager import KafkaHandler
import asyncio
from response import ResponseService
from shared.redis_manager import SessionStateManager
from shared.utils import setupAsyncLogging


listener = setupAsyncLogging(__name__)


async def main():
    """
    Initialize and run the client response service.

    This function sets up the necessary components for the service, including
    Kafka messaging and Redis clients, and starts the response service that
    delivers messages to users via WhatsApp.

    Returns:
        None
    """
    kafka_handler = KafkaHandler()
    redis_client = SessionStateManager()
    response_service = ResponseService(kafka_handler, redis_client)
    await response_service.runService()

if __name__ == "__main__":
    asyncio.run(main())