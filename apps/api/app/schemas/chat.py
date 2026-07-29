"""
=============================================================================
R-Bot — Schemas HTTP: Chat
=============================================================================

Propósito:
    Define los DTOs (Data Transfer Objects) Pydantic para los endpoints
    de conversación. Representan el contrato JSON entre frontend y backend.

Qué hace:
    - Valida automáticamente requests entrantes.
    - Serializa responses salientes con tipado estricto.

Conexión con el resto:
    - api/v1/chat.py usa estos schemas como tipos de request/response.
    - ChatOrchestrator produce datos que se mapean a ChatResponse.
    - Separado de domain/models/chat.py (entidades internas).

Nota:
    Los schemas pueden diferir de las entidades de dominio para adaptarse
    a las necesidades del frontend sin contaminar el núcleo de negocio.
=============================================================================
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """
    Cuerpo del request POST /api/v1/chat.

    Attributes:
        message: Instrucción en lenguaje natural del operario.
    """

    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Instrucción en lenguaje natural para el robot",
        examples=["Muéstrame los topics activos"],
    )


class LLMIntentResponse(BaseModel):
    """
    Representación HTTP de la intención detectada por el LLM.

    Se incluye en ChatResponse para transparencia y debugging.
    """

    intent: str = Field(description="Identificador de intención detectada")
    action: str = Field(description="Acción ROS2 equivalente")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    provider: str = Field(description="Proveedor LLM que procesó la instrucción")


class ChatResponse(BaseModel):
    """
    Cuerpo del response POST /api/v1/chat.

    Attributes:
        reply: Respuesta textual para mostrar al operario en el chat.
        intent: Intención detectada (opcional, para panel de debug).
        ros_data: Datos ROS obtenidos si la acción lo requirió.
        timestamp: Momento de la respuesta.
    """

    reply: str = Field(description="Respuesta del sistema al operario")
    intent: Optional[LLMIntentResponse] = None
    ros_data: Optional[Any] = Field(default=None, description="Datos ROS resultantes")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatHistoryItem(BaseModel):
    """
    Elemento del historial de conversación.

    Preparado para futura persistencia en base de datos.
    """

    role: str
    content: str
    timestamp: datetime

    class Config:
        from_attributes = True
