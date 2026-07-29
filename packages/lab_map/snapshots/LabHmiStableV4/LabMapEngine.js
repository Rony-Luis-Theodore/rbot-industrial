/**
 * LabMapEngine — SE2 + localize + refine-t + trail helpers.
 * Drive: ψ congelado; solo refineTranslation. Prohibido reabrir yaw al manejar.
 */

import {
  ALIGN_VER,
  LIDAR_HEADING_FLIP,
  LIDAR_YAW,
  LOCALIZE_MIRROR_X,
  LOCALIZE_OUTWARD_M,
  LOCALIZE_SCORE_MIN_FRAC,
  MAP_ALIGN_NUDGE,
  HEADING_BIAS_RAD,
  ODOM_TO_MAP_SCALE,
  effectiveOdomYSign,
  PERIMETER_YAW_META,
  REFINE_T_RADIUS_M,
  SESSION_SOURCE,
  TRACK_FLIP_IMPROVE,
  TRACK_MIN_IMPROVE,
  TRACK_XY_RADIUS_M,
  TRACK_YAW_RADIUS_RAD,
  TRAIL_MAX_POINTS,
  TRAIL_MAX_STEP_M,
  TRAIL_MIN_STEP_M,
} from "./constants.js";

export function wrapPi(a) {
  return Math.atan2(Math.sin(a), Math.cos(a));
}

export function createEmptyAlign() {
  return { tx: 0, ty: 0, yaw: 0, sx: 1, sy: 1, ready: false, source: "none" };
}

export function isNavigableAlign(a) {
  return Boolean(a?.ready) && Number.isFinite(a.yaw) && Number.isFinite(a.tx);
}

export function projectPose(odom, align) {
  const sx = Number(align?.sx) || ODOM_TO_MAP_SCALE;
  const ySign = effectiveOdomYSign();
  // Siempre reaplicar signo vivo (evita izq/der invertidos tras re-Ubicar con sy viejo).
  const sy = Math.abs(Number.isFinite(Number(align?.sy)) ? Number(align.sy) : sx) * ySign;
  const ox = (odom?.x || 0) * sx;
  const oy = (odom?.y || 0) * sy;
  const oth = odom?.theta || 0;
  const yaw = align?.yaw || 0;
  const c = Math.cos(yaw);
  const s = Math.sin(yaw);
  const theta = sy < 0 ? wrapPi(yaw - oth) : wrapPi(oth + yaw);
  return {
    x: c * ox - s * oy + (align?.tx || 0),
    y: s * ox + c * oy + (align?.ty || 0),
    theta,
  };
}

export function seedAlignFromMapPose(
  mx,
  my,
  mapTh,
  odom,
  { applyFlip = true, applyBias = true, source = SESSION_SOURCE } = {}
) {
  const sx = ODOM_TO_MAP_SCALE;
  const sy = Math.abs(ODOM_TO_MAP_SCALE) * effectiveOdomYSign();
  const ox = (odom?.x || 0) * sx;
  const oy = (odom?.y || 0) * sy;
  const oth = odom?.theta || 0;
  let th = Number(mapTh) || 0;
  if (applyFlip) th = wrapPi(th + LIDAR_HEADING_FLIP);
  // +π solo al rumbo (F/B); el tip LiDAR (mx,my) no se mueve.
  if (applyBias) th = wrapPi(th + HEADING_BIAS_RAD);
  // sy<0 → ψ = θ_map + θ_odom; sy>0 → ψ = θ_map − θ_odom
  const yaw = sy < 0 ? wrapPi(th + oth) : wrapPi(th - oth);
  const c = Math.cos(yaw);
  const s = Math.sin(yaw);
  return {
    yaw,
    tx: mx - (c * ox - s * oy) + MAP_ALIGN_NUDGE.tx,
    ty: my - (s * ox + c * oy) + MAP_ALIGN_NUDGE.ty,
    sx,
    sy,
    ready: true,
    source,
    note: "LabTrayectoriaOK SE2 + capa LOCALIZE_INVERT_LR",
  };
}

export function appendTrailPoint(trail, x, y, { allowBreak = true } = {}) {
  const out = trail ? trail.slice() : [];
  if (!out.length) {
    out.push({ x, y });
    return out.length > TRAIL_MAX_POINTS ? out.slice(-TRAIL_MAX_POINTS) : out;
  }
  const last = out[out.length - 1];
  const step = Math.hypot(x - last.x, y - last.y);
  if (step < TRAIL_MIN_STEP_M) return out;
  if (step > TRAIL_MAX_STEP_M) {
    if (allowBreak) out.push({ x, y, gap: true });
    return out.length > TRAIL_MAX_POINTS ? out.slice(-TRAIL_MAX_POINTS) : out;
  }
  out.push({ x, y });
  return out.length > TRAIL_MAX_POINTS ? out.slice(-TRAIL_MAX_POINTS) : out;
}

export function shiftTrail(trail, dtx, dty) {
  if (!trail?.length) return trail || [];
  if (Math.hypot(dtx, dty) < 1e-9) return trail.slice();
  return trail.map((p) => ({ ...p, x: p.x + dtx, y: p.y + dty }));
}

export function trackAabb(closed, pad = 0.08) {
  if (!closed || closed.length < 4) return null;
  const xs = closed.map((p) => Number(p.x));
  const ys = closed.map((p) => Number(p.y));
  return {
    minX: Math.min(...xs) + pad,
    minY: Math.min(...ys) + pad,
    maxX: Math.max(...xs) - pad,
    maxY: Math.max(...ys) - pad,
  };
}

/** Ray casting: punto dentro del polígono cerrado Occupancy (cian). */
export function pointInClosed(x, y, closed) {
  if (!closed || closed.length < 3) return false;
  let inside = false;
  for (let i = 0, j = closed.length - 1; i < closed.length; j = i++) {
    const xi = Number(closed[i].x);
    const yi = Number(closed[i].y);
    const xj = Number(closed[j].x);
    const yj = Number(closed[j].y);
    const hit =
      yi > y !== yj > y &&
      x < ((xj - xi) * (y - yi)) / (yj - yi + 1e-15) + xi;
    if (hit) inside = !inside;
  }
  return inside;
}

export function tipInsideTrack(x, y, closed, pad = 0.05) {
  const box = trackAabb(closed, pad);
  if (!box) return false;
  if (x < box.minX || x > box.maxX || y < box.minY || y > box.maxY) return false;
  // pad < 0 = zona holgada (solo AABB) para no perder el trazo en bordes
  if (pad < 0) return true;
  return pointInClosed(x, y, closed);
}

function closestOnSegment(px, py, ax, ay, bx, by) {
  const abx = bx - ax;
  const aby = by - ay;
  const t = Math.max(
    0,
    Math.min(1, ((px - ax) * abx + (py - ay) * aby) / (abx * abx + aby * aby + 1e-15))
  );
  return { x: ax + t * abx, y: ay + t * aby };
}

/** Proyecta un punto fuera al borde del cian y lo mete un poco hacia el centro. */
export function clampPointToClosed(x, y, closed, inset = 0.05) {
  if (!closed || closed.length < 3) return { x, y };
  if (pointInClosed(x, y, closed)) return { x, y };
  let best = { x, y, d: Infinity };
  const n = closed.length;
  for (let i = 0; i < n; i++) {
    const a = closed[i];
    const b = closed[(i + 1) % n];
    const p = closestOnSegment(x, y, Number(a.x), Number(a.y), Number(b.x), Number(b.y));
    const d = Math.hypot(p.x - x, p.y - y);
    if (d < best.d) best = { x: p.x, y: p.y, d };
  }
  let cx = 0;
  let cy = 0;
  for (const p of closed) {
    cx += Number(p.x);
    cy += Number(p.y);
  }
  cx /= n;
  cy /= n;
  const vx = cx - best.x;
  const vy = cy - best.y;
  const L = Math.hypot(vx, vy) || 1;
  return { x: best.x + (vx / L) * inset, y: best.y + (vy / L) * inset };
}

export function clampPointToAabb(x, y, box) {
  if (!box) return { x, y };
  return {
    x: Math.min(box.maxX, Math.max(box.minX, x)),
    y: Math.min(box.maxY, Math.max(box.minY, y)),
  };
}

/**
 * AABB de muros dorados (celdas occupied) del Occupancy.
 * inset > 0 mete el límite hacia el interior libre (casi calza el dorado).
 */
export function extractWallBox(mapGrid, mapW, mapH, mapMeta, inset = 0.04) {
  if (!mapGrid || !mapMeta) return null;
  const res = Number(mapMeta.resolution) || 0.05;
  const origin = mapMeta.origin || [0, 0];
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  let n = 0;
  for (let my = 0; my < mapH; my++) {
    for (let mx = 0; mx < mapW; mx++) {
      if (mapGrid[(mapH - 1 - my) * mapW + mx] !== 1) continue;
      const x = origin[0] + (mx + 0.5) * res;
      const y = origin[1] + (my + 0.5) * res;
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
      n += 1;
    }
  }
  if (!n) return null;
  return {
    minX: minX + inset,
    minY: minY + inset,
    maxX: maxX - inset,
    maxY: maxY - inset,
  };
}

export function wallBoxToClosed(box) {
  if (!box) return [];
  return [
    { x: box.minX, y: box.minY },
    { x: box.maxX, y: box.minY },
    { x: box.maxX, y: box.maxY },
    { x: box.minX, y: box.maxY },
    { x: box.minX, y: box.minY },
  ];
}

/** Cardinales Occupancy (LiDAR). HEADING_BIAS F/B se aplica solo al sembrar yaw. */
function mapCardinals() {
  return [0, Math.PI / 2, Math.PI, -Math.PI / 2];
}

/** Elige el rumbo Occupancy más cercano a ejes del mapa (anti-rombo 45°). */
export function bestCardinalHeading(x, y, thHint, rays, mapGrid, mapW, mapH, origin, res) {
  const cards = mapCardinals();
  let best = { th: snapToCardinal(thHint), score: -1e9 };
  for (const th of cards) {
    const score = scoreRaycast(x, y, th, rays, mapGrid, mapW, mapH, origin, res);
    if (score > best.score) best = { th, score };
  }
  return best.th;
}

export function snapToCardinal(th) {
  const cards = mapCardinals();
  let best = cards[0];
  let bestD = Infinity;
  for (const c of cards) {
    const d = Math.abs(wrapPi(th - c));
    if (d < bestD) {
      bestD = d;
      best = c;
    }
  }
  return best;
}

/** Acerca el tip a muros/esquinas (LiDAR tiende al centro del carril). */
function pushOutwardFromCenter(x, y, box, meters = LOCALIZE_OUTWARD_M) {
  if (!box || !(meters > 0)) return { x, y };
  const cx = (box.minX + box.maxX) * 0.5;
  const cy = (box.minY + box.maxY) * 0.5;
  const dx = x - cx;
  const dy = y - cy;
  const d = Math.hypot(dx, dy);
  if (d < 0.05) return { x, y };
  const f = (d + meters) / d;
  const pad = 0.05;
  return {
    x: Math.min(box.maxX - pad, Math.max(box.minX + pad, cx + dx * f)),
    y: Math.min(box.maxY - pad, Math.max(box.minY + pad, cy + dy * f)),
  };
}

/** Quita puntos fuera del perímetro (el trazo no debe “salirse” del mapa). */
export function clipTrailToTrack(trail, closed, pad = 0.02) {
  if (!trail?.length || !closed?.length) return trail || [];
  const out = [];
  let wasOut = false;
  for (const p of trail) {
    if (tipInsideTrack(p.x, p.y, closed, pad)) {
      if (wasOut && out.length) out.push({ x: p.x, y: p.y, gap: true });
      else out.push(p);
      wasOut = false;
    } else {
      wasOut = true;
    }
  }
  return out.length > TRAIL_MAX_POINTS ? out.slice(-TRAIL_MAX_POINTS) : out;
}

export function flipAlignHeading(align, odom) {
  if (!isNavigableAlign(align) || !odom) return align;
  const tip = projectPose(odom, align);
  const yaw = wrapPi((align.yaw || 0) + Math.PI);
  const sx = Number(align?.sx) || ODOM_TO_MAP_SCALE;
  const sy = Math.abs(sx) * effectiveOdomYSign();
  const c = Math.cos(yaw);
  const s = Math.sin(yaw);
  const ox = (odom.x || 0) * sx;
  const oy = (odom.y || 0) * sy;
  return {
    ...align,
    yaw,
    tx: tip.x - (c * ox - s * oy),
    ty: tip.y - (s * ox + c * oy),
    sx,
    sy,
    ready: true,
    note: "heading flipped π; tip preserved",
  };
}

function sampleRays(scan) {
  const rays = [];
  const amin = Number(scan?.angle_min) || 0;
  const ranges = scan?.ranges || [];
  const ainc =
    Number(scan?.angle_increment) || (2 * Math.PI) / Math.max(ranges.length, 1);
  ranges.forEach((range, i) => {
    if (i % 2 !== 0) return;
    if (range == null || !Number.isFinite(range) || range < 0.08 || range > 3.5) return;
    rays.push({ range, ang: amin + i * ainc + LIDAR_YAW });
  });
  return rays;
}

function raycastRange(rx, ry, ang, mapGrid, mapW, mapH, origin, res, maxR = 3.5) {
  const step = res * 0.5;
  let r = 0;
  while (r < maxR) {
    r += step;
    const wx = rx + r * Math.cos(ang);
    const wy = ry + r * Math.sin(ang);
    const mx = Math.floor((wx - origin[0]) / res);
    const my = Math.floor((wy - origin[1]) / res);
    if (mx < 0 || my < 0 || mx >= mapW || my >= mapH) return r;
    if (mapGrid[(mapH - 1 - my) * mapW + mx] === 1) return r;
  }
  return maxR;
}

export function scoreRaycast(rx, ry, rth, rays, mapGrid, mapW, mapH, origin, res) {
  const mx0 = Math.floor((rx - origin[0]) / res);
  const my0 = Math.floor((ry - origin[1]) / res);
  if (mx0 < 0 || my0 < 0 || mx0 >= mapW || my0 >= mapH) return -1e9;
  if (mapGrid[(mapH - 1 - my0) * mapW + mx0] !== 0) return -1e9;
  let score = 0;
  const sigma = 0.11;
  for (const ray of rays) {
    const pred = raycastRange(rx, ry, ray.ang + rth, mapGrid, mapW, mapH, origin, res);
    const err = pred - ray.range;
    score += Math.exp(-(err * err) / (sigma * sigma));
  }
  return score;
}

function cellFree(x, y, mapGrid, mapW, mapH, origin, res) {
  const mx = Math.floor((x - origin[0]) / res);
  const my = Math.floor((y - origin[1]) / res);
  if (mx < 1 || my < 1 || mx >= mapW - 1 || my >= mapH - 1) return false;
  return mapGrid[(mapH - 1 - my) * mapW + mx] === 0;
}

function inObs(x, y, boxes, margin = 0.05) {
  return (boxes || []).some(
    (b) =>
      x >= b.minx - margin &&
      x <= b.maxx + margin &&
      y >= b.miny - margin &&
      y <= b.maxy + margin
  );
}

function yawTrials(odomTheta, perimeterYawMeta = PERIMETER_YAW_META) {
  // θ_map en Occupancy (ejes del mapa). NUNCA prior = perimeter+odom
  // (eso fuerza ψ≈π/2 → rombo / diagonal tras giros de 90°).
  void odomTheta;
  const trials = [];
  const bases = [0, Math.PI / 2, Math.PI, -Math.PI / 2, perimeterYawMeta];
  for (const base of bases) {
    for (let d = -0.45; d <= 0.45 + 1e-9; d += 0.15) {
      trials.push(wrapPi(base + d));
    }
  }
  return trials;
}

/**
 * @returns {{ align, tip, score } | null}
 */
export function localizeInTrack({
  odom,
  scan,
  closed,
  boxes,
  mapGrid,
  mapW,
  mapH,
  mapMeta,
  perimeterYawMeta = PERIMETER_YAW_META,
}) {
  if (!mapGrid || !mapMeta) return null;
  const rays = sampleRays(scan);
  if (rays.length < 10) return null;
  const res = Number(mapMeta.resolution) || 0.05;
  const origin = mapMeta.origin || [0, 0, 0];
  // Límite = muros dorados Occupancy (casi calzados), no el PGM completo.
  const wallBox =
    extractWallBox(mapGrid, mapW, mapH, mapMeta, 0.02) || {
      minX: origin[0] + res,
      minY: origin[1] + res,
      maxX: origin[0] + mapW * res - res,
      maxY: origin[1] + mapH * res - res,
    };
  const box = wallBox;
  const trackBox = closed && closed.length >= 4 ? trackAabb(closed, 0.02) : null;
  void trackBox;
  const obsBoxes = (boxes || [])
    .map((o) => o.box || o.map_box || o)
    .filter((b) => b && Number.isFinite(Number(b.minx ?? b.minX)))
    .map((b) => ({
      minx: Number(b.minx ?? b.minX),
      maxx: Number(b.maxx ?? b.maxX),
      miny: Number(b.miny ?? b.minY),
      maxy: Number(b.maxy ?? b.maxY),
    }));

  const freeCells = [];
  for (let my = 1; my < mapH - 1; my++) {
    for (let mx = 1; mx < mapW - 1; mx++) {
      if (mapGrid[(mapH - 1 - my) * mapW + mx] !== 0) continue;
      const x = origin[0] + (mx + 0.5) * res;
      const y = origin[1] + (my + 0.5) * res;
      if (x < box.minX || x > box.maxX || y < box.minY || y > box.maxY) continue;
      if (inObs(x, y, obsBoxes, 0.03)) continue;
      freeCells.push({ x, y });
    }
  }
  if (!freeCells.length) return null;

  // Rumbo LiDAR en ejes Occupancy; F/B (+π) solo al sembrar yaw (tip no se mueve).
  const trials = [];
  const cx = (box.minX + box.maxX) * 0.5;
  const cy = (box.minY + box.maxY) * 0.5;
  const maxR = Math.hypot(box.maxX - box.minX, box.maxY - box.minY) * 0.5 || 1;
  for (const card of mapCardinals()) {
    for (let d = -0.25; d <= 0.25 + 1e-9; d += 0.125) {
      trials.push(wrapPi(card + d));
    }
  }
  void perimeterYawMeta;

  let best = { score: -1e9, x: 0, y: 0, th: 0 };
  const stride = freeCells.length > 800 ? 2 : 1;
  for (const th of trials) {
    for (let i = 0; i < freeCells.length; i += stride) {
      const c = freeCells[i];
      let score = scoreRaycast(c.x, c.y, th, rays, mapGrid, mapW, mapH, origin, res);
      // Preferir muros/esquinas frente al centro del carril.
      const dist = Math.hypot(c.x - cx, c.y - cy);
      score *= 1 + 0.35 * (dist / maxR);
      if (score > best.score) best = { score, x: c.x, y: c.y, th };
    }
  }
  let refined = {
    score: scoreRaycast(best.x, best.y, best.th, rays, mapGrid, mapW, mapH, origin, res),
    x: best.x,
    y: best.y,
    th: best.th,
  };
  for (let dx = -0.12; dx <= 0.12; dx += 0.03) {
    for (let dy = -0.12; dy <= 0.12; dy += 0.03) {
      for (let dth = -0.15; dth <= 0.15; dth += 0.05) {
        const x = best.x + dx;
        const y = best.y + dy;
        if (x < box.minX || x > box.maxX || y < box.minY || y > box.maxY) continue;
        if (inObs(x, y, obsBoxes, 0.03) || !cellFree(x, y, mapGrid, mapW, mapH, origin, res))
          continue;
        const th = wrapPi(best.th + dth);
        const score = scoreRaycast(x, y, th, rays, mapGrid, mapW, mapH, origin, res);
        if (score > refined.score) refined = { score, x, y, th };
      }
    }
  }
  if (refined.score < rays.length * LOCALIZE_SCORE_MIN_FRAC) return null;

  refined.th = bestCardinalHeading(
    refined.x,
    refined.y,
    refined.th,
    rays,
    mapGrid,
    mapW,
    mapH,
    origin,
    res
  );

  // Espejo vertical en pantalla (arriba↔abajo): flip X Occupancy + rumbo.
  if (LOCALIZE_MIRROR_X) {
    refined.x = box.minX + box.maxX - refined.x;
    refined.th = wrapPi(Math.PI - refined.th);
    refined.th = bestCardinalHeading(
      refined.x,
      refined.y,
      refined.th,
      rays,
      mapGrid,
      mapW,
      mapH,
      origin,
      res
    );
  }

  // LiDAR suele ganar en el centro del carril; empuja un poco a muro/esquina.
  const outward = pushOutwardFromCenter(refined.x, refined.y, box, LOCALIZE_OUTWARD_M);
  if (cellFree(outward.x, outward.y, mapGrid, mapW, mapH, origin, res) && !inObs(outward.x, outward.y, obsBoxes, 0.03)) {
    refined = { ...refined, x: outward.x, y: outward.y };
  }

  const align = seedAlignFromMapPose(refined.x, refined.y, refined.th, odom, {
    applyFlip: true,
    source: SESSION_SOURCE,
  });
  return {
    align,
    tip: { x: refined.x, y: refined.y },
    /** Rumbo Occupancy pre-bias; re-sembrar con odom fresca al cerrar Ubicar. */
    mapTh: refined.th,
    score: refined.score,
    flipApplied: Math.abs(LIDAR_HEADING_FLIP) > 1e-6,
    wallBox,
  };
}

/**
 * Solo traslación. @returns {{ align, dtx, dty, dist, trailShift } | null}
 */
export function refineTranslation({
  odom,
  align,
  scan,
  closed,
  boxes,
  mapGrid,
  mapW,
  mapH,
  mapMeta,
  force = false,
}) {
  if (!isNavigableAlign(align) || !mapGrid || !mapMeta) return null;
  const rays = sampleRays(scan);
  if (rays.length < 10) return null;
  const res = Number(mapMeta.resolution) || 0.05;
  const origin = mapMeta.origin || [0, 0, 0];
  const tip0 = projectPose(odom, align);
  const mapTh = wrapPi((align.yaw || 0) + (odom?.theta || 0));
  const box = trackAabb(closed, 0.06);
  if (!box) return null;
  const obs = (boxes || []).map((o) => o.box || o).filter(Boolean);

  let best = {
    score: scoreRaycast(tip0.x, tip0.y, mapTh, rays, mapGrid, mapW, mapH, origin, res),
    x: tip0.x,
    y: tip0.y,
  };
  const R = REFINE_T_RADIUS_M;
  for (let dx = -R; dx <= R + 1e-9; dx += 0.04) {
    for (let dy = -R; dy <= R + 1e-9; dy += 0.04) {
      const x = tip0.x + dx;
      const y = tip0.y + dy;
      if (x < box.minX || x > box.maxX || y < box.minY || y > box.maxY) continue;
      if (inObs(x, y, obs, 0.04) || !cellFree(x, y, mapGrid, mapW, mapH, origin, res)) continue;
      const score = scoreRaycast(x, y, mapTh, rays, mapGrid, mapW, mapH, origin, res);
      if (score > best.score) best = { score, x, y };
    }
  }
  const dtx = best.x - tip0.x;
  const dty = best.y - tip0.y;
  const dist = Math.hypot(dtx, dty);
  if (dist < 0.04 && !force) return null;
  if (best.score < rays.length * 0.1) return null;
  if (dist > 0.55 && !force) return null;
  return {
    align: {
      ...align,
      tx: align.tx + dtx,
      ty: align.ty + dty,
      ready: true,
    },
    dtx,
    dty,
    dist,
  };
}

/**
 * Mismo principio que Ubicar, pero ventana local alrededor del tip actual.
 * Corrige tx/ty y, si el LiDAR lo exige, ambigüedad π / yaw pequeño.
 * No hace búsqueda global (no teleport).
 *
 * @returns {{ align, tip, dtx, dty, dth, score, flipped } | null}
 */
export function trackNearTip({
  odom,
  align,
  scan,
  closed,
  boxes,
  mapGrid,
  mapW,
  mapH,
  mapMeta,
}) {
  if (!isNavigableAlign(align) || !mapGrid || !mapMeta) return null;
  const rays = sampleRays(scan);
  if (rays.length < 10) return null;
  const res = Number(mapMeta.resolution) || 0.05;
  const origin = mapMeta.origin || [0, 0, 0];
  const tip0 = projectPose(odom, align);
  const th0 = tip0.theta;
  const box = trackAabb(closed, -0.02);
  if (!box) return null;
  const obs = (boxes || []).map((o) => o.box || o).filter(Boolean);

  const scoreAt = (x, y, th) =>
    scoreRaycast(x, y, th, rays, mapGrid, mapW, mapH, origin, res);

  const score0 = scoreAt(tip0.x, tip0.y, th0);
  const scoreFlip0 = scoreAt(tip0.x, tip0.y, wrapPi(th0 + Math.PI));

  let best = { score: score0, x: tip0.x, y: tip0.y, th: th0 };
  // Si el flip en el mismo tip ya gana claro → rumbo π invertido al manejar
  if (scoreFlip0 > score0 * TRACK_FLIP_IMPROVE) {
    best = { score: scoreFlip0, x: tip0.x, y: tip0.y, th: wrapPi(th0 + Math.PI) };
  }

  const R = TRACK_XY_RADIUS_M;
  const bases = [best.th, wrapPi(best.th + Math.PI)];
  for (let dx = -R; dx <= R + 1e-9; dx += 0.06) {
    for (let dy = -R; dy <= R + 1e-9; dy += 0.06) {
      const x = tip0.x + dx;
      const y = tip0.y + dy;
      if (x < box.minX || x > box.maxX || y < box.minY || y > box.maxY) continue;
      if (inObs(x, y, obs, 0.04)) continue;
      if (!cellFree(x, y, mapGrid, mapW, mapH, origin, res)) continue;
      for (const base of bases) {
        for (let dth = -TRACK_YAW_RADIUS_RAD; dth <= TRACK_YAW_RADIUS_RAD + 1e-9; dth += 0.12) {
          const th = wrapPi(base + dth);
          const score = scoreAt(x, y, th);
          if (score > best.score) best = { score, x, y, th };
        }
      }
    }
  }

  const dist = Math.hypot(best.x - tip0.x, best.y - tip0.y);
  const dth = wrapPi(best.th - th0);
  const flipped = Math.abs(dth) > Math.PI / 2;
  const better = best.score >= score0 * TRACK_MIN_IMPROVE || flipped;
  if (!better && dist < 0.035) return null;
  if (best.score < score0 * 0.95 && !flipped) return null;

  const next = seedAlignFromMapPose(best.x, best.y, best.th, odom, {
    applyFlip: false,
    applyBias: false,
    source: SESSION_SOURCE,
  });
  const tip1 = projectPose(odom, next);
  return {
    align: next,
    tip: tip1,
    dtx: tip1.x - tip0.x,
    dty: tip1.y - tip0.y,
    dth,
    score: best.score,
    flipped,
  };
}

export { ALIGN_VER };
