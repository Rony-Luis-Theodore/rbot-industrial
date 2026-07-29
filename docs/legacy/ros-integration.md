# Guía de integración ROS2

Esta guía está dirigida al integrante responsable de conectar ROS2 real.

## Contrato a implementar

Archivo: `backend/app/domain/interfaces/ros_service.py`

Todos los métodos son `async` y deben retornar los tipos definidos en
`backend/app/domain/models/robot.py`.

## Referencia: MockROSService

Ver `backend/app/adapters/ros/mock_ros.py` para la estructura de datos esperada.

## Arquitectura recomendada

**IMPORTANTE:** FastAPI (asyncio) y rclpy (spin) no deben compartir el mismo hilo.

### Opción A — Nodo ROS2 dedicado + IPC (recomendada)

```
┌──────────────┐    gRPC/Redis/ZMQ    ┌──────────────┐
│   FastAPI    │ ◄──────────────────► │  ROS2 Node   │
│  (uvicorn)   │                      │  (rclpy)     │
└──────────────┘                      └──────────────┘
```

- FastAPI se comunica con un bridge externo
- El nodo ROS2 ejecuta acciones reales
- Escalable y robusto para producción 24/7

### Opción B — subprocess CLI (rápida para prototipo)

```python
import subprocess

async def get_topics(self) -> ROSResourceList:
    result = subprocess.run(
        ["ros2", "topic", "list"],
        capture_output=True, text=True
    )
    items = result.stdout.strip().split("\n")
    return ROSResourceList(resource_type="topics", items=items)
```

- Simple pero limitada (sin feedback en tiempo real)
- Útil para demo inicial

### Opción C — rclpy en thread separado

- Más compleja, requiere asyncio bridge
- Solo si no es posible proceso separado

## Pasos para integrar

### 1. Implementar RclpyROSService

Editar `backend/app/adapters/ros/rclpy_ros.py`:

```python
class RclpyROSService(ROSService):
    async def get_topics(self) -> ROSResourceList:
        # Implementar con rclpy, subprocess o bridge
        ...
```

### 2. Configurar .env

```env
ROS_PROVIDER=rclpy
ROS_DOMAIN_ID=0
```

### 3. Navegación autónoma

Para `send_navigation_goal(destination)`:

- Usar action client de Nav2: `/navigate_to_pose`
- O waypoints predefinidos: mapear "Estación A" → coordenadas
- Actualizar `RobotStatus.is_navigating` y `current_goal`

### 4. Estado del robot

`get_status()` debe retornar datos reales de:

- `/battery_state` → battery_percent
- `/amcl_pose` → position
- Estado del behavior tree → mode, is_navigating

## Mapeo de destinos simbólicos

Crear configuración de waypoints:

```yaml
# config/waypoints.yaml (futuro)
waypoints:
  "Estación A": { x: 1.0, y: 2.0, theta: 0.0 }
  "Base": { x: 0.0, y: 0.0, theta: 0.0 }
  "bomba 3": { x: 5.0, y: -3.0, theta: 1.57 }
```

## Archivos que NO debes modificar

- `api/v1/robot.py` (routers)
- `services/chat_orchestrator.py` (orquestador)
- `domain/interfaces/ros_service.py` (contrato)

## Endpoints que alimenta

| Endpoint | Método ROSService |
|----------|-------------------|
| GET /robot/status | get_status() |
| GET /robot/topics | get_topics() |
| GET /robot/nodes | get_nodes() |
| GET /robot/services | get_services() |
| GET /robot/actions | get_actions() |
| POST /chat (via LLM) | send_navigation_goal(), cancel_navigation(), return_home() |

## Futuro: telemetría en tiempo real

- WebSocket en `api/v1/ws.py` para streaming de `/scan`, `/map`, odometría
- Frontend: `js/api/ws-client.js` + actualización de placeholders mapa/LiDAR
