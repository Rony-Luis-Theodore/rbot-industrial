"""
=============================================================================
R-Bot — Contrato abstracto: LLMService (Port)
=============================================================================

Propósito:
    Define la interfaz que TODO proveedor LLM debe implementar.
    Sigue el patrón Ports & Adapters (Hexagonal Architecture).

Qué hace:
    - Declara el método process_user_instruction() como contrato único.
    - Garantiza que Mock, OpenAI, Ollama, Gemini, DeepSeek sean intercambiables.

Conexión con el resto:
    - Implementaciones concretas en app/adapters/llm/.
    - ChatOrchestrator depende de LLMService, NO de implementaciones concretas.
    - service_factory.py instancia el adapter según LLM_PROVIDER en .env.

Para el integrante del LLM:
    1. Crear una clase que herede LLMService.
    2. Implementar process_user_instruction().
    3. Registrar el provider en service_factory.py.
    4. Configurar LLM_PROVIDER en .env.

    NO modificar routers ni ChatOrchestrator.
=============================================================================
"""

from abc import ABC, abstractmethod

from app.domain.models.chat import LLMIntent


class LLMService(ABC):
    """
    Interfaz abstracta para servicios de Large Language Models.

    Todo adapter LLM debe implementar esta clase base.
    """

    @abstractmethod
    async def process_user_instruction(self, instruction: str) -> LLMIntent:
        """
        Procesa una instrucción en lenguaje natural del operario.

        Traduce el texto del usuario a una intención estructurada
        que el orquestador puede mapear a acciones ROS2.

        Args:
            instruction: Texto libre del operario (ej: "Muéstrame los topics").

        Returns:
            LLMIntent con la intención detectada, acción ROS equivalente
            y parámetros extraídos.

        Raises:
            LLMProcessingError: Si el proveedor LLM falla o no responde.
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """
        Retorna el identificador del proveedor LLM activo.

        Returns:
            Nombre del proveedor (ej: 'mock', 'openai', 'ollama').
        """
        pass
