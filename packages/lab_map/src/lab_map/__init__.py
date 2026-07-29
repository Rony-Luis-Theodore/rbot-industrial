"""lab_map — Occupancy lab stack (SE2 vivo + geometría fija)."""

from .constants import (
    DISPLAY_YAW,
    GEOMETRY_VERSION,
    LIDAR_HEADING_FLIP,
    LIDAR_YAW,
    PERIMETER_YAW_META,
    SESSION_VERSION,
    TRAIL_MAX_STEP_M,
)
from .geometry import frozen_geometry, load_obstacles, load_track
from .localize import localize_in_track, refine_translation
from .se2 import (
    forward_delta_map,
    normalize_session_align,
    project_pose,
    seed_align_from_map_pose,
    skew_to_cardinal_deg,
    wrap_pi,
)
from .trail import append_point, max_step, shift_trail

__all__ = [
    "DISPLAY_YAW",
    "GEOMETRY_VERSION",
    "LIDAR_HEADING_FLIP",
    "LIDAR_YAW",
    "PERIMETER_YAW_META",
    "SESSION_VERSION",
    "TRAIL_MAX_STEP_M",
    "append_point",
    "forward_delta_map",
    "frozen_geometry",
    "load_obstacles",
    "load_track",
    "localize_in_track",
    "max_step",
    "normalize_session_align",
    "project_pose",
    "refine_translation",
    "seed_align_from_map_pose",
    "shift_trail",
    "skew_to_cardinal_deg",
    "wrap_pi",
]
