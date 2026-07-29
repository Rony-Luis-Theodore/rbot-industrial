"""
=============================================================================
R-Bot — Servicio: Mapas OccupancyGrid (estáticos + meta)
=============================================================================

Propósito:
    Exponer mapas Occupancy (PGM/YAML) a la HMI industrial.
    La v1 usa mapas guardados; el OccupancyGrid live llega vía rosbridge.

Ubicaciones buscadas (en orden):
    1) packages/lab_map/maps/          (vendored — demo sin ROS)
    2) $ROS_MAP_DIR                    (opcional)
    3) packages/ros_ws/.../map/        (si enlazas un workspace ROS local)
=============================================================================
"""

from __future__ import annotations

import io
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from PIL import Image


def _repo_root() -> Path:
    # apps/api/app/services → rbot-industrial
    return Path(__file__).resolve().parents[4]


def _candidate_map_dirs() -> List[Path]:
    root = _repo_root()
    dirs: List[Path] = [
        root / "packages" / "lab_map" / "maps",
    ]
    env_dir = os.environ.get("ROS_MAP_DIR", "").strip()
    if env_dir:
        dirs.append(Path(env_dir).expanduser())
    dirs.append(root / "packages" / "ros_ws" / "src" / "kalman_bringup" / "map")
    # Evitar duplicados preservando orden
    seen = set()
    out: List[Path] = []
    for d in dirs:
        key = str(d.resolve()) if d.exists() else str(d)
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


def list_maps() -> List[Dict[str, Any]]:
    """Lista mapas yaml disponibles."""
    found: List[Dict[str, Any]] = []
    for directory in _candidate_map_dirs():
        if not directory.is_dir():
            continue
        for yaml_path in sorted(directory.glob("*.yaml")):
            meta = _read_yaml_meta(yaml_path)
            found.append(
                {
                    "id": yaml_path.stem,
                    "yaml": str(yaml_path),
                    "image": meta.get("image"),
                    "resolution": meta.get("resolution"),
                    "origin": meta.get("origin"),
                    "directory": str(directory),
                }
            )
        if found:
            break
    return found


def _read_yaml_meta(yaml_path: Path) -> Dict[str, Any]:
    with yaml_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    image_name = data.get("image")
    image_path = None
    if image_name:
        candidate = yaml_path.parent / image_name
        if candidate.exists():
            image_path = str(candidate)
    return {
        "image": image_path,
        "resolution": data.get("resolution"),
        "origin": data.get("origin"),
        "negate": data.get("negate", 0),
        "occupied_thresh": data.get("occupied_thresh"),
        "free_thresh": data.get("free_thresh"),
    }


def get_map_meta(map_id: str) -> Optional[Dict[str, Any]]:
    for item in list_maps():
        if item["id"] == map_id:
            yaml_path = Path(item["yaml"])
            meta = _read_yaml_meta(yaml_path)
            return {**item, **meta}
    return None


def render_map_png(map_id: str) -> Optional[Tuple[bytes, Dict[str, Any]]]:
    """
    Convierte PGM a PNG para el canvas de la HMI.
    Requiere Pillow.
    """
    meta = get_map_meta(map_id)
    if not meta or not meta.get("image"):
        return None
    pgm_path = Path(meta["image"])
    if not pgm_path.exists():
        return None

    img = Image.open(pgm_path)
    # Occupancy maps: oscuro = ocupado en visualización industrial
    if img.mode not in ("L", "P"):
        img = img.convert("L")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue(), meta


# Cache ligero del grid Occupancy (metros → libre/ocupado)
_OCC_CACHE: Dict[str, Any] = {}


def _load_occupancy(map_id: str = "laboratorio_kalman") -> Optional[Dict[str, Any]]:
    global _OCC_CACHE
    if map_id in _OCC_CACHE:
        return _OCC_CACHE[map_id]
    meta = get_map_meta(map_id)
    if not meta or not meta.get("image"):
        # fallback: primer mapa laboratorio*
        for item in list_maps():
            if "laboratorio" in item["id"]:
                meta = get_map_meta(item["id"])
                map_id = item["id"]
                break
    if not meta or not meta.get("image"):
        return None
    pgm_path = Path(meta["image"])
    if not pgm_path.exists():
        return None
    img = Image.open(pgm_path)
    if img.mode not in ("L", "P"):
        img = img.convert("L")
    w, h = img.size
    pixels = list(img.getdata())
    origin = meta.get("origin") or [-1.07, -0.9, 0]
    res = float(meta.get("resolution") or 0.05)
    grid = bytearray(w * h)
    for i, g in enumerate(pixels):
        # PGM: ~0 ocupado, ~254 libre (igual que viewer)
        if g < 50:
            grid[i] = 1
        elif g > 240:
            grid[i] = 0
        else:
            grid[i] = 2
    data = {
        "id": map_id,
        "w": w,
        "h": h,
        "res": res,
        "ox": float(origin[0]),
        "oy": float(origin[1]),
        "grid": grid,
    }
    _OCC_CACHE[map_id] = data
    return data


def map_cell_state(x: float, y: float, map_id: str = "laboratorio_kalman") -> int:
    """0=libre, 1=ocupado, 2=desconocido, -1=fuera."""
    occ = _load_occupancy(map_id)
    if not occ:
        return -1
    mx = int((x - occ["ox"]) / occ["res"])
    my = int((y - occ["oy"]) / occ["res"])
    if mx < 0 or my < 0 or mx >= occ["w"] or my >= occ["h"]:
        return -1
    # Misma convención que la HMI: fila 0 = top del PGM → flip Y
    return int(occ["grid"][(occ["h"] - 1 - my) * occ["w"] + mx])


def is_map_free(x: float, y: float, map_id: str = "laboratorio_kalman") -> bool:
    return map_cell_state(x, y, map_id) == 0


def nearest_free_xy(
    x: float,
    y: float,
    *,
    map_id: str = "laboratorio_kalman",
    max_r_m: float = 1.2,
) -> Optional[Tuple[float, float]]:
    """
    Proyecta (x,y) a la celda libre más cercana (metros Occupancy).
    Sirve para clamp cuando odom/dead-reckon se sale del mapa tras un choque.
    """
    occ = _load_occupancy(map_id)
    if not occ:
        return None
    if is_map_free(x, y, map_id):
        return float(x), float(y)
    w, h, res = occ["w"], occ["h"], float(occ["res"])
    mx, my = _world_to_cell(occ, x, y)
    max_r = max(1, int(math.ceil(max_r_m / res)), max(w, h))
    best: Optional[Tuple[float, float]] = None
    best_d = 1e18
    for r in range(1, max_r + 1):
        ring_best = None
        ring_d = 1e18
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if abs(dx) != r and abs(dy) != r:
                    continue
                nx, ny = mx + dx, my + dy
                if nx < 0 or ny < 0 or nx >= w or ny >= h:
                    continue
                if _cell_raw(occ, nx, ny) != 0:
                    continue
                wx, wy = _cell_to_world(occ, nx, ny)
                d = (wx - x) ** 2 + (wy - y) ** 2
                if d < ring_d:
                    ring_d = d
                    ring_best = (wx, wy)
        if ring_best is not None:
            return ring_best
    return best


def free_ahead(
    x: float,
    y: float,
    theta: float,
    dist_m: float = 0.18,
    map_id: str = "laboratorio_kalman",
) -> bool:
    """True si un paso en rumbo theta cae en celda libre."""
    nx = x + dist_m * math.cos(theta)
    ny = y + dist_m * math.sin(theta)
    return is_map_free(nx, ny, map_id)


def path_clear(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    *,
    step_m: float = 0.06,
    map_id: str = "laboratorio_kalman",
) -> bool:
    """Muestrea el segmento; False si toca ocupado/fuera."""
    dx, dy = x1 - x0, y1 - y0
    dist = (dx * dx + dy * dy) ** 0.5
    if dist < 1e-6:
        return is_map_free(x0, y0, map_id)
    n = max(1, int(dist / step_m))
    for i in range(n + 1):
        t = i / n
        if not is_map_free(x0 + dx * t, y0 + dy * t, map_id):
            return False
    return True


def _world_to_cell(occ: Dict[str, Any], x: float, y: float) -> Tuple[int, int]:
    mx = int((x - occ["ox"]) / occ["res"])
    my = int((y - occ["oy"]) / occ["res"])
    return mx, my


def _cell_to_world(occ: Dict[str, Any], mx: int, my: int) -> Tuple[float, float]:
    return (
        occ["ox"] + (mx + 0.5) * occ["res"],
        occ["oy"] + (my + 0.5) * occ["res"],
    )


def _cell_raw(occ: Dict[str, Any], mx: int, my: int) -> int:
    w, h = occ["w"], occ["h"]
    if mx < 0 or my < 0 or mx >= w or my >= h:
        return 1
    return int(occ["grid"][(h - 1 - my) * w + mx])


def _build_inflated_blocked(
    occ: Dict[str, Any], inflate_m: float = 0.08
) -> bytearray:
    """
    Celdas no transitables = ocupado/desconocido + inflación ligera.
    Con res=0.05 m, ~0.08 m (1–2 celdas) rodea los 4 bloques sin cerrar pasillos.
    Además: cajas de obstáculos lab + fuera del perímetro de pista (si existen).
    """
    w, h, res = occ["w"], occ["h"], float(occ["res"])
    if inflate_m <= 0:
        rad = 0
    else:
        rad = max(1, int(math.ceil(inflate_m / res - 1e-9)))
    blocked = bytearray(w * h)
    occupied: List[Tuple[int, int]] = []
    for my in range(h):
        for mx in range(w):
            if _cell_raw(occ, mx, my) != 0:
                occupied.append((mx, my))
                blocked[my * w + mx] = 1
    if rad <= 0:
        _paint_lab_geometry_blocked(occ, blocked)
        return blocked
    for mx, my in occupied:
        for dy in range(-rad, rad + 1):
            for dx in range(-rad, rad + 1):
                if dx * dx + dy * dy > rad * rad + 1:
                    continue
                nx, ny = mx + dx, my + dy
                if 0 <= nx < w and 0 <= ny < h:
                    blocked[ny * w + nx] = 1
    _paint_lab_geometry_blocked(occ, blocked)
    return blocked


def _paint_lab_geometry_blocked(occ: Dict[str, Any], blocked: bytearray) -> None:
    """Bloquea cajas de los 4 obstáculos y todo lo exterior al perímetro de pista."""
    try:
        from app.services.lab_traces import obstacle_boxes_for_planner, track_box_for_planner
    except Exception:
        return
    w, h = occ["w"], occ["h"]

    # Extra inflación de cajas Occupancy (por si el PGM es fino)
    for box in obstacle_boxes_for_planner():
        pad = 0.04
        x0, x1 = box["minx"] - pad, box["maxx"] + pad
        y0, y1 = box["miny"] - pad, box["maxy"] + pad
        mx0, my0 = _world_to_cell(occ, x0, y0)
        mx1, my1 = _world_to_cell(occ, x1, y1)
        for my in range(min(my0, my1), max(my0, my1) + 1):
            for mx in range(min(mx0, mx1), max(mx0, mx1) + 1):
                if 0 <= mx < w and 0 <= my < h:
                    blocked[my * w + mx] = 1

    track = track_box_for_planner(margin_m=0.02)
    if not track:
        return
    # Fuera del AABB del perímetro → no transitable (restringe a pista real)
    for my in range(h):
        for mx in range(w):
            if blocked[my * w + mx]:
                continue
            wx, wy = _cell_to_world(occ, mx, my)
            if (
                wx < track["minx"]
                or wx > track["maxx"]
                or wy < track["miny"]
                or wy > track["maxy"]
            ):
                blocked[my * w + mx] = 1


def _nearest_free_cell(
    blocked: bytearray, w: int, h: int, mx: int, my: int, max_r: int = 8
) -> Optional[Tuple[int, int]]:
    if 0 <= mx < w and 0 <= my < h and blocked[my * w + mx] == 0:
        return mx, my
    for r in range(1, max_r + 1):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if abs(dx) != r and abs(dy) != r:
                    continue
                nx, ny = mx + dx, my + dy
                if 0 <= nx < w and 0 <= ny < h and blocked[ny * w + nx] == 0:
                    return nx, ny
    return None


def _simplify_waypoints(
    pts: List[Tuple[float, float]], *, max_step_m: float = 0.38, min_turn_deg: float = 22.0
) -> List[Tuple[float, float]]:
    """Conserva esquinas y limita longitud de tramo (open-loop más seguro)."""
    if len(pts) <= 2:
        return pts
    keep = [pts[0]]
    min_turn = math.radians(min_turn_deg)
    i = 0
    while i < len(pts) - 1:
        ax, ay = keep[-1]
        best_j = i + 1
        for j in range(i + 1, len(pts)):
            dist = math.hypot(pts[j][0] - ax, pts[j][1] - ay)
            if dist > max_step_m:
                break
            best_j = j
            if j + 1 < len(pts):
                h0 = math.atan2(pts[j][1] - ay, pts[j][0] - ax)
                h1 = math.atan2(pts[j + 1][1] - pts[j][1], pts[j + 1][0] - pts[j][0])
                turn = abs((h1 - h0 + math.pi) % (2 * math.pi) - math.pi)
                if turn >= min_turn and dist >= 0.12:
                    break
        if best_j <= i:
            best_j = min(i + 1, len(pts) - 1)
        keep.append(pts[best_j])
        i = best_j
    if keep[-1] != pts[-1]:
        keep.append(pts[-1])
    # Dedup casi-iguales
    out: List[Tuple[float, float]] = [keep[0]]
    for p in keep[1:]:
        if math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) >= 0.06:
            out.append(p)
    if out[-1] != pts[-1]:
        out.append(pts[-1])
    return out


def plan_path(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    *,
    map_id: str = "laboratorio_kalman",
    inflate_m: float = 0.08,
    max_step_m: float = 0.38,
) -> Dict[str, Any]:
    """
    A* 8-conectado sobre Occupancy inflado (evita los 4 bloques del lab).
    Devuelve waypoints en metros Occupancy.
    """
    import heapq

    occ = _load_occupancy(map_id)
    if not occ:
        return {"ok": False, "reason": "no_map", "waypoints": []}

    # Camino recto libre → un solo segmento (rápido)
    if path_clear(x0, y0, x1, y1, map_id=map_id) and is_map_free(x0, y0, map_id) and is_map_free(
        x1, y1, map_id
    ):
        # Comprobar también con inflación ligera muestreando
        dist = math.hypot(x1 - x0, y1 - y0)
        if dist < 1e-3:
            return {
                "ok": True,
                "waypoints": [(x0, y0)],
                "length_m": 0.0,
                "n_cells": 1,
                "mode": "trivial",
            }
        return {
            "ok": True,
            "waypoints": [(x0, y0), (x1, y1)],
            "length_m": dist,
            "n_cells": 2,
            "mode": "straight",
        }

    # Intentar inflación cómoda; si cierra pasillos, relajar
    for inf in (inflate_m, 0.08, 0.05, 0.0):
        if inf > inflate_m + 1e-9:
            continue
        blocked = _build_inflated_blocked(occ, inflate_m=inf)
        w, h = occ["w"], occ["h"]
        smx, smy = _world_to_cell(occ, x0, y0)
        gmx, gmy = _world_to_cell(occ, x1, y1)
        start = _nearest_free_cell(blocked, w, h, smx, smy)
        goal = _nearest_free_cell(blocked, w, h, gmx, gmy)
        if not start or not goal:
            continue

        def heur(a: Tuple[int, int], b: Tuple[int, int]) -> float:
            return math.hypot(a[0] - b[0], a[1] - b[1])

        neighbors = (
            (1, 0, 1.0),
            (-1, 0, 1.0),
            (0, 1, 1.0),
            (0, -1, 1.0),
            (1, 1, math.sqrt(2)),
            (1, -1, math.sqrt(2)),
            (-1, 1, math.sqrt(2)),
            (-1, -1, math.sqrt(2)),
        )

        open_h: List[Tuple[float, int, int]] = []
        heapq.heappush(open_h, (0.0, start[0], start[1]))
        came: Dict[Tuple[int, int], Tuple[int, int]] = {}
        gscore: Dict[Tuple[int, int], float] = {start: 0.0}
        closed: set = set()
        found = False
        while open_h:
            _, cx, cy = heapq.heappop(open_h)
            cur = (cx, cy)
            if cur in closed:
                continue
            if cur == goal:
                found = True
                break
            closed.add(cur)
            for dx, dy, cost in neighbors:
                nx, ny = cx + dx, cy + dy
                if nx < 0 or ny < 0 or nx >= w or ny >= h:
                    continue
                if blocked[ny * w + nx]:
                    continue
                if dx != 0 and dy != 0:
                    if blocked[cy * w + nx] or blocked[ny * w + cx]:
                        continue
                nxt = (nx, ny)
                ng = gscore[cur] + cost
                if ng >= gscore.get(nxt, 1e18):
                    continue
                came[nxt] = cur
                gscore[nxt] = ng
                heapq.heappush(open_h, (ng + heur(nxt, goal), nx, ny))

        if not found:
            continue

        cells: List[Tuple[int, int]] = []
        cur = goal
        while cur != start:
            cells.append(cur)
            cur = came[cur]
        cells.append(start)
        cells.reverse()

        world = [_cell_to_world(occ, mx, my) for mx, my in cells]
        world[0] = (float(x0), float(y0))
        world[-1] = (float(x1), float(y1))
        simple = _simplify_waypoints(world, max_step_m=max_step_m)
        length = 0.0
        for i in range(1, len(simple)):
            length += math.hypot(
                simple[i][0] - simple[i - 1][0], simple[i][1] - simple[i - 1][1]
            )

        return {
            "ok": True,
            "waypoints": simple,
            "length_m": length,
            "n_cells": len(cells),
            "mode": "astar",
            "inflate_m": inf,
        }

    return {"ok": False, "reason": "no_path", "waypoints": []}
