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

## Ejecución Local

1. Requiere [Azure Functions Core Tools](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local).
2. Requiere el emulador de Storage ([Azurite](https://learn.microsoft.com/en-us/azure/storage/common/storage-use-azurite)) o una cuenta real para las colas y Durable Tasks.
3. Configura tu `local.settings.json` con las cadenas de conexión:

   ```json
   {
     "IsEncrypted": false,
     "Values": {
       "AzureWebJobsStorage": "UseDevelopmentStorage=true",
       "FUNCTIONS_WORKER_RUNTIME": "python",
       "AzureWebJobsFeatureFlags": "EnableWorkerIndexing",
       "AzureCosmosDBConnectionString": "<TU CONECTION STRING de Cosmos>",
       "AzureQueueConnectionString": "<TU CONNECTION STRING de Storage Account>"
     }
   }
   ```

4. Instala dependencias: `pip install -r requirements.txt`.
5. Levanta el proyecto: `func start`.

## CI/CD

El proyecto cuenta con un flujo completo de subida en `.github/workflows/deploy.yml` que empaqueta y publica en Azure la aplicación cuando se hace PUSH a `main`.

Requiere configurar el Secret: `AZURE_FUNCTIONAPP_PUBLISH_PROFILE` a nivel de GitHub Actions.
