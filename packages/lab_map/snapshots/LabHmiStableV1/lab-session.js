/**
 * lab-session — SE2 vivo + trazo Occupancy.
 *
 * Fluidez (modelo que ya funcionó):
 *  1. Ubicar (manual o 1× al cargar si no hay pose) fija ψ y tip → CONGELA.
 *  2. Al manejar: SOLO project(odom) + trazo. Cero LiDAR / cero refine / cero Ubicar.
 *  3. Invertir rumbo o Ubicar otra vez = única forma de tocar el align.
 *  4. Trazo en odom; al dibujar se proyecta. En giro puro (casi sin Δxy) no se pinta tinta.
 */

import { ENDPOINTS } from "../config.js";
import { fetchMapMeta, fetchScan, fetchStatus } from "../api/robot.js";
import {
  PERIMETER_YAW_META,
  DISPLAY_YAW,
  SESSION_SOURCE,
  HEADING_LOCKED,
  REQUIRE_MANUAL_UBICAR,
  CHECKPOINT_NAME,
  ODOM_TO_MAP_SCALE,
  effectiveOdomYSign,
} from "./constants.js";
import * as LabMap from "./LabMapEngine.js";

/** Por debajo de esto (m odom) se considera giro en sitio, no avance. */
const SPIN_XY_MAX_M = 0.012;
/** Giro mínimo (rad) para clasificar como spin puro. */
const SPIN_DTH_MIN = 0.08;
/** Salto de θ (parado) típico de glitch Kalman — no aplicar a la flecha. */
const STILL_THETA_GLITCH_RAD = 0.55 * Math.PI;
const STILL_XY_MAX_M = 0.025;
const TRAIL_MIN_STEP_M = 0.008;
const TRAIL_GAP_M = 0.85;

const state = {
  mapId: "laboratorio_kalman",
  mapMeta: null,
  mapImage: null,
  mapGrid: null,
  mapW: 0,
  mapH: 0,
  geometry: null,
  closed: [],
  /** Perímetro real = muros dorados Occupancy. */
  wallBox: null,
  wallClosed: [],
  boxes: [],
  odom: { x: 0, y: 0, theta: 0 },
  align: LabMap.createEmptyAlign(),
  alignFrozen: false,
  /** true hasta Ubicar manual (gate HMI). */
  needsUbicar: true,
  trailOdom: [],
  trail: [],
  scan: null,
  localizing: false,
  status: "need_ubicar",
  hint: `Checkpoint ${CHECKPOINT_NAME} — pulsa «Ubicar en el mapa»`,
  listeners: new Set(),
};

export function getLabState() {
  return state;
}

export function isLabAnchored() {
  return (
    !state.needsUbicar &&
    state.alignFrozen &&
    LabMap.isNavigableAlign(state.align)
  );
}

export function subscribeLab(fn) {
  state.listeners.add(fn);
  return () => state.listeners.delete(fn);
}

function syncUbicarGate() {
  const need = Boolean(REQUIRE_MANUAL_UBICAR && state.needsUbicar);
  document.body.classList.toggle("lab-needs-ubicar", need);
  document.body.classList.toggle("lab-anchored", !need && isLabAnchored());
}

function emit() {
  syncUbicarGate();
  for (const fn of state.listeners) {
    try {
      fn(state);
    } catch {
      /* ignore */
    }
  }
}

function setHint(text, status = state.status) {
  state.hint = text;
  state.status = status;
  emit();
}

function clearAnchor(reasonHint) {
  state.align = LabMap.createEmptyAlign();
  state.alignFrozen = false;
  state.needsUbicar = true;
  state.trailOdom = [];
  state.trail = [];
  setHint(
    reasonHint || "Pulsa «Ubicar en el mapa» para anclar (obligatorio)",
    "need_ubicar"
  );
}

function projectOdomXY(ox, oy) {
  // Misma proyección que projectPose (incluye ODOM_TO_MAP_SCALE vía align.sx).
  const p = LabMap.projectPose(
    { x: ox, y: oy, theta: state.odom.theta || 0 },
    state.align
  );
  return { x: p.x, y: p.y };
}

/** Borde real = muros dorados (Occupancy), no el PGM completo. */
function outerMapBox(inset = 0.0) {
  if (state.wallBox) {
    return {
      minX: state.wallBox.minX + inset,
      minY: state.wallBox.minY + inset,
      maxX: state.wallBox.maxX - inset,
      maxY: state.wallBox.maxY - inset,
    };
  }
  if (!state.mapMeta || !state.mapW || !state.mapH) return null;
  const res = Number(state.mapMeta.resolution) || 0.05;
  const origin = state.mapMeta.origin || [0, 0];
  return {
    minX: origin[0] + 0.08,
    minY: origin[1] + 0.08,
    maxX: origin[0] + state.mapW * res - 0.08,
    maxY: origin[1] + state.mapH * res - 0.08,
  };
}

function clampToOuterMap(x, y) {
  const box = outerMapBox(0.06);
  if (!box) return { x, y };
  return LabMap.clampPointToAabb(x, y, box);
}

function tipRaw() {
  if (!LabMap.isNavigableAlign(state.align)) return null;
  return LabMap.projectPose(state.odom, state.align);
}

function tipClamped() {
  const raw = tipRaw();
  if (!raw) return null;
  const c = clampToOuterMap(raw.x, raw.y);
  return { ...raw, x: c.x, y: c.y };
}

function rebuildTrailMap() {
  if (!LabMap.isNavigableAlign(state.align) || !state.trailOdom.length) {
    state.trail = [];
    return;
  }
  const out = [];
  for (const p of state.trailOdom) {
    const m = projectOdomXY(p.x, p.y);
    out.push(p.gap ? { ...m, gap: true } : m);
  }
  state.trail = out.length > 900 ? out.slice(-900) : out;
}

/** Añade un punto; interpola si el salto de telemetría es grande (menos lag visual). */
function appendTrailPoint(ox, oy, { gap = false } = {}) {
  if (!state.trailOdom.length) {
    state.trailOdom = [{ x: ox, y: oy }];
    state.trail = [projectOdomXY(ox, oy)];
    return;
  }
  const last = state.trailOdom[state.trailOdom.length - 1];
  const step = Math.hypot(ox - last.x, oy - last.y);
  if (step < TRAIL_MIN_STEP_M) return;

  if (!gap && step > 0.06 && step < TRAIL_GAP_M) {
    const n = Math.min(10, Math.max(1, Math.floor(step / 0.03)));
    for (let i = 1; i <= n; i++) {
      const t = i / (n + 1);
      const ix = last.x + (ox - last.x) * t;
      const iy = last.y + (oy - last.y) * t;
      state.trailOdom.push({ x: ix, y: iy });
      state.trail.push(projectOdomXY(ix, iy));
    }
  }

  const entry = gap || step > TRAIL_GAP_M ? { x: ox, y: oy, gap: true } : { x: ox, y: oy };
  state.trailOdom.push(entry);
  if (state.trailOdom.length > 900) {
    state.trailOdom = state.trailOdom.slice(-900);
    rebuildTrailMap();
    return;
  }
  const tip = projectOdomXY(ox, oy);
  state.trail.push(entry.gap ? { ...tip, gap: true } : tip);
  if (state.trail.length > 900) state.trail = state.trail.slice(-900);
}

export function updateLabOdom(pose) {
  if (!pose) return;
  const nx = Number(pose.x);
  const ny = Number(pose.y);
  const nth = Number(pose.theta);
  if (!Number.isFinite(nx) || !Number.isFinite(ny)) return;

  const prev = state.odom;
  const jump = Math.hypot(nx - (prev.x || 0), ny - (prev.y || 0));
  const dth = Number.isFinite(nth)
    ? Math.abs(LabMap.wrapPi(nth - (prev.theta || 0)))
    : 0;
  const prevMag = Math.hypot(prev.x || 0, prev.y || 0);
  const atOrigin = Math.abs(nx) < 1e-4 && Math.abs(ny) < 1e-4;
  const spinning = jump < SPIN_XY_MAX_M && dth >= SPIN_DTH_MIN;

  state.odom = {
    x: nx,
    y: ny,
    theta: Number.isFinite(nth) ? nth : prev.theta || 0,
  };

  // Reset odom real → robot “desaparece”: exigir Ubicar de nuevo (mismo SE2).
  if (prevMag > 0.08 && atOrigin) {
    clearAnchor("Odom reiniciada — pulsa «Ubicar en el mapa» (obligatorio)");
    return;
  }

  // Parado + salto brusco de θ → ruido Kalman (flecha “sola”). Conservar θ previa.
  if (
    LabMap.isNavigableAlign(state.align) &&
    state.alignFrozen &&
    jump < STILL_XY_MAX_M &&
    dth >= STILL_THETA_GLITCH_RAD
  ) {
    state.odom = {
      x: nx,
      y: ny,
      theta: prev.theta || 0,
    };
    emit();
    return;
  }

  if (LabMap.isNavigableAlign(state.align) && state.alignFrozen) {
    // Solo omitir tinta en giro PURO en sitio; correcciones izq/der sí pintan.
    const pureSpin = spinning && jump < 0.006;
    if (!pureSpin) {
      const raw = tipRaw();
      const box = outerMapBox(0.04);
      const outside =
        raw &&
        box &&
        (raw.x < box.minX ||
          raw.x > box.maxX ||
          raw.y < box.minY ||
          raw.y > box.maxY);
      if (!outside) {
        appendTrailPoint(nx, ny, { gap: jump > TRAIL_GAP_M });
      }
    }
  }
  emit();
}

async function loadGeometry() {
  const res = await fetch(ENDPOINTS.labGeometry);
  if (!res.ok) throw new Error("No geometry");
  const data = await res.json();
  state.geometry = data.geometry || data;
  state.closed = state.geometry.trail_map_closed || [];
  state.boxes = state.geometry.obstacle_boxes || [];
}

async function persistAlign() {
  if (!LabMap.isNavigableAlign(state.align)) return;
  const body = JSON.stringify({
    yaw: state.align.yaw,
    tx: state.align.tx,
    ty: state.align.ty,
  });
  try {
    await fetch(ENDPOINTS.labSessionAlign, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
  } catch {
    await fetch(ENDPOINTS.liveAlign, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    }).catch(() => {});
  }
}

function rasterizeMap(img) {
  const c = document.createElement("canvas");
  c.width = img.width;
  c.height = img.height;
  const cx = c.getContext("2d");
  cx.drawImage(img, 0, 0);
  const data = cx.getImageData(0, 0, img.width, img.height).data;
  const grid = new Uint8Array(img.width * img.height);
  for (let i = 0; i < grid.length; i++) {
    const g = data[i * 4];
    if (g < 50) grid[i] = 1;
    else if (g > 240) grid[i] = 0;
    else grid[i] = 2;
  }
  return grid;
}

export async function loadLabMap(mapId) {
  state.mapId = mapId || state.mapId;
  setHint("Cargando Occupancy…", "loading");
  state.mapMeta = await fetchMapMeta(state.mapId);
  const img = new Image();
  await new Promise((resolve, reject) => {
    img.onload = resolve;
    img.onerror = () => reject(new Error("map image"));
    img.src = ENDPOINTS.mapImage(state.mapId);
  });
  state.mapImage = img;
  state.mapW = img.width;
  state.mapH = img.height;
  state.mapGrid = rasterizeMap(img);
  state.wallBox = LabMap.extractWallBox(
    state.mapGrid,
    state.mapW,
    state.mapH,
    state.mapMeta,
    0.04
  );
  state.wallClosed = LabMap.wallBoxToClosed(state.wallBox);
  await loadGeometry();
  clearAnchor("Mapa listo — pulsa «Ubicar en el mapa» (obligatorio)");
}

/**
 * Ubicar manual: N pasadas LiDAR — se queda con la de mejor score
 * y re-siembra ψ con odom fresca (evita izq/der raros + flecha que “salta sola”).
 * Auto al boot: bloqueado (REQUIRE_MANUAL_UBICAR).
 */
export async function relocalizeLab({ reason = "", auto = false, passes } = {}) {
  // Checkpoint: jamás auto-Ubicar al boot (falla y deja izq/der raros).
  if (auto && REQUIRE_MANUAL_UBICAR) {
    if (!isLabAnchored()) {
      setHint("Pulsa «Ubicar en el mapa» para anclar (obligatorio)", "need_ubicar");
    }
    return false;
  }
  if (state.localizing) return false;
  if (auto && state.alignFrozen && LabMap.isNavigableAlign(state.align)) {
    return false;
  }
  if (!state.mapGrid) {
    setHint("Falta mapa Occupancy", "error");
    return false;
  }

  const nPasses = Math.max(1, Number(passes) || (auto ? 1 : 2));
  state.localizing = true;
  state.alignFrozen = false;
  state.needsUbicar = true;
  setHint("Sincronizando odom…", "localizing");

  let best = null;
  try {
    // Odom fresca antes de sembrar ψ (θ=0 / stale → izq/der mal y flecha que gira sola).
    let sync = await refreshOdomFromStatus();
    await sleep(80);
    sync = await refreshOdomFromStatus();
    if (sync.connection === "disconnected" || sync.connection === "error") {
      setHint("Sin enlace ROS — espera «connected» y vuelve a Ubicar", "error");
      state.needsUbicar = true;
      return false;
    }
    if (!sync.ok) {
      setHint("Odom sin θ válida — espera telemetría y reintenta", "error");
      state.needsUbicar = true;
      return false;
    }

    for (let i = 0; i < nPasses; i++) {
      if (nPasses > 1) {
        setHint(`Ubicando ${i + 1}/${nPasses}…`, "localizing");
      } else {
        setHint("Ubicando (manual)…", "localizing");
      }
      state.scan = await fetchScan(360);
      const result = LabMap.localizeInTrack({
        odom: state.odom,
        scan: state.scan,
        closed: state.closed,
        boxes: state.boxes,
        mapGrid: state.mapGrid,
        mapW: state.mapW,
        mapH: state.mapH,
        mapMeta: state.mapMeta,
        perimeterYawMeta:
          Number(state.geometry?.perimeter_yaw_meta) || PERIMETER_YAW_META,
      });
      // Mejor score (antes se quedaba la ÚLTIMA pasada → a veces empeoraba izq/der).
      if (result && (!best || result.score >= best.score)) {
        best = result;
      }
      if (i < nPasses - 1) await sleep(320);
    }

    if (!best?.tip || !Number.isFinite(best.mapTh)) {
      setHint("No pude ubicar — mírate a un muro y reintenta", "error");
      state.needsUbicar = true;
      return false;
    }

    // Re-sembrar con odom del momento de anclar (no la del scan intermedio).
    await refreshOdomFromStatus();
    state.align = LabMap.seedAlignFromMapPose(
      best.tip.x,
      best.tip.y,
      best.mapTh,
      state.odom,
      { applyFlip: true, applyBias: true, source: SESSION_SOURCE }
    );
    state.align.sx = ODOM_TO_MAP_SCALE;
    state.align.sy = Math.abs(ODOM_TO_MAP_SCALE) * effectiveOdomYSign();
    state.alignFrozen = true;
    state.needsUbicar = false;
    state.trailOdom = [{ x: state.odom.x || 0, y: state.odom.y || 0 }];
    rebuildTrailMap();
    await persistAlign();
    const t = LabMap.projectPose(state.odom, state.align);
    const deg = ((state.align.yaw * 180) / Math.PI).toFixed(0);
    const passNote = nPasses > 1 ? ` · ×${nPasses}` : "";
    setHint(
      `Anclado (${t.x.toFixed(2)}, ${t.y.toFixed(2)}) · ψ=${deg}° · rumbo fijo${passNote} · ${CHECKPOINT_NAME}`,
      "ok"
    );
    return true;
  } catch (err) {
    setHint(`LiDAR: ${err.message || err}`, "error");
    state.needsUbicar = true;
    return false;
  } finally {
    state.localizing = false;
    emit();
  }
}

async function refreshOdomFromStatus() {
  try {
    const status = await fetchStatus();
    const p = status?.position;
    const connection = String(status?.connection || "").toLowerCase();
    if (!p) return { ok: false, connection };
    const nx = Number(p.x);
    const ny = Number(p.y);
    const nth = Number(p.theta);
    if (!Number.isFinite(nx) || !Number.isFinite(ny)) {
      return { ok: false, connection };
    }
    state.odom = {
      x: nx,
      y: ny,
      theta: Number.isFinite(nth) ? nth : state.odom.theta || 0,
    };
    return { ok: Number.isFinite(nth), connection };
  } catch {
    return { ok: false, connection: "error" };
  }
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/** API legacy: refine-t solo bajo demanda explícita (no loop de manejo). */
export async function refineLabTranslation() {
  return false;
}

export function clearLabTrail() {
  state.trailOdom = LabMap.isNavigableAlign(state.align)
    ? [{ x: state.odom.x || 0, y: state.odom.y || 0 }]
    : [];
  rebuildTrailMap();
  setHint("Trazo limpio", state.status);
}

export async function flipLabHeading() {
  if (HEADING_LOCKED) {
    setHint("Rumbo ya fijado (validado) — Invertir desactivado", "ok");
    return false;
  }
  if (!LabMap.isNavigableAlign(state.align)) {
    setHint("Ubica primero", "error");
    return false;
  }
  state.align = LabMap.flipAlignHeading(state.align, state.odom);
  state.alignFrozen = true;
  rebuildTrailMap();
  await persistAlign();
  const deg = ((state.align.yaw * 180) / Math.PI).toFixed(0);
  setHint(`Rumbo invertido · ψ=${deg}° · sigue manejando`, "ok");
  return true;
}

export function mapPose() {
  if (!isLabAnchored()) {
    return { x: state.odom.x, y: state.odom.y, theta: state.odom.theta };
  }
  return tipClamped() || LabMap.projectPose(state.odom, state.align);
}

export { DISPLAY_YAW, SESSION_SOURCE, HEADING_LOCKED, CHECKPOINT_NAME };
