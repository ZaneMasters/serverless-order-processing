import os
import json
import base64
import logging
from azure.storage.queue import QueueClient

# Queue Trigger environment config 
QUEUE_CONNECTION_STRING = os.environ.get("AzureWebJobsStorage", "UseDevelopmentStorage=true")
QUEUE_TO_PROCESS = "orders-to-process"
QUEUE_PROCESSED = "orders-processed"

def get_queue_client(queue_name: str) -> QueueClient:
    """Returns an initialized QueueClient for a given queue."""
    client = QueueClient.from_connection_string(
        conn_str=QUEUE_CONNECTION_STRING,
        queue_name=queue_name
    )
    
    # Manually encoding allows predictable behavior across SDK versions
    return client

def publish_message(queue_name: str, message_dict: dict):
    """Encodes a dictionary to JSON string, then Base64 encodes it and posts to the queue."""
    try:
        client = get_queue_client(queue_name)
        
        # Azure Functions normally expect base64 encoded JSON strings for Queue Triggers
        message_json = json.dumps(message_dict)
        message_b64 = base64.b64encode(message_json.encode('utf-8')).decode('utf-8')
        
        client.send_message(message_b64)
        logging.info(f"Published message to queue {queue_name}: {message_dict}")
    except Exception as e:
        logging.error(f"Failed to publish message to queue {queue_name}: {e}")
        raise e
