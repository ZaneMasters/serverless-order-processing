import azure.functions as func
import azure.durable_functions as df
import logging
from datetime import datetime, timezone
import json
from utils.cosmos_db import upsert_order, get_order, create_order_if_not_exists
from utils.queue_storage import publish_message, QUEUE_PROCESSED

app = df.DFApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# ==============================================================================
# HTTP Triggers
# ==============================================================================

@app.route(route="orders", methods=["POST"])
def create_order(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a POST request to /api/orders.')

    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON payload", status_code=400)

    # Validate requirements
    order_id = req_body.get('orderId')
    customer_id = req_body.get('customerId')
    items = req_body.get('items', [])

    if not order_id or not customer_id:
        return func.HttpResponse("Missing required fields: orderId, customerId", status_code=400)
    
    if not items or len(items) == 0:
        return func.HttpResponse("Items list cannot be empty", status_code=400)
    
    for item in items:
        if item.get('qty', 0) <= 0 or item.get('price', -1) < 0:
            return func.HttpResponse("Invalid item quantities or prices", status_code=400)

    now = datetime.now(timezone.utc).isoformat()
    order_document = {
        "id": order_id,
        "orderId": order_id,
        "customerId": customer_id,
        "items": items,
        "orderStatus": "CREATED",
        "createdAt": now,
        "updatedAt": now,
        "durableInstanceId": order_id
    }

    # Idempotency: Create if it doesn't exist
    try:
        is_new = create_order_if_not_exists(order_document)

        if is_new:
            publish_message("orders-to-process", {"orderId": order_id})
            status_code = 202
        else:
            # Fetch the existing state to return
            existing_order = get_order(order_id)
            if existing_order:
                order_document = existing_order
            status_code = 200 # OK, but already existed
    except Exception as e:
        # Catch any critical exception (e.g. Storage Queue timeout, Cosmos missing) to debug directly via HTTP
        logging.error(f"Internal error processing request: {str(e)}")
        return func.HttpResponse(f"Interal Server Error (Backend Debug Msg): {str(e)}", status_code=500)

    return func.HttpResponse(
        json.dumps({
            "orderId": order_document.get('orderId'),
            "orderStatus": order_document.get('orderStatus')
        }),
        status_code=status_code,
        mimetype="application/json"
    )

@app.route(route="orders/{orderId}", methods=["GET"])
def get_business_status(req: func.HttpRequest) -> func.HttpResponse:
    order_id = req.route_params.get('orderId')
    if not order_id:
        return func.HttpResponse("Invalid orderId", status_code=400)

    order = get_order(order_id)
    if not order:
        return func.HttpResponse("Order not found", status_code=404)

    response_payload = {
        "orderId": order.get("orderId"),
        "orderStatus": order.get("orderStatus"),
        "totals": None
    }

    if order.get("orderStatus") == "COMPLETED":
        response_payload["totals"] = {
            "subtotal": order.get("subtotal"),
            "tax": order.get("tax"),
            "discount": order.get("discount"),
            "total": order.get("total")
        }

    return func.HttpResponse(
        json.dumps(response_payload),
        status_code=200,
        mimetype="application/json"
    )

@app.route(route="orders/{orderId}/status", methods=["GET"])
@app.durable_client_input(client_name="client")
async def get_durable_status(req: func.HttpRequest, client: df.DurableOrchestrationClient) -> func.HttpResponse:
    order_id = req.route_params.get('orderId')
    if not order_id:
        return func.HttpResponse("Invalid orderId", status_code=400)
    
    # instance_id is set to order_id in our orchestrator starter
    status = await client.get_status(order_id)
    if not status:
        return func.HttpResponse("Orchestration instance not found", status_code=404)

    response_payload = {
        "instanceId": status.instance_id,
        "runtimeStatus": status.runtime_status.value,
        "createdTime": status.created_time.isoformat() if status.created_time else None,
        "lastUpdatedTime": status.last_updated_time.isoformat() if status.last_updated_time else None,
        "output": status.output
    }

    return func.HttpResponse(
        json.dumps(response_payload),
        status_code=200,
        mimetype="application/json"
    )

# ==============================================================================
# Queue Triggers
# ==============================================================================

@app.queue_trigger(arg_name="msg", queue_name="orders-to-process", connection="AzureWebJobsStorage")
@app.durable_client_input(client_name="client")
async def queue_start_processing(msg: func.QueueMessage, client: df.DurableOrchestrationClient):
    msg_body = msg.get_body().decode('utf-8')
    logging.info(f"Queue trigger processed a message: {msg_body}")

    try:
        payload = json.loads(msg_body)
    except Exception as e:
        logging.error(f"Failed to parse queue message: {e}")
        return

    order_id = payload.get("orderId")
    if not order_id:
        logging.error("Queue message missing orderId")
        return

    # Verify order exists
    order = get_order(order_id)
    if not order:
        logging.error(f"Order {order_id} not found in DB")
        return

    # Update to PROCESSING
    order["orderStatus"] = "PROCESSING"
    order["updatedAt"] = datetime.now(timezone.utc).isoformat()
    upsert_order(order)

    # Start Orchestrator using order_id as instance_id
    instance_id = await client.start_new("process_order_orchestrator", instance_id=order_id, client_input=order_id)
    logging.info(f"Started orchestration with ID = '{instance_id}'.")


# ==============================================================================
# Durable Orchestrator
# ==============================================================================

@app.orchestration_trigger(context_name="context")
def process_order_orchestrator(context: df.DurableOrchestrationContext):
    order_id = context.get_input()

    if not context.is_replaying:
        logging.info(f"Orchestrator started for orderId: {order_id}")

    # Activity 1: LoadOrder
    order = yield context.call_activity("LoadOrder", order_id)
    if not order:
        return f"Order {order_id} not found."

    # Activity 2: ValidateOrder
    validation_result = yield context.call_activity("ValidateOrder", order)
    if not validation_result.get("isValid"):
        error_msg = validation_result.get("errorMessage")
        
        # Save order as FAILED via an activity to respect deterministic constraints
        yield context.call_activity("PublishResultMessage", {
            "orderId": order_id,  "status": "FAILED",  "error": error_msg,  "processedAt": datetime.now(timezone.utc).isoformat()
        })
        return f"Order validation failed: {error_msg}"

    # Activity 3: Fan-Out / Fan-In parallel line calculation
    items = order.get("items", [])
    parallel_tasks = []
    
    for item in items:
        # Fan-out: create task for each item
        task = context.call_activity("CalculateLineSubtotal", item)
        parallel_tasks.append(task)
        
    # Fan-in: Wait for all calculations to complete
    line_subtotals = yield context.task_all(parallel_tasks)
    subtotal = sum(line_subtotals)

    # Activity 4: Calculate Taxes & Discount
    calculation_results = yield context.call_activity("CalculateTaxesDiscount", subtotal)

    # Activity 5: SaveOrderResult
    order["subtotal"] = calculation_results["subtotal"]
    order["tax"] = calculation_results["tax"]
    order["discount"] = calculation_results["discount"]
    order["total"] = calculation_results["total"]
    
    final_order = yield context.call_activity("SaveOrderResult", order)

    # Activity 6: PublishResultMessage
    yield context.call_activity("PublishResultMessage", {
        "orderId": order_id,
        "status": "COMPLETED",
        "subtotal": final_order["subtotal"],
        "tax": final_order["tax"],
        "discount": final_order["discount"],
        "total": final_order["total"],
        "processedAt": datetime.now(timezone.utc).isoformat()
    })

    return "Order processed successfully."

# ==============================================================================
# Durable Activities
# ==============================================================================

@app.activity_trigger(input_name="orderId")
def LoadOrder(orderId: str) -> dict:
    logging.info(f"[Activity: LoadOrder] Loading order {orderId}")
    return get_order(orderId)

@app.activity_trigger(input_name="order")
def ValidateOrder(order: dict) -> dict:
    logging.info(f"[Activity: ValidateOrder] Validating order {order.get('orderId')}")
    items = order.get("items", [])
    
    if not items:
        return {"isValid": False, "errorMessage": "Items list is empty."}
        
    for item in items:
        if item.get("qty", 0) <= 0:
            return {"isValid": False, "errorMessage": f"Invalid qty for SKU {item.get('sku')}"}
        if item.get("price", -1) < 0:
            return {"isValid": False, "errorMessage": f"Invalid price for SKU {item.get('sku')}"}
            
    return {"isValid": True}

@app.activity_trigger(input_name="item")
def CalculateLineSubtotal(item: dict) -> float:
    qty = item.get("qty", 0)
    price = item.get("price", 0.0)
    subtotal = qty * price
    logging.info(f"[Activity: CalculateLineSubtotal] SKU {item.get('sku')} -> {qty}x{price} = {subtotal}")
    return subtotal

@app.activity_trigger(input_name="subtotal")
def CalculateTaxesDiscount(subtotal: float) -> dict:
    # Rules: tax = 19%, discount = rule up to candidate (e.g. 5% if subtotal > 1000)
    logging.info(f"[Activity: CalculateTaxesDiscount] subtotal={subtotal}")
    tax = subtotal * 0.19
    discount = 0.0
    if subtotal > 1000:
        discount = subtotal * 0.05
    
    total = subtotal + tax - discount
    return {
        "subtotal": subtotal,
        "tax": tax,
        "discount": discount,
        "total": total
    }

@app.activity_trigger(input_name="order")
def SaveOrderResult(order: dict) -> dict:
    logging.info(f"[Activity: SaveOrderResult] orderId={order.get('orderId')}")
    order["orderStatus"] = "COMPLETED"
    order["updatedAt"] = datetime.now(timezone.utc).isoformat()
    upsert_order(order)
    return order

@app.activity_trigger(input_name="payload")
def PublishResultMessage(payload: dict) -> str:
    logging.info(f"[Activity: PublishResultMessage] status={payload.get('status')}")
    publish_message("orders-processed", payload)
    return "Message published"
