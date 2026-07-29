"""
=============================================================================
R-Bot — Modelos de dominio: Eventos
=============================================================================

Propósito:
    Define la entidad EventLogEntry para el registro de eventos del sistema.

Qué hace:
    - Representa una entrada individual en el log de eventos visible
      en el panel lateral del frontend.

Conexión con el resto:
    - EventLogger crea y almacena instancias de EventLogEntry.
    - GET /api/v1/robot/events devuelve estas entradas al frontend.
    - Futura integración con BD persistirá la misma estructura.

Escalabilidad:
    - Agregar campos robot_id, user_id cuando haya multi-robot y auth.
=============================================================================
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class EventLogEntry:
    """
    Entrada individual en el registro de eventos del sistema.

    Attributes:
        id: Identificador único incremental del evento.
        level: Severidad ('info', 'warning', 'error', 'success').
        message: Descripción legible del evento.
        source: Módulo que generó el evento (ej: 'chat', 'ros', 'system').
        timestamp: Momento en que ocurrió el evento.
        metadata: Datos adicionales estructurados para diagnóstico.
    """

    id: int
    level: str
    message: str
    source: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
