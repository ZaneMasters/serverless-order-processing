import os
import json
import base64
import logging
from azure.storage.queue import QueueClient, BinaryBase64EncodePolicy, BinaryBase64DecodePolicy

QUEUE_CONNECTION_STRING = os.environ.get("AzureQueueConnectionString", "UseDevelopmentStorage=true")
QUEUE_TO_PROCESS = "orders-to-process"
QUEUE_PROCESSED = "orders-processed"

def get_queue_client(queue_name: str) -> QueueClient:
    """Returns an initialized QueueClient for a given queue."""
    client = QueueClient.from_connection_string(
        conn_str=QUEUE_CONNECTION_STRING,
        queue_name=queue_name
    )
    
    # Azure Functions usually expect base64 encoded messages
    client.message_encode_policy = BinaryBase64EncodePolicy()
    client.message_decode_policy = BinaryBase64DecodePolicy()
    return client

def publish_message(queue_name: str, message_dict: dict):
    """Encodes a dictionary to JSON string, then Base64 encodes it and posts to the queue."""
    try:
        client = get_queue_client(queue_name)
        
        # Enforce Base64 Encoding
        message_bytes = json.dumps(message_dict).encode('utf-8')
        
        client.send_message(message_bytes)
        logging.info(f"Published message to queue {queue_name}: {message_dict}")
    except Exception as e:
        logging.error(f"Failed to publish message to queue {queue_name}: {e}")
        raise e
