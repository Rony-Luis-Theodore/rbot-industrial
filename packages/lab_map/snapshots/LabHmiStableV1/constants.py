"""Checkpoint LabTrayectoriaOK — validado 2026-07-27 en lab real.

NO TOCAR SE2 / orientación / escala sin petición explícita.
Snapshot: packages/lab_map/snapshots/LabTrayectoriaOK/
"""

from __future__ import annotations

import math

LIDAR_YAW: float = -math.pi / 2
LIDAR_HEADING_FLIP: float = 0.0
HEADING_LOCKED: bool = True
HEADING_BIAS_RAD: float = math.pi
DISPLAY_YAW: float = math.pi / 2
PERIMETER_YAW_META: float = 1.570083462815548

MAP_ALIGN_NUDGE_TX: float = -0.06
MAP_ALIGN_NUDGE_TY: float = 0.0
LOCALIZE_OUTWARD_M: float = 0.18
LOCALIZE_MIRROR_X: bool = True

ODOM_TO_MAP_SCALE: float = 7.0 / 6.0
ODOM_Y_SIGN: float = -1.0
# Capa HMI: invierte izq/der (tip LiDAR OK). Pedido explícito post-LabTrayectoriaOK.
LOCALIZE_INVERT_LR: bool = True
REQUIRE_MANUAL_UBICAR: bool = True

TRAIL_MAX_STEP_M: float = 0.55
TRAIL_MIN_STEP_M: float = 0.015
TRAIL_MAX_POINTS: int = 900

LOCALIZE_SCORE_MIN_FRAC: float = 0.12
REFINE_T_RADIUS_M: float = 0.40
REFINE_T_MIN_DELTA_M: float = 0.04

SESSION_SOURCE: str = "lidar_in_track"
GEOMETRY_VERSION: str = "lab-geometry-v1"
SESSION_VERSION: str = "lab-hmi-chat-v1"
SNAPSHOT_NAME: str = "LabHmiStableV1"
