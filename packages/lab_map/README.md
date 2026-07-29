# lab_map

Stack Occupancy del laboratorio Maze Runner (R-Bot Industrial).

## Invariantes (validados en lab real — no romper)

1. Overlays (`trail_map_closed`, obstacles) son coords Occupancy fijas.
2. SE2 vivo: `ψ = θ_map − θ_odom` (+ `LIDAR_HEADING_FLIP` al sembrar LiDAR).
3. `DISPLAY_YAW = π/2` solo en render (icono: `θ_map + DISPLAY_YAW`, sin ±π inventados).
4. `perimeter_yaw` es metadato del grabado; no clampear `live_align`.
5. Tras **Ubicar**: congelar ψ. Al manejar **solo** `project` + trazo; refine-t no toca yaw.
6. Trazo en **odom** (`trailOdom`), proyectado al Occupancy al dibujar. gaps ≠ wipe.
7. Un solo escritor de SE2. Prohibido re-resolver rumbo/π en un loop al teleoperar
   (eso reintroduce L/R y adelante/atrás invertidos).

## Layout

- `src/lab_map/` — núcleo Python (SE2, localize, refine-t, trail, geometry)
- `assets/` — snapshot de perimeter + 4 obstacles
- `tests/test_invariants.py`

## Uso

```bash
cd packages/lab_map && python3 tests/test_invariants.py
python3 scripts/test_lab_align_stability.py
```
