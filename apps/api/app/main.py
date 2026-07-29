"""
=============================================================================
R-Bot — Punto de entrada FastAPI (main.py)
=============================================================================

Propósito:
    Inicializa y configura la aplicación FastAPI.
    Punto de arranque del servidor backend.

Qué hace:
    - Crea la instancia FastAPI con metadatos y lifespan.
    - Configura CORS para el frontend.
    - Monta el router API v1.
    - Sirve archivos estáticos del frontend (opcional en desarrollo).
    - Registra evento de inicio en EventLogger.

Conexión con el resto:
    - Ejecutar con: uvicorn app.main:app --reload
    - Importa router desde api/v1/router.py.
    - Lee configuración desde core/config.py.

Escalabilidad:
    - Agregar middleware de autenticación aquí.
    - Agregar exception handlers globales para RBotException.
    - Agregar WebSocket endpoint en lifespan.
=============================================================================
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import router as api_v1_router
from app.core.config import settings
from app.core.constants import API_V1_PREFIX, EVENT_LEVEL_INFO
from app.services.event_logger import event_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestor del ciclo de vida de la aplicación.

    Se ejecuta al iniciar y al cerrar el servidor.
    Útil para conexiones BD, nodos ROS2, etc.
    """
    # --- Startup ---
    event_logger.log(
        f"{settings.APP_NAME} v{settings.APP_VERSION} iniciado",
        level=EVENT_LEVEL_INFO,
        source="system",
        metadata={
            "llm_provider": settings.LLM_PROVIDER,
            "ros_provider": settings.ROS_PROVIDER,
            "debug": settings.DEBUG,
        },
    )
    yield
    # --- Shutdown ---
    event_logger.log("Servidor detenido", level=EVENT_LEVEL_INFO, source="system")


def create_app() -> FastAPI:
    """
    Factory que construye y configura la aplicación FastAPI.

    Returns:
        Instancia FastAPI lista para servir.
    """
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "API REST para control inteligente del robot R-Bot. "
            "Traduce instrucciones en lenguaje natural a acciones ROS2 "
            "mediante capa LLM."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # --- CORS: permitir requests del frontend ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def no_cache_hmi(request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.endswith((".js", ".css", ".html")) or path in ("/", "/index.html"):
            response.headers["Cache-Control"] = "no-store, max-age=0"
        return response


    # --- Montar API REST versionada ---
    app.include_router(api_v1_router, prefix=API_V1_PREFIX)

    # --- Servir HMI industrial (apps/web) ---
    # main.py vive en apps/api/app/ → web está en apps/web/
    frontend_path = Path(__file__).resolve().parent.parent.parent / "web"
    if frontend_path.exists():
        app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")

    return app


# Instancia de la aplicación — uvicorn importa este objeto
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
