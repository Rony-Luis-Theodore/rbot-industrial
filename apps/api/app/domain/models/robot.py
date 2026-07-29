"""
=============================================================================
R-Bot — Modelos de dominio: Robot
=============================================================================

Propósito:
    Define entidades internas que representan el estado y capacidades
    del robot R-Bot en el dominio de negocio.

Qué hace:
    - RobotPosition: coordenadas y orientación en el mapa.
    - RobotStatus: snapshot completo del estado operativo.
    - NavigationGoal: destino de navegación autónoma.

Conexión con el resto:
    - ROSService (mock o rclpy) produce y consume estos modelos.
    - RobotStatusService los transforma a schemas HTTP para el frontend.
    - Panel lateral del frontend muestra RobotStatus.

Escalabilidad:
    - Agregar robot_id cuando se soporte flota de robots.
    - Agregar campos de telemetría (velocidad, odometría) según necesidad.
=============================================================================
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class RobotPosition:
    """
    Posición del robot en el frame del mapa.

    Attributes:
        x: Coordenada X en metros.
        y: Coordenada Y en metros.
        theta: Orientación en radianes.
        frame_id: Frame de referencia ROS (ej: 'map').
    """

    x: float
    y: float
    theta: float = 0.0
    frame_id: str = "map"


@dataclass
class NavigationGoal:
    """
    Objetivo de navegación autónoma.

    Attributes:
        name: Nombre simbólico del destino (ej: 'Estación A', 'Base').
        position: Coordenadas objetivo (opcional si se usa nombre simbólico).
        description: Descripción legible para el operario.
    """

    name: str
    position: Optional[RobotPosition] = None
    description: str = ""


@dataclass
class RobotStatus:
    """
    Estado operativo completo del robot en un instante dado.

    Attributes:
        connection: Estado de conexión ('connected', 'disconnected', 'degraded').
        battery_percent: Nivel de batería (0-100).
        mode: Modo operativo actual ('idle', 'navigating', etc.).
        position: Posición actual en el mapa.
        is_navigating: True si hay una navegación activa.
        current_goal: Destino activo de navegación (si aplica).
        last_updated: Timestamp de la última actualización.
    """

    connection: str
    battery_percent: float
    mode: str
    position: RobotPosition
    is_navigating: bool = False
    current_goal: Optional[str] = None
    last_updated: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ROSTopicInfo:
    """Información de un topic ROS2."""

    name: str
    type: str


@dataclass
class ROSNodeInfo:
    """Información de un nodo ROS2 activo."""

    name: str
    namespace: str = ""


@dataclass
class ROSServiceInfo:
    """Información de un servicio ROS2 disponible."""

    name: str
    type: str


@dataclass
class ROSActionInfo:
    """Información de una action ROS2 disponible."""

    name: str
    type: str


@dataclass
class ROSResourceList:
    """
    Contenedor genérico para listas de recursos ROS.

    Attributes:
        resource_type: Tipo de recurso ('topics', 'nodes', 'services', 'actions').
        items: Lista de nombres o objetos de información.
        count: Cantidad total de elementos.
    """

    resource_type: str
    items: List[str]
    count: int = 0

    def __post_init__(self):
        if self.count == 0:
            self.count = len(self.items)
