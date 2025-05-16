from shared.kafka_manager import KafkaHandler
from safe_naming import TopicNames
import asyncio




async def main():
    # Initialize the connection with all queue names (values)
    await KafkaHandler()._initializeConnection(list(TopicNames))

        
     
if __name__ == "__main__":
    asyncio.run(main())


