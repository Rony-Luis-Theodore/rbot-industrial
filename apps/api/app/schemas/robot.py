"""
=============================================================================
R-Bot — Schemas HTTP: Robot
=============================================================================

Propósito:
    Define los DTOs Pydantic para los endpoints de estado y recursos ROS.

Qué hace:
    - Valida y serializa datos del robot para consumo del frontend.
    - Estructura las respuestas de introspección ROS (topics, nodes, etc.).

Conexión con el resto:
    - api/v1/robot.py retorna estos schemas.
    - RobotStatusService transforma domain/models → schemas.
    - Panel lateral del frontend consume RobotStatusResponse.
=============================================================================
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PositionResponse(BaseModel):
    """Posición del robot en el mapa (respuesta HTTP)."""

    x: float
    y: float
    theta: float = 0.0
    frame_id: str = "map"


class RobotStatusResponse(BaseModel):
    """
    Estado completo del robot para el panel lateral.

    Attributes:
        connection: Estado de conexión con el robot/ROS.
        battery_percent: Nivel de batería (0-100).
        mode: Modo operativo actual.
        position: Coordenadas actuales.
        is_navigating: Si hay navegación activa.
        current_goal: Destino de navegación activo.
        llm_provider: Proveedor LLM configurado.
        ros_provider: Adapter ROS configurado.
        last_updated: Timestamp de última actualización.
    """

    connection: str
    battery_percent: float = Field(ge=0.0, le=100.0)
    mode: str
    position: PositionResponse
    is_navigating: bool = False
    current_goal: Optional[str] = None
    llm_provider: str = "mock"
    ros_provider: str = "mock"
    robot_profile: Optional[str] = None
    robot_label: Optional[str] = None
    robot_mode: Optional[str] = None  # lab | sim
    ros_domain_id: Optional[int] = None
    default_map_id: Optional[str] = None
    laboratory_name: Optional[str] = None
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class RobotSessionResponse(BaseModel):
    """Sesión activa: perfil R-Bot / Nexus / Sim."""

    profile: str
    label: str
    mode: str
    domain_id: int
    rmw: str
    default_map_id: str
    require_battery: bool
    caps: Dict[str, bool] = Field(default_factory=dict)
    kalman: Dict[str, Any] = Field(default_factory=dict)
    peers_hint: str = ""
    sim_hint: str = ""
    available_profiles: List[Dict[str, str]] = Field(default_factory=list)


class RobotSessionRequest(BaseModel):
    """Cambiar perfil activo."""

    profile: str = Field(description="auto | rbot | nexus | sim")


class ROSResourceResponse(BaseModel):
    """
    Lista de recursos ROS (topics, nodes, services, actions).

    Attributes:
        resource_type: Tipo de recurso consultado.
        items: Lista de nombres.
        count: Cantidad total.
    """

    resource_type: str
    items: List[str]
    count: int


class NavigationResultResponse(BaseModel):
    """Resultado de una operación de navegación."""

    success: bool
    message: str
    goal: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class EventLogResponse(BaseModel):
    """Entrada del registro de eventos para el frontend."""

    id: int
    level: str
    message: str
    source: str
    timestamp: datetime

    class Config:
        from_attributes = True


class HealthResponse(BaseModel):
    """Respuesta del endpoint de health check."""

    status: str = "ok"
    app_name: str
    version: str
    llm_provider: str
    ros_provider: str
