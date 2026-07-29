"""Servicio API del stack lab Occupancy (geometry fija + session SE2)."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Prefer packaged lab_map
_LAB_MAP_SRC = (
    Path(__file__).resolve().parents[4] / "packages" / "lab_map" / "src"
)
if _LAB_MAP_SRC.is_dir() and str(_LAB_MAP_SRC) not in sys.path:
    sys.path.insert(0, str(_LAB_MAP_SRC))

from lab_map.constants import PERIMETER_YAW_META, SESSION_VERSION  # noqa: E402
from lab_map.geometry import frozen_geometry  # noqa: E402
from lab_map.se2 import normalize_session_align  # noqa: E402

from app.services.lab_traces import TRACK_PERIMETER_PATH, load_track_perimeter


def get_lab_geometry_v1() -> Dict[str, Any]:
    """Geometría Occupancy read-only + session align separado."""
    geom = frozen_geometry()
    track = load_track_perimeter() or {}
    live = normalize_session_align(track.get("live_align") or track.get("align_canonical"))
    return {
        "geometry": geom,
        "session": {
            "version": SESSION_VERSION,
            "align": live,
        },
        # Compat HMI vieja (viewer / lab_traces consumers)
        "track": {
            "trail_map_closed": geom["trail_map_closed"],
            "map_box": geom["map_box"],
            "map_center": geom["map_center"],
            "perimeter_yaw": geom["perimeter_yaw_meta"],
            "live_align": live,
            "align_canonical": live,
        },
        "obstacles": geom["obstacles"],
        "obstacle_boxes": geom["obstacle_boxes"],
        "align": live,
    }


def get_session_align() -> Optional[Dict[str, Any]]:
    track = load_track_perimeter() or {}
    return normalize_session_align(track.get("live_align") or track.get("align_canonical"))


def set_session_align(yaw: float, tx: float, ty: float, *, source: str = "lidar_in_track") -> Dict[str, Any]:
    """Escribe SOLO live_align. No clampea yaw. No toca trail_map_closed."""
    track = load_track_perimeter()
    if not track:
        raise ValueError("No hay perímetro guardado")
    closed_before = json.dumps(track.get("trail_map_closed") or [])
    align = {
        "yaw": float(yaw),
        "tx": float(tx),
        "ty": float(ty),
        "sx": 1.0,
        "sy": 1.0,
        "ready": True,
        "source": source,
        "note": "session SE2 ψ=θmap−θodom; overlays Occupancy unchanged",
    }
    # Normalizar yaw a [-π, π]
    align["yaw"] = math.atan2(math.sin(align["yaw"]), math.cos(align["yaw"]))
    track.setdefault("perimeter_yaw", PERIMETER_YAW_META)
    track.setdefault("geometry_version", "lab-geometry-v1")
    track["live_align"] = dict(align)
    # Compat navegación: align_canonical = sesión viva (no geometría)
    track["align_canonical"] = dict(align)
    track["hint"] = "geometry frozen; live_align is session SE2 only"
    TRACK_PERIMETER_PATH.write_text(
        json.dumps(track, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    closed_after = json.dumps(track.get("trail_map_closed") or [])
    if closed_before != closed_after:
        raise RuntimeError("BUG: trail_map_closed mutated by set_session_align")
    return {"ok": True, "align": align}
