import logging
import os
import re
import uuid
from datetime import datetime
from urllib.parse import urlparse
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

class S3Handler:
    """
    Handles interactions with Amazon S3 for uploading, generating presigned URLs, and deleting objects.

    This class provides methods to upload files to S3, generate presigned URLs for accessing files,
    and delete files from S3. It uses the boto3 library to interact with S3 and requires AWS credentials
    to be configured in the environment.
    """

    def __init__(self):
        """
        Initializes the S3Handler with a boto3 S3 client.

        The S3 client is used to perform operations on the specified S3 bucket.
        """
        self._logger = logger
        self.s3_client = boto3.client('s3')
        self.bucket_name = os.getenv("S3_BUCKET_NAME")

    async def uploadToS3(self, phone_number: str, file_bytes: bytes, file_type: str) -> str | None:
        """
        Uploads a file to S3 and returns its path.

        Args:
            phone_number (str): The phone number associated with the file.
            file_bytes (bytes): The file content to upload.
            file_type (str): The type of the file (e.g., 'image', 'jpg', 'png', 'xlsx').

        Returns:
            str | None: The S3 path of the uploaded file, or None if the upload fails.
        """
        logger.debug(f"the phone number in upload to s3 is: {phone_number} bytes")
        logger.debug(f"the file bytes in s3 in upload to s3 is: {file_bytes} bytes")
        try:
            sanitized_phone = re.sub(r'\D', '', phone_number)  # Remove non-digits
            supported_types = {
                "image": "image/png",  
                "jpg": "image/jpeg",
                "jpeg": "image/jpeg",
                "png": "image/png",
                "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            }
            if file_type not in supported_types:
                logger.error(f"Unsupported file type: {file_type}")
                return None

            folder = "microservice-uploads" 
            filename = f"{sanitized_phone}_{uuid.uuid4().hex[:8]}.{file_type}"
            s3_path = f"{folder}/{sanitized_phone}/{filename}"
            content_type = supported_types[file_type] 

            logger.debug(f"the aws s3 path in s3 class: {s3_path}")
            logger.debug(f"the file bytes in s3 before upload: {file_bytes} bytes")
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_path,
                Body=file_bytes,
                ContentType=content_type
            )
            logger.info(f"File uploaded successfully to {s3_path}")
            return s3_path

        except ClientError as e:
            logger.error(f"Upload failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return None

    async def generatePresignedUrl(self, s3_path: str, expiration: int = 600) -> str | None:
        """
        Generates a presigned URL for accessing a file in S3.

        Args:
            s3_path (str): The S3 path of the file.
            expiration (int, optional): The expiration time of the URL in seconds. Defaults to 600.

        Returns:
            str | None: The presigned URL, or None if generation fails.
        """
        try:
            url = self.s3_client.generate_presigned_url('get_object',
                                                        Params={'Bucket': self.bucket_name, 'Key': s3_path,'ResponseContentDisposition': 'attachment'},
                                                        ExpiresIn=expiration,
                                                        )
            logger.info(f"Presigned URL generated for {s3_path}")
            return url
        except Exception as e:
            logger.error(f"Error generating presigned URL: {e}")
            return None

    async def deleteFromS3(self, s3_path: str) -> bool:
        """
        Deletes a file from S3.

        Args:
            s3_path (str): The S3 path of the file to delete.

        Returns:
            bool: True if the file was successfully deleted, False otherwise.
        """
        try:
            if s3_path.startswith("https"):
                parsed_url = urlparse(s3_path)
                s3_key = parsed_url.path.lstrip('/')  
            else:
                s3_key = s3_path  
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            logger.info(f"Deleted object from S3: {s3_key}")
            return True
        except ClientError as e:
            logger.error(f"Failed to delete object {s3_key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error while deleting {s3_key}: {e}")
            return False
