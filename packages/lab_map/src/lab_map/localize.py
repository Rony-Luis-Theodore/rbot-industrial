"""Localización LiDAR dentro del perímetro Occupancy + refine traslación."""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .constants import (
    LIDAR_HEADING_FLIP,
    LIDAR_YAW,
    LOCALIZE_SCORE_MIN_FRAC,
    PERIMETER_YAW_META,
    REFINE_T_MIN_DELTA_M,
    REFINE_T_RADIUS_M,
)
from .geometry import aabb_from_closed, point_in_aabb, point_in_any_box
from .se2 import nudge_translation, project_pose, seed_align_from_map_pose, wrap_pi

CellFn = Callable[[float, float], int]  # 0 free, 1 occ, 2 unk


def sample_rays(
    scan: Mapping[str, Any],
    *,
    stride: int = 2,
    rmin: float = 0.08,
    rmax: float = 3.5,
) -> List[Dict[str, float]]:
    amin = float(scan.get("angle_min") or 0.0)
    ranges = scan.get("ranges") or []
    ainc = float(scan.get("angle_increment") or ((2 * math.pi) / max(len(ranges), 1)))
    rays: List[Dict[str, float]] = []
    for i, r in enumerate(ranges):
        if stride > 1 and i % stride:
            continue
        try:
            rr = float(r)
        except (TypeError, ValueError):
            continue
        if not (rmin < rr < rmax):
            continue
        rays.append({"range": rr, "ang": amin + i * ainc + LIDAR_YAW})
    return rays


def raycast_range(
    rx: float,
    ry: float,
    ang: float,
    cell: CellFn,
    res: float,
    max_r: float = 3.5,
) -> float:
    step = res * 0.5
    r = 0.0
    while r < max_r:
        r += step
        wx = rx + r * math.cos(ang)
        wy = ry + r * math.sin(ang)
        if cell(wx, wy) == 1:
            return r
    return max_r


def score_raycast(
    rx: float,
    ry: float,
    rth: float,
    rays: Sequence[Mapping[str, float]],
    cell: CellFn,
    res: float,
    max_r: float = 3.5,
) -> float:
    if cell(rx, ry) != 0:
        return -1e9
    sigma = 0.11
    score = 0.0
    for ray in rays:
        pred = raycast_range(rx, ry, float(ray["ang"]) + rth, cell, res, max_r)
        err = pred - float(ray["range"])
        score += math.exp(-(err * err) / (sigma * sigma))
    return score


def free_cells_in_track(
    closed: List[Dict[str, float]],
    boxes: List[Dict[str, float]],
    cell: CellFn,
    *,
    origin: Tuple[float, float],
    res: float,
    width: int,
    height: int,
    pad: float = 0.08,
) -> List[Tuple[float, float]]:
    box = aabb_from_closed(closed, pad=pad)
    if not box:
        return []
    ox, oy = origin
    out: List[Tuple[float, float]] = []
    for row in range(1, height - 1):
        for col in range(1, width - 1):
            x = ox + (col + 0.5) * res
            y = oy + (row + 0.5) * res
            if not point_in_aabb(x, y, box):
                continue
            if point_in_any_box(x, y, boxes, margin=0.05):
                continue
            if cell(x, y) != 0:
                continue
            out.append((x, y))
    return out


def yaw_trials(odom_theta: float, perimeter_yaw_meta: float = PERIMETER_YAW_META) -> List[float]:
    """θ_map en Occupancy. No usar perimeter+odom (forzaba ψ≈π/2 → rombo)."""
    del odom_theta  # reserved for future motion priors
    trials: List[float] = []
    bases = (0.0, math.pi / 2, math.pi, -math.pi / 2, perimeter_yaw_meta)
    for base in bases:
        d = -0.45
        while d <= 0.45 + 1e-9:
            trials.append(wrap_pi(base + d))
            d += 0.15
    uniq: List[float] = []
    for t in trials:
        if not any(abs(wrap_pi(t - u)) < 1e-3 for u in uniq):
            uniq.append(t)
    return uniq


def localize_in_track(
    *,
    odom: Mapping[str, float],
    scan: Mapping[str, Any],
    closed: List[Dict[str, float]],
    boxes: List[Dict[str, float]],
    cell: CellFn,
    origin: Tuple[float, float],
    res: float,
    width: int,
    height: int,
    perimeter_yaw_meta: float = PERIMETER_YAW_META,
) -> Optional[Dict[str, Any]]:
    rays = sample_rays(scan)
    if len(rays) < 10:
        return None
    cells = free_cells_in_track(
        closed, boxes, cell, origin=origin, res=res, width=width, height=height
    )
    if not cells:
        return None
    trials = yaw_trials(float(odom.get("theta") or 0.0), perimeter_yaw_meta)
    best = {"score": -1e9, "x": 0.0, "y": 0.0, "th": 0.0}
    stride = 2 if len(cells) > 500 else 1
    for th in trials:
        for i in range(0, len(cells), stride):
            x, y = cells[i]
            sc = score_raycast(x, y, th, rays, cell, res)
            if sc > best["score"]:
                best = {"score": sc, "x": x, "y": y, "th": th}
    # refine
    refined = dict(best)
    for dx in [i * 0.03 for i in range(-4, 5)]:
        for dy in [i * 0.03 for i in range(-4, 5)]:
            for dth in [i * 0.05 for i in range(-4, 5)]:
                x = best["x"] + dx
                y = best["y"] + dy
                box = aabb_from_closed(closed, pad=0.08)
                if not box or not point_in_aabb(x, y, box):
                    continue
                if point_in_any_box(x, y, boxes) or cell(x, y) != 0:
                    continue
                th = wrap_pi(best["th"] + dth)
                sc = score_raycast(x, y, th, rays, cell, res)
                if sc > refined["score"]:
                    refined = {"score": sc, "x": x, "y": y, "th": th}
    if refined["score"] < len(rays) * LOCALIZE_SCORE_MIN_FRAC:
        return None
    align = seed_align_from_map_pose(
        refined["x"], refined["y"], refined["th"], odom, apply_lidar_flip=True
    )
    return {"align": align, "tip": {"x": refined["x"], "y": refined["y"]}, "score": refined["score"]}


def refine_translation(
    *,
    odom: Mapping[str, float],
    align: Mapping[str, float],
    scan: Mapping[str, Any],
    closed: List[Dict[str, float]],
    boxes: List[Dict[str, float]],
    cell: CellFn,
    res: float,
    force: bool = False,
) -> Optional[Dict[str, Any]]:
    """Solo tx/ty; yaw intacto. Corrige desfase de carril."""
    rays = sample_rays(scan)
    if len(rays) < 10:
        return None
    tip0 = project_pose(odom, align)
    map_th = wrap_pi(float(align.get("yaw") or 0.0) + float(odom.get("theta") or 0.0))
    box = aabb_from_closed(closed, pad=0.06)
    if not box:
        return None
    best = {
        "score": score_raycast(tip0["x"], tip0["y"], map_th, rays, cell, res),
        "x": tip0["x"],
        "y": tip0["y"],
    }
    r = REFINE_T_RADIUS_M
    step = 0.04
    dx = -r
    while dx <= r + 1e-9:
        dy = -r
        while dy <= r + 1e-9:
            x = tip0["x"] + dx
            y = tip0["y"] + dy
            if not point_in_aabb(x, y, box):
                dy += step
                continue
            if point_in_any_box(x, y, boxes, margin=0.04) or cell(x, y) != 0:
                dy += step
                continue
            sc = score_raycast(x, y, map_th, rays, cell, res)
            if sc > best["score"]:
                best = {"score": sc, "x": x, "y": y}
            dy += step
        dx += step
    dtx = best["x"] - tip0["x"]
    dty = best["y"] - tip0["y"]
    dist = math.hypot(dtx, dty)
    if dist < REFINE_T_MIN_DELTA_M and not force:
        return None
    if best["score"] < len(rays) * 0.1:
        return None
    if dist > 0.55 and not force:
        return None
    new_align = nudge_translation(align, dtx, dty)
    return {"align": new_align, "dtx": dtx, "dty": dty, "dist": dist, "score": best["score"]}
