from fastapi import APIRouter, Request, Depends
from fastapi.responses import PlainTextResponse
from twilio.twiml.messaging_response import MessagingResponse
from shared.redis_manager import SessionStateManager
from shared.kafka_manager import KafkaHandler
from shared.safe_naming import TopicNames, UserState
from shared.utils import getMenuOptions
from dependencies import getSessionManager, getKafka

router = APIRouter()


@router.post("/whatsapp")
async def receiveMessage(
        request: Request,
        session_manager: SessionStateManager = Depends(getSessionManager),
        kafka: KafkaHandler = Depends(getKafka)
):
    """
    Webhook endpoint that handles incoming WhatsApp messages.

    This function:
    1. Extracts message content and sender information from the webhook request
    2. Retrieves the current conversation state for the user
    3. Processes the message based on the current state
    4. Sends appropriate processing requests to Kafka topics
    5. Updates the user's conversation state
    6. Returns a response message to the user

    The function implements a state machine that guides users through the conversation:
    - START: Initial state, prompts user to select an option
    - CHOOSING: User selects between invoice image processing or information retrieval
    - AWAITING_IMAGE: Waiting for user to send an invoice image
    - AWAITING_TEXT: Waiting for user to send a text query about invoices
    - PROCESSING: Request is being processed, ask user to wait
    - ERROR: Error state, prompts user to restart

    Args:
        request (Request): The FastAPI request object containing the webhook payload
        session_manager (SessionStateManager): Redis-based session state manager
        kafka (KafkaHandler): Kafka client for publishing messages to processing topics

    Returns:
        PlainTextResponse: XML response for Twilio containing the message to send to the user
    """
    form_data = await request.form()
    form_dict = dict(form_data)
    from_number = form_dict.get("From")
    body = form_dict.get("Body", "").strip()
    response = MessagingResponse()
    msg = response.message()

    current_state = await session_manager.getSession(from_number)

    if body == "0":
        await session_manager.deleteSession(from_number)
        msg.body(
            "Thank you for using Invoice Assistant. Your session has ended. To begin a new session, simply send another message. 👋")
        return PlainTextResponse(str(response), media_type="text/xml")

    match current_state:
        case UserState.START:
            msg.body(f"Welcome to the Invoice Assistant!\n\n{getMenuOptions(include_header=False)}")
            await session_manager.updateSession(from_number, UserState.CHOOSING)

        case UserState.CHOOSING:
            match body:
                case '1':
                    msg.body("Please provide a single image to process.")
                    await session_manager.updateSession(from_number, UserState.AWAITING_IMAGE, new_expire=300)
                case '2':
                    msg.body("Please write a sentence describing what information you would like.")
                    await session_manager.updateSession(from_number, UserState.AWAITING_TEXT, new_expire=300)
                case _:
                    msg.body("Invalid choice. Select:\n1. Process invoice Image\n2. Retreieve invoice/s info")

        case UserState.AWAITING_IMAGE:
            msg.body("Processing your image. Please wait.")
            await session_manager.updateSession(from_number, UserState.PROCESSING, new_expire=300)
            await kafka.publishToTopic(TopicNames.IMAGE_TOPIC.value, form_dict)

        case UserState.AWAITING_TEXT:
            msg.body("Processing your request. Please wait.")
            await session_manager.updateSession(from_number, UserState.PROCESSING, new_expire=300)
            await kafka.publishToTopic(TopicNames.QUERY_TOPIC.value, form_dict)

        case UserState.PROCESSING:
            msg.body("Please wait while we process your previous request.")
            return PlainTextResponse(str(response), media_type="text/xml")

        case UserState.ERROR:
            msg.body(f"Something went wrong. Please start over.\n\n{getMenuOptions(include_header=False)}")
            await session_manager.updateSession(from_number, UserState.START)
        case _:
            msg.body("Something went wrong. Start over.")
            await session_manager.updateSession(from_number, UserState.START)

    return PlainTextResponse(str(response), media_type="text/xml")


@router.get("/health")
async def health_check():
    return {"status": "ok"}