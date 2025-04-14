import asyncio
import json
import logging
import os
import re
import openai
import backoff
from dotenv import load_dotenv
from openai import OpenAIError

load_dotenv()
logger = logging.getLogger(__name__)

class GptApiHandler:

    schema_description = """
        Schema:
        users(whatsapp_number PK, username, created_at),
        invoices(invoice_id PK, whatsapp_number FK → users, invoice_date, expense_amount, vat, payee_name, payment_method, raw_image_url, created_at),
        queries(query_id PK, whatsapp_number FK → users, query_text, query_result, created_at)

        All fields are lowercase and must be used exactly as defined. Do not make up columns.
        """


    def __init__(self):
        """
        Initializes the GptApiHandler with an OpenAI client.

        The client is configured using the API key from environment variables.
        """
        self.gpt_client = openai.AsyncClient(api_key=os.getenv("GPT_API_KEY"))

    @backoff.on_exception(
        backoff.expo,
        OpenAIError,
        max_tries=5,
        base=2,
        logger=logger,
        giveup=lambda e: GptApiHandler.stopRetries(e)
    )
    async def callGptApi(self, messages: list[dict]) -> str:
        """
        Calls the GPT-4 API asynchronously with retry logic.

        Args:
            messages (list): A list of message dictionaries to send to the GPT-4 API.

        Returns:
            str: The content of the response message from GPT-4.

        Raises:
            OpenAIError: If an error occurs during the API call.
        """
        try:
            response = await self.gpt_client.chat.completions.create(
                model="gpt-4o",
                messages=messages
            )
            return response.choices[0].message.content
        except OpenAIError as e:
            logger.error(f"Error during GPT API call: {e}")
            raise

    async def gptMessageParser(self, image_url: str) -> dict:
        """
        Parses a message by sending an image URL to GPT-4 for analysis.

        Args:
            image_url (str): The URL of the image to be analyzed.

        Returns:
            dict: A JSON object containing the analysis result or an error message.
        """
        logger.debug(f"Sending image URL to GPT: {image_url}")
        messages = [
            {
                "role": "system",
                "content": (
                        "You are a document analysis assistant. Your task is to analyze the text in images,"
                        "specifically determining if the image contains an invoice, regardless of the document's language. "
                        "You must support multilingual invoices and extract relevant details in English in a structured JSON format. "
                        "If the image is not an invoice, return {\"error\": \"Not an invoice\"}. Strictly follow the requested output format. "
                        "You must download and analyze the image from the provided URL before responding. "
                        "If the image URL is invalid, inaccessible, or the download fails, return {\"error\": \"Invalid or inaccessible URL\"}. "
                        "Do not return null under any circumstances—always return a JSON object."
                    ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Analyze the image and extract any text. If the document is an invoice, return the extracted details in JSON format as shown below.\n\n"
                            "Important Rules:\n"
                            "- Before analyzing, you must first download the image.\n"
                            "- If you cannot access the image, return {\"error\": \"Invalid or inaccessible URL\"} immediately.\n"
                            "- If the image is not an invoice, return {\"error\": \"Not an invoice\"}.\n"
                            "- Do not guess or generate missing fields. If data is missing, return null for those fields within the JSON object.\n"
                            "- Do not return null as the top-level response—always return a JSON object.\n\n"
                            "Correct Output Example (Invoice Found):\n"
                            "```json\n"
                            "{\n"
                            "  \"invoice_date\": \"2024-02-20\",\n"
                            "  \"expense_amount\": 125.50,\n"
                            "  \"vat\": 25.10,\n"
                            "  \"payee_name\": \"ABC Electronics\",\n"
                            "  \"payment_method\": \"Visa Credit Card\",\n"
                            "  \"phone_number\": \"+1-555-123-4567\"\n"
                            "}\n"
                            "```\n"
                            "Error Example (Not an Invoice):\n"
                            "```json\n"
                            "{\"error\": \"Not an invoice\"}\n"
                            "```\n"
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url, "detail": "high"}
                    }
                ],
            }
        ]
        parsed_message = await self.callGptApi(messages)
        logger.debug(f"Raw GPT response: {parsed_message}")
        return self.validateGptResponse(parsed_message)

    async def generateInvoiceQuery(self, user_request: str, user_phone_num_primary_key: str) -> dict:
        """
        Generates an Postgres SQL query based on a user's request using GPT-4.

        Args:
            user_request (str): The user's request for data retrieval.
            user_phone_num_primary_key (str): The user's phone number used as a primary key.

        Returns:
            dict: A JSON object containing the SQL query or an error message.
        """
        messages = [
            {
                "role": "system",
                "content": (
                    f"You are an expert Postgres SQL assistant specializing in PostgreSQL query generation. "
                    f"Your task is to generate an optimized Postgres SQL query based on a user's request while strictly following the database schema:\n\n"
                    f"{self.schema_description}\n\n"
                    "Ensure that whatsapp_number is used as the key for filtering across all relevant tables. "
                    "Return your response **only** in valid JSON format with a single key 'query' for success, "
                    "or 'error' with a reason for failure. "
                    "Example (Success): {\"query\": \"SELECT * FROM invoices WHERE whatsapp_number = '{user_phone_num_primary_key}' ORDER BY created_at DESC LIMIT 1;\"}\n"
                    "Example (Failure): {\"error\": \"Unclear request\"}\n"
                    "Do not return null under any circumstances—always return a JSON object."
                ),
            }
            ,
            {
                "role": "user",
                "content": f"""
                **Task:** Generate a valid **PostgreSQL SQL query** based on the user request.  
                - The query must **only** retrieve data relevant to the user's request.  
                - If the request is unclear or too vague, return {{"error": "Unclear request"}}.  
                - Return **only** a JSON object with either a 'query' key or an 'error' key. Do **not** include any explanations.  

                ### **Database Schema**
                - **users** (whatsapp_number is the primary key)
                - **invoices** (whatsapp_number is a foreign key referencing users)
                - **queries** (whatsapp_number is a foreign key referencing users)

                ### **Rules for Query Generation**
                - Use whatsapp_number = '{user_phone_num_primary_key}' to filter data.
                - Optimize joins between users, invoices, and queries where relevant.
                - Ensure all field names match the schema exactly.
                - If the user request is **unclear**, return {{"error": "Unclear request"}}.
                - **Return JSON format ONLY. No extra text, explanations, or formatting.**
                - **Use "created_at" to sort the most recent occurrence of stored information**

                **User Request:** {user_request}  
                **User WhatsApp Number (Primary Key):** {user_phone_num_primary_key}
                """
            }
        ]
        sql_query = await self.callGptApi(messages)
        logger.debug(f"Raw GPT response: {sql_query}")
        return self.validateGptResponse(sql_query)

    def validateGptResponse(self, gpt_response: str) -> dict | None:
        """
        Validates and parses the response from GPT-4.

        Args:
            gpt_response (str): The raw response string from GPT-4.

        Returns:
            dict or None: A parsed JSON object if valid, otherwise None.
        """
        logger.debug(f"Raw GPT response before validation: {gpt_response}")
        if not gpt_response:
            logger.error("No response received from GPT")
            return None
        
        gpt_response = re.sub(r"```json|```", "", gpt_response).strip()
        try:
            gpt_response_dict = json.loads(gpt_response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse GPT response as JSON: {e}, response: {gpt_response}")
            return None

        if "error" in gpt_response_dict:
            logger.info(f"GPT returned an error: '{gpt_response_dict['error']}'")
            return None
        elif "query" in gpt_response_dict:
            query = gpt_response_dict["query"]
            logger.debug(f"Validated query: {query}")
            return query
        logger.debug(f"Validated image response: {gpt_response_dict}")
        return gpt_response_dict


    @staticmethod
    def stopRetries(raised_exception: OpenAIError) -> bool:
        if hasattr(raised_exception, "status_code"):
            if raised_exception.status_code in {400, 401, 403, 404, 422}:
                error_response = getattr(raised_exception, "response", {})
                error_message = (error_response.get("error") or {}).get("message", "No error message")
                logging.error(f"GPT call failed and won't be retried. Reason: {error_message}")
                return True
        return False