"""
Zonas / waypoints del lab Maze Runner (Occupancy laboratorio_kalman).

Marco canónico Occupancy (el mismo que usa la HMI tras el norte SE(2)):
  - Coords en metros Occupancy (origin yaml, res 0.05).
  - Goto usa odom→mapa con align HMI (LIDAR_HEADING_FLIP + perímetro).
  - DISPLAY_YAW=π/2 es solo vista: pantalla arriba = +X mapa, izq = +Y mapa
    → TL pantalla ≈ Almacén (+x,+y) · TR ≈ Sala máquinas (+x,-y)

Cualquier ruta/sentido nuevo debe usar zone ids o (x,y) Occupancy — no pantalla.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

# Waypoints en espacio libre (carril exterior / cruces). w×h ≈ 0.18–0.28 m.
LAB_ZONES: List[Dict[str, Any]] = [
    # --- Esquinas (L naranjas) ---
    {
        "id": "almacen",
        "label": "Almacén",
        "aliases": (
            "almacen",
            "almacén",
            "deposito",
            "depósito",
            "warehouse",
            "esquina superior izquierda",
            "esquina almacén",
        ),
        "x": 0.58,
        "y": 0.58,
        "w": 0.20,
        "h": 0.20,
    },
    {
        "id": "sala_maquinas",
        "label": "Sala de máquinas",
        "aliases": (
            "sala de maquinas",
            "sala máquinas",
            "maquinas",
            "máquinas",
            "machine room",
            "esquina superior derecha",
        ),
        "x": 0.58,
        "y": -0.40,
        "w": 0.20,
        "h": 0.18,
    },
    {
        "id": "oficina",
        "label": "Oficina",
        "aliases": (
            "oficina",
            "despacho",
            "office",
            "esquina inferior izquierda",
        ),
        "x": -0.58,
        "y": 0.58,
        "w": 0.20,
        "h": 0.20,
    },
    {
        "id": "recepcion",
        "label": "Recepción",
        "aliases": (
            "recepcion",
            "recepción",
            "entrada",
            "reception",
            "esquina inferior derecha",
        ),
        "x": -0.58,
        "y": -0.40,
        "w": 0.20,
        "h": 0.18,
    },
    # --- Pasillos / eje (cajas naranjas centrales y laterales) ---
    {
        "id": "pasillo_norte",
        "label": "Pasillo norte",
        "aliases": (
            "pasillo norte",
            "norte",
            "arriba",
            "pasillo superior",
            "cruce norte",
        ),
        "x": 0.58,
        "y": 0.0,
        "w": 0.28,
        "h": 0.16,
    },
    {
        "id": "pasillo_sur",
        "label": "Pasillo sur",
        "aliases": (
            "pasillo sur",
            "sur",
            "abajo",
            "pasillo inferior",
            "cruce sur",
        ),
        "x": -0.55,
        "y": 0.0,
        "w": 0.20,
        "h": 0.28,
    },
    {
        "id": "pasillo_oeste",
        "label": "Pasillo oeste",
        "aliases": (
            "pasillo oeste",
            "oeste",
            "pasillo izquierdo",
            "lado izquierdo",
        ),
        "x": 0.0,
        "y": 0.58,
        "w": 0.16,
        "h": 0.24,
    },
    {
        "id": "pasillo_este",
        "label": "Pasillo este",
        "aliases": (
            "pasillo este",
            "este",
            "pasillo derecho",
            "lado derecho",
        ),
        "x": 0.0,
        "y": -0.40,
        "w": 0.16,
        "h": 0.22,
    },
    {
        "id": "centro",
        "label": "Centro",
        "aliases": ("centro", "patio", "cruz", "cruce", "logo", "medio"),
        "x": 0.05,
        "y": 0.0,
        "w": 0.22,
        "h": 0.22,
    },
]


def zones_for_map(map_id: str) -> List[Dict[str, Any]]:
    if "laboratorio" not in (map_id or ""):
        return []
    out = []
    for z in LAB_ZONES:
        out.append(
            {
                "id": z["id"],
                "label": z["label"],
                "x": z["x"],
                "y": z["y"],
                "w": z["w"],
                "h": z["h"],
                "radius": max(z["w"], z["h"]) * 0.5,
            }
        )
    return out


def resolve_zone(destination: str) -> Optional[Dict[str, Any]]:
    """Resuelve 'voy a recepción' / 'almacen' / 'warehouse' → zona canónica."""
    raw = (destination or "").strip().lower()
    if not raw:
        return None
    # No tratar giros puros como zona (izquierda/derecha solos)
    if raw in ("izquierda", "derecha", "left", "right", "adelante", "atras", "atrás"):
        return None
    for pref in (
        "la ",
        "el ",
        "al ",
        "a la ",
        "a el ",
        "del ",
        "de la ",
        "voy a ",
        "ve a ",
        "ve al ",
        "ir a ",
        "ir al ",
        "dirígete a ",
        "dirigete a ",
        "navega a ",
        "navega al ",
    ):
        if raw.startswith(pref):
            raw = raw[len(pref) :].strip()
    raw = raw.replace("_", " ").strip()

    for z in LAB_ZONES:
        keys = {z["id"].replace("_", " "), z["label"].lower(), *z["aliases"]}
        if raw in keys:
            return z

    for z in LAB_ZONES:
        keys = {z["id"].replace("_", " "), z["label"].lower(), *z["aliases"]}
        for k in keys:
            if len(k) < 4:
                continue
            if k in raw or raw in k:
                return z
    return None


def zone_goal_xy(zone: Dict[str, Any]) -> Tuple[float, float]:
    return float(zone["x"]), float(zone["y"])


def odom_to_map(
    x: float, y: float, theta: float, align: Dict[str, float]
) -> Tuple[float, float, float]:
    yaw = float(align["yaw"])
    c, s = math.cos(yaw), math.sin(yaw)
    mx = c * x - s * y + float(align["tx"])
    my = s * x + c * y + float(align["ty"])
    return mx, my, theta + yaw


def zone_catalog_for_prompt() -> str:
    lines = [
        "Zonas del lab (destination = id o label):",
    ]
    for z in LAB_ZONES:
        lines.append(f'- {z["id"]} / "{z["label"]}"')
    lines.append(
        'Ejemplos: "voy a almacén", "ve a sala de máquinas", '
        '"ve al pasillo norte", "dirígete a recepción".'
    )
    return "\n".join(lines)
