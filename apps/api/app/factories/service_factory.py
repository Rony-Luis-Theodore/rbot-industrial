"""
=============================================================================
R-Bot — Factory: Creación de servicios según configuración
=============================================================================

Propósito:
    Instancia los adapters LLM y ROS correctos según variables de entorno.
    Centraliza la lógica de selección de proveedores.

Qué hace:
    - create_llm_service(): retorna Mock, OpenAI, Ollama, etc.
    - create_ros_service(): retorna Mock o Rclpy.
    - Valida configuración antes de instanciar.

Conexión con el resto:
    - api/deps.py usa estas factories para inyección de dependencias.
    - Cambiar LLM_PROVIDER en .env cambia el comportamiento sin tocar código.

Para agregar un nuevo proveedor LLM:
    1. Crear adapter en adapters/llm/.
    2. Agregar case en create_llm_service().
    3. Documentar variable de entorno en .env.example.
=============================================================================
"""

from app.adapters.llm.gemini_llm import GeminiLLMService
from app.adapters.llm.mock_llm import MockLLMService
from app.adapters.llm.ollama_llm import OllamaLLMService
from app.adapters.llm.openai_llm import OpenAILLMService
from app.adapters.ros.mock_ros import MockROSService
from app.adapters.ros.rclpy_ros import RclpyROSService
from app.core.config import settings
from app.core.exceptions import ServiceNotConfiguredError
from app.domain.interfaces.llm_service import LLMService
from app.domain.interfaces.ros_service import ROSService

import os
from pathlib import Path


def create_llm_service() -> LLMService:
    """
    Factory que crea la instancia de LLMService según LLM_PROVIDER.

    Returns:
        Instancia concreta de LLMService.

    Raises:
        ServiceNotConfiguredError: Si el provider no existe o falta configuración.
    """
    provider = settings.LLM_PROVIDER.lower()

    if provider == "mock":
        return MockLLMService()

    if provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise ServiceNotConfiguredError(
                "LLM_PROVIDER=openai requiere OPENAI_API_KEY en .env"
            )
        return OpenAILLMService(api_key=settings.OPENAI_API_KEY)

    if provider == "ollama":
        return OllamaLLMService(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_MODEL,
        )

    if provider == "gemini":
        if not settings.GEMINI_API_KEY:
            raise ServiceNotConfiguredError(
                "LLM_PROVIDER=gemini requiere GEMINI_API_KEY en .env"
            )
        return GeminiLLMService(api_key=settings.GEMINI_API_KEY)

    if provider == "deepseek":
        # DeepSeek usa API compatible con OpenAI — reutilizar adapter cuando se implemente
        raise ServiceNotConfiguredError(
            "LLM_PROVIDER=deepseek aún no implementado. Ver docs/llm-integration.md."
        )

    raise ServiceNotConfiguredError(
        f"LLM_PROVIDER desconocido: '{provider}'. "
        f"Valores válidos: mock, openai, ollama, gemini, deepseek"
    )


def create_ros_service() -> ROSService:
    """
    Factory que crea la instancia de ROSService según ROS_PROVIDER + perfil.

    Returns:
        Instancia concreta de ROSService.

    Raises:
        ServiceNotConfiguredError: Si el provider no existe.
    """
    from app.core.robot_session import robot_session

    provider = settings.ROS_PROVIDER.lower()

    if provider == "mock":
        return MockROSService()

    if provider == "rclpy":
        runtime = robot_session.refresh_from_settings()
        env_ws = os.environ.get("ROS_WS_SETUP", "").strip()
        ws_candidates = []
        if env_ws:
            ws_candidates.append(os.path.expanduser(env_ws))
        # Opcional: symlink packages/ros_ws → workspace local
        root = Path(__file__).resolve().parents[4]
        ws_candidates.append(str(root / "packages" / "ros_ws" / "install" / "setup.bash"))
        # Convención local fuera del repo (Documents/Proyectos/_local/ros/...)
        ws_candidates.append(
            os.path.expanduser(
                "~/Documents/Proyectos/_local/ros/upnrobot-ros-main/install/setup.bash"
            )
        )
        workspace = next((p for p in ws_candidates if os.path.isfile(p)), None)
        return RclpyROSService(
            domain_id=int(runtime["domain_id"]),
            rmw=str(runtime["rmw"]),
            source_kalman=bool(runtime["source_kalman"]),
            require_battery=bool(runtime["require_battery"]),
            profile_id=str(runtime["profile"]),
            workspace_setup=workspace if runtime["mode"] == "sim" else None,
        )

    raise ServiceNotConfiguredError(
        f"ROS_PROVIDER desconocido: '{provider}'. "
        f"Valores válidos: mock, rclpy"
    )
