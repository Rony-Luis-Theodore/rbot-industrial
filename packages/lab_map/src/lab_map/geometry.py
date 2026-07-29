"""Geometría Occupancy fija: perímetro cyan + cajas naranja. Nunca mutar con SE2 vivo."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .constants import GEOMETRY_VERSION, PERIMETER_YAW_META

_ASSETS = Path(__file__).resolve().parents[2] / "assets"
_DEFAULT_TRACES = (
    Path(__file__).resolve().parents[4]
    / "apps"
    / "api"
    / "app"
    / "services"
    / "lab_obstacle_traces"
)


def _traces_dir(override: Optional[Path] = None) -> Path:
    if override is not None:
        return override
    if (_ASSETS / "track_perimeter.json").is_file():
        return _ASSETS
    return _DEFAULT_TRACES


def load_track(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or (_traces_dir() / "track_perimeter.json")
    return json.loads(p.read_text(encoding="utf-8"))


def load_obstacles(directory: Optional[Path] = None) -> List[Dict[str, Any]]:
    d = directory or _traces_dir()
    out: List[Dict[str, Any]] = []
    for name in ("obstacle_sw", "obstacle_se", "obstacle_nw", "obstacle_ne"):
        fp = d / f"{name}.json"
        if fp.is_file():
            out.append(json.loads(fp.read_text(encoding="utf-8")))
    return out


def aabb_from_closed(
    closed: List[Dict[str, float]],
    pad: float = 0.0,
) -> Optional[Dict[str, float]]:
    if not closed or len(closed) < 4:
        return None
    xs = [float(p["x"]) for p in closed]
    ys = [float(p["y"]) for p in closed]
    return {
        "minx": min(xs) + pad,
        "maxx": max(xs) - pad,
        "miny": min(ys) + pad,
        "maxy": max(ys) - pad,
    }


def point_in_aabb(x: float, y: float, box: Dict[str, float]) -> bool:
    return (
        float(box["minx"]) <= x <= float(box["maxx"])
        and float(box["miny"]) <= y <= float(box["maxy"])
    )


def point_in_any_box(
    x: float,
    y: float,
    boxes: List[Dict[str, float]],
    margin: float = 0.05,
) -> bool:
    for b in boxes:
        if (
            float(b["minx"]) - margin <= x <= float(b["maxx"]) + margin
            and float(b["miny"]) - margin <= y <= float(b["maxy"]) + margin
        ):
            return True
    return False


def frozen_geometry(directory: Optional[Path] = None) -> Dict[str, Any]:
    """Vista read-only para HMI/API: sin live_align como verdad de geometría."""
    track = load_track(_traces_dir(directory) / "track_perimeter.json")
    closed = list(track.get("trail_map_closed") or [])
    box = track.get("map_box") or aabb_from_closed(closed) or {}
    obstacles = load_obstacles(directory)
    boxes = []
    for o in obstacles:
        b = o.get("map_box")
        if b:
            boxes.append(
                {
                    "id": o.get("id"),
                    "box": {
                        "minx": float(b["minx"]),
                        "maxx": float(b["maxx"]),
                        "miny": float(b["miny"]),
                        "maxy": float(b["maxy"]),
                    },
                    "center": o.get("map_center"),
                }
            )
    return {
        "version": GEOMETRY_VERSION,
        "perimeter_yaw_meta": float(track.get("perimeter_yaw") or PERIMETER_YAW_META),
        "trail_map_closed": closed,
        "map_box": box,
        "map_center": track.get("map_center"),
        "obstacles": obstacles,
        "obstacle_boxes": boxes,
    }


def closed_vertices_fingerprint(closed: List[Dict[str, float]]) -> Tuple[Tuple[float, float], ...]:
    return tuple((round(float(p["x"]), 6), round(float(p["y"]), 6)) for p in closed)
