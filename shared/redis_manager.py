import logging
import os
from typing import Optional
import redis.asyncio as redis
from .safe_naming import UserState

logger = logging.getLogger(__name__)


class SessionStateManager:
    """
    Manages user session states using Redis.

    This class provides methods to initialize connections to a Redis server,
    set, get, update, and delete session states for WhatsApp numbers. It also
    ensures that the Redis connection is properly closed when no longer needed.
    """

    def __init__(self):
        """
        Initializes the SessionStateManager with a Redis client.

        The Redis client is set to None initially and will be initialized
        when connections are established.
        """
        self.redis_client: Optional[redis.Redis] = None

    async def initializeConnections(self) -> None:
        """
        Initializes the connection to the Redis server.

        Attempts to connect to the Redis server and verifies the connection
        with a PING command.

        Raises:
            redis.ConnectionError: If the connection to Redis fails.
        """
        self.redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "redis"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            db=int(os.getenv("REDIS_DB", 0))
        )
        
        try:
            # Check connection with a PING command
            response = await self.redis_client.ping()  # Should return 'PONG'
            if response:
                logger.info("Successfully connected to Redis!")
            else:
                logger.error("Failed to connect to Redis: No response from PING")
                raise redis.ConnectionError("No response from Redis PING")
        except redis.ConnectionError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def setSession(self, whatsapp_number: str, state: UserState, expire: int = 15 * 60) -> None:
        """
        Sets the session state for a given WhatsApp number in Redis.

        Args:
            whatsapp_number (str): The WhatsApp number to set the session for.
            state (UserState): The state to set for the session.
            expire (int, optional): The expiration time for the session in seconds. Defaults to 15 minutes.
        """
        await self.redis_client.set(whatsapp_number, state.value, ex=expire)
        

    async def getSession(self, whatsapp_number: str) -> UserState:
        """
        Retrieves the session state for a given WhatsApp number from Redis.

        Args:
            whatsapp_number (str): The WhatsApp number to retrieve the session for.

        Returns:
            UserState: The current state of the session.
        """
        try:
            state_value = await self.redis_client.get(whatsapp_number)
            if state_value:
                decoded_state = state_value.decode('utf-8')
                logger.info(f"Retrieved state for {whatsapp_number}: {decoded_state}")
                return UserState(decoded_state)  # Convert to enum
            else:
                logger.warning(f"No state found for {whatsapp_number}, initializing new session.")
                await self.setSession(whatsapp_number, UserState.START)  # Ensure session is initialized
                return UserState.START  # Default value
        except Exception as e:
            logger.error(f"Error getting session for {whatsapp_number}: {e}")
            return UserState.START  # Fallback to prevent None issues


    async def updateSession(self, whatsapp_number: str, new_state: UserState, new_expire: Optional[int] = None) -> None:
        """
        Updates the session state for a given WhatsApp number in Redis.

        Args:
            whatsapp_number (str): The WhatsApp number to update the session for.
            new_state (UserState): The new state to set for the session.
            new_expire (Optional[int], optional): The new expiration time for the session in seconds.
        """
        await self.redis_client.set(whatsapp_number, new_state.value)
        if new_expire is not None:
            await self.redis_client.expire(whatsapp_number, new_expire, new_expire or 15 * 60)

    async def deleteSession(self, whatsapp_number: str) -> None:
        """
        Deletes the session for a given WhatsApp number from Redis.

        Args:
            whatsapp_number (str): The WhatsApp number to delete the session for.
        """
        await self.redis_client.delete(whatsapp_number)
        
    async def shutdown(self) -> None:
        """
        Closes the connection to the Redis server.

        Ensures that the Redis connection is properly closed when no longer needed.
        """
        if self.redis_client:
            try:
                await self.redis_client.close()
                logger.info("Redis connection closed.")
            except Exception as e:
                logger.error(f"Error closing Redis connection: {e}")