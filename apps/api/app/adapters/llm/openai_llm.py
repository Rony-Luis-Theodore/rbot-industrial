"""
=============================================================================
R-Bot — Adapter LLM: OpenAI (STUB — no implementado)
=============================================================================

Propósito:
    Placeholder para integración futura con OpenAI API (GPT-4, GPT-4o, etc.).

Qué hace:
    - Define la estructura de la clase sin lógica real.
    - Documenta los pasos de implementación para el integrante del LLM.

Conexión con el resto:
    - Implementará domain/interfaces/llm_service.py.
    - Se activará con LLM_PROVIDER=openai en .env.
    - Requiere OPENAI_API_KEY en configuración.

Para implementar:
    1. Instalar: pip install openai
    2. Implementar process_user_instruction() con function calling o JSON mode.
    3. Mapear respuesta del modelo a LLMIntent.
    4. Registrar en service_factory.py.
    5. Ver docs/llm-integration.md para prompt engineering y ejemplos.
=============================================================================
"""

from app.core.exceptions import ServiceNotConfiguredError
from app.domain.interfaces.llm_service import LLMService
from app.domain.models.chat import LLMIntent


class OpenAILLMService(LLMService):
    """
    Adapter para OpenAI API — PENDIENTE DE IMPLEMENTACIÓN.

    El integrante del LLM debe completar esta clase.
    """

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        """
        Inicializa el cliente OpenAI.

        Args:
            api_key: Clave API de OpenAI.
            model: Identificador del modelo (gpt-4o, gpt-4-turbo, etc.).
        """
        self._api_key = api_key
        self._model = model
        # TODO: self._client = OpenAI(api_key=api_key)

    async def process_user_instruction(self, instruction: str) -> LLMIntent:
        """
        Procesa instrucción usando OpenAI API.

        IMPLEMENTACIÓN PENDIENTE — ver docs/llm-integration.md
        """
        raise ServiceNotConfiguredError(
            "OpenAILLMService no implementado. "
            "Ver docs/llm-integration.md para instrucciones."
        )

    def get_provider_name(self) -> str:
        return "openai"
