"""
=============================================================================
R-Bot — Router API v1: Agregador de endpoints
=============================================================================

Propósito:
    Agrupa todos los routers de la versión 1 de la API bajo /api/v1.

Conexión con el resto:
    - main.py incluye este router con prefix API_V1_PREFIX.
    - chat.py y robot.py se montan como sub-routers.
=============================================================================
"""

from fastapi import APIRouter

from app.api.v1 import chat, robot, voice, ws
from app.core.config import settings
from app.schemas.robot import HealthResponse

router = APIRouter()

# Montar sub-routers con sus prefijos y tags para documentación Swagger
router.include_router(chat.router, tags=["Chat"])
router.include_router(robot.router, prefix="/robot", tags=["Robot"])
router.include_router(voice.router, prefix="/voice", tags=["Voice"])
router.include_router(ws.router, tags=["Realtime"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Verifica que la API esté operativa y reporta providers activos.",
    tags=["System"],
)
async def health_check() -> HealthResponse:
    """Endpoint de health check para monitoreo."""
    return HealthResponse(
        status="ok",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        llm_provider=settings.LLM_PROVIDER,
        ros_provider=settings.ROS_PROVIDER,
    )
