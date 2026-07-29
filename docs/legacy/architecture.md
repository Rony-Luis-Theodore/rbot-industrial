# =============================================================================
# R-Bot — Documentación de Arquitectura
# =============================================================================

## Visión general

R-Bot es un sistema de control inteligente para robots autónomos que traduce
instrucciones en lenguaje natural a acciones ROS2 mediante una capa LLM.

```
┌─────────────┐     HTTP/REST      ┌──────────────┐
│  Frontend   │ ◄──────────────►  │   FastAPI    │
│  (JS/HTML)  │                    │   Backend    │
└─────────────┘                    └──────┬───────┘
                                          │
                              ┌───────────┴───────────┐
                              │   ChatOrchestrator    │
                              └───────────┬───────────┘
                                    ┌─────┴─────┐
                                    ▼           ▼
                              ┌─────────┐ ┌─────────┐
                              │LLMService│ │ROSService│
                              │ (Port)  │ │ (Port)  │
                              └────┬────┘ └────┬────┘
                                   ▼           ▼
                              ┌─────────┐ ┌─────────┐
                              │ Adapters│ │ Adapters│
                              │mock/openai│ │mock/rclpy│
                              └─────────┘ └─────────┘
```

## Capas del backend

| Capa | Carpeta | Responsabilidad |
|------|---------|-----------------|
| Presentación | `api/` | Endpoints HTTP, validación de entrada |
| Aplicación | `services/` | Orquestación de lógica de negocio |
| Dominio | `domain/` | Entidades e interfaces (contratos) |
| Infraestructura | `adapters/` | Implementaciones concretas (LLM, ROS) |
| Configuración | `core/` | Settings, constantes, excepciones |

## Flujo de una instrucción

1. Usuario escribe "Muéstrame los topics" en el frontend
2. `POST /api/v1/chat` recibe `{ "message": "..." }`
3. `ChatOrchestrator.process_message()` coordina:
   - Envía al `LLMService` → detecta intent `list_topics`
   - Invoca `ROSService.get_topics()` → obtiene lista
   - Construye respuesta legible
4. Frontend muestra la respuesta en el chat

## Principios de diseño

- **Dependency Inversion**: servicios dependen de interfaces, no de implementaciones
- **Open/Closed**: nuevos LLMs/ROS adapters sin modificar orquestador
- **Single Responsibility**: cada módulo tiene una función clara
- **Factory Pattern**: selección de providers vía `.env`

## Extensibilidad futura

| Feature | Punto de integración |
|---------|---------------------|
| WebSockets | `api/v1/ws.py` + `js/api/ws-client.js` |
| Voz | `adapters/voice/` + orquestador |
| Auth | `api/deps.py` + middleware |
| Base de datos | `adapters/repositories/` |
| Multi-robot | `robot_id` en modelos + factory |
| Mapa/LiDAR | `adapters/ros/` + componentes sidebar |
