from enum import Enum


class TopicNames(Enum):
    """
    Represents the names of the topics in the Kafka system.

    This enum defines the names of the topics used in the application,
    including the broker host address, image topic, query topic, response topic,
    and error topic.
    """
    KAFKA_HOST = 'kafka'
    IMAGE_TOPIC = 'message_topic'
    QUERY_TOPIC = 'query_topic'
    RESPONSE_TOPIC = 'response_topic'
    

class ValidInput(Enum):
    """
    Represents the types of valid input messages in the application.

    This enum defines the types of valid input messages that can be processed,
    including valid media, valid text, and invalid message.
    """ 
    VALID_MEDIA = "VALID_MEDIA"
    VALID_TEXT = "VALID_TEXT"
    INVALID_MESSAGE = "INVALID_MESSAGE"
    
class MessageType(Enum):
    """
    Represents the types of messages in the application.

    This enum defines the types of messages that can be processed,
    including error and success.
    """
    ERROR = "error"
    SUCCESS = "success"


class UserState(Enum):
    """
    Represents the state of a user's session in the application.

    This enum defines the possible states a user can be in during their session,
    including the initial start state, choosing an option, awaiting an image,
    awaiting text input, processing data, and handling errors.
    """
    START = "start"
    CHOOSING = "choosing"
    AWAITING_IMAGE = "awaiting_image"
    AWAITING_TEXT = "awaiting_text"
    PROCESSING = "processing"
    ERROR = "error"