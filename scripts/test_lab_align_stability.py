#!/usr/bin/env python3
"""Regresión lab_map: geometría fija + session SE2 + trazo sin wipe."""

from __future__ import annotations

import json
import math
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "http://127.0.0.1:8000"
TRACES = ROOT / "apps/api/app/services/lab_obstacle_traces"
LAB_MAP_SRC = ROOT / "packages" / "lab_map" / "src"
sys.path.insert(0, str(LAB_MAP_SRC))

from lab_map.geometry import closed_vertices_fingerprint, frozen_geometry  # noqa: E402
from lab_map.se2 import forward_delta_map, seed_align_from_map_pose, skew_to_cardinal_deg  # noqa: E402
from lab_map.trail import append_point, continuous_segment_count  # noqa: E402


def get(url: str):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode())


def post(url: str, body: dict):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def main() -> int:
    fails = []

    # Unit invariants (no API)
    try:
        g = frozen_geometry()
        assert len(g["trail_map_closed"]) >= 4
        assert len(g["obstacle_boxes"]) == 4
    except Exception as exc:
        fails.append(f"frozen_geometry: {exc}")

    try:
        odom = {"x": 0.0, "y": 0.0, "theta": -2.5}
        bad = {"yaw": math.pi / 2, "tx": 0.0, "ty": 0.0}
        dx, dy = forward_delta_map(odom, bad, 0.3)
        assert skew_to_cardinal_deg(dx, dy) > 20.0
        good = seed_align_from_map_pose(0.0, 0.0, math.pi / 2 - math.pi, odom, apply_lidar_flip=True)
        dx2, dy2 = forward_delta_map(odom, good, 0.3)
        assert skew_to_cardinal_deg(dx2, dy2) < 5.0
    except Exception as exc:
        fails.append(f"diagonal_invariant: {exc}")

    try:
        trail = append_point([], 0, 0)
        trail = append_point(trail, 0.1, 0)
        n = len(trail)
        trail = append_point(trail, 2, 2, allow_break=True)
        assert len(trail) == n + 1 and continuous_segment_count(trail) == 2
    except Exception as exc:
        fails.append(f"trail_gap: {exc}")

    # API
    try:
        health = get(f"{API}/api/v1/health")
        assert health.get("status") == "ok"
    except Exception as exc:
        fails.append(f"health: {exc}")
        print("FAILS", fails)
        return 1

    try:
        geom = get(f"{API}/api/v1/robot/lab/geometry")
        assert geom["geometry"]["trail_map_closed"]
        assert len(geom["geometry"]["obstacle_boxes"]) == 4
    except Exception as exc:
        fails.append(f"lab/geometry: {exc}")

    track = json.loads((TRACES / "track_perimeter.json").read_text())
    fp0 = closed_vertices_fingerprint(track.get("trail_map_closed") or [])

    try:
        out = post(
            f"{API}/api/v1/robot/lab/session/align",
            {"yaw": -2.1, "tx": 0.4, "ty": -0.2},
        )
        assert out.get("ok")
        track2 = json.loads((TRACES / "track_perimeter.json").read_text())
        fp1 = closed_vertices_fingerprint(track2.get("trail_map_closed") or [])
        assert fp0 == fp1, "trail_map_closed mutated"
        live = track2.get("live_align") or {}
        assert abs(float(live["yaw"]) + 2.1) < 0.05 or abs(float(live["yaw"]) - (-2.1)) < 0.05
        # must NOT be clamped to ±π/2
        assert abs(abs(float(live["yaw"])) - math.pi / 2) > 0.3
    except Exception as exc:
        fails.append(f"session/align: {exc}")

    try:
        lab = get(f"{API}/api/v1/robot/lab_traces")
        assert lab.get("geometry") or lab.get("track")
        assert lab.get("align") is not None or lab.get("session")
    except Exception as exc:
        fails.append(f"lab_traces: {exc}")

    if fails:
        print("FAIL")
        for f in fails:
            print(" -", f)
        return 1
    print("OK lab_map stability")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
