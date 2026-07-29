"""
Dependencias FastAPI — soporta recrear ROSService al cambiar perfil.
"""

from functools import lru_cache
from typing import Optional

from app.domain.interfaces.llm_service import LLMService
from app.domain.interfaces.ros_service import ROSService
from app.factories.service_factory import create_llm_service, create_ros_service
from app.services.chat_orchestrator import ChatOrchestrator
from app.services.event_logger import EventLogger, event_logger
from app.services.robot_status_service import RobotStatusService

_ros_service: Optional[ROSService] = None
_llm_service: Optional[LLMService] = None


@lru_cache
def get_llm_service() -> LLMService:
    return create_llm_service()


def get_ros_service() -> ROSService:
    """Singleton mutable: se recrea al cambiar ROBOT_PROFILE en sesión."""
    global _ros_service
    if _ros_service is None:
        _ros_service = create_ros_service()
    return _ros_service


def reset_ros_service() -> ROSService:
    """Recrea el adapter ROS (tras POST /robot/session)."""
    global _ros_service
    _ros_service = create_ros_service()
    return _ros_service


def get_event_logger() -> EventLogger:
    return event_logger


def get_chat_orchestrator() -> ChatOrchestrator:
    return ChatOrchestrator(
        llm_service=get_llm_service(),
        ros_service=get_ros_service(),
        event_logger=get_event_logger(),
    )


def get_robot_status_service() -> RobotStatusService:
    return RobotStatusService(ros_service=get_ros_service())
