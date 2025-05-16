from fastapi import Request
from shared.redis_manager import SessionStateManager
from shared.kafka_manager import KafkaHandler


async def getSessionManager(request: Request) -> SessionStateManager:
    """
    Dependency that provides access to the Redis session manager.
    
    The session manager handles user state persistence across WhatsApp interactions,
    allowing the service to maintain conversation context.
    
    Args:
        request (Request): The FastAPI request object containing application state
        
    Returns:
        SessionStateManager: The initialized Redis session manager instance
    """
    return request.app.state.session_manager

async def getKafka(request: Request) -> KafkaHandler:
    """
    Dependency that provides access to the Kafka handler.
    
    The Kafka handler is used to publish messages to processing topics
    for invoice image analysis and text query handling.
    
    Args:
        request (Request): The FastAPI request object containing application state
        
    Returns:
        KafkaHandler: The initialized Kafka handler instance
    """
    return request.app.state.kafka_handler

