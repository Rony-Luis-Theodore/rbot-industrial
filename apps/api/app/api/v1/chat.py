"""
=============================================================================
R-Bot — Endpoint: Chat (POST /api/v1/chat)
=============================================================================

Propósito:
    Expone el endpoint principal de conversación con el robot.
    El operario envía instrucciones en lenguaje natural.

Qué hace:
    - Recibe ChatRequest con el mensaje del usuario.
    - Delega TODA la lógica a ChatOrchestrator.
    - Retorna ChatResponse con respuesta, intención y datos ROS.

Conexión con el resto:
    - Frontend js/api/chat.js consume este endpoint.
    - NO contiene lógica de negocio (principio de router delgado).

Escalabilidad:
    - Futuro: WebSocket en ws.py para streaming de respuestas LLM.
    - Futuro: historial de conversación con GET /chat/history.
=============================================================================
"""

from fastapi import APIRouter, Depends

from app.api.deps import get_chat_orchestrator
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_orchestrator import ChatOrchestrator

router = APIRouter()


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Enviar instrucción al robot",
    description=(
        "Recibe una instrucción en lenguaje natural del operario. "
        "El LLM la traduce a una acción ROS2 y retorna la respuesta."
    ),
)
async def send_chat_message(
    request: ChatRequest,
    orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
) -> ChatResponse:
    """
    Procesa una instrucción del operario vía orquestador de chat.

    Args:
        request: Cuerpo JSON con el mensaje del usuario.
        orchestrator: Inyectado por FastAPI desde deps.py.

    Returns:
        ChatResponse con respuesta textual y metadatos de intención/ROS.
    """
    return await orchestrator.process_message(request.message)
