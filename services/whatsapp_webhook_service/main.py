"""
WhatsApp Webhook Service - Main Application Module

This service handles incoming WhatsApp messages via a webhook endpoint, allowing users
to interact with an invoice processing system through a conversational interface.

The service:
1. Receives incoming messages from WhatsApp (via Twilio's API)
2. Maintains user session state using Redis
3. Processes user requests for invoice image analysis or text-based information retrieval
4. Forwards requests to appropriate processing services via Kafka topics
5. Provides immediate feedback to users and manages conversation flow

This module initializes and configures the FastAPI application with the required
dependencies, routes, and lifecycle management.
"""

from fastapi import FastAPI
from lifespan import lifespan
from dispatcher import router 
from shared.utils import startServer
import logging
from shared.utils import setupAsyncLogging


listener = setupAsyncLogging(__name__)
logger = logging.getLogger(__name__)


def createApp() -> FastAPI:
    """
    Creates and configures the FastAPI application with all necessary components.
    
    This function:
    - Creates a new FastAPI instance with the lifespan context manager
    - Includes the router containing webhook endpoints
    - Sets up logging
    
    Returns:
        FastAPI: The configured FastAPI application instance
    """
    try:
        app = FastAPI(lifespan=lifespan)
        app.include_router(router)
        logger.info("FastAPI app created successfully.")
        return app
    except Exception as e:
        logger.error(f"Error during app creation: {e}")
        raise

def main():
    """
    Main entry point that initializes and starts the webhook service.
    
    This function:
    - Creates the FastAPI application
    - Starts the HTTP server on port 8000
    - Handles any startup errors
    """
    try:
        logger.info("Starting application...")
        app = createApp()
        startServer(app, 8000)
        logger.info("Server started successfully on port 8000.")
    except Exception as e:
        logger.error(f"Error starting server: {e}")

if __name__ == "__main__":
    main()
