"""
=============================================================================
R-Bot — Endpoints: Robot (GET /api/v1/robot/*)
=============================================================================

Propósito:
    Expone endpoints REST para consultar estado y recursos ROS del robot.
    Alimenta el panel lateral del frontend.

Endpoints:
    GET /robot/status    → Estado operativo completo
    GET /robot/topics    → Lista de topics ROS2
    GET /robot/nodes     → Lista de nodos ROS2
    GET /robot/services  → Lista de servicios ROS2
    GET /robot/actions   → Lista de actions ROS2
    GET /robot/events    → Registro de eventos del sistema
    GET /health          → Health check de la API

Conexión con el resto:
    - Frontend js/api/robot.js consume estos endpoints.
    - Delega a ROSService y RobotStatusService (sin lógica en router).

Escalabilidad:
    - Futuro: POST /robot/navigate, POST /robot/cancel
    - Futuro: GET /robot/map, GET /robot/lidar (streaming)
    - Futuro: WebSocket /ws/telemetry para datos en tiempo real
=============================================================================
"""

from typing import Any, Dict, List, Optional

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.api.deps import (
    get_event_logger,
    get_robot_status_service,
    get_ros_service,
    reset_ros_service,
)
from app.core.robot_session import robot_session
from app.domain.interfaces.ros_service import ROSService
from app.schemas.robot import (
    EventLogResponse,
    ROSResourceResponse,
    RobotSessionRequest,
    RobotSessionResponse,
    RobotStatusResponse,
)
from app.services.event_logger import EventLogger
from app.services.map_service import get_map_meta, list_maps, render_map_png
from app.services.robot_status_service import RobotStatusService

router = APIRouter()


class EmergencyStopResponse(BaseModel):
    """Respuesta de parada de emergencia."""

    success: bool
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


def _session_response() -> RobotSessionResponse:
    r = robot_session.runtime
    return RobotSessionResponse(
        profile=r["profile"],
        label=r["label"],
        mode=r["mode"],
        domain_id=int(r["domain_id"]),
        rmw=str(r["rmw"]),
        default_map_id=str(r["default_map_id"]),
        require_battery=bool(r["require_battery"]),
        caps=dict(r.get("caps") or {}),
        kalman=dict(r.get("kalman") or {}),
        peers_hint=str(r.get("peers_hint") or ""),
        sim_hint=str(r.get("sim_hint") or ""),
        available_profiles=list(r.get("available_profiles") or []),
    )


@router.get(
    "/session",
    response_model=RobotSessionResponse,
    summary="Sesión robot activa (R-Bot / Nexus / Sim)",
)
async def get_robot_session() -> RobotSessionResponse:
    robot_session.refresh_from_settings()
    return _session_response()


@router.post(
    "/session",
    response_model=RobotSessionResponse,
    summary="Cambiar perfil de robot",
)
async def set_robot_session(body: RobotSessionRequest) -> RobotSessionResponse:
    try:
        robot_session.set_profile(body.profile)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ros = reset_ros_service()
    runtime = robot_session.runtime
    # No bloquear la HMI: discovery/LiDAR en background
    if runtime.get("mode") == "lab":

        async def _warm() -> None:
            try:
                if hasattr(ros, "refresh_discovery"):
                    await ros.refresh_discovery(force=True)
                if hasattr(ros, "ensure_lidar_powered"):
                    await ros.ensure_lidar_powered()
            except Exception:  # noqa: BLE001
                pass

        asyncio.create_task(_warm())
    return _session_response()


@router.get(
    "/status",
    response_model=RobotStatusResponse,
    summary="Estado del robot",
    description="Retorna conexión, batería, modo, posición y metadatos del sistema.",
)
async def get_robot_status(
    status_service: RobotStatusService = Depends(get_robot_status_service),
) -> RobotStatusResponse:
    """Consulta estado operativo completo del robot."""
    return await status_service.get_status()


@router.get(
    "/topics",
    response_model=ROSResourceResponse,
    summary="Topics ROS2 activos",
    description="Equivalente a: ros2 topic list",
)
async def get_topics(
    ros: ROSService = Depends(get_ros_service),
) -> ROSResourceResponse:
    """Lista topics ROS2 activos."""
    result = await ros.get_topics()
    return ROSResourceResponse(
        resource_type=result.resource_type,
        items=result.items,
        count=result.count,
    )


@router.get(
    "/nodes",
    response_model=ROSResourceResponse,
    summary="Nodos ROS2 activos",
    description="Equivalente a: ros2 node list",
)
async def get_nodes(
    ros: ROSService = Depends(get_ros_service),
) -> ROSResourceResponse:
    """Lista nodos ROS2 activos."""
    result = await ros.get_nodes()
    return ROSResourceResponse(
        resource_type=result.resource_type,
        items=result.items,
        count=result.count,
    )


@router.get(
    "/services",
    response_model=ROSResourceResponse,
    summary="Servicios ROS2 disponibles",
    description="Equivalente a: ros2 service list",
)
async def get_services(
    ros: ROSService = Depends(get_ros_service),
) -> ROSResourceResponse:
    """Lista servicios ROS2 disponibles."""
    result = await ros.get_services()
    return ROSResourceResponse(
        resource_type=result.resource_type,
        items=result.items,
        count=result.count,
    )


@router.get(
    "/actions",
    response_model=ROSResourceResponse,
    summary="Actions ROS2 disponibles",
    description="Equivalente a: ros2 action list",
)
async def get_actions(
    ros: ROSService = Depends(get_ros_service),
) -> ROSResourceResponse:
    """Lista actions ROS2 disponibles."""
    result = await ros.get_actions()
    return ROSResourceResponse(
        resource_type=result.resource_type,
        items=result.items,
        count=result.count,
    )


@router.get(
    "/events",
    response_model=List[EventLogResponse],
    summary="Registro de eventos",
    description="Retorna los eventos más recientes del sistema.",
)
async def get_events(
    limit: int = 50,
    logger: EventLogger = Depends(get_event_logger),
) -> List[EventLogResponse]:
    """
    Consulta registro de eventos del sistema.

    Args:
        limit: Cantidad máxima de eventos (default 50).
    """
    events = logger.get_events(limit=limit)
    return [
        EventLogResponse(
            id=e.id,
            level=e.level,
            message=e.message,
            source=e.source,
            timestamp=e.timestamp,
        )
        for e in events
    ]


@router.post(
    "/emergency_stop",
    response_model=EmergencyStopResponse,
    summary="Parada de emergencia",
    description="Publica /cmd_vel = 0 y cancela navegación activa.",
)
async def emergency_stop(
    ros: ROSService = Depends(get_ros_service),
    logger: EventLogger = Depends(get_event_logger),
) -> EmergencyStopResponse:
    """E-STOP operativo para la HMI industrial."""
    result = await ros.cancel_navigation()
    logger.log(
        "E-STOP activado desde HMI",
        level="warning",
        source="hmi",
        metadata=result if isinstance(result, dict) else {},
    )
    return EmergencyStopResponse(
        success=bool(result.get("success", True)),
        message=result.get("message", "Parada enviada"),
        details=result.get("details", {}),
    )


class TeleopRequest(BaseModel):
    """Comando de teleoperación manual."""

    linear_x: float = Field(0.0, ge=-0.3, le=0.3, description="m/s adelante(+)/atrás(-)")
    angular_z: float = Field(0.0, ge=-1.5, le=1.5, description="rad/s giro")


class TeleopResponse(BaseModel):
    """Respuesta de teleop."""

    success: bool
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


@router.post(
    "/teleop",
    response_model=TeleopResponse,
    summary="Teleoperación manual (/cmd_vel)",
    description="El operario toma control. Reenviar ~10 Hz mientras mantiene el mando.",
)
async def teleop(
    body: TeleopRequest,
    ros: ROSService = Depends(get_ros_service),
) -> TeleopResponse:
    """Publica Twist hacia el robot."""
    result = await ros.publish_cmd_vel(body.linear_x, body.angular_z)
    return TeleopResponse(
        success=bool(result.get("success", False)),
        message=result.get("message", ""),
        details=result.get("details", {}),
    )


@router.get(
    "/scan",
    summary="LiDAR LaserScan (/scan) en vivo",
    description="Devuelve un scan compactado para dibujar en la HMI.",
)
async def get_scan(
    max_points: int = 360,
    ros: ROSService = Depends(get_ros_service),
) -> Dict[str, Any]:
    """Lee /scan del robot (o mock)."""
    try:
        return await ros.get_laser_scan(max_points=max_points)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get(
    "/maps",
    summary="Listar mapas OccupancyGrid guardados",
)
async def get_maps() -> List[Dict[str, Any]]:
    """Mapas YAML/PGM del workspace Kalman."""
    return list_maps()


@router.get(
    "/maps/{map_id}",
    summary="Metadatos de un mapa",
)
async def get_map(map_id: str) -> Dict[str, Any]:
    meta = get_map_meta(map_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Mapa '{map_id}' no encontrado")
    from app.services.lab_zones import zones_for_map

    return {
        "id": meta.get("id"),
        "resolution": meta.get("resolution"),
        "origin": meta.get("origin"),
        "image_url": f"/api/v1/robot/maps/{map_id}/image",
        "zones": zones_for_map(map_id),
    }


class HmiDebugPayload(BaseModel):
    trail_odom: List[Dict[str, float]] = Field(default_factory=list)
    align: Dict[str, Any] = Field(default_factory=dict)
    hint: str = ""
    perimeter_fitted: bool = False
    odom: Optional[Dict[str, float]] = None


@router.post(
    "/hmi_debug",
    summary="Snapshot trazo/align desde la HMI (diagnóstico)",
)
async def post_hmi_debug(body: HmiDebugPayload) -> Dict[str, Any]:
    from app.services.hmi_state import set_hmi_debug

    return set_hmi_debug(
        trail_odom=body.trail_odom,
        align=body.align,
        hint=body.hint,
        perimeter_fitted=body.perimeter_fitted,
        odom=body.odom,
    )


@router.get(
    "/hmi_debug",
    summary="Leer último snapshot HMI",
)
async def get_hmi_debug() -> Dict[str, Any]:
    from app.services.hmi_state import get_hmi_debug as _get

    return _get()


class TrackPerimeterPayload(BaseModel):
    trail_odom: List[Dict[str, float]] = Field(default_factory=list)
    align: Dict[str, Any] = Field(default_factory=dict)
    closed_odom: Optional[List[Dict[str, float]]] = None
    hint: str = ""


@router.post(
    "/lab_traces/track_perimeter",
    summary="Guardar perímetro de pista (cierra a rectángulo si falta cierre)",
)
async def post_track_perimeter(body: TrackPerimeterPayload) -> Dict[str, Any]:
    from app.services.lab_traces import save_track_perimeter

    try:
        return save_track_perimeter(
            trail_odom=body.trail_odom,
            align=body.align,
            closed_odom=body.closed_odom,
            hint=body.hint,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/lab_traces/track_perimeter",
    summary="Leer perímetro rectangular guardado",
)
async def get_track_perimeter() -> Dict[str, Any]:
    from app.services.lab_traces import load_track_perimeter

    data = load_track_perimeter()
    if not data:
        raise HTTPException(status_code=404, detail="Aún no hay perímetro guardado")
    return data


@router.get(
    "/lab_traces",
    summary="Geometría lab: perímetro + 4 obstáculos (overlay / planner)",
)
async def get_lab_traces() -> Dict[str, Any]:
    from app.services.lab_traces import get_lab_geometry

    return get_lab_geometry()


@router.post(
    "/lab_traces/sync_obstacles",
    summary="Anclar 4 obstáculos a blobs Occupancy",
)
async def post_sync_obstacles() -> Dict[str, Any]:
    from app.services.lab_traces import load_track_perimeter, sync_obstacles_from_occupancy

    track = load_track_perimeter() or {}
    return sync_obstacles_from_occupancy(align=track.get("align_canonical"))


class AnchorTranslationPayload(BaseModel):
    tx: float
    ty: float


@router.post(
    "/lab_traces/anchor_translation",
    summary="Re-anclar tx/ty sin mover el perímetro Occupancy",
)
async def post_anchor_translation(body: AnchorTranslationPayload) -> Dict[str, Any]:
    from app.services.hmi_state import _remember_good
    from app.services.lab_traces import update_align_translation

    try:
        # compat: si solo mandan t, conservar yaw actual
        from app.services.lab_traces import load_track_perimeter

        track = load_track_perimeter() or {}
        yaw = float((track.get("align_canonical") or {}).get("yaw") or 0.0)
        from app.services.lab_traces import update_live_align

        out = update_live_align(yaw, body.tx, body.ty)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _remember_good({**out["align"], "ready": True, "source": "perimeter"})
    return out


class LiveAlignPayload(BaseModel):
    yaw: float
    tx: float
    ty: float


@router.post(
    "/lab_traces/live_align",
    summary="SE(2) vivo del robot; overlays Occupancy intactos",
)
async def post_live_align(body: LiveAlignPayload) -> Dict[str, Any]:
    from app.services.hmi_state import _remember_good
    from app.services.lab_map_service import set_session_align

    try:
        out = set_session_align(body.yaw, body.tx, body.ty, source="lidar_in_track")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _remember_good({**out["align"], "ready": True, "source": "lidar_in_track"})
    return out


@router.get(
    "/lab/geometry",
    summary="Geometría Occupancy fija (cyan + obstáculos); sin SE2 de sesión",
)
async def get_lab_geometry_endpoint() -> Dict[str, Any]:
    from app.services.lab_map_service import get_lab_geometry_v1

    data = get_lab_geometry_v1()
    return {
        "version": data["geometry"]["version"],
        "geometry": data["geometry"],
    }


@router.get(
    "/lab/session/align",
    summary="SE(2) vivo de la sesión actual",
)
async def get_lab_session_align() -> Dict[str, Any]:
    from app.services.lab_map_service import get_session_align

    align = get_session_align()
    if not align:
        raise HTTPException(status_code=404, detail="Sin live_align de sesión")
    return {"align": align}


@router.post(
    "/lab/session/align",
    summary="Actualizar SE(2) vivo; no muta geometría Occupancy",
)
async def post_lab_session_align(body: LiveAlignPayload) -> Dict[str, Any]:
    from app.services.hmi_state import _remember_good
    from app.services.lab_map_service import set_session_align

    try:
        out = set_session_align(body.yaw, body.tx, body.ty, source="lidar_in_track")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _remember_good({**out["align"], "ready": True, "source": "lidar_in_track"})
    return out


@router.get(
    "/maps/{map_id}/image",
    summary="Imagen PNG del mapa OccupancyGrid",
    response_class=Response,
)
async def get_map_image(map_id: str) -> Response:
    rendered = render_map_png(map_id)
    if not rendered:
        raise HTTPException(status_code=404, detail=f"Imagen de mapa '{map_id}' no disponible")
    png_bytes, _meta = rendered
    return Response(content=png_bytes, media_type="image/png")
