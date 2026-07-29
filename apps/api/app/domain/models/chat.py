"""
=============================================================================
R-Bot — Modelos de dominio: Chat
=============================================================================

Propósito:
    Define entidades internas del dominio relacionadas con conversaciones.
    Estas clases NO son DTOs HTTP — representan el modelo de negocio puro.

Qué hace:
    - ChatMessage: un mensaje individual (usuario, asistente o sistema).
    - LLMIntent: resultado estructurado del procesamiento LLM.
    - ChatTurn: par pregunta-respuesta completo.

Conexión con el resto:
    - LLMService devuelve LLMIntent.
    - ChatOrchestrator construye ChatTurn a partir de mensajes e intents.
    - Futura capa de BD persistirá ChatMessage / ChatTurn.

Nota:
    Usamos dataclasses por simplicidad. Si se requiere validación
    estricta en el dominio, migrar a Pydantic models internos.
=============================================================================
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ChatMessage:
    """
    Representa un mensaje en la conversación.

    Attributes:
        role: Rol del emisor ('user', 'assistant', 'system').
        content: Texto del mensaje.
        timestamp: Momento de creación (UTC).
        metadata: Datos adicionales (intent, acción ROS, etc.).
    """

    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMIntent:
    """
    Resultado estructurado del análisis LLM sobre una instrucción del usuario.

    El LLM traduce lenguaje natural a una intención ejecutable.

    Attributes:
        intent: Identificador de la acción (ej: 'list_topics', 'navigate').
        action: Comando o acción ROS equivalente (ej: 'ros2 topic list').
        parameters: Parámetros extraídos (ej: destino de navegación).
        confidence: Nivel de confianza del LLM (0.0 - 1.0).
        raw_response: Respuesta textual completa del LLM.
    """

    intent: str
    action: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    raw_response: str = ""
    reply: str = ""

@dataclass
class ChatTurn:
    """
    Representa un intercambio completo usuario → sistema.

    Attributes:
        user_message: Mensaje original del operario.
        assistant_response: Respuesta final mostrada al usuario.
        llm_intent: Intención detectada por el LLM.
        ros_result: Resultado de la acción ROS (si aplica).
    """

    user_message: str
    assistant_response: str
    llm_intent: Optional[LLMIntent] = None
    ros_result: Optional[Any] = None
