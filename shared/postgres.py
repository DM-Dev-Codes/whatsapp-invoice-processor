import logging
import os
import re
from datetime import date, datetime
from decimal import Decimal
import asyncpg
from dotenv import load_dotenv
import backoff
from dateutil.parser import parse
load_dotenv()

logger = logging.getLogger(__name__)




class DatabaseManager:

    def __init__(self):
        """
        Initializes the DatabaseManager and establishes a connection to the PostgreSQL database.

        The connection parameters are loaded from environment variables.
        """
        self._connection: asyncpg.Connection | None = None
        


    @backoff.on_exception(
        backoff.expo,  
        asyncpg.PostgresError,  
        max_tries=5,  
        logger=logger  # Logger to use for logging retry attempts
    )
    async def connect(self) -> None:
        """
        Establishes a connection to the PostgreSQL database with retry logic.

        Attempts to connect to the database up to a maximum number of retries specified.
        """
        try:
            self._connection = await asyncpg.connect(
                host=os.getenv('POSTGRES_HOST'),
                user=os.getenv('POSTGRES_USER'),
                password=os.getenv('POSTGRES_PASSWORD'),
                database=os.getenv('POSTGRES_DATABASE', "fintrak")
            )
            logger.info("Database connection established successfully.")
        except asyncpg.PostgresError as error:
            logger.error(f"Failed to connect to the database: {error}")
            raise




    async def close(self) -> None:
        """
        Closes the connection to the PostgreSQL database.

        Ensures that the connection is properly closed when no longer needed.
        """
        if self._connection:
            try:
                await self._connection.close()
                logger.info("Database connection closed")
                self._connection = None
            except asyncpg.PostgresError as error:
                logger.error(f"Error closing connection: {error}")
                
                
    async def insertUser(self, user_data: dict) -> None:
        """
        Inserts a new user record into the database.

        Args:
            user_data (dict): A dictionary containing user information to be inserted.
        """
        await self.ensureActiveConnection()
        try:
            await self._connection.execute("""
                INSERT INTO users (whatsapp_number, username)
                VALUES ($1, $2)
                ON CONFLICT (whatsapp_number) DO NOTHING
            """, user_data.get('phone_number'), user_data.get('phone_number'))
            return True
        except Exception as insert_user_error:
            await self.rollback("Error inserting user", insert_user_error)
            return False

    async def insertInvoice(self, invoice_data: dict) -> None:
        """
        Inserts a new invoice record into the database.

        Args:
            invoice_data (dict): A dictionary containing invoice information to be inserted.
        """
        await self.ensureActiveConnection()
        try:
            await self._connection.execute("""
                INSERT INTO invoices 
                (whatsapp_number, invoice_date, expense_amount, vat, 
                payee_name, payment_method, raw_image_url)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, 
                invoice_data['phone_number'],
                invoice_data['invoice_date'],
                invoice_data['expense_amount'],
                invoice_data['vat'],
                invoice_data['payee_name'],
                invoice_data['payment_method'],  
                invoice_data['raw_image_url']
            )
            return True
        except Exception as insert_invoice_error:
            await self.rollback("Error inserting invoice", insert_invoice_error)
            return False

    async def writeMsgDb(self, parsed_data: dict) -> None:
        """
        Writes parsed message data to the database.

        Args:
            parsed_data (dict): A dictionary containing parsed message data to be stored.
        """
        await self.ensureActiveConnection()
        user_data = {
            'phone_number': parsed_data['phone_number'],
            'username': parsed_data['phone_number']  
        }
        invoice_data = {
            'phone_number': parsed_data['phone_number'],
            'invoice_date': parse(parsed_data.get('invoice_date')).date() if parsed_data.get('invoice_date') else None,
            'expense_amount': parsed_data['expense_amount'] or None,
            'vat': parsed_data['vat'] or None,
            'payee_name': parsed_data['payee_name'] or None,
            'payment_method': parsed_data['payment_method'] or None,
            'raw_image_url': parsed_data['raw_image_url']
        }
        try:
            async with self._connection.transaction():
                user_result = await self.insertUser(user_data)
                if not user_result:
                    raise Exception("Failed to insert/update user")
                invoice_result = await self.insertInvoice(invoice_data)
                if not invoice_result:
                    raise Exception("Failed to insert invoice")
                logger.info("Inserted successfully")
                return True
        except Exception as write_db_msg_error:
            await self.rollback("Transaction failed in writeMsgDb", write_db_msg_error)  
            return False

    def validateQuery(self, query: str) -> bool:
        """
        Validates the structure of an SQL query.

        Args:
            query (str): The SQL query string to be validated.

        Returns:
            bool: True if the query is valid, False otherwise.
        """
        query_words = {match.group().lower() for match in re.finditer(r"\b\w+\b", query)}
        dangerous_keywords = {
            'drop', 'delete', 'truncate', 'insert', 'update', 
            'grant', 'revoke', 'alter', 'create', 'replace'
        }
        if "select" not in query_words:
            logger.error("Query must be a SELECT statement")
            return False
        found_keywords = query_words.intersection(dangerous_keywords)
        if found_keywords:
            logger.error(f"Found forbidden keyword(s): {', '.join(found_keywords)}")
            return False
        return True


    def convertDataTypes(self, value) -> str | int | float | None:
        """
        Converts database values to appropriate Python data types.

        Args:
            value: The database value to be converted.

        Returns:
            str | int | float | None: The converted value in the appropriate Python data type.
        """
        if isinstance(value, (date, datetime)):
            return value.strftime("%Y-%m-%d")  # Convert DATE/TIMESTAMP to string
        elif isinstance(value, Decimal):
            return float(value)  # Convert NUMERIC/DECIMAL to float
        return value


    async def executeQuery(self, query: str, whatsapp_number: str) -> list[asyncpg.Record] | None:
        """
        Executes a given SQL query with a specified WhatsApp number.

        Args:
            query (str): The SQL query to be executed.
            whatsapp_number (str): The WhatsApp number to filter the query.

        Returns:
            list[asyncpg.Record]: A list of records returned by the query.
        """
        logger.debug(f"Received query for execution: {query}")
        logger.debug(f"Received query for execution: {query}, bytes: {query.encode('utf-8')}")
        await self.ensureActiveConnection()
        try:
            if not self.validateQuery(query):
                logger.info("Invalid query")
                return None
            
            results = await self._connection.fetch(query)
            formatted_results = [
                {key: self.convertDataTypes(value) for key, value in row.items()}
                for row in results
            ]
            if not formatted_results:
                logger.info("Query executed but returned no results.")
                return [] 
            result_str = str(formatted_results)
            await self._connection.execute("""
                INSERT INTO queries (whatsapp_number, query_text, query_result)
                VALUES ($1, $2, $3)
            """, whatsapp_number, query, result_str)
            return formatted_results
        except Exception as executing_query_error:
                await self.rollback("Error executing query", executing_query_error)
                return None
                    
                
                    
    async def rollback(self, error_message: str, error: Exception) -> None:
        logger.error(f"{error_message}: {error}")
        logger.warning("Manual rollback skipped — handled by 'async with connection.transaction()'.")

    async def ensureActiveConnection(self) -> None:
        """
        Ensures that the database connection is active and reconnects if necessary.

        Re-establishes the connection if it has been closed or lost.
        """
        if not self._connection:
            await self.connect()
                
            