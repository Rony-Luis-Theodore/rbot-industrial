"""
=============================================================================
R-Bot — Constantes globales del sistema
=============================================================================

Propósito:
    Define valores constantes reutilizados en múltiples módulos para evitar
    strings mágicos dispersos en el código.

Qué hace:
    - Agrupa prefijos de API, niveles de eventos, modos del robot, etc.

Conexión con el resto:
    - Routers usan API_V1_PREFIX para versionado.
    - EventLogger usa EVENT_LEVELS para clasificar entradas.
    - Mock adapters usan ROBOT_MODES y estados simulados.
=============================================================================
"""

# Prefijo base de la API REST versionada
API_V1_PREFIX: str = "/api/v1"

# Niveles de severidad para el registro de eventos
EVENT_LEVEL_INFO: str = "info"
EVENT_LEVEL_WARNING: str = "warning"
EVENT_LEVEL_ERROR: str = "error"
EVENT_LEVEL_SUCCESS: str = "success"

# Modos operativos del robot (simulados por ahora)
ROBOT_MODE_IDLE: str = "idle"
ROBOT_MODE_NAVIGATING: str = "navigating"
ROBOT_MODE_CHARGING: str = "charging"
ROBOT_MODE_ERROR: str = "error"
ROBOT_MODE_MANUAL: str = "manual"

# Estados de conexión
CONNECTION_CONNECTED: str = "connected"
CONNECTION_DISCONNECTED: str = "disconnected"
CONNECTION_DEGRADED: str = "degraded"

# Intenciones que el LLM puede devolver (usadas por MockLLM y futuro orquestador)
INTENT_LIST_TOPICS: str = "list_topics"
INTENT_LIST_NODES: str = "list_nodes"
INTENT_LIST_SERVICES: str = "list_services"
INTENT_LIST_ACTIONS: str = "list_actions"
INTENT_NAVIGATE: str = "navigate"
INTENT_SEQUENCE: str = "sequence"
INTENT_CANCEL_NAVIGATION: str = "cancel_navigation"
INTENT_RETURN_HOME: str = "return_home"
INTENT_GET_STATUS: str = "get_status"
INTENT_GET_BATTERY: str = "get_battery"
INTENT_HELP: str = "help"
INTENT_UNKNOWN: str = "unknown"

# Límite de eventos en memoria (antes de persistir en BD futura)
MAX_EVENTS_IN_MEMORY: int = 100
