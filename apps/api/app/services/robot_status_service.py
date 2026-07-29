"""
Servicio de estado del robot — enriquece con perfil de sesión.
"""

from app.core.config import settings
from app.core.robot_session import robot_session
from app.domain.interfaces.ros_service import ROSService
from app.schemas.robot import PositionResponse, RobotStatusResponse


class RobotStatusService:
    def __init__(self, ros_service: ROSService):
        self._ros = ros_service

    async def get_status(self) -> RobotStatusResponse:
        status = await self._ros.get_status()
        runtime = robot_session.runtime
        kalman = runtime.get("kalman") or {}

        return RobotStatusResponse(
            connection=status.connection,
            battery_percent=status.battery_percent,
            mode=status.mode,
            position=PositionResponse(
                x=status.position.x,
                y=status.position.y,
                theta=status.position.theta,
                frame_id=status.position.frame_id,
            ),
            is_navigating=status.is_navigating,
            current_goal=status.current_goal,
            llm_provider=settings.LLM_PROVIDER,
            ros_provider=self._ros.get_provider_name(),
            robot_profile=runtime.get("profile"),
            robot_label=runtime.get("label"),
            robot_mode=runtime.get("mode"),
            ros_domain_id=runtime.get("domain_id"),
            default_map_id=runtime.get("default_map_id"),
            laboratory_name=kalman.get("laboratory_name"),
            last_updated=status.last_updated,
        )
