"""
=============================================================================
R-Bot — Servicio: Registro de Eventos (EventLogger)
=============================================================================

Propósito:
    Centraliza el registro de eventos del sistema en memoria.
    Alimenta el panel de "Registro de eventos" del frontend.

Qué hace:
    - Almacena EventLogEntry con ID incremental.
    - Limita tamaño en memoria (MAX_EVENTS_IN_MEMORY).
    - Expone métodos para consultar y registrar eventos.

Conexión con el resto:
    - ChatOrchestrator registra eventos de conversación.
    - Routers ROS registran eventos de operaciones.
    - GET /api/v1/robot/events consulta este servicio.

Escalabilidad:
    - Reemplazar almacenamiento en memoria por repositorio BD.
    - Agregar suscripción WebSocket para push en tiempo real.
    - Agregar filtrado por nivel, fuente, robot_id.
=============================================================================
"""

from typing import List, Optional

from app.core.constants import EVENT_LEVEL_INFO, MAX_EVENTS_IN_MEMORY
from app.domain.models.events import EventLogEntry


class EventLogger:
    """
    Servicio singleton de registro de eventos en memoria.

    Thread-safe suficiente para desarrollo; en producción considerar
    asyncio.Lock o persistencia en BD.
    """

    def __init__(self):
        """Inicializa buffer vacío de eventos."""
        self._events: List[EventLogEntry] = []
        self._counter: int = 0

    def log(
        self,
        message: str,
        level: str = EVENT_LEVEL_INFO,
        source: str = "system",
        metadata: Optional[dict] = None,
    ) -> EventLogEntry:
        """
        Registra un nuevo evento en el buffer.

        Args:
            message: Descripción legible del evento.
            level: Severidad (info, warning, error, success).
            source: Módulo origen (chat, ros, system, api).
            metadata: Datos adicionales opcionales.

        Returns:
            EventLogEntry creado con ID asignado.
        """
        self._counter += 1
        entry = EventLogEntry(
            id=self._counter,
            level=level,
            message=message,
            source=source,
            metadata=metadata or {},
        )
        self._events.append(entry)

        # Mantener límite de eventos en memoria (FIFO)
        if len(self._events) > MAX_EVENTS_IN_MEMORY:
            self._events = self._events[-MAX_EVENTS_IN_MEMORY:]

        return entry

    def get_events(self, limit: int = 50) -> List[EventLogEntry]:
        """
        Retorna los eventos más recientes.

        Args:
            limit: Cantidad máxima de eventos a retornar.

        Returns:
            Lista de EventLogEntry ordenada del más reciente al más antiguo.
        """
        return list(reversed(self._events[-limit:]))

    def clear(self) -> None:
        """Limpia todos los eventos (útil para testing)."""
        self._events.clear()
        self._counter = 0


# Singleton global — compartido entre requests vía deps.py
event_logger = EventLogger()
