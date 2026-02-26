# Serverless Order Processing (Backend)

Este repositorio contiene la lógica del negocio implementada en Python utilizando el modelo v2 de **Azure Functions** y **Durable Functions** para procesar órdenes de forma asíncrona.

## Arquitectura

El flujo funciona de la siguiente manera:

1. Un cliente envía un `POST` a `/api/orders`.
2. La Function HTTP guarda la intención de la orden temporalmente en **Cosmos DB** y envía un mensaje a la cola **orders-to-process** (Azure Storage Queue). Retorna 202 Accepted.
3. Un Queue Trigger detecta el mensaje y lanza el **Durable Orchestrator**.
4. El Orchestrator ejecuta las siguientes actividades:
   - `LoadOrder`: Carga estado inicial desde Cosmos DB.
   - `ValidateOrder`: Verifica la estructura. Si falla, guarda `FAILED` y publica `orders-processed`.
   - `CalculateLineSubtotal`: Usa un patrón Fan-out (paralelo) seguido de un Fan-in (sumando todas las subtotales devueltas) para calcular los costos de línea de cada ítem.
   - `CalculateTaxesDiscount`: Computa los resultados finales.
   - `SaveOrderResult`: Guarda estado final en Cosmos DB (`COMPLETED`).
   - `PublishResultMessage`: Publica confirmación a la cola `orders-processed`.

## API Endpoints y Flujo de Uso

La aplicación expone una API REST para interactuar de forma sencilla con el sistema Serverless:

### 1. Crear Orden (POST `/api/orders`)

Envía una nueva orden de compra para ser encolada. El sistema valida idempotentemente la orden, la crea en Cosmos DB con estado `CREATED` y la envía a la cola `orders-to-process`.

- **Cuerpo esperado:**

```json
{
  "orderId": "ORD-123",
  "customerId": "CUST-01",
  "items": [
    { "sku": "ITEM-A", "qty": 2, "price": 100 },
    { "sku": "ITEM-B", "qty": 1, "price": 999 }
  ]
}
```

- **Respuesta Exitosa:** `202 Accepted`

### 2. Consultar Nivel de Negocio (GET `/api/orders/{orderId}`)

Consulta la base de datos de lectura (Cosmos DB) para ver el estado financiero de la orden.

- **Respuesta en Progreso:**

```json
{
  "orderId": "ORD-123",
  "orderStatus": "PROCESSING",
  "totals": null
}
```

- **Respuesta Completada (Fan-in concluido):**

```json
{
  "orderId": "ORD-123",
  "orderStatus": "COMPLETED",
  "totals": {
    "subtotal": 1199.0,
    "tax": 227.81,
    "discount": 59.95,
    "total": 1366.86
  }
}
```

### 3. Diagnóstico de Infraestructura (GET `/api/orders/{orderId}/status`)

Retorna los metadatos crudos del framework de Durable Functions, especificando en qué actividad se encuentra atrapado el orquestador (ej. `Running`, `Completed`, `Failed`). Útil para depurar problemas de ejecución en paralelo.

## CI/CD

El proyecto cuenta con un flujo completo de subida en `.github/workflows/deploy.yml` que empaqueta y publica en Azure la aplicación cuando se hace PUSH a `main`.

