from fastapi import FastAPI
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from shared.redis_manager import SessionStateManager
from shared.rabbitmq import RabbitMQHandler
from shared.safe_naming import QueueNames

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Lifespan context manager for the FastAPI application.
    
    This context manager:
    1. Initializes the session manager (Redis) connection
    2. Initializes the RabbitMQ connection and configures message queues
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
    rabbit_instance = RabbitMQHandler()
    await rabbit_instance._initializeConnection([
        QueueNames.IMAGE_QUEUE.value,
        QueueNames.QUERY_QUEUE.value
    ])
    
    # Store instances in app state
    app.state.session_manager = session_manager
    app.state.rabbitmq = rabbit_instance
    
    yield
    
    # Cleanup
    await session_manager.shutdown()
    await rabbit_instance.shutdown()