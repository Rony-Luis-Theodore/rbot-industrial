"""Invariantes del stack lab Occupancy."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lab_map.geometry import (  # noqa: E402
    closed_vertices_fingerprint,
    frozen_geometry,
    load_track,
)
from lab_map.se2 import (  # noqa: E402
    forward_delta_map,
    project_pose,
    seed_align_from_map_pose,
    skew_to_cardinal_deg,
)
from lab_map.trail import append_point, continuous_segment_count, max_step, shift_trail  # noqa: E402


def test_frozen_geometry_has_cyan_and_boxes():
    g = frozen_geometry()
    assert len(g["trail_map_closed"]) >= 4
    assert g["map_box"]
    assert len(g["obstacle_boxes"]) == 4
    assert abs(g["perimeter_yaw_meta"] - math.pi / 2) < 0.05


def test_seed_align_not_perimeter_locked():
    """ψ = θ_map (+FLIP) − θ_odom; FLIP=0 tras validación 2026-07-27."""
    odom = {"x": -0.4, "y": -1.0, "theta": -2.5}
    map_th = 0.3
    align = seed_align_from_map_pose(0.2, 0.1, map_th, odom, apply_lidar_flip=True)
    # FLIP=0 → yaw = map_th - odom.theta
    expected = math.atan2(math.sin(0.3 + 2.5), math.cos(0.3 + 2.5))
    assert abs(align["yaw"] - expected) < 1e-6
    assert abs(abs(align["yaw"]) - math.pi / 2) > 0.2  # not locked to π/2


def test_locked_psi_causes_diagonal_regression():
    """Documenta el bug: ψ=π/2 con odom θ≠0 → avance no axial."""
    odom = {"x": 0.0, "y": 0.0, "theta": -2.5}
    bad = {"yaw": math.pi / 2, "tx": 0.0, "ty": 0.0}
    dx, dy = forward_delta_map(odom, bad, 0.3)
    skew_bad = skew_to_cardinal_deg(dx, dy)
    # Good: ψ chosen so map heading is cardinal (+Y)
    map_head = math.pi / 2
    good = seed_align_from_map_pose(
        0.0,
        0.0,
        map_head,  # FLIP=0: θ_map = map_head
        odom,
        apply_lidar_flip=True,
    )
    dx2, dy2 = forward_delta_map(odom, good, 0.3)
    skew_good = skew_to_cardinal_deg(dx2, dy2)
    assert skew_good < 5.0
    assert skew_bad > 20.0  # locked perimeter yaw is diagonal for this odom


def test_trail_gap_does_not_wipe():
    trail = []
    trail = append_point(trail, 0.0, 0.0)
    trail = append_point(trail, 0.1, 0.0)
    trail = append_point(trail, 0.2, 0.0)
    n = len(trail)
    trail = append_point(trail, 2.0, 2.0, allow_break=True)  # big jump
    assert len(trail) == n + 1
    assert trail[-1].get("gap") is True
    assert continuous_segment_count(trail) == 2


def test_shift_trail_preserves_length():
    trail = append_point([], 0.0, 0.0)
    trail = append_point(trail, 0.1, 0.05)
    shifted = shift_trail(trail, -0.3, 0.1)
    assert len(shifted) == len(trail)
    assert abs(shifted[0]["x"] + 0.3) < 1e-9


def test_update_live_align_must_not_mutate_closed(tmp_path: Path | None = None):
    """Simula: fingerprint de cyan intacto tras escribir live_align."""
    track = load_track()
    fp0 = closed_vertices_fingerprint(track["trail_map_closed"])
    # mutate only live fields in a copy
    track2 = json.loads(json.dumps(track))
    track2["live_align"] = {
        "yaw": -2.2,
        "tx": 0.5,
        "ty": -0.3,
        "ready": True,
        "source": "lidar_in_track",
    }
    track2["align_canonical"] = dict(track2["live_align"])
    fp1 = closed_vertices_fingerprint(track2["trail_map_closed"])
    assert fp0 == fp1


def test_project_pose_roundtrip_tip():
    from lab_map.constants import MAP_ALIGN_NUDGE_TX, MAP_ALIGN_NUDGE_TY

    odom = {"x": 0.1, "y": -0.2, "theta": 0.3}
    align = seed_align_from_map_pose(0.5, 0.25, 1.0, odom, apply_lidar_flip=True)
    tip = project_pose(odom, align)
    assert abs(tip["x"] - (0.5 + MAP_ALIGN_NUDGE_TX)) < 1e-9
    assert abs(tip["y"] - (0.25 + MAP_ALIGN_NUDGE_TY)) < 1e-9


if __name__ == "__main__":
    # minimal runner without pytest dependency
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            fn()
            print("OK", fn.__name__)
        except Exception as exc:
            failed += 1
            print("FAIL", fn.__name__, exc)
    raise SystemExit(failed)
