"""
Perfiles de robot: R-Bot (Create3), Nexus, Simulación, Auto (Kalman).

Auto lee /var/lib/kalman/robot_name + env.bash cuando hay sesión de laboratorio.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


KALMAN_DIR = Path("/var/lib/kalman")


@dataclass
class RobotProfile:
    id: str
    label: str
    mode: str  # lab | sim | mock
    default_map_id: str
    source_kalman: bool
    domain_id: Optional[int]  # None = heredar de Kalman / settings
    rmw: Optional[str]  # None = heredar
    require_battery: bool
    caps: Dict[str, bool] = field(default_factory=dict)
    peers_hint: str = ""
    sim_hint: str = ""


PROFILES: Dict[str, RobotProfile] = {
    "rbot": RobotProfile(
        id="rbot",
        label="R-Bot",
        mode="lab",
        default_map_id="laboratorio_kalman",
        source_kalman=True,
        domain_id=None,
        rmw=None,
        require_battery=True,
        caps={"dock": True, "undock": True, "teleop": True, "lidar": True},
        peers_hint="robot-create3 / sesión Kalman Create3",
    ),
    "nexus": RobotProfile(
        id="nexus",
        label="Nexus",
        mode="lab",
        default_map_id="laboratorio_kalman",
        source_kalman=True,
        domain_id=None,
        rmw=None,
        require_battery=False,
        caps={"dock": False, "undock": False, "teleop": True, "lidar": True},
        peers_hint="robot-pi5-instance / Maze Runner",
    ),
    "sim": RobotProfile(
        id="sim",
        label="Simulación",
        mode="sim",
        default_map_id="laboratorio_kalman",
        source_kalman=False,
        domain_id=42,
        rmw="rmw_fastrtps_cpp",
        require_battery=False,
        caps={"dock": False, "undock": False, "teleop": True, "lidar": True},
        sim_hint="bash scripts/sim-gazebo.sh laboratorio && bash scripts/sim-nav.sh laboratorio",
        peers_hint="Gazebo local ROS_DOMAIN_ID=42",
    ),
}


def read_kalman_session() -> Dict[str, Any]:
    """Lee identidad de sesión Kalman si existe."""
    info: Dict[str, Any] = {
        "active": False,
        "robot_name": None,
        "laboratory_name": None,
        "ros_domain_id": None,
        "rmw": None,
    }
    if not KALMAN_DIR.is_dir():
        return info

    def _read(name: str) -> Optional[str]:
        p = KALMAN_DIR / name
        try:
            if p.is_file():
                return p.read_text(encoding="utf-8", errors="replace").strip() or None
        except OSError:
            return None
        return None

    robot = _read("robot_name")
    lab = _read("laboratory_name")
    domain_raw = _read("ros_domain_id")
    env_bash = KALMAN_DIR / "env.bash"

    domain = None
    rmw = None
    if domain_raw and domain_raw.isdigit():
        domain = int(domain_raw)
    if env_bash.is_file():
        try:
            text = env_bash.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        m = re.search(r"export\s+ROS_DOMAIN_ID=(\d+)", text)
        if m:
            domain = int(m.group(1))
        m = re.search(r"export\s+RMW_IMPLEMENTATION=(\S+)", text)
        if m:
            rmw = m.group(1).strip().strip("'\"")

    info.update(
        {
            "active": bool(robot or (env_bash.is_file() and domain is not None)),
            "robot_name": robot,
            "laboratory_name": lab,
            "ros_domain_id": domain,
            "rmw": rmw,
        }
    )
    return info


def resolve_profile_id(requested: str) -> str:
    """Normaliza id de perfil; 'auto' → rbot|nexus según Kalman."""
    key = (requested or "auto").strip().lower()
    if key in ("auto", "detect", ""):
        kalman = read_kalman_session()
        name = (kalman.get("robot_name") or "").lower()
        if "nexus" in name:
            return "nexus"
        if "create" in name or "r-bot" in name or "rbot" in name:
            return "rbot"
        # Sin sesión Kalman → sim por defecto para desarrollo local
        if not kalman.get("active"):
            return "sim"
        return "nexus" if kalman.get("ros_domain_id") not in (None, 0) else "rbot"
    if key in PROFILES:
        return key
    raise ValueError(f"Perfil desconocido: {requested}. Usa: auto, rbot, nexus, sim")


def build_runtime_config(
    profile_id: str,
    settings_domain: int = 0,
) -> Dict[str, Any]:
    """
    Config efectiva para el adapter ROS.

    Returns dict con: profile, label, mode, domain_id, rmw, source_kalman,
    default_map_id, require_battery, caps, kalman, sim_hint, peers_hint
    """
    pid = resolve_profile_id(profile_id)
    profile = PROFILES[pid]
    kalman = read_kalman_session()

    if profile.source_kalman and kalman.get("ros_domain_id") is not None:
        domain = int(kalman["ros_domain_id"])
    elif profile.domain_id is not None:
        domain = int(profile.domain_id)
    else:
        domain = int(settings_domain)

    if profile.source_kalman and kalman.get("rmw"):
        rmw = str(kalman["rmw"])
    elif profile.rmw:
        rmw = profile.rmw
    else:
        rmw = os.environ.get("RMW_IMPLEMENTATION", "rmw_cyclonedds_cpp")

    return {
        "profile": pid,
        "label": profile.label,
        "mode": profile.mode,
        "domain_id": domain,
        "rmw": rmw,
        "source_kalman": profile.source_kalman,
        "default_map_id": profile.default_map_id,
        "require_battery": profile.require_battery,
        "caps": dict(profile.caps),
        "kalman": kalman,
        "sim_hint": profile.sim_hint,
        "peers_hint": profile.peers_hint,
        "available_profiles": [
            {"id": p.id, "label": p.label, "mode": p.mode} for p in PROFILES.values()
        ],
    }


def list_profile_summaries() -> List[Dict[str, str]]:
    return [{"id": p.id, "label": p.label, "mode": p.mode} for p in PROFILES.values()]
