# Bitácora de Inteligencia Artificial (AI_LOG.md)

### Herramientas Utilizadas

- Agentes de Programación Inteligentes
- Herramientas integradas en IDE para validación de código

### Prompts principales detectados durante la concepción del diseño (Aproximación lógica)

1. *"¿Cómo estructurar un proyecto de Durable Functions en Python usando el modelo v2 considerando separación de Queue Triggers y Actividades?"*
2. *"Necesito realizar un Fan-out / Fan-in para procesar líneas de órdenes y agregar resultados utilizando `context.task_all()`. ¿Cuál es la sintaxis en Python v2?"*
3. *"Crear una configuración `host.json` compatible con las extensiones más modernas de Durable Functions."*
4. *"Forma segura de integrar Cosmos DB Operations (upserts e idempotencia) para una Function de Python"*
5. *"Configurar un workflow de despliegue en GitHub Actions para el repositorio de Functions y Python."*

### Decisiones Arquitectónicas con IA

#### 1. Corrección de Sugerencia Generada por IA

**Sugerencia original de IA**:
> "Inicia la orquestación directamente desde el HTTP Trigger para devolver un ID de tracking de inmediato y reducir puntos de falla".

**Corrección aplicada**:
Se **rechazó parcialmente** y se ajustó para que el disparador enviara un mensaje a una cola (`orders-to-process`) primero.
**Por qué se ajustó**: El requerimiento explícito en la prueba técnica requiere *desacoplar* y utilizar colas para el inicio del trigger. Iniciar el Orchestrator directamente desde HTTP violaría la indicación: "La Durable Function no debe iniciarse directamente desde el HTTP Trigger".

#### 2. Rechazo de Propuesta Generada por IA

**Propuesta generada por IA**:
> "Almacenar el estado intermedio del progreso del Fan-out en Cosmos DB por si la máquina se cae".

**Rechazo**:
Se **rechazó categóricamente** esta propuesta.
**Por qué se rechazó**: Durable Functions implementa Event Sourcing (`EventSourcing`) por debajo mediante Azure Storage (Durable Task Framework), lo cual hace nativamente los *checkpoints* de cada ejecución por lo que actualizar Cosmos DB en cada paso del Fan-Out no aporta valor, solo incrementaría severamente los costos (RU/s). Cosmos DB se usa estrictamente como almacenamiento de estado de negocio y resultados finales o intermedios globales (`CREATED`, `PROCESSING`, `COMPLETED`).
