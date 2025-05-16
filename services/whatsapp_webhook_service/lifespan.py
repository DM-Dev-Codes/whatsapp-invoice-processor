from fastapi import FastAPI
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from shared.redis_manager import SessionStateManager
from shared.kafka_manager import KafkaHandler
from shared.safe_naming import TopicNames


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Lifespan context manager for the FastAPI application.

    This context manager:
    1. Initializes the session manager (Redis) connection
    2. Initializes the Kafka connection and configures message topics
    3. Attaches these resources to the FastAPI application state
    4. Ensures proper cleanup of all resources when the application terminates

    The initialized resources are made available to route handlers through
    dependency injection using the functions defined in dependencies.py.

    Args:
        app (FastAPI): The FastAPI application instance

    Yields:
        None: Control is yielded back to the application while it runs
    """
    session_manager = SessionStateManager()
    await session_manager.initializeConnections()
    kafka_handler = KafkaHandler()
    await kafka_handler._initializeConnection([
        TopicNames.IMAGE_TOPIC.value,
        TopicNames.QUERY_TOPIC.value
    ])

    # Store instances in app state
    app.state.session_manager = session_manager
    app.state.kafka_handler = kafka_handler

    yield

    # Cleanup
    await session_manager.shutdown()
    await kafka_handler.shutdown()