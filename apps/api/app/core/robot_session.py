"""
Estado de sesión de robot (perfil activo). Permite cambiar R-Bot / Nexus / Sim
en caliente sin reiniciar uvicorn.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.robot_profiles import build_runtime_config, resolve_profile_id


class RobotSession:
    def __init__(self) -> None:
        raw = getattr(settings, "ROBOT_PROFILE", "auto") or "auto"
        self._requested = raw
        self._runtime: Dict[str, Any] = build_runtime_config(
            raw, settings_domain=settings.ROS_DOMAIN_ID
        )

    @property
    def requested(self) -> str:
        return self._requested

    @property
    def runtime(self) -> Dict[str, Any]:
        return self._runtime

    def refresh_from_settings(self) -> Dict[str, Any]:
        self._runtime = build_runtime_config(
            self._requested, settings_domain=settings.ROS_DOMAIN_ID
        )
        return self._runtime

    def set_profile(self, profile_id: str) -> Dict[str, Any]:
        # Valida
        resolve_profile_id(profile_id)
        self._requested = profile_id
        self._runtime = build_runtime_config(
            profile_id, settings_domain=settings.ROS_DOMAIN_ID
        )
        return self._runtime


robot_session = RobotSession()
