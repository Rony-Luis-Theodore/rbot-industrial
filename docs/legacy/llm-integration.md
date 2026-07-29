# Guía de integración LLM

Esta guía está dirigida al integrante responsable de conectar el modelo de IA.

## Contrato a implementar

Archivo: `backend/app/domain/interfaces/llm_service.py`

```python
class LLMService(ABC):
    async def process_user_instruction(self, instruction: str) -> LLMIntent:
        ...

    def get_provider_name(self) -> str:
        ...
```

## Qué debe retornar

`LLMIntent` contiene:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `intent` | str | Identificador de acción (ver constantes) |
| `action` | str | Comando ROS equivalente |
| `parameters` | dict | Parámetros extraídos (ej: destino) |
| `confidence` | float | Confianza 0.0-1.0 |
| `raw_response` | str | Respuesta textual del LLM |

## Intenciones soportadas

Definidas en `backend/app/core/constants.py`:

- `list_topics` → ros2 topic list
- `list_nodes` → ros2 node list
- `list_services` → ros2 service list
- `list_actions` → ros2 action list
- `navigate` → send_navigation_goal (params: destination)
- `cancel_navigation` → cancel_navigation
- `return_home` → return_home
- `unknown` → no reconocido

## Pasos para integrar un proveedor

### 1. Crear adapter

Copiar estructura de `adapters/llm/openai_llm.py` o implementar desde cero:

```python
# backend/app/adapters/llm/mi_proveedor_llm.py
class MiProveedorLLMService(LLMService):
    async def process_user_instruction(self, instruction: str) -> LLMIntent:
        # 1. Enviar instruction al LLM con system prompt
        # 2. Parsear respuesta a LLMIntent
        # 3. Retornar
        ...
```

### 2. Registrar en factory

Editar `backend/app/factories/service_factory.py`:

```python
if provider == "mi_proveedor":
    return MiProveedorLLMService(...)
```

### 3. Configurar .env

```env
LLM_PROVIDER=mi_proveedor
MI_PROVEEDOR_API_KEY=...
```

### 4. Probar

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Muéstrame los topics"}'
```

## Referencia: MockLLM

Ver `backend/app/adapters/llm/mock_llm.py` como ejemplo funcional de qué debe retornar tu implementación.

## System prompt sugerido

```
Eres el interfaz de control del robot R-Bot. El operario te da instrucciones
en lenguaje natural. Debes traducirlas a una de estas acciones:

- list_topics: listar topics ROS2
- list_nodes: listar nodos ROS2
- list_services: listar servicios ROS2
- list_actions: listar actions ROS2
- navigate: enviar objetivo de navegación (extraer destino)
- cancel_navigation: detener navegación
- return_home: regresar a base

Responde SOLO en JSON:
{"intent": "...", "action": "...", "parameters": {}, "confidence": 0.95}
```

## Archivos que NO debes modificar

- `api/v1/chat.py` (router)
- `services/chat_orchestrator.py` (orquestador)
- `domain/interfaces/llm_service.py` (contrato)

## Proveedores con stub preparado

- `openai_llm.py` — OpenAI API
- `ollama_llm.py` — Ollama local (Llama, Mistral)
- `gemini_llm.py` — Google Gemini

DeepSeek puede reutilizar la estructura de OpenAI (API compatible).
