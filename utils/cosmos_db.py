import os
import logging
from azure.cosmos import CosmosClient, PartitionKey

# Environment variables
COSMOS_CONNECTION_STRING = os.environ.get("COSMOS_CONNECTION_STRING")
DATABASE_NAME = os.environ.get("COSMOS_DATABASE_NAME", "orders-db")
CONTAINER_NAME = os.environ.get("COSMOS_CONTAINER_NAME", "orders")

# Initialize Cosmos Client
# If the connection string isn't available, we warn but don't crash on import
# It allows tests to run without issues.
client = None
database = None
container = None

if COSMOS_CONNECTION_STRING:
    try:
        client = CosmosClient.from_connection_string(COSMOS_CONNECTION_STRING)
        database = client.create_database_if_not_exists(id=DATABASE_NAME)
        container = database.create_container_if_not_exists(
            id=CONTAINER_NAME,
            partition_key=PartitionKey(path="/orderId"),
            offer_throughput=400
        )
        logging.info("Cosmos DB client initialized successfully.")
    except Exception as e:
        logging.error(f"Failed to initialize Cosmos DB client: {e}")

def get_order(order_id: str) -> dict:
    """Retrieve an order from Cosmos DB by orderId."""
    if not container:
        raise ValueError("Cosmos DB container not initialized.")
    try:
        response = container.read_item(item=order_id, partition_key=order_id)
        return response
    except Exception as e:
        # e.g., azure.cosmos.exceptions.CosmosResourceNotFoundError if not found
        logging.warning(f"Order {order_id} not found or error occurred: {e}")
        return None

def upsert_order(order_data: dict) -> dict:
    """Insert or update an order in Cosmos DB."""
    if not container:
        raise ValueError("Cosmos DB container not initialized.")
    if 'id' not in order_data:
        order_data['id'] = order_data['orderId']
    
    response = container.upsert_item(body=order_data)
    return response

def create_order_if_not_exists(order_data: dict) -> bool:
    """
    Tries to create an order. Returns True if created, False if it already existed.
    """
    if not container:
        raise ValueError("Cosmos DB container not initialized.")
    if 'id' not in order_data:
        order_data['id'] = order_data['orderId']
        
    try:
        container.create_item(body=order_data)
        return True
    except Exception as e: # Catch conflict error when it already exists
        logging.warning(f"Order {order_data['orderId']} already exists. {e}")
        return False
