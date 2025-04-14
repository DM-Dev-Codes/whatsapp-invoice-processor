from fastapi import Request
from shared.redis_manager import SessionStateManager
from shared.rabbitmq import RabbitMQHandler


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

async def getRabbitmq(request: Request) -> RabbitMQHandler:
    """
    Dependency that provides access to the RabbitMQ handler.
    
    The RabbitMQ handler is used to send messages to processing queues
    for invoice image analysis and text query handling.
    
    Args:
        request (Request): The FastAPI request object containing application state
        
    Returns:
        RabbitMQHandler: The initialized RabbitMQ handler instance
    """
    return request.app.state.rabbitmq

