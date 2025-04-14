import logging
import asyncio
from typing import Optional, Union, Dict
from shared.utils import downloadTwillieoUrl, createResponseMessage, getMenuOptions
from shared.safe_naming import QueueNames, MessageType
from shared.rabbitmq import RabbitMQHandler 
from shared.safe_naming import UserState

logger = logging.getLogger(__name__)


class ImageProcessor:
    """
    Processes invoice images sent by users via WhatsApp.
    
    This class handles the receipt, validation, processing, and storage of invoice images.
    It extracts data from images using GPT and stores the results in a database.
    
    Attributes:
        s3_client: Client for S3 operations to store and retrieve images
        rabbit_handler: Handler for RabbitMQ message queue operations
        db_writer: Database client for storing extracted invoice data
        gpt_client: Client for GPT API interactions to extract data from images
        redis_manager: Client for managing user session states
    """
     
    def __init__(self, s3_client, rabbit_handler: RabbitMQHandler, db_writer, gpt_client, redis_manager):
        """
        Initialize the ImageProcessor with necessary clients and handlers.
        
        Args:
            s3_client: Client for S3 operations
            rabbit_handler: Handler for RabbitMQ operations
            db_writer: Database client for storing invoice data
            gpt_client: Client for GPT API interactions
            redis_manager: Client for managing user session states
        """
        self.s3_client = s3_client
        self.rabbit_handler = rabbit_handler
        self.db_writer = db_writer
        self.gpt_client = gpt_client
        self.redis_manager = redis_manager
        logger.debug("ImageProcessor initialized")
        

    async def runService(self) -> None:
        """
        Initialize connections and start consuming messages from the queue.
        
        This method sets up connections to RabbitMQ and Redis, then starts
        listening for messages on the image queue. It runs in an infinite loop
        to maintain the service.
        
        Returns:
            None
        """
        logger.info("Initializing RabbitMQ connection...")
        await self.rabbit_handler._initializeConnection([QueueNames.IMAGE_QUEUE.value, QueueNames.RESPONSE_QUEUE.value])
        logger.info("Initializing Redis connection...")
        await self.redis_manager.initializeConnections()
        logger.info("Connection initialized, starting consumer...")
        await self.rabbit_handler.consumeFromQueue(QueueNames.IMAGE_QUEUE.value, self.processImage)
        logger.info("Consumer started, entering main loop...")
        while True:
            await asyncio.sleep(1)


    async def processImage(self, media_msg_to_parse: dict) -> None:
        """
        Process an incoming image message, validate it, and handle the response.
        
        This method performs the following steps:
        1. Validates the user's current state
        2. Checks that the message contains a single media item
        3. Downloads and validates the image
        4. Extracts invoice data using GPT
        5. Stores the data in the database
        6. Sends a response to the user
        
        Args:
            media_msg_to_parse: Dictionary containing message data from WhatsApp
                                including media URLs and user information
        
        Returns:
            None
        """
        client_num = media_msg_to_parse.get("From", None)
        current_state = await self.redis_manager.getSession(client_num)
        
        if current_state != UserState.PROCESSING:
            logger.warning(f"Invalid state transition attempt: {current_state} -> PROCESSING")
            await self.handleResponse(client_num, "Please start over with a new image", MessageType.ERROR)
            await self.redis_manager.updateSession(client_num, UserState.START)
            return

        is_valid, error_reason = self.validateMediaMessage(media_msg_to_parse)
        if not is_valid:
            await self.handleResponse(client_num, error_reason, MessageType.ERROR)
            await self.redis_manager.updateSession(client_num, UserState.AWAITING_IMAGE)
            return
        
        media_url = media_msg_to_parse.get("MediaUrl0", None)
        incoming_image = await downloadTwillieoUrl(media_url)
        
        if not incoming_image:
            await self.handleResponse(client_num, "There was an issue accessing the image please resend ", 
                                      MessageType.ERROR)
            await self.redis_manager.updateSession(client_num, UserState.AWAITING_IMAGE)
            return
        
        gpt_response = await self.validateInvoice(client_num, incoming_image)
        
        if not gpt_response:
            await self.handleResponse(client_num, "The image you provided is not a valid *invoice*, Please try again ",
                                      MessageType.ERROR)
            await self.redis_manager.updateSession(client_num, UserState.AWAITING_IMAGE)
            return
        
        success_flag = await self.db_writer.writeMsgDb(gpt_response)
        
        if not success_flag:
            await self.handleResponse(client_num, "There was an issue saving your'e invoice please restart the process",
                                      MessageType.ERROR)
            await self.redis_manager.updateSession(client_num, UserState.START)
            return
        
        success_message = f"Your invoice has been successfully processed!\n\n{getMenuOptions()}"
        await self.handleResponse(client_num, success_message, MessageType.SUCCESS)
        await self.redis_manager.updateSession(client_num, UserState.CHOOSING)
        return 
        
            
    async def uploadImage(self, phone_num: str, image_for_upload: bytes) -> tuple[str, str]:
        """
        Upload an image to S3 and return the presigned URL.
        
        Args:
            phone_num: The phone number of the user, used for file naming
            image_for_upload: The binary image data to upload
            
        Returns:
            tuple: (presigned_url, image_path) The URL to access the image and its path in S3
        """
        image_path = await self.s3_client.uploadToS3(phone_num, image_for_upload, "image")
        presigned_url = await self.s3_client.generatePresignedUrl(image_path)  
        return presigned_url, image_path

        
    async def validateProperImage(self, s3_img_link: str) -> Union[Dict, bool]:
        """
        Validate if the image at the given S3 link is a proper invoice.
        
        This method uses the GPT API to analyze the image and extract invoice data.
        
        Args:
            s3_img_link: The presigned URL to the image in S3
            
        Returns:
            Union[Dict, bool]: Dictionary of extracted invoice data if valid,
                               False otherwise
        """
        logger.info(f"Validating image from S3: {s3_img_link}") 
        gpt_result = await self.gpt_client.gptMessageParser(s3_img_link)
        logger.debug(f"this is the response process image got {gpt_result}")
        if gpt_result is None:
            logger.debug("GPT result is None; returning invalid invoice.")
            delete_flag = await self.s3_client.deleteFromS3(s3_img_link)
            if not delete_flag:
                logger.debug("There was an issue removing the presigned url ")
        return gpt_result
        
            
    def validateMediaMessage(self, msg: dict) -> tuple[bool, str]:
        """
        Validates that the WhatsApp message contains exactly one supported image media.

        Args:
            msg (dict): The message dictionary from Twilio.

        Returns:
            (bool, str): Tuple of (is_valid, error_reason)
        """
        num_media = int(msg.get("NumMedia", 0))
        if num_media == 0:
            logger.warning("No media found in the message.")
            return False, "No media file was found. Please send one invoice image."

        if num_media > 1:
            logger.warning(f"Too many media attachments: {num_media}")
            return False, "You sent more than one image. Please send only *one* invoice image."

        media_type = msg.get("MediaContentType0", "")
        allowed_types = {"image/jpeg", "image/png", "image/jpg", "image/webp"}

        if media_type not in allowed_types:
            logger.warning(f"Unsupported media type: {media_type}")
            return False, f"The file type '{media_type}' is not supported. Please resend a JPG or PNG image."

        return True, ""
    
    
    async def validateInvoice(self, clients_num: str, image_for_upload: bytes) -> Optional[Dict]:
        """
        Validate the invoice image and return the parsed data.
        
        This method uploads the image to S3, validates it, and returns
        the extracted invoice data if valid.
        
        Args:
            clients_num: The phone number of the user
            image_for_upload: The binary image data to validate
            
        Returns:
            Optional[Dict]: Dictionary of extracted invoice data if valid,
                           None otherwise
        """
        s3_presigned_url, img_path = await self.uploadImage(clients_num, image_for_upload)
        gpt_response = await self.validateProperImage(s3_presigned_url)
        if gpt_response and img_path:
            gpt_response['phone_number'] = clients_num
            gpt_response['raw_image_url'] = img_path
            return gpt_response
        return None

            
    async def handleResponse(self, phone_num: str, msg_content: str, msg_type: MessageType = None) -> None:
        """
        Send a response message to the user.
        
        Args:
            phone_num: The phone number to send the message to
            msg_content: The content of the message to send
            msg_type: The type of message (error, success, etc.)
            
        Returns:
            None
        """
        response = createResponseMessage(msg_content, phone_num)
        await self.rabbit_handler.sendToQueue(QueueNames.RESPONSE_QUEUE.value, response, msg_type)
    
