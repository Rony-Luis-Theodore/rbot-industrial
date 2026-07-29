"""
=============================================================================
R-Bot — Utilidades: Envelope de respuestas API
=============================================================================

Propósito:
    Proporciona un formato estándar opcional para respuestas API,
    facilitando manejo uniforme de éxito y error en el frontend.

Qué hace:
    - APIResponse: wrapper genérico con data, success, message.
    - Helpers para construir respuestas consistentes.

Conexión con el resto:
    - Routers pueden usar estos helpers para respuestas no-Pydantic.
    - Frontend api/client.js puede interpretar el envelope si se adopta.

Nota:
    Los endpoints actuales retornan schemas Pydantic directamente.
    Este módulo queda preparado para endpoints futuros que requieran
    envelope uniforme (WebSockets, streaming, batch operations).
=============================================================================
"""

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """
    Envelope genérico de respuesta API.

    Attributes:
        success: True si la operación fue exitosa.
        message: Mensaje descriptivo opcional.
        data: Payload de datos tipado.
    """

    success: bool = True
    message: Optional[str] = None
    data: Optional[T] = None


def success_response(data: Any, message: str = "OK") -> dict:
    """
    Construye un diccionario de respuesta exitosa.

    Args:
        data: Datos a incluir en el payload.
        message: Mensaje descriptivo.

    Returns:
        Diccionario con formato envelope estándar.
    """
    return {"success": True, "message": message, "data": data}


def error_response(message: str, code: str = "ERROR") -> dict:
    """
    Construye un diccionario de respuesta de error.

    Args:
        message: Descripción del error.
        code: Código interno de error.

    Returns:
        Diccionario con formato envelope de error.
    """
    return {"success": False, "message": message, "code": code, "data": None}
