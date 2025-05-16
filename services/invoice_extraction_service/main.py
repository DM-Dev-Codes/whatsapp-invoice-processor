"""
Invoice Extraction Microservice

This microservice processes invoice images submitted by users through the WhatsApp
webhook service. It performs the following functions:
1. Consumes messages from the Kafka image topic
2. Validates and processes invoice images
3. Uses GPT to extract data from valid invoices
4. Stores processed invoice data in PostgreSQL
5. Sends response messages back to users

The service is designed to work asynchronously as part of a larger microservice
architecture for invoice processing and data extraction.
"""

import asyncio
from shared.kafka_manager import KafkaHandler
from parse_app import ImageProcessor
from shared.s3_connection import S3Handler
from shared.postgres import DatabaseManager
from shared.gpt_api import GptApiHandler
from shared.redis_manager import SessionStateManager    
from shared.utils import setupAsyncLogging

# Set up asynchronous logging
listener = setupAsyncLogging(__name__)


async def main() -> None:
    """
    Initialize and run the invoice extraction service.
    
    This function sets up the necessary components for the service, including
    database, message queue, S3, GPT, and Redis clients, and starts the image
    processing service.
    
    Returns:
        None
    """
    # Initialize database manager and connect to the database
    database_manager = DatabaseManager()
    await database_manager.connect()
    # Initialize other service components
    kafka_handler = KafkaHandler()
    aws_s3_client = S3Handler()
    gpt_client = GptApiHandler()
    redis_manager = SessionStateManager()
    
    # Create and run the image processing service
    parsing_img_service = ImageProcessor(
        aws_s3_client, kafka_handler, database_manager, gpt_client, redis_manager
    )
    await parsing_img_service.runService()

if __name__ == "__main__":
    asyncio.run(main())