"""Trazos de laboratorio: 4 obstáculos + perímetro rectangular de pista."""

from __future__ import annotations

import json
import math
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

TRACES_DIR = Path(__file__).resolve().parent / "lab_obstacle_traces"
TRACES_DIR.mkdir(parents=True, exist_ok=True)

TRACK_PERIMETER_PATH = TRACES_DIR / "track_perimeter.json"

# Esquinas del lab Occupancy (mapa ROS, no pantalla)
_OBSTACLE_META = {
    "obstacle_sw": {
        "label": "Obstáculo inferior izquierdo",
        "corner": "southwest",
        "screen_hint": "izquierda inferior",
    },
    "obstacle_se": {
        "label": "Obstáculo inferior derecho",
        "corner": "southeast",
        "screen_hint": "derecha inferior",
    },
    "obstacle_nw": {
        "label": "Obstáculo superior izquierdo",
        "corner": "northwest",
        "screen_hint": "izquierda superior",
    },
    "obstacle_ne": {
        "label": "Obstáculo superior derecho",
        "corner": "northeast",
        "screen_hint": "derecha superior",
    },
}


def _centroid(pts: List[Dict[str, float]]) -> Dict[str, float]:
    if not pts:
        return {"x": 0.0, "y": 0.0}
    sx = sum(float(p["x"]) for p in pts)
    sy = sum(float(p["y"]) for p in pts)
    n = float(len(pts))
    return {"x": sx / n, "y": sy / n}


def infer_closed_rectangle_odom(pts: List[Dict[str, float]]) -> Optional[List[Dict[str, float]]]:
    """OBB por PCA en odom → 5 vértices (cierra el perímetro)."""
    if not pts or len(pts) < 4:
        return None
    n = len(pts)
    cx = sum(float(p["x"]) for p in pts) / n
    cy = sum(float(p["y"]) for p in pts) / n
    sxx = sxy = syy = 0.0
    for p in pts:
        dx = float(p["x"]) - cx
        dy = float(p["y"]) - cy
        sxx += dx * dx
        sxy += dx * dy
        syy += dy * dy
    angle = 0.5 * math.atan2(2.0 * sxy, sxx - syy if abs(sxx - syy) > 1e-12 else 1e-9)
    c, s = math.cos(angle), math.sin(angle)
    min_u = min_v = float("inf")
    max_u = max_v = float("-inf")
    for p in pts:
        dx = float(p["x"]) - cx
        dy = float(p["y"]) - cy
        u = c * dx + s * dy
        v = -s * dx + c * dy
        min_u, max_u = min(min_u, u), max(max_u, u)
        min_v, max_v = min(min_v, v), max(max_v, v)
    w = max(0.05, max_u - min_u)
    h = max(0.05, max_v - min_v)
    if w < 0.5 or h < 0.5:
        return None
    u0 = (min_u + max_u) / 2.0
    v0 = (min_v + max_v) / 2.0
    rcx = cx + c * u0 - s * v0
    rcy = cy + s * u0 + c * v0
    hw, hh = w / 2.0, h / 2.0
    corners_uv = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh), (-hw, -hh)]
    out = []
    for u, v in corners_uv:
        out.append({"x": rcx + c * u - s * v, "y": rcy + s * u + c * v})
    return out


def project_odom_to_map(
    pts: List[Dict[str, float]], align: Dict[str, Any]
) -> List[Dict[str, float]]:
    yaw = float(align.get("yaw") or 0.0)
    tx = float(align.get("tx") or 0.0)
    ty = float(align.get("ty") or 0.0)
    c, s = math.cos(yaw), math.sin(yaw)
    out = []
    for p in pts:
        x, y = float(p["x"]), float(p["y"])
        out.append({"x": c * x - s * y + tx, "y": s * x + c * y + ty})
    return out


def _find_interior_obstacle_blobs(map_id: str = "laboratorio_kalman") -> List[Dict[str, Any]]:
    """4 bloques interiores del PGM (no el anillo de muros)."""
    try:
        from PIL import Image
        import yaml
    except ImportError:
        return []

    # Resolver PGM vía mapa vendored (lab_map/maps) o ros_ws enlazado
    root = Path(__file__).resolve().parents[4]  # rbot-industrial
    yaml_candidates = [
        root / "packages" / "lab_map" / "maps" / f"{map_id}.yaml",
        root / "packages" / "ros_ws" / "src" / "kalman_bringup" / "map" / f"{map_id}.yaml",
    ]
    yaml_path = next((p for p in yaml_candidates if p.is_file()), None)
    if yaml_path is None:
        return []
    meta = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    img_name = str(meta.get("image") or f"{map_id}.pgm")
    img_path = yaml_path.parent / img_name
    if not img_path.is_file():
        return []

    img = Image.open(img_path)
    w, h = img.size
    pix = img.load()
    res = float(meta["resolution"])
    ox, oy = float(meta["origin"][0]), float(meta["origin"][1])

    occ = [[0] * w for _ in range(h)]
    for row in range(h):
        for col in range(w):
            if pix[col, row] < 50:
                occ[row][col] = 1

    wall = [[0] * w for _ in range(h)]
    q: deque = deque()
    for col in range(w):
        for row in (0, h - 1):
            if occ[row][col]:
                wall[row][col] = 1
                q.append((row, col))
    for row in range(h):
        for col in (0, w - 1):
            if occ[row][col] and not wall[row][col]:
                wall[row][col] = 1
                q.append((row, col))
    while q:
        r, c = q.popleft()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            rr, cc = r + dr, c + dc
            if 0 <= rr < h and 0 <= cc < w and occ[rr][cc] and not wall[rr][cc]:
                wall[rr][cc] = 1
                q.append((rr, cc))

    seen = [[0] * w for _ in range(h)]
    blobs: List[Dict[str, Any]] = []
    for row in range(h):
        for col in range(w):
            if not occ[row][col] or wall[row][col] or seen[row][col]:
                continue
            q = deque([(row, col)])
            seen[row][col] = 1
            cells: List[Tuple[int, int]] = []
            while q:
                r, c = q.popleft()
                cells.append((r, c))
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    rr, cc = r + dr, c + dc
                    if (
                        0 <= rr < h
                        and 0 <= cc < w
                        and occ[rr][cc]
                        and not wall[rr][cc]
                        and not seen[rr][cc]
                    ):
                        seen[rr][cc] = 1
                        q.append((rr, cc))
            if len(cells) < 6 or len(cells) > 80:
                continue
            xs = [ox + c * res for r, c in cells]
            ys = [oy + (h - 1 - r) * res for r, c in cells]
            blobs.append(
                {
                    "n": len(cells),
                    "cx": sum(xs) / len(xs),
                    "cy": sum(ys) / len(ys),
                    "minx": min(xs),
                    "maxx": max(xs) + res,
                    "miny": min(ys),
                    "maxy": max(ys) + res,
                }
            )
    blobs.sort(key=lambda b: (b["cy"], b["cx"]))
    return blobs


def _assign_blobs_to_corners(blobs: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Asigna hasta 4 blobs a SW/SE/NW/NE por cuadrante relativo al centroide."""
    if len(blobs) < 4:
        # Tomar los 4 más grandes si hay más filtros
        return {}
    # Usar los 4 de tamaño medio (ya filtrados); si hay >4, los 4 más cercanos al centro libre
    use = blobs[:4] if len(blobs) == 4 else sorted(blobs, key=lambda b: -b["n"])[:4]
    cx = sum(b["cx"] for b in use) / len(use)
    cy = sum(b["cy"] for b in use) / len(use)
    buckets: Dict[str, List[Dict[str, Any]]] = {
        "obstacle_sw": [],
        "obstacle_se": [],
        "obstacle_nw": [],
        "obstacle_ne": [],
    }
    for b in use:
        if b["cy"] >= cy and b["cx"] < cx:
            buckets["obstacle_nw"].append(b)
        elif b["cy"] >= cy and b["cx"] >= cx:
            buckets["obstacle_ne"].append(b)
        elif b["cy"] < cy and b["cx"] < cx:
            buckets["obstacle_sw"].append(b)
        else:
            buckets["obstacle_se"].append(b)
    out: Dict[str, Dict[str, Any]] = {}
    for oid, items in buckets.items():
        if not items:
            continue
        # Si dos cayeron en el mismo cuadrante, el más extremo
        items.sort(key=lambda b: abs(b["cx"] - cx) + abs(b["cy"] - cy), reverse=True)
        out[oid] = items[0]
    # Si faltan, rellenar con blobs no usados
    used = {id(v) for v in out.values()}
    leftover = [b for b in use if id(b) not in used]
    for oid in _OBSTACLE_META:
        if oid in out:
            continue
        if not leftover:
            break
        out[oid] = leftover.pop(0)
    return out


def sync_obstacles_from_occupancy(
    *,
    align: Optional[Dict[str, Any]] = None,
    map_id: str = "laboratorio_kalman",
) -> Dict[str, Any]:
    """
    Ancla los 4 obstáculos a blobs Occupancy (verdad de mapa).
    No usa trail_odom viejo (odom de otra sesión → centros fuera del carril).
    """
    blobs = _find_interior_obstacle_blobs(map_id)
    assigned = _assign_blobs_to_corners(blobs)
    if len(assigned) < 4:
        return {"ok": False, "reason": "need_4_blobs", "found": len(blobs), "assigned": len(assigned)}

    align_clean = None
    if align:
        align_clean = {
            "yaw": float(align.get("yaw") or 0.0),
            "tx": float(align.get("tx") or 0.0),
            "ty": float(align.get("ty") or 0.0),
            "source": "occupancy_blobs",
        }

    written = []
    for oid, blob in assigned.items():
        meta = _OBSTACLE_META[oid]
        # Conservar trail_odom histórico si existe
        prev: Dict[str, Any] = {}
        path = TRACES_DIR / f"{oid}.json"
        if path.is_file():
            try:
                prev = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                prev = {}
        box = {
            "minx": round(blob["minx"], 4),
            "maxx": round(blob["maxx"], 4),
            "miny": round(blob["miny"], 4),
            "maxy": round(blob["maxy"], 4),
        }
        corners = [
            {"x": box["minx"], "y": box["miny"]},
            {"x": box["maxx"], "y": box["miny"]},
            {"x": box["maxx"], "y": box["maxy"]},
            {"x": box["minx"], "y": box["maxy"]},
            {"x": box["minx"], "y": box["miny"]},
        ]
        data = {
            "id": oid,
            "label": meta["label"],
            "corner": meta["corner"],
            "screen_hint": meta["screen_hint"],
            "source": "occupancy_blob",
            "n_cells": blob["n"],
            "map_center": {"x": round(blob["cx"], 4), "y": round(blob["cy"], 4)},
            "map_box": box,
            "trail_map": corners,
            "trail_odom": prev.get("trail_odom") or [],
            "align_used": align_clean
            or {"yaw": 0.0, "tx": 0.0, "ty": 0.0, "source": "occupancy_blob"},
            "align_note": "centros desde Occupancy PGM (4 bloques reales)",
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append({"id": oid, "center": data["map_center"], "box": box})

    return {"ok": True, "n": len(written), "obstacles": written}


def save_track_perimeter(
    *,
    trail_odom: List[Dict[str, float]],
    align: Dict[str, Any],
    closed_odom: Optional[List[Dict[str, float]]] = None,
    hint: str = "",
) -> Dict[str, Any]:
    raw = [
        {"x": float(p["x"]), "y": float(p["y"])}
        for p in (trail_odom or [])
        if p and "x" in p and "y" in p
    ]
    closed = closed_odom or infer_closed_rectangle_odom(raw)
    if not closed:
        raise ValueError("No se pudo inferir rectángulo del trazo (pocos puntos / muy fino)")
    align_clean = {
        "yaw": float(align.get("yaw") or 0.0),
        "tx": float(align.get("tx") or 0.0),
        "ty": float(align.get("ty") or 0.0),
        "sx": 1.0,
        "sy": 1.0,
        "ready": True,
        "source": align.get("source") or "perimeter",
    }
    closed_map = project_odom_to_map(closed, align_clean)
    # AABB mapa del perímetro (para acotar planner)
    xs = [p["x"] for p in closed_map]
    ys = [p["y"] for p in closed_map]
    map_box = {
        "minx": min(xs),
        "maxx": max(xs),
        "miny": min(ys),
        "maxy": max(ys),
    }
    payload = {
        "id": "track_perimeter",
        "label": "Perímetro rectangular de pista (inferido/cerrado)",
        "n_raw": len(raw),
        "trail_odom_raw": raw[-900:],
        "trail_odom_closed": closed,
        "trail_map_closed": closed_map,
        "map_center": _centroid(closed_map),
        "map_box": map_box,
        "align_canonical": align_clean,
        "hint": hint,
    }
    TRACK_PERIMETER_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    # Obstáculos = blobs Occupancy (no odom de otra sesión)
    obstacles = sync_obstacles_from_occupancy(align=align_clean)
    return {
        "ok": True,
        "path": str(TRACK_PERIMETER_PATH),
        "n_raw": len(raw),
        "n_closed": len(closed),
        "map_center": payload["map_center"],
        "map_box": map_box,
        "align": align_clean,
        "obstacles": obstacles,
    }


def load_track_perimeter() -> Optional[Dict[str, Any]]:
    if not TRACK_PERIMETER_PATH.is_file():
        return None
    try:
        return json.loads(TRACK_PERIMETER_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def list_obstacle_traces() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in sorted(TRACES_DIR.glob("obstacle_*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def get_lab_geometry() -> Dict[str, Any]:
    """Overlay HMI + planner: geometry fija + session SE2 (lab_map)."""
    from app.services.lab_map_service import get_lab_geometry_v1

    return get_lab_geometry_v1()


def obstacle_boxes_for_planner() -> List[Dict[str, float]]:
    boxes = []
    for o in list_obstacle_traces():
        b = o.get("map_box")
        if not b:
            continue
        boxes.append(
            {
                "minx": float(b["minx"]),
                "maxx": float(b["maxx"]),
                "miny": float(b["miny"]),
                "maxy": float(b["maxy"]),
            }
        )
    return boxes


def track_box_for_planner(*, margin_m: float = 0.05) -> Optional[Dict[str, float]]:
    track = load_track_perimeter()
    if not track:
        return None
    b = track.get("map_box")
    if not b:
        closed = track.get("trail_map_closed") or []
        if len(closed) < 4:
            return None
        xs = [float(p["x"]) for p in closed]
        ys = [float(p["y"]) for p in closed]
        b = {"minx": min(xs), "maxx": max(xs), "miny": min(ys), "maxy": max(ys)}
    return {
        "minx": float(b["minx"]) - margin_m,
        "maxx": float(b["maxx"]) + margin_m,
        "miny": float(b["miny"]) - margin_m,
        "maxy": float(b["maxy"]) + margin_m,
    }


def update_live_align(yaw: float, tx: float, ty: float) -> Dict[str, Any]:
    """SE(2) de sesión. NO clampea yaw. NO toca trail_map_closed."""
    from app.services.lab_map_service import set_session_align

    return set_session_align(yaw, tx, ty, source="lidar_in_track")
