"""Trazo Occupancy: append con gaps; NUNCA wipe total por un salto."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .constants import TRAIL_MAX_POINTS, TRAIL_MAX_STEP_M, TRAIL_MIN_STEP_M


def empty_trail() -> List[Dict[str, Any]]:
    return []


def append_point(
    trail: List[Dict[str, Any]],
    x: float,
    y: float,
    *,
    allow_break: bool = True,
    max_step: float = TRAIL_MAX_STEP_M,
    min_step: float = TRAIL_MIN_STEP_M,
) -> List[Dict[str, Any]]:
    out = list(trail)
    if not out:
        out.append({"x": float(x), "y": float(y)})
        return _trim(out)
    last = out[-1]
    step = ((float(x) - float(last["x"])) ** 2 + (float(y) - float(last["y"])) ** 2) ** 0.5
    if step < min_step:
        return out
    if step > max_step:
        if allow_break:
            out.append({"x": float(x), "y": float(y), "gap": True})
        return _trim(out)
    out.append({"x": float(x), "y": float(y)})
    return _trim(out)


def shift_trail(
    trail: List[Dict[str, Any]],
    dtx: float,
    dty: float,
) -> List[Dict[str, Any]]:
    if abs(dtx) < 1e-9 and abs(dty) < 1e-9:
        return list(trail)
    return [
        {**p, "x": float(p["x"]) + dtx, "y": float(p["y"]) + dty}
        for p in trail
    ]


def max_step(trail: List[Dict[str, Any]]) -> float:
    m = 0.0
    for i in range(1, len(trail)):
        if trail[i].get("gap"):
            continue
        dx = float(trail[i]["x"]) - float(trail[i - 1]["x"])
        dy = float(trail[i]["y"]) - float(trail[i - 1]["y"])
        m = max(m, (dx * dx + dy * dy) ** 0.5)
    return m


def continuous_segment_count(trail: List[Dict[str, Any]]) -> int:
    """Número de polilíneas (1 + gaps)."""
    if not trail:
        return 0
    n = 1
    for p in trail[1:]:
        if p.get("gap"):
            n += 1
    return n


def _trim(trail: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(trail) > TRAIL_MAX_POINTS:
        return trail[-TRAIL_MAX_POINTS:]
    return trail
