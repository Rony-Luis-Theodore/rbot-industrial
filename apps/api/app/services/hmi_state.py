"""
Estado HMI compartido (trazo/align/odom) para diagnóstico y navegación a zonas.

El «norte» (align SE(2) bueno: lidar/perímetro) se conserva aparte del snapshot
crudo, para que un provisional/pending de la HMI no tumbe la navegación.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

_HMI_DEBUG: Dict[str, Any] = {}
_GOOD_ALIGN: Optional[Dict[str, Any]] = None
_PLANNED_PATH: Optional[Dict[str, Any]] = None

_NORTH_PATH = Path.home() / ".cache" / "rbot-industrial" / "hmi_north.json"
_NAV_SOURCES = frozenset({"lidar", "perimeter", "soft", "north", "lidar_in_track"})


def _is_identity(a: Dict[str, Any]) -> bool:
    try:
        return (
            abs(float(a.get("tx") or 0.0)) < 0.05
            and abs(float(a.get("ty") or 0.0)) < 0.05
            and abs(float(a.get("yaw") or 0.0)) < 0.05
        )
    except (TypeError, ValueError):
        return True


def _normalize_align(a: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not a or not a.get("ready"):
        return None
    source = str(a.get("source") or "unknown").lower()
    if source in ("pending", "none", "unknown", ""):
        return None
    if source not in _NAV_SOURCES:
        return None
    # Identidad solo válida tras un perímetro real (casi nunca)
    if _is_identity(a) and source != "perimeter":
        return None
    try:
        return {
            "yaw": float(a.get("yaw") or 0.0),
            "tx": float(a.get("tx") or 0.0),
            "ty": float(a.get("ty") or 0.0),
            "sx": float(a.get("sx") or 1.0),
            "sy": float(a.get("sy") or 1.0),
            "ready": True,
            "source": source,
        }
    except (TypeError, ValueError):
        return None


def _load_north_disk() -> Optional[Dict[str, Any]]:
    try:
        if not _NORTH_PATH.is_file():
            return None
        data = json.loads(_NORTH_PATH.read_text(encoding="utf-8"))
        return _normalize_align(data if isinstance(data, dict) else {})
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def _save_north_disk(align: Dict[str, Any]) -> None:
    try:
        _NORTH_PATH.parent.mkdir(parents=True, exist_ok=True)
        _NORTH_PATH.write_text(
            json.dumps(align, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def _remember_good(align: Dict[str, Any]) -> None:
    global _GOOD_ALIGN
    norm = _normalize_align(align)
    if not norm:
        return
    # Preferir perímetro > lidar > soft al actualizar
    rank = {"perimeter": 3, "north": 3, "lidar": 2, "soft": 1}
    cur = _GOOD_ALIGN
    if cur:
        if rank.get(norm["source"], 0) < rank.get(str(cur.get("source")), 0):
            # soft no pisa un perímetro/lidar ya bueno salvo yaw muy distinto
            dyaw = abs(
                (float(norm["yaw"]) - float(cur["yaw"]) + math.pi) % (2 * math.pi)
                - math.pi
            )
            if norm["source"] == "soft" and dyaw < 0.35:
                return
    _GOOD_ALIGN = dict(norm)
    _save_north_disk(_GOOD_ALIGN)


def clear_good_align() -> None:
    """Invalida el norte guardado (sim↔lab o rumbo invertido)."""
    global _GOOD_ALIGN
    _GOOD_ALIGN = None
    try:
        if _NORTH_PATH.is_file():
            _NORTH_PATH.unlink()
    except OSError:
        pass


def _canon_ok(canon: Dict[str, Any]) -> bool:
    try:
        float(canon.get("yaw"))
        float(canon.get("tx"))
        float(canon.get("ty"))
        return True
    except (TypeError, ValueError):
        return False


def set_hmi_debug(
    *,
    trail_odom: List[Dict[str, float]],
    align: Dict[str, Any],
    hint: str = "",
    perimeter_fitted: bool = False,
    odom: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    global _HMI_DEBUG
    _HMI_DEBUG = {
        "trail_odom": trail_odom[-900:],
        "align": align or {},
        "hint": hint,
        "perimeter_fitted": bool(perimeter_fitted),
        "odom": odom,
        "n_trail": len(trail_odom),
    }
    a = dict(align or {})
    # Con perímetro canónico en disco: lidar/soft de la HMI no lo pisan.
    try:
        from app.services.lab_traces import load_track_perimeter

        track = load_track_perimeter() or {}
        canon = track.get("align_canonical") or {}
        if canon and _canon_ok(canon):
            if str(a.get("source") or "") == "perimeter" and a.get("ready"):
                a = {**a, "ready": True, "source": "perimeter"}
                _HMI_DEBUG["align"] = a
                _HMI_DEBUG["perimeter_fitted"] = True
                _remember_good(a)
            else:
                frozen = {
                    "yaw": float(canon.get("yaw") or 0.0),
                    "tx": float(canon.get("tx") or 0.0),
                    "ty": float(canon.get("ty") or 0.0),
                    "sx": 1.0,
                    "sy": 1.0,
                    "ready": True,
                    "source": "perimeter",
                }
                _HMI_DEBUG["align"] = frozen
                _HMI_DEBUG["perimeter_fitted"] = True
                _remember_good(frozen)
            return {
                "ok": True,
                "n_trail": _HMI_DEBUG["n_trail"],
                "align_ok": True,
                "align_source": "perimeter",
            }
    except Exception:
        pass

    if perimeter_fitted:
        a = {
            **a,
            "ready": True,
            "source": a.get("source")
            if a.get("source") in ("perimeter", "soft", "lidar", "north")
            else "perimeter",
        }
        _HMI_DEBUG["align"] = a
        _HMI_DEBUG["perimeter_fitted"] = True
    if a.get("clear_north") or (
        not a.get("ready") and str(a.get("source") or "") in ("none", "reset")
    ):
        clear_good_align()
    else:
        _remember_good(a)
    return {
        "ok": True,
        "n_trail": _HMI_DEBUG["n_trail"],
        "align_ok": get_align() is not None,
        "align_source": (get_align() or {}).get("source"),
    }


def set_planned_path(
    waypoints: Optional[List[Any]] = None,
    *,
    zone_id: str = "",
    label: str = "",
    length_m: float = 0.0,
    mode: str = "",
) -> None:
    """Ruta A* en Occupancy para dibujar en la HMI (y depurar)."""
    global _PLANNED_PATH
    if not waypoints:
        _PLANNED_PATH = None
        return
    pts = []
    for p in waypoints:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            pts.append({"x": float(p[0]), "y": float(p[1])})
        elif isinstance(p, dict) and "x" in p and "y" in p:
            pts.append({"x": float(p["x"]), "y": float(p["y"])})
    _PLANNED_PATH = {
        "waypoints": pts,
        "zone_id": zone_id,
        "label": label,
        "length_m": float(length_m),
        "mode": mode,
        "n": len(pts),
    }


def clear_planned_path() -> None:
    global _PLANNED_PATH
    _PLANNED_PATH = None


def get_planned_path() -> Optional[Dict[str, Any]]:
    return dict(_PLANNED_PATH) if _PLANNED_PATH else None


def get_hmi_debug() -> Dict[str, Any]:
    out = dict(_HMI_DEBUG) if _HMI_DEBUG else {
        "n_trail": 0,
        "trail_odom": [],
        "align": {},
    }
    good = get_align()
    out["good_align"] = good
    out["align_ok"] = good is not None
    out["planned_path"] = get_planned_path()
    return out


def get_align() -> Optional[Dict[str, float]]:
    """
    Align SE(2) odom→mapa navegable.

    Prioridad (lab_map v1):
      1) live_align de sesión únicamente
      2) norte en memoria/disco
      3) snapshot HMI
    """
    global _GOOD_ALIGN
    if _GOOD_ALIGN is None:
        _GOOD_ALIGN = _load_north_disk()

    try:
        from app.services.lab_map_service import get_session_align

        live = get_session_align()
        if live:
            canon = _normalize_align(live)
            if canon:
                _GOOD_ALIGN = dict(canon)
                _save_north_disk(_GOOD_ALIGN)
                return {
                    "yaw": canon["yaw"],
                    "tx": canon["tx"],
                    "ty": canon["ty"],
                    "source": str(canon.get("source") or "lidar_in_track"),
                }
    except Exception:
        pass

    # 2) Norte bueno ya congelado
    if _GOOD_ALIGN and str(_GOOD_ALIGN.get("source") or "") in (
        "perimeter",
        "lidar_in_track",
        "lidar",
    ):
        return {
            "yaw": float(_GOOD_ALIGN["yaw"]),
            "tx": float(_GOOD_ALIGN["tx"]),
            "ty": float(_GOOD_ALIGN["ty"]),
            "source": str(_GOOD_ALIGN.get("source") or "lidar_in_track"),
        }

    # 3) Snapshot HMI: no dejar que lidar pise un perímetro
    snap = _normalize_align((_HMI_DEBUG or {}).get("align") or {})
    if snap:
        if (
            _GOOD_ALIGN
            and str(_GOOD_ALIGN.get("source") or "") == "perimeter"
            and snap["source"] != "perimeter"
        ):
            return {
                "yaw": float(_GOOD_ALIGN["yaw"]),
                "tx": float(_GOOD_ALIGN["tx"]),
                "ty": float(_GOOD_ALIGN["ty"]),
                "source": "perimeter",
            }
        _remember_good(snap)
        return {
            "yaw": snap["yaw"],
            "tx": snap["tx"],
            "ty": snap["ty"],
            "source": snap["source"],
        }

    if _GOOD_ALIGN:
        return {
            "yaw": float(_GOOD_ALIGN["yaw"]),
            "tx": float(_GOOD_ALIGN["tx"]),
            "ty": float(_GOOD_ALIGN["ty"]),
            "source": str(_GOOD_ALIGN.get("source") or "north"),
        }
    return None


def get_odom_fallback() -> Optional[Dict[str, float]]:
    """Última odom reportada por la HMI (si /odom CLI falla en el worker)."""
    o = (_HMI_DEBUG or {}).get("odom") or {}
    try:
        x = float(o.get("x"))
        y = float(o.get("y"))
        th = float(o.get("theta") or 0.0)
    except (TypeError, ValueError):
        return None
    # (0,0) suele ser basura tras desconexión — no envenenar el status
    if abs(x) < 1e-6 and abs(y) < 1e-6:
        return None
    return {"x": x, "y": y, "theta": th}
