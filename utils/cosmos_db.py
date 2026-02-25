import os
import logging
from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError, CosmosHttpResponseError

COSMOS_CONNECTION_STRING = os.environ.get("COSMOS_CONNECTION_STRING")
DATABASE_NAME = os.environ.get("COSMOS_DATABASE_NAME", "orders-db")
CONTAINER_NAME = os.environ.get("COSMOS_CONTAINER_NAME", "orders")

_client = None
_container = None

def get_container():
    global _client, _container
    if _container is not None:
        return _container
    
    if not COSMOS_CONNECTION_STRING:
        raise ValueError("COSMOS_CONNECTION_STRING environment variable is missing.")

    _client = CosmosClient.from_connection_string(COSMOS_CONNECTION_STRING)
    database = _client.get_database_client(DATABASE_NAME)
    _container = database.get_container_client(CONTAINER_NAME)
    return _container

def get_order(order_id: str) -> dict:
    """Retrieve an order from Cosmos DB by orderId."""
    container = get_container()
    try:
        response = container.read_item(item=order_id, partition_key=order_id)
        return response
    except CosmosResourceNotFoundError:
        return None
    except CosmosHttpResponseError as e:
        logging.error(f"Error fetching order {order_id}: {e.message}")
        raise e

def upsert_order(order_data: dict) -> dict:
    """Insert or update an order in Cosmos DB."""
    container = get_container()
    if 'id' not in order_data:
        order_data['id'] = order_data['orderId']
    
    response = container.upsert_item(body=order_data)
    return response

def create_order_if_not_exists(order_data: dict) -> bool:
    """
    Tries to create an order. Returns True if created, False if it already existed.
    """
    container = get_container()
    if 'id' not in order_data:
        order_data['id'] = order_data['orderId']
        
    try:
        container.create_item(body=order_data)
        return True
    except CosmosHttpResponseError as e: 
        if e.status_code == 409: # Conflict - already exists
            logging.warning(f"Order {order_data['orderId']} already exists.")
            return False
        # If it's another error, bubble it up
        raise e
