import logging
import logging.handlers
import queue
import httpx
import os
from pathlib import Path



def setupAsyncLogging(module_name: str):
    """
    Sets up asynchronous logging for a module.

    This function creates a log queue, log directory, and log filename.
    It also creates a stream handler and file handler, and a formatter.
    It then creates a listener for the log queue, and starts it.
    """
    log_queue = queue.Queue()   
    log_dir = Path("logs")  
    log_dir.mkdir(parents=True, exist_ok=True)
    log_filename = log_dir / f"{module_name}.log"
    stream_handler = logging.StreamHandler() 
    file_handler = logging.FileHandler(log_filename)  
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    stream_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)
    listener = logging.handlers.QueueListener(log_queue, stream_handler, file_handler)
    listener.start()
    logger = logging.getLogger(module_name)  
    logger.setLevel(logging.DEBUG)  
    logger.handlers = []  
    queue_handler = logging.handlers.QueueHandler(log_queue)
    logger.addHandler(queue_handler)
    logging.getLogger().setLevel(logging.DEBUG)
    logging.getLogger().addHandler(queue_handler)
    return listener



async def downloadTwillieoUrl(url: str) -> bytes:
    """
    Downloads an image from a Twilio URL.

    This function downloads an image from a Twilio URL using the Twilio API.
    It returns the image as bytes if the download is successful, or None if it fails.
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    if not account_sid or not auth_token:
        logging.error("Twilio authentication credentials are missing.")
        return None
    async with httpx.AsyncClient(follow_redirects=True) as client:  
        response = await client.get(url, auth=(account_sid, auth_token))
        if response.status_code == 200:
            return response.content
        else:
            logging.error(f"Error downloading image from {url} | Status: {response.status_code} | Response: {response.text}")
            return None

def createResponseMessage(return_msg: str | dict, return_number: str):
    """
    Creates a response message for a Twilio API.

    This function creates a response message for a Twilio API.
    It returns a dictionary with the response message, from, and to.
    """ 
    response = {
        "body": "",
        "from_": f"whatsapp:{os.getenv('TWILIO_PHONE_NUMBER')}",
        "to": return_number
    }
    if isinstance(return_msg, dict):
        if "from" in return_msg:  
            return_msg["from_"] = return_msg.pop("from")
        if "error" in return_msg:
            return_msg.pop("error")
        response.update(return_msg)  
    elif isinstance(return_msg, str):
        response["body"] = return_msg
    return response

def startServer(app_name, port_num):
    """
    Starts a server.

    This function starts a server using the uvicorn library.
    It runs the specified app on the specified port.
    """
    import uvicorn
    uvicorn.run(app_name, host="0.0.0.0", port=port_num)
    
def getMenuOptions(include_header=True):
    """
    Returns a nicely formatted menu of options for users.

    Args:
        include_header (bool): Whether to include the header text asking what to do next

    Returns:
        str: A formatted menu string
    """
    header = "*What would you like to do next?*\n\n" if include_header else ""

    options = [
        {"key": "0", "title": "Exit Assistant", "desc": "Type 0 anytime to end the session and reset"},
        {"key": "1", "title": "Upload & Process Invoice Image", "desc": "Upload an invoice image for analysis"},
        {"key": "2", "title": "Retrieve Invoice Information", "desc": "Query your stored invoice data"},
    ]

    menu_lines = ["*Choose an option:*\n"]
    for option in options:
        menu_lines.append(f"*{option['key']}.* {option['title']}\n  _{option['desc']}_\n")

    return header + "\n".join(menu_lines)
