"""
=============================================================================
R-Bot — Configuración global de la aplicación
=============================================================================

Propósito:
    Centraliza la configuración del sistema mediante variables de entorno.
    Utiliza Pydantic Settings para validación y tipado automático.

Qué hace:
    - Lee variables desde `.env` y el entorno del sistema operativo.
    - Expone un singleton `settings` accesible desde cualquier módulo.

Conexión con el resto:
    - `main.py` usa settings para host, puerto y CORS.
    - `service_factory.py` usa LLM_PROVIDER y ROS_PROVIDER para elegir adapters.
    - Futuros adapters (OpenAI, rclpy) leerán sus API keys desde aquí.

Uso:
    from app.core.config import settings
    print(settings.LLM_PROVIDER)
=============================================================================
"""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Modelo de configuración validado por Pydantic.

    Cada atributo corresponde a una variable de entorno.
    Los valores por defecto permiten ejecutar el proyecto sin `.env`.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # --- Metadatos de la aplicación ---
    APP_NAME: str = "Sonar"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # --- Servidor HTTP ---
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # --- Selección de proveedores (mock | openai | ollama | gemini | deepseek | rclpy) ---
    LLM_PROVIDER: str = "mock"
    ROS_PROVIDER: str = "mock"

    # --- CORS: orígenes permitidos (cadena separada por comas) ---
    CORS_ORIGINS: str = "http://localhost:5500,http://127.0.0.1:5500,http://localhost:8000"

    # --- Claves API (vacías hasta conectar proveedores reales) ---
    OPENAI_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:1.5b"
    GEMINI_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""

    # --- ROS2 / robot ---
    # ROBOT_PROFILE: auto | rbot | nexus | sim
    ROBOT_PROFILE: str = "auto"
    ROS_DOMAIN_ID: int = 0
    # Fallback si el perfil no hereda de Kalman
    ROS_RMW: str = "rmw_fastrtps_cpp"

    # --- Voz (faster-whisper / openai-whisper) ---
    ML_WHISPER_MODEL: str = "base"

    @property
    def cors_origins_list(self) -> List[str]:
        """
        Convierte CORS_ORIGINS de cadena CSV a lista para FastAPI.

        Returns:
            Lista de URLs de origen permitidas.
        """
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """
    Factory cacheada que retorna la instancia única de Settings.

    `@lru_cache` garantiza que la configuración se lea una sola vez
    durante el ciclo de vida del proceso.

    Returns:
        Instancia singleton de Settings.
    """
    return Settings()


# Instancia global de configuración — importar directamente en otros módulos
settings = get_settings()
