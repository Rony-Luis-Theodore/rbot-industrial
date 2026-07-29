"""
=============================================================================
R-Bot — Adapter LLM: Gemini (STUB — no implementado)
=============================================================================

Propósito:
    Placeholder para integración futura con Google Gemini API.

Conexión con el resto:
    - LLM_PROVIDER=gemini en .env
    - GEMINI_API_KEY en configuración
    - Ver docs/llm-integration.md
=============================================================================
"""

from app.core.exceptions import ServiceNotConfiguredError
from app.domain.interfaces.llm_service import LLMService
from app.domain.models.chat import LLMIntent


class GeminiLLMService(LLMService):
    """Adapter para Google Gemini — PENDIENTE DE IMPLEMENTACIÓN."""

    def __init__(self, api_key: str, model: str = "gemini-pro"):
        self._api_key = api_key
        self._model = model

    async def process_user_instruction(self, instruction: str) -> LLMIntent:
        raise ServiceNotConfiguredError(
            "GeminiLLMService no implementado. Ver docs/llm-integration.md."
        )

    def get_provider_name(self) -> str:
        return "gemini"
