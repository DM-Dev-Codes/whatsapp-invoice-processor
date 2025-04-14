from rabbitmq import RabbitMQHandler
from safe_naming import QueueNames
import asyncio




async def main():
    # Initialize the connection with all queue names (values)
    await RabbitMQHandler()._initializeConnection(list(QueueNames))

        
     
if __name__ == "__main__":
    asyncio.run(main())


