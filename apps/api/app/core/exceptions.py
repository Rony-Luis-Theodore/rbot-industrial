"""
=============================================================================
R-Bot — Excepciones de dominio personalizadas
=============================================================================

Propósito:
    Define excepciones semánticas del dominio de negocio, separadas de
    excepciones HTTP de FastAPI.

Qué hace:
    - Permite capturar errores de negocio en services y convertirlos
      a respuestas HTTP apropiadas en los routers o exception handlers.

Conexión con el resto:
    - ChatOrchestrator lanza LLMProcessingError si el LLM falla.
    - ROSService adapters lanzan ROSConnectionError si ROS no responde.
    - main.py puede registrar handlers globales para estas excepciones.

Escalabilidad:
    - Agregar nuevas excepciones aquí cuando se incorporen voz, BD, auth, etc.
=============================================================================
"""


class RBotException(Exception):
    """
    Excepción base de todos los errores del dominio R-Bot.

    Attributes:
        message: Descripción legible del error.
        code: Código interno para logging y diagnóstico.
    """

    def __init__(self, message: str, code: str = "RBOT_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class LLMProcessingError(RBotException):
    """
    Error al procesar una instrucción con el servicio LLM.

    Se lanza cuando el proveedor LLM no está disponible o devuelve
    una respuesta inválida.
    """

    def __init__(self, message: str = "Error al procesar instrucción con LLM"):
        super().__init__(message, code="LLM_ERROR")


class ROSConnectionError(RBotException):
    """
    Error de conexión o comunicación con ROS2.

    Se lanza cuando el adapter ROS no puede ejecutar una acción
    (nodo caído, topic no disponible, etc.).
    """

    def __init__(self, message: str = "Error de conexión con ROS2"):
        super().__init__(message, code="ROS_ERROR")


class ServiceNotConfiguredError(RBotException):
    """
    Error cuando se solicita un proveedor no configurado o no implementado.

    Por ejemplo: LLM_PROVIDER=openai sin OPENAI_API_KEY configurada.
    """

    def __init__(self, message: str = "Servicio no configurado correctamente"):
        super().__init__(message, code="CONFIG_ERROR")
