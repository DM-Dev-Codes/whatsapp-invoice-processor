import asyncio
import logging
import os
import backoff
from dotenv import load_dotenv
from twilio.base.exceptions import TwilioRestException, TwilioException
from twilio.rest import Client
from shared.safe_naming import QueueNames, UserState



load_dotenv()
logger = logging.getLogger(__name__)

class ResponseService:
    """
    Handles delivery of WhatsApp messages to users via Twilio.
    
    This class manages the receipt of messages from the response queue,
    delivery of those messages via the Twilio API, and handling of any
    errors or retries that occur during message delivery.
    
    Attributes:
        rabbit_handler: Handler for RabbitMQ message queue operations
        redis_manager: Client for managing user session states
        twilio_client: Client for Twilio API interactions
    """

    def __init__(self, rabbit_handler, redis_manager):
        """
        Initialize the ResponseService with necessary clients and handlers.
        
        Args:
            rabbit_handler: Handler for RabbitMQ operations
            redis_manager: Client for managing user session states
        """
        self.rabbit_handler = rabbit_handler
        self.redis_manager = redis_manager
        self.twilio_client = None
        
        
    @backoff.on_exception(
        backoff.expo,
        (TwilioException, Exception),
        max_tries=3,
        base=2,
        logger=logger
    )    
    def _initializeTwilio(self):
        """
        Initialize the Twilio client with credentials from environment variables.
        
        This method is decorated with backoff to handle transient failures
        during Twilio client initialization.
        
        Returns:
            bool: True if initialization was successful
            
        Raises:
            TwilioException: If Twilio credentials are missing or invalid
        """
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        if not account_sid or not auth_token:
            logger.error("Missing Twilio credentials in environment")
            raise TwilioException("Missing Twilio credentials")    
        self.twilio_client = Client(account_sid, auth_token)
        logger.info("Twilio client initialized successfully")
        return True
        
    async def runService(self):
        """
        Initialize connections and start consuming messages from the queue.
        
        This method sets up the Twilio client, RabbitMQ connection, and Redis
        connection, then starts listening for messages on the response queue.
        It runs in an infinite loop to maintain the service.
        
        Returns:
            None
        """
        logger.info("Initializing Twilio client...")
        try:
            self._initializeTwilio()
        except Exception as e:
            logger.error(f"Initial Twilio setup failed: {e}")
            logger.info("Will retry when sending messages")
        logger.info("Initializing RabbitMQ connection...")
        await self.rabbit_handler._initializeConnection([QueueNames.RESPONSE_QUEUE.value])
        logger.info("Initializing Redis connection...")
        await self.redis_manager.initializeConnections()
        logger.info("Connection initialized, starting consumer...")
        await self.rabbit_handler.consumeFromQueue(QueueNames.RESPONSE_QUEUE.value, self.validateSentMessage)
        logger.info("Consumer started, entering main loop...")
        while True:
            await asyncio.sleep(1)
            
    @backoff.on_exception(
        backoff.expo,
        (TwilioException, TwilioRestException),
        max_tries=3,
        base=2,
        logger=logger
    )
    async def sendWhatsappMessage(self, return_msg) -> bool:
        """
        Send a WhatsApp message via the Twilio API.
        
        This method is decorated with backoff to handle transient failures
        during message sending. It validates the Twilio client, sends the
        message, and checks the result status.
        
        Args:
            return_msg: Dictionary containing message data to send via Twilio
            
        Returns:
            bool: True if the message was sent successfully
            
        Raises:
            TwilioException: If the Twilio client is not initialized
            TwilioRestException: If the message fails to send
        """
        if not await self.validateTwilioClient():
            logger.error("Twilio Client is None!")
            raise TwilioException("Failed to initialize Twilio client")
        text_message = await asyncio.to_thread(self.twilio_client.messages.create, **return_msg)
        logger.info(f"Message SID: {text_message.sid}, Status: {text_message.status}")
        if text_message.status.lower() in {"queued", "sent", "delivered"}:
            return True
        logger.warning(f"Message sending failed. Status: {text_message.status}")
        raise TwilioRestException(
            status=int(getattr(text_message, 'error_code', 500)),
            uri="whatsapp_message",
            msg=f"Message failed with status: {text_message.status}"
        )

    async def validateSentMessage(self, dequed_msg):
        """
        Process a message from the queue and attempt to send it.
        
        This method is called for each message dequeued from the response
        queue. It attempts to send the message, updates the user state on
        success, and handles failures.
        
        Args:
            dequed_msg: Dictionary containing the message to send
            
        Returns:
            bool: True if the message was sent successfully, False otherwise
        """
        try:
            success = await self.sendWhatsappMessage(dequed_msg)
            if success:
                logger.info("The message was sent successfully!")
                return True
        except Exception as e:
            logger.error(f"All retry attempts failed. Message was not delivered: {e}")
            await self.resetUserState(dequed_msg.get('to'))
        return False
            
    async def validateTwilioClient(self) -> bool:
        """
        Ensure the Twilio client is initialized.
        
        If the client is not initialized, this method attempts to initialize it.
        
        Returns:
            bool: True if the client is or was successfully initialized, False otherwise
        """
        if self.twilio_client is not None:
            return True
        logger.warning("Twilio client is None, attempting to reinitialize...")
        try:
            return self._initializeTwilio()
        except Exception as e:
            logger.error(f"Failed to initialize Twilio client: {e}")
            return False
            
            
    async def resetUserState(self, whatsapp_number):
        """
        Reset a user's state to START after a message failure.
        
        Args:
            whatsapp_number: The phone number of the user to reset
            
        Returns:
            None
        """
        try:
            if whatsapp_number:
                await self.redis_manager.setSession(whatsapp_number, UserState.START)
                logger.info(f"Reset state to START for user {whatsapp_number} after message failure")
        except Exception as state_error:
            logger.error(f"Failed to reset user state: {state_error}")







            
        