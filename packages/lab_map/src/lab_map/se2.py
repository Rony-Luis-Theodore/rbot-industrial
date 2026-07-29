"""SE(2) odom → Occupancy: map = R(ψ)·odom + t."""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping, MutableMapping, Optional, Tuple

from .constants import LIDAR_HEADING_FLIP, MAP_ALIGN_NUDGE_TX, MAP_ALIGN_NUDGE_TY, ODOM_TO_MAP_SCALE


def wrap_pi(a: float) -> float:
    return math.atan2(math.sin(a), math.cos(a))


def project_xy(x: float, y: float, yaw: float, tx: float, ty: float) -> Tuple[float, float]:
    c, s = math.cos(yaw), math.sin(yaw)
    return c * x - s * y + tx, s * x + c * y + ty


def project_pose(
    odom: Mapping[str, float],
    align: Mapping[str, float],
) -> Dict[str, float]:
    scale = float(align.get("sx") or ODOM_TO_MAP_SCALE)
    ox = float(odom.get("x") or 0.0) * scale
    oy = float(odom.get("y") or 0.0) * scale
    oth = float(odom.get("theta") or 0.0)
    yaw = float(align.get("yaw") or 0.0)
    tx = float(align.get("tx") or 0.0)
    ty = float(align.get("ty") or 0.0)
    mx, my = project_xy(ox, oy, yaw, tx, ty)
    return {"x": mx, "y": my, "theta": wrap_pi(oth + yaw)}


def seed_align_from_map_pose(
    mx: float,
    my: float,
    map_th: float,
    odom: Mapping[str, float],
    *,
    apply_lidar_flip: bool = True,
    source: str = "lidar_in_track",
) -> Dict[str, Any]:
    """ψ = (θ_map [+ FLIP]) − θ_odom. Odom se escala a metros Occupancy."""
    scale = ODOM_TO_MAP_SCALE
    ox = float(odom.get("x") or 0.0) * scale
    oy = float(odom.get("y") or 0.0) * scale
    oth = float(odom.get("theta") or 0.0)
    th = float(map_th)
    if apply_lidar_flip:
        th = wrap_pi(th + LIDAR_HEADING_FLIP)
    yaw = wrap_pi(th - oth)
    c, s = math.cos(yaw), math.sin(yaw)
    return {
        "yaw": yaw,
        "tx": mx - (c * ox - s * oy) + MAP_ALIGN_NUDGE_TX,
        "ty": my - (s * ox + c * oy) + MAP_ALIGN_NUDGE_TY,
        "sx": scale,
        "sy": scale,
        "ready": True,
        "source": source,
        "note": "live SE2; odom×scale→Occupancy",
    }


def nudge_translation(
    align: Mapping[str, float],
    dtx: float,
    dty: float,
) -> Dict[str, Any]:
    out = dict(align)
    out["tx"] = float(align.get("tx") or 0.0) + float(dtx)
    out["ty"] = float(align.get("ty") or 0.0) + float(dty)
    out["ready"] = True
    return out


def forward_delta_map(
    odom: Mapping[str, float],
    align: Mapping[str, float],
    body_forward_m: float = 0.3,
) -> Tuple[float, float]:
    """Δmapa al avanzar `body_forward_m` en el eje del robot (odom)."""
    scale = float(align.get("sx") or ODOM_TO_MAP_SCALE)
    ox = float(odom.get("x") or 0.0)
    oy = float(odom.get("y") or 0.0)
    oth = float(odom.get("theta") or 0.0)
    yaw = float(align.get("yaw") or 0.0)
    tx = float(align.get("tx") or 0.0)
    ty = float(align.get("ty") or 0.0)
    x0, y0 = project_xy(ox * scale, oy * scale, yaw, tx, ty)
    x1, y1 = project_xy(
        (ox + body_forward_m * math.cos(oth)) * scale,
        (oy + body_forward_m * math.sin(oth)) * scale,
        yaw,
        tx,
        ty,
    )
    return x1 - x0, y1 - y0


def skew_to_cardinal_deg(dx: float, dy: float) -> float:
    """0° = alineado a ejes Occupancy."""
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return 0.0
    ang = abs(math.atan2(dy, dx))
    mod = ang % (math.pi / 2)
    return min(mod, math.pi / 2 - mod) * 180.0 / math.pi


def normalize_session_align(raw: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    try:
        yaw = float(raw["yaw"])
        tx = float(raw["tx"])
        ty = float(raw["ty"])
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(v) for v in (yaw, tx, ty)):
        return None
    return {
        "yaw": wrap_pi(yaw),
        "tx": tx,
        "ty": ty,
        "sx": 1.0,
        "sy": 1.0,
        "ready": True,
        "source": str(raw.get("source") or "lidar_in_track"),
        "note": str(raw.get("note") or "live SE2"),
    }
