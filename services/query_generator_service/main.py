"""
Query Generator Microservice

This microservice processes text queries about invoices submitted by users
through the WhatsApp webhook service. It performs the following functions:
1. Consumes messages from the Kafka query topic
2. Uses GPT to generate SQL queries based on user text input
3. Retrieves invoice data from PostgreSQL based on those queries
4. Formats the results as an Excel file
5. Uploads the file to S3 and sends the link back to the user

The service is designed to work asynchronously as part of a larger microservice
architecture for invoice processing and data retrieval.
"""


import asyncio
from shared.kafka_manager import KafkaHandler
from parse_query import QueryProcessor
from shared.s3_connection import S3Handler
from shared.postgres import DatabaseManager
from shared.gpt_api import GptApiHandler
from shared.redis_manager import SessionStateManager
from shared.utils import setupAsyncLogging


listener = setupAsyncLogging(__name__)



async def main():
    """
    Initialize and run the query generator service.

    This function sets up the necessary components for the service, including
    database, message queue, S3, GPT, and Redis clients, and starts the query
    processing service.

    Returns:
        None
    """
    database_manager = DatabaseManager()
    await database_manager.connect()
    kafka_handler = KafkaHandler()
    aws_s3_client = S3Handler()
    gpt_client = GptApiHandler()
    redis_manager = SessionStateManager()
    parsing_img_service = QueryProcessor(kafka_handler, aws_s3_client, database_manager, gpt_client, redis_manager)
    await parsing_img_service.runService()


    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())