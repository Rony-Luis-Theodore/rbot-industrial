/**
 * Laboratorio HMI — fachada sobre lab/LabMapEngine (SE2 + trazo Occupancy).
 * Pose: map = R(yaw)·odom + t. Vista: DISPLAY_YAW solo render.
 */

import { ENDPOINTS } from "../config.js";
import { fetchHmiDebug, fetchMapMeta, fetchMaps, fetchScan } from "../api/robot.js";
import { getElement } from "../utils/dom.js";
import {
  ALIGN_VER,
  DISPLAY_YAW,
  LIDAR_HEADING_FLIP,
  LIDAR_YAW,
  NORTH_VER,
  PERIMETER_YAW_META,
  TRAIL_MAX_STEP_M,
} from "../lab/constants.js";
import * as LabMap from "../lab/LabMapEngine.js";
import "../lab/LabCanvas.js"; // DISPLAY helpers available if needed later

const gazeboCanvas = getElement("gazebo-canvas");
const select = getElement("map-select");
const hint = getElement("view-hint");
const btnLocalize = getElement("btn-localize");
const btnClearTrail = getElement("btn-clear-trail");
const btnLidar = getElement("btn-lidar");
const labStage = getElement("lab-stage");

const gctx = gazeboCanvas.getContext("2d", { willReadFrequently: false });

let activeView = "lab";
let showLidar = true;
let mapImage = null; // grayscale PNG from API
let mapMeta = null;
let mapGrid = null; // Uint8Array occupancy: 0 free, 1 occupied, 2 unknown
let mapW = 0;
let mapH = 0;
let mapZones = [];

let odomPose = { x: 0, y: 0, theta: 0 };
/**
 * map = R(yaw) * odom + t  — SE2 vivo (LabMapEngine).
 */
let align = LabMap.createEmptyAlign();

/**
 * Semillas de búsqueda LiDAR (cualquier esquina / pasillo libre).
 * NO hay “arranque fijo”: el robot puede estar en cualquiera.
 */
const LOCALIZE_SEEDS = [
  { id: "sala_maquinas", x: 0.58, y: -0.4 },
  { id: "almacen", x: 0.58, y: 0.58 },
  { id: "recepcion", x: -0.58, y: -0.4 },
  { id: "oficina", x: -0.58, y: 0.58 },
  { id: "pasillo_norte", x: 0.58, y: 0.0 },
  { id: "pasillo_sur", x: -0.55, y: 0.0 },
  { id: "pasillo_oeste", x: 0.0, y: 0.58 },
  { id: "pasillo_este", x: 0.0, y: -0.4 },
  { id: "centro", x: 0.05, y: 0.0 },
];

/** @deprecated use lab/constants — kept for any residual refs */
const MAP_ALIGN_NUDGE = { tx: 0.0, ty: 0.0 };
const NORTH_KEY = "rbot_north_align";
const NORTH_VER_KEY = "rbot_north_ver";
const PERIMETER_YAW_LOCKED = PERIMETER_YAW_META;

let scanData = null;
let scanTimer = null;
/** Trail en odom (diagnóstico / ajuste perímetro). */
let trailOdom = [];
/** Trail en metros Occupancy — verdad de dibujo (no baila si cambia t). */
let trailMap = [];
let localizePending = false;
let localizing = false;
let lastLocalizeAttemptMs = 0;
let perimeterFitted = false;
let lastFitPathLen = 0;
let lastAutoFitPathLen = 0;
let alignNeedsManual = false;
/** Align congelado: no re-sembrar ni auto-girar. */
let alignFrozen = false;
/** Ya se alineó el yaw a los muros (evita rombo). */
let yawWallSnapped = false;
/** Pasadas de snap (máx. 3) para afinar residuales ~15–20°. */
let yawSnapPasses = 0;
/** Traslación del perímetro ya centrada en el carril Occupancy. */
let trailCentered = false;
/** Ruta A* planificada (metros Occupancy) para dibujar. */
let plannedPath = null;
/** Perímetro cerrado + 4 cajas Occupancy (overlay). */
let labGeometry = null;
/** Throttle del nudge tx/ty en vivo. */
let lastTransNudgeMs = 0;
let lastTransNudgeOdom = { x: 0, y: 0 };
/** Throttle recuperación tip-only (perímetro canónico). */
let lastTipRecoverMs = 0;
let lastLaneRefineMs = 0;

const GAZEBO = {
  free: [91, 155, 213],
  occupied: [232, 197, 71],
  unknown: [45, 55, 65],
  border: [245, 200, 66],
};

export async function initViewer() {
  document.body.dataset.view = "lab";

  document.querySelectorAll(".view-tab").forEach((tab) => {
    tab.addEventListener("click", () => setView(tab.dataset.view));
  });

  btnLocalize?.addEventListener("click", () => {
    if (btnLocalize.disabled) return;
    // Única vía manual para reescribir el align
    alignFrozen = false;
    perimeterFitted = false;
    lastFitPathLen = 0;
    alignNeedsManual = false;
    yawWallSnapped = false;
    yawSnapPasses = 0;
    trailCentered = false;
    if (fitMapToTrailPerimeter({ manual: true })) {
      syncLocalizeButton();
      fitAll();
      draw();
      return;
    }
    // Fallback: LiDAR en cualquier zona libre
    void (async () => {
      try {
        scanData = await fetchScan(320);
        if (await localizeInitialPose({ manual: true, force: true })) {
          syncLocalizeButton();
          return;
        }
      } catch {
        /* fall through */
      }
      localizePending = true;
      void localizeOnMap({ manual: true });
      syncLocalizeButton();
    })();
  });

  btnClearTrail?.addEventListener("click", () => {
    clearTrail({ announce: true });
  });

  btnLidar?.addEventListener("click", () => {
    showLidar = !showLidar;
    btnLidar.classList.toggle("is-active", showLidar);
    btnLidar.setAttribute("aria-pressed", showLidar ? "true" : "false");
    hint.textContent = showLidar ? "LiDAR visible" : "LiDAR oculto";
    draw();
  });

  window.addEventListener("resize", fitAll);
  fitAll();
  syncLocalizeButton();
  // Migrar norte: v17 = perímetro canónico del servidor manda siempre
  try {
    const ver = localStorage.getItem(NORTH_VER_KEY);
    if (ver === NORTH_VER) {
      restorePersistedTrail();
    } else if (
      ver === "north-v12" ||
      ver === "north-v13" ||
      ver === "north-v14" ||
      ver === "north-v15" ||
      ver === "north-v16" ||
      ver === "north-v17" ||
      ver === "north-v18"
    ) {
      // No confiar en lidar local viejo: el loadMap aplicará track_perimeter
      try {
        localStorage.setItem(NORTH_VER_KEY, NORTH_VER);
      } catch {
        /* ignore */
      }
      restorePersistedTrail();
      perimeterFitted = false;
      alignFrozen = false;
    } else {
      restorePersistedTrail();
    }
  } catch {
    restorePersistedTrail();
  }

  try {
    const maps = await fetchMaps();
    select.innerHTML = "";
    for (const m of maps) {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = m.id.replaceAll("_", " ");
      select.appendChild(opt);
    }
    select.addEventListener("change", () => loadMap(select.value));
    const preferred =
      maps.find((m) => m.id.includes("laboratorio"))?.id ||
      maps.find((m) => m.id.includes("mapa_kalman"))?.id ||
      maps[0]?.id;
    if (preferred) {
      select.value = preferred;
      await loadMap(preferred);
    }
  } catch (err) {
    hint.textContent = err.message;
  }

  startScanLoop();
  requestAnimationFrame(loop);
}

export async function applyDefaultMap(mapId) {
  if (!mapId || !select) return;
  if (![...select.options].some((o) => o.value === mapId)) return;
  if (select.value === mapId && mapMeta?.id === mapId) {
    // Misma mapa, pero al (re)conectar hay que reubicar
    requestRelocalize();
    return;
  }
  select.value = mapId;
  await loadMap(mapId);
}

/** Tras reconectar / cambiar perfil: invalidar norte viejo y reubicar con LiDAR. */
export function requestRelocalize() {
  // Tras desconexión el odom suele resetearse: el norte guardado ya no sirve
  invalidateAlignForRelocalize("reconnect");
  localizePending = true;
  void (async () => {
    try {
      scanData = await fetchScan(320);
      const ok = await localizeInitialPose({ manual: false, force: true });
      if (!ok) await localizeOnMap({ manual: true });
    } catch {
      /* scan loop reintenta */
    }
    syncLocalizeButton();
  })();
  syncLocalizeButton();
}

/**
 * Tras odom reset/salto: overlays Occupancy fijos; SE(2) VIVO se recalcula
 * (el SE2 del día del grabado NO vale tras reset — tip caía fuera del cyan).
 */
function invalidateAlignForRelocalize(reason = "") {
  const hadCanon =
    perimeterFitted ||
    align?.source === "perimeter" ||
    Boolean(labGeometry?.track?.align_canonical) ||
    Boolean(labGeometry?.track?.trail_map_closed?.length);

  if (hadCanon) {
    localizePending = false;
    void (async () => {
      try {
        if (!labGeometry?.track) await loadLabGeometry();
        trailOdom = [{ x: odomPose.x, y: odomPose.y }];
        trailMap = [];
        let ok = false;
        try {
          if (!scanData?.ranges?.length) scanData = await fetchScan(320);
          ok = await localizeInsideTrack({ force: true, manual: false });
        } catch {
          ok = false;
        }
        if (!ok) {
          // Sin LiDAR: tip dentro del AABB cyan (no SE2 viejo fuera de pista)
          snapRobotTipInsideTrack({ clearTrail: true, announce: false });
        }
        persistTrail();
        uploadHmiDebug(true);
        if (hint) {
          hint.textContent = ok
            ? reason === "odom-reset" || reason === "odom-jump"
              ? "Odom reiniciado — reubicado en pista Occupancy"
              : "Reubicado en pista Occupancy"
            : "Sin LiDAR — tip anclado dentro del perímetro cyan";
        }
        syncLocalizeButton();
        draw();
      } catch {
        /* ignore */
      }
    })();
    return;
  }

  alignFrozen = false;
  perimeterFitted = false;
  lastFitPathLen = 0;
  yawWallSnapped = false;
  yawSnapPasses = 0;
  trailCentered = false;
  align = { tx: 0, ty: 0, yaw: 0, sx: 1, sy: 1, ready: false, source: "none" };
  try {
    localStorage.removeItem(NORTH_KEY);
    sessionStorage.removeItem("rbot_align");
    sessionStorage.setItem("rbot_perimeter_fitted", "0");
  } catch {
    /* ignore */
  }
  if (hint) {
    hint.textContent = reason
      ? `Reubicando (${reason}) — LiDAR en cualquier zona libre…`
      : "Reubicando con LiDAR…";
  }
}

export function updateRobotPose(pose) {
  if (!pose) return;
  const nx = Number(pose.x);
  const ny = Number(pose.y);
  const nth = Number(pose.theta);
  if (!Number.isFinite(nx) || !Number.isFinite(ny)) return;

  const prev = odomPose;
  const prevMag = Math.hypot(prev.x || 0, prev.y || 0);
  const atOrigin = Math.abs(nx) < 1e-4 && Math.abs(ny) < 1e-4;
  const jump = Math.hypot(nx - (prev.x || 0), ny - (prev.y || 0));

  // Odom reset tras reconexión
  if (prevMag > 0.08 && atOrigin) {
    odomPose = { x: nx, y: ny, theta: Number.isFinite(nth) ? nth : 0 };
    trailOdom = [{ x: nx, y: ny }];
    persistTrail();
    invalidateAlignForRelocalize("odom-reset");
    if (!perimeterFitted) localizePending = true;
    syncLocalizeButton();
    draw();
    return;
  }

  // No ignorar (0,0) si es la pose real tras undock (prev también ~0)
  odomPose = {
    x: nx,
    y: ny,
    theta: Number.isFinite(nth) ? nth : 0,
  };

  // Salto grande al reconectar: reiniciar trazo; yaw Occupancy intacto
  if (trailOdom.length > 0 && jump > 1.5) {
    trailOdom = [{ x: nx, y: ny }];
    trailMap = [];
    persistTrail();
    if (isNavigableAlign(align) || perimeterFitted) {
      invalidateAlignForRelocalize("odom-jump");
      if (!perimeterFitted) localizePending = true;
    }
  } else {
    const last = trailOdom[trailOdom.length - 1];
    const step = last ? Math.hypot(nx - last.x, ny - last.y) : 0;
    if (align.ready && mapGrid && !perimeterFitted) {
      const raw = mapPoseRaw({ x: nx, y: ny, theta: nth });
      if (!cellFree(raw.x, raw.y) || clearanceToWall(raw.x, raw.y) < 0.07) {
        maybeNudgeTranslationFit({ force: true, reason: "drift-wall" });
      }
    }
    if (!last || (step > 0.0015 && step <= TRAIL_MAX_STEP_M)) {
      trailOdom.push({ x: nx, y: ny });
      if (trailOdom.length > 900) trailOdom = trailOdom.slice(-850);
      if (align.ready) pushTrailMapPoint(mapPoseRaw({ x: nx, y: ny, theta: nth }));
      persistTrail();
    } else if (step > TRAIL_MAX_STEP_M) {
      // Odom glitch: NO borrar el trazo Occupancy (antes desaparecía entero)
      trailOdom.push({ x: nx, y: ny });
      if (trailOdom.length > 900) trailOdom = trailOdom.slice(-850);
      if (align.ready) {
        pushTrailMapPoint(mapPoseRaw({ x: nx, y: ny, theta: nth }), {
          allowBreak: true,
        });
      }
      persistTrail();
    }
  }

  if (perimeterFitted) {
    // Fuera de pista o desfase carril: solo traslación LiDAR (yaw intacto)
    const tip = mapPoseRaw(odomPose);
    const now = performance.now();
    const outside =
      !tipInsideTrack(tip.x, tip.y, 0.02) || !cellFree(tip.x, tip.y);
    if (outside && now - lastTipRecoverMs > 4000) {
      lastTipRecoverMs = now;
      void refineTranslationKeepYaw({ reason: "outside" });
    }
  } else if (!alignFrozen) {
    maybeAutoFitTrail();
  } else {
    maybeNudgeTranslationFit({ force: false });
  }
  syncLocalizeButton();
}

/**
 * Gira el align para que los lados del trazo queden // a los muros Occupancy.
 * Mantiene la pose mapa actual del robot (solo corrige el rombo).
 * Puede repetir hasta 3 pasadas si queda sesgo residual (~15–20°).
 */
function maybeSnapYawToWalls({ force = false } = {}) {
  // Con perímetro Occupancy el yaw es fijo — snap a muros creaba rombos/saltos
  if (perimeterFitted || align?.source === "perimeter" || align?.source === "lidar_in_track") {
    return false;
  }
  if (!isNavigableAlign(align) || !mapGrid || !mapMeta) return false;
  if (!force && yawSnapPasses >= 3) return false;
  if (trailOdom.length < 8) return false;
  const len = trailPathLength(trailOdom);
  if (len < 1.0) return false;

  const skew0 = sideAlignRad(trailOdom, align.yaw);
  // ~0.07 rad ≈ 4° — objetivo visual cuadrado, no rombo
  if (!force && skew0 < 0.07) {
    yawWallSnapped = true;
    return false;
  }
  // Si ya “terminamos” pero el sesgo volvió a subir, reintentar
  if (!force && yawWallSnapped && skew0 < 0.12) return false;

  const ox = odomPose.x || 0;
  const oy = odomPose.y || 0;
  const cur = mapPoseRaw(odomPose);

  const scoreYaw = (yaw, deg) => {
    const skew = sideAlignRad(trailOdom, yaw);
    const c = Math.cos(yaw);
    const s = Math.sin(yaw);
    const tx = cur.x - (c * ox - s * oy);
    const ty = cur.y - (s * ox + c * oy);
    const free = freeSpaceScore(trailOdom, yaw, tx, ty, 1);
    // Sesgo manda; libre es freno suave (no bloquear el óptimo angular)
    const score = skew * 20 - Math.min(free, 0.85) * 2;
    return { score, yaw, tx, ty, skew, free, deg };
  };

  let best = null;
  for (let deg = -90; deg <= 90; deg += 0.5) {
    const cand = scoreYaw(wrapPi(align.yaw + (deg * Math.PI) / 180), deg);
    if (!best || cand.score < best.score) best = cand;
  }
  if (!best) return false;

  // Refinado fino ±4°
  const center = best.deg;
  for (let deg = center - 4; deg <= center + 4; deg += 0.1) {
    const cand = scoreYaw(wrapPi(align.yaw + (deg * Math.PI) / 180), deg);
    if (cand.score < best.score) best = cand;
  }

  // Debe mejorar (al menos ~1°)
  if (best.skew > skew0 - 0.015) {
    if (skew0 < 0.12) yawWallSnapped = true;
    return false;
  }
  // Evitar salirse mucho del libre
  if (best.free < 0.22) return false;

  align = {
    yaw: best.yaw,
    tx: best.tx,
    ty: best.ty,
    sx: 1,
    sy: 1,
    ready: true,
    source: align.source === "perimeter" ? "perimeter" : "lidar",
  };
  yawSnapPasses += 1;
  yawWallSnapped = best.skew < 0.08;
  trailCentered = false; // yaw cambió → recentrar traslación
  alignFrozen = true;
  lockNorthAlign("yaw-walls");
  if (hint) {
    const d = best.deg >= 0 ? `+${best.deg.toFixed(1)}` : best.deg.toFixed(1);
    const sk = ((best.skew * 180) / Math.PI).toFixed(1);
    hint.textContent = `Rumbo a muros (${d}°, sesgo ${sk}°) — perímetro cuadrado.`;
  }
  maybeCenterTrailInLane({ force: true });
  return true;
}

/**
 * Con yaw fijo, desplaza tx/ty para que el AABB del trazo quede centrado
 * en el carril Occupancy y maximice puntos en libre.
 * Corrige el “cuadrado bien orientado pero corrido a la derecha/abajo”.
 * Puede reabrir si el libre baja (deriva hacia el muro).
 */
function maybeCenterTrailInLane({ force = false } = {}) {
  if (!isNavigableAlign(align) || !mapGrid || !mapMeta) return false;
  if (trailOdom.length < 8) return false;
  const len = trailPathLength(trailOdom);
  if (len < 0.7) return false;

  const loop = extractLastLoop(trailOdom) || trailOdom.slice(-60);
  const freeNow = freeSpaceScore(loop, align.yaw, align.tx, align.ty, 1);
  if (!force && trailCentered && freeNow >= 0.72) return false;

  const skew = sideAlignRad(trailOdom, align.yaw);
  if (!force && skew > 0.16) return false;

  const walls = mapContentBounds();
  const inset = 0.14;
  const mcx = (walls.minX + walls.maxX) / 2;
  const mcy = (walls.minY + walls.maxY) / 2;
  const base = rigidCenterForYaw(loop, align.yaw, mcx, mcy);

  let best = {
    tx: base.tx,
    ty: base.ty,
    free: freeSpaceScore(loop, align.yaw, base.tx, base.ty, 1),
  };

  for (let dtx = -0.45; dtx <= 0.45; dtx += 0.02) {
    for (let dty = -0.45; dty <= 0.45; dty += 0.02) {
      const tx = base.tx + dtx;
      const ty = base.ty + dty;
      const free = freeSpaceScore(loop, align.yaw, tx, ty, 1);
      if (free > best.free) best = { tx, ty, free };
    }
  }

  // Exigir que la punta actual quede libre con holgura
  const ox = odomPose.x || 0;
  const oy = odomPose.y || 0;
  const c = Math.cos(align.yaw);
  const s = Math.sin(align.yaw);
  const tipScore = (tx, ty) => {
    const mx = c * ox - s * oy + tx;
    const my = s * ox + c * oy + ty;
    if (!cellFree(mx, my)) return -1;
    return clearanceToWall(mx, my);
  };

  let use = best;
  let tipClr = tipScore(best.tx, best.ty);
  if (tipClr < 0.08) {
    // Preferir candidatos con punta libre aunque el free del trazo baje un poco
    for (let dtx = -0.4; dtx <= 0.4; dtx += 0.025) {
      for (let dty = -0.4; dty <= 0.4; dty += 0.025) {
        const tx = align.tx + dtx;
        const ty = align.ty + dty;
        const clr = tipScore(tx, ty);
        if (clr < 0.08) continue;
        const free = freeSpaceScore(loop, align.yaw, tx, ty, 1);
        const score = free * 8 + Math.min(clr, 0.28) * 15;
        const bestScore = use.free * 8 + Math.min(tipClr, 0.28) * 15;
        if (score > bestScore) {
          use = { tx, ty, free };
          tipClr = clr;
        }
      }
    }
  }

  const shift = Math.hypot(use.tx - align.tx, use.ty - align.ty);
  if (shift < 0.025 && use.free <= freeNow + 0.02 && tipClr >= 0.08) {
    trailCentered = true;
    return false;
  }
  if (use.free < freeNow - 0.1 && tipClr >= 0.1 && freeNow >= 0.75) {
    trailCentered = true;
    return false;
  }

  align = {
    ...align,
    tx: use.tx,
    ty: use.ty,
    sx: 1,
    sy: 1,
    ready: true,
  };
  trailCentered = true;
  alignFrozen = true;
  lockNorthAlign("center-lane");
  if (hint) {
    hint.textContent = `Perímetro centrado · libre ${(use.free * 100).toFixed(0)}% · holgura ${tipClr.toFixed(2)} m`;
  }
  persistTrail();
  uploadHmiDebug(true);
  return true;
}

/**
 * Distancia aprox. a la celda ocupada más cercana (m). Holgura al muro.
 */
function clearanceToWall(x, y, maxRm = 0.4) {
  if (!mapGrid || !mapMeta) return 0;
  if (!cellFree(x, y)) return 0;
  const res = Number(mapMeta.resolution) || 0.05;
  const origin = mapMeta.origin || [0, 0];
  const mx0 = Math.floor((x - origin[0]) / res);
  const my0 = Math.floor((y - origin[1]) / res);
  const maxR = Math.max(1, Math.ceil(maxRm / res));
  for (let r = 1; r <= maxR; r++) {
    for (let dy = -r; dy <= r; dy++) {
      for (let dx = -r; dx <= r; dx++) {
        if (Math.abs(dx) !== r && Math.abs(dy) !== r) continue;
        const mx = mx0 + dx;
        const my = my0 + dy;
        if (mx < 0 || my < 0 || mx >= mapW || my >= mapH) return r * res;
        if (mapGrid[(mapH - 1 - my) * mapW + mx] === 1) return r * res;
      }
    }
  }
  return maxRm;
}

/**
 * Solo traslación (yaw fijo): empuja tx/ty para que pose+trazo queden en libre
 * con holgura al muro. Evita el “pegado a la pared” del clamp visual.
 */
function maybeNudgeTranslationFit({ force = false, reason = "" } = {}) {
  // Con perímetro canónico el SE(2) es sagrado: no mover tx/ty
  if (perimeterFitted || align?.source === "perimeter") return false;
  if (!isNavigableAlign(align) || !mapGrid || !mapMeta) return false;
  const now = performance.now();
  const ox = odomPose.x || 0;
  const oy = odomPose.y || 0;
  const moved = Math.hypot(ox - lastTransNudgeOdom.x, oy - lastTransNudgeOdom.y);
  if (!force && now - lastTransNudgeMs < 700 && moved < 0.12) return false;

  const raw = mapPoseRaw(odomPose);
  const clr0 = clearanceToWall(raw.x, raw.y);
  const pts =
    trailOdom.length >= 4 ? trailOdom.slice(-50) : [{ x: ox, y: oy }];
  const free0 = freeSpaceScore(pts, align.yaw, align.tx, align.ty, 1);
  const needs =
    force ||
    !cellFree(raw.x, raw.y) ||
    clr0 < 0.09 ||
    free0 < 0.55;
  if (!needs) return false;

  const c = Math.cos(align.yaw);
  const s = Math.sin(align.yaw);
  let best = null;

  for (let dtx = -0.5; dtx <= 0.5; dtx += 0.02) {
    for (let dty = -0.5; dty <= 0.5; dty += 0.02) {
      const tx = align.tx + dtx;
      const ty = align.ty + dty;
      const mx = c * ox - s * oy + tx;
      const my = s * ox + c * oy + ty;
      if (!cellFree(mx, my)) continue;
      const clr = clearanceToWall(mx, my);
      if (clr < 0.07) continue;
      const free = freeSpaceScore(pts, align.yaw, tx, ty, 1);
      // Holgura de la punta manda; libre del trazo refuerza
      const score = Math.min(clr, 0.3) * 25 + free * 10 - Math.hypot(dtx, dty) * 2;
      if (!best || score > best.score) {
        best = { tx, ty, score, free, clr, dtx, dty };
      }
    }
  }
  if (!best) return false;

  const shift = Math.hypot(best.tx - align.tx, best.ty - align.ty);
  if (shift < 0.02 && cellFree(raw.x, raw.y) && clr0 >= 0.09) return false;

  align = {
    ...align,
    tx: best.tx,
    ty: best.ty,
    sx: 1,
    sy: 1,
    ready: true,
  };
  trailCentered = false;
  alignFrozen = true;
  lastTransNudgeMs = now;
  lastTransNudgeOdom = { x: ox, y: oy };
  lockNorthAlign(reason ? `nudge-${reason}` : "nudge-tx-ty");
  if (hint) {
    hint.textContent = `Calce traslación Δ${shift.toFixed(2)} m · holgura ${best.clr.toFixed(2)} m · libre ${(best.free * 100).toFixed(0)}%`;
  }
  persistTrail();
  uploadHmiDebug(true);
  return true;
}

/** SE(2) del trazo: una sola fijación; sin soft continuo. */
function maybeAutoFitTrail() {
  if (alignFrozen || perimeterFitted) return;
  if (!mapMeta || !mapGrid) return;
  if (isNavigableAlign(align)) return;

  const len = trailPathLength(trailOdom);
  if (trailOdom.length < 20) return;
  const closed = isClosedPerimeter(trailOdom);
  if (!closed) {
    // Sin cierre de vuelta: no auto-mover el mapa (evita saltos)
    const box = trailOrientedBounds(trailOdom);
    if (len > 3.5 && box.width >= 0.85 && box.height >= 0.85) {
      alignNeedsManual = true;
    }
    return;
  }

  const ok = fitMapToTrailPerimeter({ manual: false, soft: false });
  if (ok) {
    alignNeedsManual = false;
    perimeterFitted = true;
    alignFrozen = true;
    align.source = "perimeter";
    lastFitPathLen = len;
    lastAutoFitPathLen = len;
    persistTrail();
  }
}

function syncLocalizeButton() {
  if (!btnLocalize) return;
  // Siempre se puede forzar reubicación LiDAR (pose inicial en cualquier sitio)
  const trailOk =
    trailOdom.length >= 12 &&
    (alignNeedsManual ||
      (() => {
        const b = trailOrientedBounds(trailOdom);
        return b.width >= 0.85 && b.height >= 0.85 && trailPathLength(trailOdom) >= 2.5;
      })());
  const enable = true;
  btnLocalize.disabled = !enable;
  btnLocalize.title = trailOk
    ? "Ajustar mapa al perímetro azul o reubicar con LiDAR"
    : "Reubicar robot con LiDAR (cualquier zona libre del mapa)";
  btnLocalize.setAttribute("aria-disabled", "false");
}

/** Borra el trazo verde vivo. No tira el calce Occupancy/perímetro. */
export function clearTrail({ announce = true } = {}) {
  trailOdom = [];
  trailMap = [];
  lastAutoFitPathLen = 0;
  alignNeedsManual = false;
  lastFitPathLen = 0;
  // Si hay perímetro canónico en servidor, conservar SE(2)
  if (!labGeometry?.track?.align_canonical) {
    perimeterFitted = false;
    if (align.source === "perimeter" || align.source === "soft") {
      align.source = "lidar";
    }
  }
  try {
    sessionStorage.removeItem("rbot_trail_odom");
    sessionStorage.removeItem("rbot_trail_map");
    if (!labGeometry?.track?.align_canonical) {
      sessionStorage.setItem("rbot_perimeter_fitted", "0");
      sessionStorage.setItem("rbot_last_fit_len", "0");
    }
    sessionStorage.setItem("rbot_align", JSON.stringify(align));
  } catch {
    /* ignore */
  }
  if (announce) {
    hint.textContent = align.ready
      ? "Trazo borrado — mapa Occupancy / perímetro canónico intactos"
      : "Trazo borrado — dibuja el perímetro del circuito (pista exterior)";
  }
  syncLocalizeButton();
  draw();
}

/**
 * Al cambiar sim ↔ lab el odom y el norte no son transferibles.
 * Evita mandar el robot real a la pared con un align de Gazebo.
 */
export function resetMappingForRobotSwitch(reason = "cambio de robot") {
  trailOdom = [];
  trailMap = [];
  perimeterFitted = false;
  lastFitPathLen = 0;
  lastAutoFitPathLen = 0;
  alignNeedsManual = false;
  localizePending = false;
  alignFrozen = false;
  yawWallSnapped = false;
  yawSnapPasses = 0;
  trailCentered = false;
  align = { tx: 0, ty: 0, yaw: 0, sx: 1, sy: 1, ready: false, source: "none", clear_north: true };
  try {
    localStorage.removeItem(NORTH_KEY);
    localStorage.removeItem(NORTH_VER_KEY);
    sessionStorage.removeItem("rbot_align");
    sessionStorage.removeItem("rbot_trail_odom");
    sessionStorage.removeItem("rbot_perimeter_fitted");
    sessionStorage.removeItem("rbot_last_fit_len");
    sessionStorage.setItem("rbot_align_ver", ALIGN_VER);
  } catch {
    /* ignore */
  }
  uploadHmiDebug(true);
  align = { tx: 0, ty: 0, yaw: 0, sx: 1, sy: 1, ready: false, source: "none" };
  if (hint) {
    hint.textContent =
      `Mapa reiniciado (${reason}). Espera LiDAR / teleopera; el rumbo se fija una sola vez.`;
  }
  syncLocalizeButton();
  draw();
}

function isNavigableAlign(a) {
  if (!a || !a.ready) return false;
  const src = String(a.source || "");
  if (src === "pending" || src === "none" || !src) return false;
  if (!["lidar", "perimeter", "soft", "north", "lidar_in_track"].includes(src)) return false;
  const nearId =
    Math.abs(Number(a.tx) || 0) < 0.05 &&
    Math.abs(Number(a.ty) || 0) < 0.05 &&
    Math.abs(Number(a.yaw) || 0) < 0.05;
  if (nearId && src !== "perimeter") return false;
  return true;
}

function provisionalAlign() {
  // Solo dibujo: ready=false para no envenenar la API / navegación a zonas.
  align = { tx: 0, ty: 0, yaw: 0, sx: 1, sy: 1, ready: false, source: "pending" };
}

function wrapPi(a) {
  return LabMap.wrapPi(a);
}

/** Guarda el norte canónico. Una vez congelado, no se reescribe solo. */
function lockNorthAlign(reason = "") {
  if (!isNavigableAlign(align)) return;
  align.yaw = wrapPi(align.yaw);
  const snap = {
    tx: align.tx,
    ty: align.ty,
    yaw: align.yaw,
    sx: 1,
    sy: 1,
    ready: true,
    source: align.source,
    odom_ref: { x: odomPose.x, y: odomPose.y, theta: odomPose.theta },
    lockedAt: Date.now(),
    reason: reason || align.source,
  };
  alignFrozen = true;
  try {
    localStorage.setItem(NORTH_KEY, JSON.stringify(snap));
    localStorage.setItem(NORTH_VER_KEY, NORTH_VER);
    sessionStorage.setItem("rbot_align_ver", ALIGN_VER);
    sessionStorage.setItem("rbot_align", JSON.stringify(align));
  } catch {
    /* ignore */
  }
  uploadHmiDebug(true);
}

/**
 * Restaura norte solo si la pose mapa cae en libre (si no → saltos al recargar).
 */
function restoreNorthAlign({ announce = true } = {}) {
  let snap = null;
  try {
    if (localStorage.getItem(NORTH_VER_KEY) === NORTH_VER) {
      snap = JSON.parse(localStorage.getItem(NORTH_KEY) || "null");
    }
  } catch {
    snap = null;
  }
  if (!isNavigableAlign(snap)) return false;
  align = {
    tx: Number(snap.tx) || 0,
    ty: Number(snap.ty) || 0,
    yaw: wrapPi(Number(snap.yaw) || 0),
    sx: 1,
    sy: 1,
    ready: true,
    source: snap.source === "soft" ? "north" : snap.source || "north",
  };
  // Validar más tarde cuando haya mapGrid; por ahora marcar frozen
  alignFrozen = true;
  localizePending = false;
  try {
    sessionStorage.setItem("rbot_align_ver", ALIGN_VER);
    sessionStorage.setItem("rbot_align", JSON.stringify(align));
  } catch {
    /* ignore */
  }
  uploadHmiDebug(true);
  if (announce && hint) {
    hint.textContent = "Norte restaurado (congelado). Teleopera: el mapa no debe saltar.";
  }
  return true;
}

function ensureNavigableAlign({ announce = false } = {}) {
  if (isNavigableAlign(align)) return true;
  return restoreNorthAlign({ announce });
}

/**
 * Fija odom→mapa vía LabMapEngine (ψ = θ_map+FLIP − θ_odom).
 */
function seedAlignToMapPose(mx, my, mth, source = "lidar", { force = false, manual = false } = {}) {
  const applyFlip = source === "lidar" || source === "lidar_in_track";
  align = LabMap.seedAlignFromMapPose(mx, my, mth, odomPose, {
    applyFlip,
    source: source === "lidar" ? "lidar" : "lidar_in_track",
  });
  localizePending = false;
  alignFrozen = true;
  if (labGeometry?.track?.trail_map_closed) perimeterFitted = true;
  lockNorthAlign(source);
}

/** Celda Occupancy libre (misma convención que el raster HMI). */
function cellFree(x, y) {
  if (!mapGrid || !mapMeta) return false;
  const res = Number(mapMeta.resolution) || 0.05;
  const origin = mapMeta.origin || [0, 0];
  const mx = Math.floor((x - origin[0]) / res);
  const my = Math.floor((y - origin[1]) / res);
  if (mx < 1 || my < 1 || mx >= mapW - 1 || my >= mapH - 1) return false;
  return mapGrid[(mapH - 1 - my) * mapW + mx] === 0;
}

/** Celda Occupancy (0 libre, 1 ocupado, 2 unk, -1 fuera). */
function cellState(x, y) {
  if (!mapGrid || !mapMeta) return -1;
  const res = Number(mapMeta.resolution) || 0.05;
  const origin = mapMeta.origin || [0, 0];
  const mx = Math.floor((x - origin[0]) / res);
  const my = Math.floor((y - origin[1]) / res);
  if (mx < 0 || my < 0 || mx >= mapW || my >= mapH) return -1;
  return mapGrid[(mapH - 1 - my) * mapW + mx];
}

/**
 * Proyecta una pose mapa a la celda libre más cercana (no salir del Occupancy).
 * Tras choques el odom se “fuga”; la HMI debe quedarse dentro del lab.
 */
function nearestFreeMap(x, y, maxRm = 0.6) {
  if (cellFree(x, y)) return { x, y };
  if (!mapGrid || !mapMeta) return { x, y };
  const res = Number(mapMeta.resolution) || 0.05;
  const origin = mapMeta.origin || [0, 0];
  const mx0 = Math.floor((x - origin[0]) / res);
  const my0 = Math.floor((y - origin[1]) / res);
  const maxR = Math.max(1, Math.ceil(maxRm / res));
  let best = null;
  let bestD = Infinity;
  for (let r = 1; r <= maxR; r++) {
    for (let dy = -r; dy <= r; dy++) {
      for (let dx = -r; dx <= r; dx++) {
        if (Math.abs(dx) !== r && Math.abs(dy) !== r) continue;
        const mx = mx0 + dx;
        const my = my0 + dy;
        if (mx < 1 || my < 1 || mx >= mapW - 1 || my >= mapH - 1) continue;
        if (mapGrid[(mapH - 1 - my) * mapW + mx] !== 0) continue;
        const wx = origin[0] + (mx + 0.5) * res;
        const wy = origin[1] + (my + 0.5) * res;
        const d = (wx - x) ** 2 + (wy - y) ** 2;
        if (d < bestD) {
          bestD = d;
          best = { x: wx, y: wy };
        }
      }
    }
    if (best) return best;
  }
  // Último recurso: interior del AABB de muros con inset
  const walls = mapContentBounds();
  const inset = 0.14;
  return {
    x: Math.min(walls.maxX - inset, Math.max(walls.minX + inset, x)),
    y: Math.min(walls.maxY - inset, Math.max(walls.minY + inset, y)),
  };
}

function clampMapPose(p) {
  if (!p || !mapGrid) return p;
  if (cellFree(p.x, p.y)) return { ...p, clamped: false };
  const n = nearestFreeMap(p.x, p.y);
  return { x: n.x, y: n.y, theta: p.theta, clamped: true };
}

/** Pose odom→mapa cruda (sin clamp) — LabMapEngine. */
function mapPoseRaw(odom) {
  return LabMap.projectPose(odom || odomPose, align);
}

function mapPoseFrom(odom) {
  return clampMapPose(mapPoseRaw(odom));
}

function mapPose() {
  return mapPoseFrom(odomPose);
}

/** Tras restaurar norte: el perímetro Occupancy NUNCA se invalida. */
function validateRestoredAlign() {
  if (!isNavigableAlign(align) || !mapGrid) return;
  if (perimeterFitted || align.source === "perimeter") {
    // Solo re-anclar tip a libre (yaw intacto); no tirar el SE(2)
    reanchorTranslationToFree({ clearTrail: false });
    return;
  }
  const p = mapPoseRaw(odomPose);
  if (cellFree(p.x, p.y)) return;
  alignFrozen = false;
  align = { tx: 0, ty: 0, yaw: 0, sx: 1, sy: 1, ready: false, source: "none" };
  perimeterFitted = false;
  try {
    localStorage.removeItem(NORTH_KEY);
    sessionStorage.removeItem("rbot_align");
  } catch {
    /* ignore */
  }
  if (hint) {
    hint.textContent =
      "Norte guardado inválido tras recargar — reubicando con LiDAR…";
  }
}

/** AABB del perímetro cyan Occupancy (metros mapa). */
function trackAabb(pad = 0.08) {
  return LabMap.trackAabb(labGeometry?.track?.trail_map_closed, pad);
}

function tipInsideTrack(x, y, pad = 0.05) {
  return LabMap.tipInsideTrack(x, y, labGeometry?.track?.trail_map_closed, pad);
}

/** Celda libre más cercana DENTRO del perímetro cyan (no cualquier pasillo Occupancy). */
function nearestFreeInTrack(x, y, maxRm = 1.2) {
  const box = trackAabb(0.08);
  if (!box || !mapGrid || !mapMeta) return null;
  const res = Number(mapMeta.resolution) || 0.05;
  const origin = mapMeta.origin || [0, 0];
  const inBox = (px, py) =>
    px >= box.minX && px <= box.maxX && py >= box.minY && py <= box.maxY;
  if (inBox(x, y) && cellFree(x, y)) return { x, y };
  const mx0 = Math.floor((x - origin[0]) / res);
  const my0 = Math.floor((y - origin[1]) / res);
  const maxR = Math.max(1, Math.ceil(maxRm / res));
  let best = null;
  let bestD = Infinity;
  for (let r = 0; r <= maxR; r++) {
    for (let dy = -r; dy <= r; dy++) {
      for (let dx = -r; dx <= r; dx++) {
        if (r > 0 && Math.abs(dx) !== r && Math.abs(dy) !== r) continue;
        const mx = mx0 + dx;
        const my = my0 + dy;
        if (mx < 1 || my < 1 || mx >= mapW - 1 || my >= mapH - 1) continue;
        if (mapGrid[(mapH - 1 - my) * mapW + mx] !== 0) continue;
        const px = origin[0] + (mx + 0.5) * res;
        const py = origin[1] + (my + 0.5) * res;
        if (!inBox(px, py)) continue;
        const d = Math.hypot(px - x, py - y);
        if (d < bestD) {
          bestD = d;
          best = { x: px, y: py };
        }
      }
    }
  }
  if (best) return best;
  // Último recurso: centro del AABB cyan si es libre / vecino
  const cx = (box.minX + box.maxX) / 2;
  const cy = (box.minY + box.maxY) / 2;
  if (cellFree(cx, cy)) return { x: cx, y: cy };
  return nearestFreeMap(cx, cy, 0.5);
}

/**
 * Solo mueve tx/ty para meter el tip en libre DENTRO del cyan.
 * NUNCA toca align.yaw (eso causaba avance diagonal).
 */
function reanchorTranslationToFree({ clearTrail = true } = {}) {
  if (!isNavigableAlign(align) || !mapGrid || !mapMeta) return false;
  if (!(perimeterFitted || align.source === "perimeter" || align.source === "lidar_in_track")) {
    return false;
  }
  if (!odomLooksValid()) return false;
  const tip = mapPoseRaw(odomPose);
  const insideOk =
    tipInsideTrack(tip.x, tip.y) &&
    cellFree(tip.x, tip.y) &&
    clearanceToWall(tip.x, tip.y) >= 0.08;
  if (insideOk) return false;
  const nf = nearestFreeInTrack(tip.x, tip.y, 1.4);
  if (!nf || !cellFree(nf.x, nf.y)) return false;
  const dtx = nf.x - tip.x;
  const dty = nf.y - tip.y;
  if (Math.hypot(dtx, dty) < 0.02) return false;
  align = {
    ...align,
    tx: align.tx + dtx,
    ty: align.ty + dty,
    ready: true,
  };
  alignFrozen = true;
  perimeterFitted = true;
  lockNorthAlign("reanchor-free");
  void persistCanonicalTranslation();
  if (clearTrail) {
    trailMap = [];
    trailOdom = odomLooksValid()
      ? [{ x: odomPose.x, y: odomPose.y }]
      : [];
    pushTrailMapPoint(mapPoseRaw(odomPose));
  }
  if (hint) {
    hint.textContent = `Tip dentro de pista Occupancy (Δ${Math.hypot(dtx, dty).toFixed(2)} m)`;
  }
  return true;
}

/**
 * Sin LiDAR: solo traslación (conserva yaw SE2 vivo).
 */
function snapRobotTipInsideTrack({ clearTrail = true, announce = true } = {}) {
  if (!mapGrid) return false;
  if (!isNavigableAlign(align)) {
    // Semilla débil: ψ≈π/2 (receta validada) hasta que llegue LiDAR
    const box = trackAabb(0);
    const mx = box ? (box.minX + box.maxX) / 2 : 0;
    const my = box ? (box.minY + box.maxY) / 2 : 0.2;
    const oth = odomPose.theta || 0;
    // seedAlign suma FLIP → mapTh buscado = ψ + oth − FLIP
    seedAlignToMapPose(
      mx,
      my,
      wrapPi(PERIMETER_YAW_LOCKED + oth - LIDAR_HEADING_FLIP),
      "lidar_in_track"
    );
  }
  const tip = mapPoseRaw(odomPose);
  const target =
    nearestFreeInTrack(tip.x, tip.y, 1.6) ||
    nearestFreeInTrack(0, 0.15, 1.6);
  if (!target) return false;
  const dtx = target.x - tip.x;
  const dty = target.y - tip.y;
  if (Math.hypot(dtx, dty) >= 0.02) {
    align = { ...align, tx: align.tx + dtx, ty: align.ty + dty, ready: true };
  }
  perimeterFitted = true;
  alignFrozen = true;
  if (clearTrail) {
    trailMap = [];
    trailOdom = odomLooksValid()
      ? [{ x: odomPose.x, y: odomPose.y }]
      : [];
  }
  pushTrailMapPoint(mapPoseRaw(odomPose), { allowBreak: true });
  void persistLiveAlign();
  if (announce && hint) {
    hint.textContent = `Tip anclado en pista (${target.x.toFixed(2)}, ${target.y.toFixed(2)})`;
  }
  return true;
}

async function persistCanonicalTranslation() {
  try {
    await fetch(ENDPOINTS.anchorTranslation, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tx: align.tx, ty: align.ty }),
    });
  } catch {
    /* ignore */
  }
}

function pushTrailMapPoint(mp, { allowBreak = false } = {}) {
  if (!mp || !Number.isFinite(mp.x) || !Number.isFinite(mp.y)) return;
  trailMap = LabMap.appendTrailPoint(trailMap, mp.x, mp.y, { allowBreak });
}

/** Metadato del grabado — NO usar como ψ del SE2 vivo. */
function perimeterYaw() {
  const locked = Number(labGeometry?.track?.perimeter_yaw);
  if (Number.isFinite(locked)) return wrapPi(locked);
  return PERIMETER_YAW_LOCKED;
}

/**
 * Ubica el robot EN VIVO dentro del cyan Occupancy.
 * SE2 = receta validada: ψ = (θ_map + FLIP) − θ_odom via seedAlignToMapPose.
 * Overlays cyan/naranja NO se mueven. No borra el trazo.
 */
async function localizeInsideTrack({ manual = false, force = false } = {}) {
  if (localizing) return false;
  if (!mapGrid || !mapMeta) return false;
  const closed = labGeometry?.track?.trail_map_closed;
  if (!closed || closed.length < 4) return false;
  if (!scanData?.ranges?.length) {
    try {
      scanData = await fetchScan(320);
    } catch {
      return false;
    }
  }
  if (!odomLooksValid()) return false;

  localizing = true;
  try {
    const result = LabMap.localizeInTrack({
      odom: odomPose,
      scan: scanData,
      closed,
      boxes: labGeometry?.obstacle_boxes || [],
      mapGrid,
      mapW,
      mapH,
      mapMeta,
      perimeterYawMeta: perimeterYaw(),
    });
    if (!result) {
      if (manual && hint) hint.textContent = "No pude ubicar dentro de la pista";
      return false;
    }
    align = result.align;
    localizePending = false;
    alignFrozen = true;
    perimeterFitted = true;
    yawWallSnapped = true;
    yawSnapPasses = 99;
    lockNorthAlign("lidar_in_track");
    await refineTranslationKeepYaw({ reason: "post-localize", force: true });
    pushTrailMapPoint(mapPoseRaw(odomPose), { allowBreak: true });
    void persistLiveAlign();
    if (hint) {
      const tip = mapPoseRaw(odomPose);
      const deg = ((align.yaw * 180) / Math.PI).toFixed(1);
      hint.textContent = `Ubicado · (${tip.x.toFixed(2)}, ${tip.y.toFixed(2)}) · ψ=${deg}°`;
    }
    uploadHmiDebug(true);
    draw();
    return true;
  } finally {
    localizing = false;
  }
}

async function persistLiveAlign() {
  const body = JSON.stringify({
    yaw: align.yaw,
    tx: align.tx,
    ty: align.ty,
  });
  try {
    await fetch(ENDPOINTS.labSessionAlign || ENDPOINTS.liveAlign, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
  } catch {
    try {
      await fetch(ENDPOINTS.liveAlign, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
      });
    } catch {
      /* ignore */
    }
  }
}

async function localizeInitialPose({ manual = false, force = false } = {}) {
  if (localizing) return false;
  // Preferir localización DENTRO de la pista Occupancy (perímetro cyan)
  if (labGeometry?.track?.trail_map_closed?.length >= 4) {
    const ok = await localizeInsideTrack({ manual, force: true });
    if (ok) return true;
  }
  if (alignFrozen && isNavigableAlign(align) && !manual && !force) return false;
  if (!mapGrid || !mapMeta) return false;
  if (!scanData?.ranges?.length) {
    if (manual) hint.textContent = "Esperando LiDAR…";
    localizePending = true;
    return false;
  }
  if (!odomLooksValid()) {
    if (manual) hint.textContent = "Esperando odometría válida…";
    localizePending = true;
    return false;
  }

  localizing = true;
  lastLocalizeAttemptMs = performance.now();
  try {
    const res = Number(mapMeta.resolution) || 0.05;
    const origin = mapMeta.origin || [0, 0, 0];
    const rays = sampleRays(scanData);
    if (rays.length < 10) {
      localizePending = true;
      if (manual) hint.textContent = "Pocos hits LiDAR — reintenta";
      return false;
    }

    const freeCells = [];
    const seen = new Set();
    const pushCell = (x, y) => {
      const key = `${(Math.round(x / res) * res).toFixed(2)},${(Math.round(y / res) * res).toFixed(2)}`;
      if (seen.has(key)) return;
      seen.add(key);
      freeCells.push({ x, y });
    };

    // Semillas de zonas + TODAS las celdas libres (stride 1)
    for (const seed of LOCALIZE_SEEDS) {
      for (let my = 1; my < mapH - 1; my++) {
        for (let mx = 1; mx < mapW - 1; mx++) {
          if (mapGrid[(mapH - 1 - my) * mapW + mx] !== 0) continue;
          const x = origin[0] + (mx + 0.5) * res;
          const y = origin[1] + (my + 0.5) * res;
          if (Math.hypot(x - seed.x, y - seed.y) <= 0.5) pushCell(x, y);
        }
      }
    }
    for (let my = 1; my < mapH - 1; my++) {
      for (let mx = 1; mx < mapW - 1; mx++) {
        if (mapGrid[(mapH - 1 - my) * mapW + mx] !== 0) continue;
        pushCell(origin[0] + (mx + 0.5) * res, origin[1] + (my + 0.5) * res);
      }
    }
    if (!freeCells.length) return false;

    const yawMap = [];
    for (let i = 0; i < 24; i++) yawMap.push((i * Math.PI) / 12);

    let best = { score: -1e9, x: 0, y: 0, th: 0 };
    let second = -1e9;
    const cellStride = freeCells.length > 600 ? 2 : 1;
    for (const th of yawMap) {
      for (let i = 0; i < freeCells.length; i += cellStride) {
        const c = freeCells[i];
        const score = scoreRaycast(c.x, c.y, th, rays, origin, res);
        if (score > best.score) {
          second = best.score;
          best = { score, x: c.x, y: c.y, th };
        } else if (score > second) {
          second = score;
        }
      }
    }

    // Refine local SIN mutar best dentro del bucle (bug anterior desplazaba 2×)
    let refined = { ...best };
    for (let dx = -0.15; dx <= 0.15; dx += 0.025) {
      for (let dy = -0.15; dy <= 0.15; dy += 0.025) {
        for (let dth = -0.3; dth <= 0.3; dth += 0.05) {
          const x = best.x + dx;
          const y = best.y + dy;
          const th = best.th + dth;
          const score = scoreRaycast(x, y, th, rays, origin, res);
          if (score > refined.score) refined = { score, x, y, th };
        }
      }
    }
    best = refined;

    const minScore = rays.length * 0.28;
    const margin = best.score - second;
    if (best.score < minScore) {
      localizePending = true;
      if (manual || hint) {
        hint.textContent = `LiDAR débil (${best.score.toFixed(0)}/${rays.length}) — reintentando…`;
      }
      return false;
    }
    // Empate fuerte entre hipótesis: aceptar pero marcar para re-check
    if (margin < rays.length * 0.04 && second > minScore * 0.85) {
      if (hint) {
        hint.textContent = `Ubicación ambigua (margen ${margin.toFixed(1)}) — mejorando…`;
      }
    }

    alignFrozen = false;
    seedAlignToMapPose(best.x, best.y, best.th, "lidar", {
      force: true,
      manual,
    });
    // Tras LiDAR: calzar traslación (holgura al muro) sin tocar rumbo
    if (!perimeterFitted) {
      maybeNudgeTranslationFit({ force: true, reason: "post-lidar" });
    }
    if (!trailOdom.length && odomLooksValid()) {
      trailOdom = [{ x: odomPose.x, y: odomPose.y }];
    }
    persistTrail();
    localizePending = false;
    hint.textContent = `Ubicado (${best.x.toFixed(2)}, ${best.y.toFixed(2)}) · match ${best.score.toFixed(0)}/${rays.length}`;
    draw();
    uploadHmiDebug(true);
    return true;
  } finally {
    localizing = false;
  }
}

/**
 * Si el norte guardado no cuadra con el LiDAR/odom actuales → forzar reubicación.
 */
async function verifyOrRelocalizeOnLoad() {
  if (!mapGrid || !mapMeta) return false;
  // Con perímetro canónico: nunca mutar SE(2)
  if (perimeterFitted || align.source === "perimeter") {
    trailOdom = keepContinuousTrailTail(trailOdom);
    return false;
  }

  // Sin align: localizar sí o sí
  if (!isNavigableAlign(align)) {
    localizePending = true;
    return localizeInitialPose({ manual: false, force: true });
  }

  let snap = null;
  try {
    snap = JSON.parse(localStorage.getItem(NORTH_KEY) || "null");
  } catch {
    snap = null;
  }
  const ref = snap?.odom_ref;
  const ox = odomPose.x || 0;
  const oy = odomPose.y || 0;
  const atOrigin = Math.abs(ox) < 1e-4 && Math.abs(oy) < 1e-4;

  // Odom reiniciado (origen) vs ref antigua → norte inválido SIEMPRE
  if (ref && Number.isFinite(ref.x) && Number.isFinite(ref.y)) {
    const refMag = Math.hypot(Number(ref.x), Number(ref.y));
    const jump = Math.hypot(ox - Number(ref.x), oy - Number(ref.y));
    if ((atOrigin && refMag > 0.05) || jump > 0.35) {
      if (hint) {
        hint.textContent =
          "Odom reiniciado tras reconexión — reubicando pose/rumbo con LiDAR…";
      }
      invalidateAlignForRelocalize("odom-ref-mismatch");
      localizePending = true;
      return localizeInitialPose({ manual: false, force: true });
    }
  }

  // Pose mapa fuera de libre → relocalizar
  const raw = mapPoseRaw(odomPose);
  if (!cellFree(raw.x, raw.y)) {
    if (hint) {
      hint.textContent = "Pose fuera de libre — reubicando con LiDAR…";
    }
    invalidateAlignForRelocalize("pose-not-free");
    localizePending = true;
    return localizeInitialPose({ manual: false, force: true });
  }

  // Align «válido» pero LiDAR no lo respalda
  if (scanData?.ranges?.length) {
    const rays = sampleRays(scanData);
    const sc = lidarScoreAtMapPose(raw.x, raw.y, raw.theta);
    if (rays.length >= 10 && sc < rays.length * 0.22) {
      if (hint) {
        hint.textContent =
          "Pose inicial no coincide con LiDAR — reubicando…";
      }
      invalidateAlignForRelocalize("lidar-mismatch");
      localizePending = true;
      return localizeInitialPose({ manual: false, force: true });
    }
  }
  return false;
}

async function localizeNearCorners(opts) {
  return localizeInitialPose(opts);
}

function persistTrail() {
  try {
    sessionStorage.setItem(
      "rbot_trail_odom",
      JSON.stringify(trailOdom.slice(-900))
    );
    sessionStorage.setItem(
      "rbot_trail_map",
      JSON.stringify(trailMap.slice(-900))
    );
    sessionStorage.setItem("rbot_align", JSON.stringify(align));
    sessionStorage.setItem(
      "rbot_perimeter_fitted",
      perimeterFitted ? "1" : "0"
    );
    sessionStorage.setItem("rbot_last_fit_len", String(lastFitPathLen || 0));
  } catch {
    /* ignore quota */
  }
  // Subir snapshot para diagnóstico (throttled)
  uploadHmiDebug();
}

let lastDebugUploadMs = 0;
function uploadHmiDebug(force = false) {
  const now = performance.now();
  if (!force && now - lastDebugUploadMs < 2000) return;
  lastDebugUploadMs = now;
  // Nunca subir pending como “ready” (rompe goto a zonas).
  const payloadAlign = isNavigableAlign(align)
    ? align
    : { ...align, ready: false, source: align.source || "pending" };
  const body = {
    trail_odom: trailOdom.slice(-900),
    align: {
      ...payloadAlign,
      ready: Boolean(payloadAlign.ready) || perimeterFitted,
      source: perimeterFitted
        ? payloadAlign.source === "soft"
          ? "soft"
          : "perimeter"
        : payloadAlign.source,
    },
    hint: hint?.textContent || "",
    perimeter_fitted: perimeterFitted,
    odom: odomPose,
  };
  void fetch("/api/v1/robot/hmi_debug", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).catch(() => {});
}

function restorePersistedTrail() {
  try {
    // Preferir norte canónico (localStorage) sobre session provisional
    if (restoreNorthAlign({ announce: false })) {
      // ok
    } else {
      const raw = sessionStorage.getItem("rbot_trail_odom");
      const pts = raw ? JSON.parse(raw) : [];
      if (Array.isArray(pts) && pts.length > 5) {
        trailOdom = pts
          .filter((p) => p && Number.isFinite(p.x) && Number.isFinite(p.y))
          .map((p) => ({ x: Number(p.x), y: Number(p.y) }));
      }
      const a = JSON.parse(sessionStorage.getItem("rbot_align") || "null");
      if (a && typeof a.yaw === "number" && a.ready) {
        const ver = sessionStorage.getItem("rbot_align_ver");
        if (ver === ALIGN_VER) {
          align = {
            tx: Number(a.tx) || 0,
            ty: Number(a.ty) || 0,
            yaw: Number(a.yaw) || 0,
            sx: 1,
            sy: 1,
            ready: true,
            source: a.source || "perimeter",
          };
          if (!isNavigableAlign(align)) {
            align.ready = false;
            perimeterFitted = false;
          } else {
            perimeterFitted =
              align.source === "perimeter" ||
              sessionStorage.getItem("rbot_perimeter_fitted") === "1";
            lastFitPathLen = Number(sessionStorage.getItem("rbot_last_fit_len") || 0);
            localizePending = false;
            lockNorthAlign("restore");
          }
        } else {
          sessionStorage.removeItem("rbot_align");
          sessionStorage.removeItem("rbot_perimeter_fitted");
          sessionStorage.removeItem("rbot_last_fit_len");
          perimeterFitted = false;
          lastFitPathLen = 0;
        }
      } else {
        perimeterFitted = sessionStorage.getItem("rbot_perimeter_fitted") === "1";
        lastFitPathLen = Number(sessionStorage.getItem("rbot_last_fit_len") || 0);
      }
    }
    // Trazo siempre desde session si existe (sin puntos 0,0 basura)
    const rawTrail = sessionStorage.getItem("rbot_trail_odom");
    if (rawTrail && !trailOdom.length) {
      const pts = JSON.parse(rawTrail);
      if (Array.isArray(pts) && pts.length > 5) {
        trailOdom = pts
          .filter(
            (p) =>
              p &&
              Number.isFinite(p.x) &&
              Number.isFinite(p.y) &&
              !(Math.abs(p.x) < 1e-6 && Math.abs(p.y) < 1e-6)
          )
          .map((p) => ({ x: Number(p.x), y: Number(p.y) }));
      }
    }
    try {
      const rawMap = sessionStorage.getItem("rbot_trail_map");
      if (rawMap && !trailMap.length) {
        const pts = JSON.parse(rawMap);
        if (Array.isArray(pts) && pts.length > 1) {
          trailMap = pts
            .filter((p) => p && Number.isFinite(p.x) && Number.isFinite(p.y))
            .map((p) => ({ x: Number(p.x), y: Number(p.y) }));
        }
      }
    } catch {
      /* ignore */
    }
    if (isNavigableAlign(align)) {
      perimeterFitted =
        perimeterFitted ||
        align.source === "perimeter" ||
        sessionStorage.getItem("rbot_perimeter_fitted") === "1";
      lastFitPathLen = Number(sessionStorage.getItem("rbot_last_fit_len") || 0) || lastFitPathLen;
      localizePending = false;
      uploadHmiDebug(true);
    }
    sessionStorage.setItem("rbot_align_ver", ALIGN_VER);
  } catch {
    /* ignore */
  }
}

function trailPathLength(pts) {
  let len = 0;
  for (let i = 1; i < pts.length; i++) {
    const dx = pts[i].x - pts[i - 1].x;
    const dy = pts[i].y - pts[i - 1].y;
    len += Math.hypot(dx, dy);
  }
  return len;
}

/**
 * Quedarse solo con la última vuelta cerrada (ignora cuadrados anteriores).
 * Si no hay cierre claro, devolver todo el trazo (útil para ajuste manual).
 */
function extractLastLoop(pts) {
  if (!pts || pts.length < 30) return pts || [];
  const end = pts[pts.length - 1];
  for (let i = pts.length - 25; i >= 0; i--) {
    if (Math.hypot(pts[i].x - end.x, pts[i].y - end.y) > 0.35) continue;
    const seg = pts.slice(i);
    if (trailPathLength(seg) < 2.8) continue;
    const box = trailOrientedBounds(seg);
    if (box.width >= 0.7 && box.height >= 0.7) return seg;
  }
  return pts;
}

function isClosedPerimeter(pts) {
  const loop = extractLastLoop(pts);
  if (loop.length < 30) return false;
  if (trailPathLength(loop) < 3.0) return false;
  const box = trailOrientedBounds(loop);
  if (box.width < 0.75 || box.height < 0.75) return false;
  const a = loop[0];
  const b = loop[loop.length - 1];
  return Math.hypot(a.x - b.x, a.y - b.y) < 0.35;
}

/** Rectángulo orientado (PCA) del trail en odom. */
function trailOrientedBounds(pts) {
  const n = pts.length;
  let cx = 0;
  let cy = 0;
  for (const p of pts) {
    cx += p.x;
    cy += p.y;
  }
  cx /= n;
  cy /= n;
  let sxx = 0;
  let sxy = 0;
  let syy = 0;
  for (const p of pts) {
    const dx = p.x - cx;
    const dy = p.y - cy;
    sxx += dx * dx;
    sxy += dx * dy;
    syy += dy * dy;
  }
  const angle = 0.5 * Math.atan2(2 * sxy, sxx - syy || 1e-9);
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  let minU = Infinity;
  let maxU = -Infinity;
  let minV = Infinity;
  let maxV = -Infinity;
  for (const p of pts) {
    const dx = p.x - cx;
    const dy = p.y - cy;
    const u = c * dx + s * dy;
    const v = -s * dx + c * dy;
    if (u < minU) minU = u;
    if (u > maxU) maxU = u;
    if (v < minV) minV = v;
    if (v > maxV) maxV = v;
  }
  const u0 = (minU + maxU) / 2;
  const v0 = (minV + maxV) / 2;
  return {
    angle,
    width: Math.max(0.05, maxU - minU),
    height: Math.max(0.05, maxV - minV),
    cx: cx + c * u0 - s * v0,
    cy: cy + s * u0 + c * v0,
  };
}

/**
 * AABB en metros de las celdas ocupadas (muros reales), sin el padding gris del PGM.
 */
function mapContentBounds() {
  const res = Number(mapMeta?.resolution) || 0.05;
  const origin = mapMeta?.origin || [0, 0, 0];
  if (!mapGrid || !mapW || !mapH) {
    return {
      minX: origin[0],
      minY: origin[1],
      maxX: origin[0] + mapW * res,
      maxY: origin[1] + mapH * res,
    };
  }
  let minMX = mapW;
  let maxMX = -1;
  let minMY = mapH;
  let maxMY = -1;
  for (let my = 0; my < mapH; my++) {
    for (let mx = 0; mx < mapW; mx++) {
      if (mapGrid[(mapH - 1 - my) * mapW + mx] !== 1) continue;
      if (mx < minMX) minMX = mx;
      if (mx > maxMX) maxMX = mx;
      if (my < minMY) minMY = my;
      if (my > maxMY) maxMY = my;
    }
  }
  if (maxMX < minMX) {
    return {
      minX: origin[0],
      minY: origin[1],
      maxX: origin[0] + mapW * res,
      maxY: origin[1] + mapH * res,
    };
  }
  return {
    minX: origin[0] + minMX * res,
    minY: origin[1] + minMY * res,
    maxX: origin[0] + (maxMX + 1) * res,
    maxY: origin[1] + (maxMY + 1) * res,
  };
}

/** Fracción de puntos del trail (ya en mapa) que caen en celda libre. */
function freeSpaceScore(loop, yaw, tx, ty, s) {
  if (!mapGrid || !mapMeta) return 0;
  const res = Number(mapMeta.resolution) || 0.05;
  const origin = mapMeta.origin || [0, 0, 0];
  const c = Math.cos(yaw);
  const sn = Math.sin(yaw);
  let ok = 0;
  let n = 0;
  const step = Math.max(1, Math.floor(loop.length / 80));
  for (let i = 0; i < loop.length; i += step) {
    const p = loop[i];
    const xr = c * p.x - sn * p.y;
    const yr = sn * p.x + c * p.y;
    const x = s * xr + tx;
    const y = s * yr + ty;
    const mx = Math.floor((x - origin[0]) / res);
    const my = Math.floor((y - origin[1]) / res);
    n += 1;
    if (mx < 0 || my < 0 || mx >= mapW || my >= mapH) continue;
    if (mapGrid[(mapH - 1 - my) * mapW + mx] === 0) ok += 1;
  }
  return n ? ok / n : 0;
}

/**
 * Inclinación media de los tramos del perímetro vs ejes del mapa (0 = lados // muros).
 * Acumula segmentos cortos (densify 6 cm) hasta ≥0.2 m — si no, skew queda fijo ~20°
 * y el fit solo mira «libre» → rombo con 100% free.
 */
function sideAlignRad(loop, yaw) {
  const c = Math.cos(yaw);
  const sn = Math.sin(yaw);
  let wSum = 0;
  let pSum = 0;
  let accDx = 0;
  let accDy = 0;
  let accLen = 0;
  const flush = () => {
    if (accLen < 0.18) {
      accDx = 0;
      accDy = 0;
      accLen = 0;
      return;
    }
    const mx = c * accDx - sn * accDy;
    const my = sn * accDx + c * accDy;
    let ang = Math.atan2(my, mx);
    ang = ((ang % Math.PI) + Math.PI) % Math.PI;
    if (ang > Math.PI / 2) ang -= Math.PI / 2;
    const pen = Math.min(ang, Math.PI / 2 - ang);
    pSum += pen * accLen;
    wSum += accLen;
    accDx = 0;
    accDy = 0;
    accLen = 0;
  };
  for (let i = 1; i < loop.length; i++) {
    const dx = loop[i].x - loop[i - 1].x;
    const dy = loop[i].y - loop[i - 1].y;
    const len = Math.hypot(dx, dy);
    if (len < 1e-6) continue;
    // Cambio brusco de dirección → cerrar tramo
    if (accLen > 0.05) {
      const dot = accDx * dx + accDy * dy;
      if (dot < 0) flush();
    }
    accDx += dx;
    accDy += dy;
    accLen += len;
    if (accLen >= 0.22) flush();
  }
  flush();
  return wSum > 0 ? pSum / wSum : 0.35;
}

/** AABB rotado + traslación que centra el carril. */
function rigidCenterForYaw(loop, yaw, mcx, mcy) {
  const c = Math.cos(yaw);
  const sn = Math.sin(yaw);
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const p of loop) {
    const x = c * p.x - sn * p.y;
    const y = sn * p.x + c * p.y;
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
  }
  const tw = Math.max(0.05, maxX - minX);
  const th = Math.max(0.05, maxY - minY);
  const tx = mcx - (minX + maxX) / 2;
  const ty = mcy - (minY + maxY) / 2;
  return { tx, ty, tw, th };
}

/**
 * Infere rectángulo cerrado (OBB odom) aunque el trazo no cierre o se vea rombo en mapa.
 * El rombo visual suele ser yaw malo; la geometría en odom es casi rectangular.
 */
function inferClosedRectangle(pts) {
  if (!pts || pts.length < 4) return null;
  const box = trailOrientedBounds(pts);
  if (box.width < 0.5 || box.height < 0.5) return null;
  const hw = box.width / 2;
  const hh = box.height / 2;
  const c = Math.cos(box.angle);
  const s = Math.sin(box.angle);
  const uv = [
    [-hw, -hh],
    [hw, -hh],
    [hw, hh],
    [-hw, hh],
    [-hw, -hh],
  ];
  return uv.map(([u, v]) => ({
    x: box.cx + c * u - s * v,
    y: box.cy + s * u + c * v,
  }));
}

/** Densifica lados del rectángulo para score de libre / dibujo. */
function densifyClosedRect(corners, step = 0.08) {
  if (!corners || corners.length < 2) return corners || [];
  const out = [];
  for (let i = 1; i < corners.length; i++) {
    const a = corners[i - 1];
    const b = corners[i];
    const len = Math.hypot(b.x - a.x, b.y - a.y);
    const n = Math.max(1, Math.ceil(len / step));
    for (let k = 0; k < n; k++) {
      const t = k / n;
      out.push({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t });
    }
  }
  out.push({ ...corners[corners.length - 1] });
  return out;
}

async function saveTrackPerimeterToApi(closedOdom) {
  try {
    await fetch(ENDPOINTS.trackPerimeter, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        trail_odom: trailOdom.slice(-900),
        closed_odom: closedOdom || null,
        align: { ...align, ready: true, source: align.source || "perimeter" },
        hint: hint?.textContent || "",
      }),
    });
  } catch {
    /* ignore */
  }
}

async function loadLabGeometry() {
  try {
    const res = await fetch(ENDPOINTS.labTraces);
    if (!res.ok) return false;
    labGeometry = await res.json();
    return true;
  } catch {
    labGeometry = null;
    return false;
  }
}

/**
 * Aplica el SE(2) canónico guardado en el servidor (track_perimeter).
 * Es lo que hace que pose/orientación queden bien sin que el usuario pulse nada.
 */
/**
 * Aplica live_align de sesión si existe; NO fuerza ψ=perimeter_yaw
 * (eso hacía que avanzar de frente saliera en diagonal).
 */
function applyCanonicalLabAlign({ announce = true } = {}) {
  const a =
    labGeometry?.track?.live_align ||
    labGeometry?.align ||
    labGeometry?.track?.align_canonical ||
    null;
  if (!a || !Number.isFinite(Number(a.yaw))) return false;
  align = {
    yaw: wrapPi(Number(a.yaw) || 0),
    tx: Number(a.tx) || 0,
    ty: Number(a.ty) || 0,
    sx: 1,
    sy: 1,
    ready: true,
    source: a.source === "lidar_in_track" ? "lidar_in_track" : "perimeter",
  };
  perimeterFitted = Boolean(labGeometry?.track?.trail_map_closed?.length);
  alignFrozen = true;
  yawWallSnapped = true;
  yawSnapPasses = 99;
  trailCentered = true;
  localizePending = false;
  alignNeedsManual = false;
  lockNorthAlign("live-server");
  try {
    sessionStorage.setItem("rbot_perimeter_fitted", perimeterFitted ? "1" : "0");
    sessionStorage.setItem("rbot_align_ver", ALIGN_VER);
  } catch {
    /* ignore */
  }
  // Solo tip dentro del cyan; yaw intacto
  reanchorTranslationToFree({ clearTrail: false });
  if (announce && hint) {
    const deg = ((align.yaw * 180) / Math.PI).toFixed(1);
    hint.textContent = `Mapa listo · SE2 vivo (ψ=${deg}°) · overlays Occupancy`;
  }
  return true;
}

/**
 * Solo traslación LiDAR con yaw congelado.
 * Corrige desfase de carril (p.ej. tip «subido») sin reintroducir diagonal.
 * Desplaza trailMap el mismo Δ para que el trazo no quede desfasado.
 */
async function refineTranslationKeepYaw({
  reason = "",
  force = false,
} = {}) {
  if (!LabMap.isNavigableAlign(align) || !mapGrid || !mapMeta) return false;
  if (!scanData?.ranges?.length) {
    try {
      scanData = await fetchScan(280);
    } catch {
      return false;
    }
  }
  const closed = labGeometry?.track?.trail_map_closed;
  if (!closed || closed.length < 4) return false;
  const result = LabMap.refineTranslation({
    odom: odomPose,
    align,
    scan: scanData,
    closed,
    boxes: labGeometry?.obstacle_boxes || [],
    mapGrid,
    mapW,
    mapH,
    mapMeta,
    force: force || reason === "outside",
  });
  if (!result) return false;
  align = result.align;
  if (result.dist >= 0.03 && trailMap.length) {
    trailMap = LabMap.shiftTrail(trailMap, result.dtx, result.dty);
  }
  alignFrozen = true;
  perimeterFitted = true;
  lockNorthAlign("t-refine");
  void persistLiveAlign();
  if (hint && result.dist >= 0.05) {
    hint.textContent = `Carril recalibrado (Δ${result.dist.toFixed(2)} m) · rumbo intacto`;
  }
  uploadHmiDebug(true);
  draw();
  return true;
}

/** @deprecated */
async function recoverTranslationKeepYaw() {
  return refineTranslationKeepYaw({ reason: "legacy", force: false });
}

/** Conserva solo la cola continua del trazo (sin saltos > TRAIL_MAX_STEP_M). */
function keepContinuousTrailTail(pts) {
  if (!pts || !pts.length) return [];
  let start = 0;
  for (let i = pts.length - 1; i > 0; i--) {
    const d = Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
    if (d > TRAIL_MAX_STEP_M) {
      start = i;
      break;
    }
    start = i - 1;
  }
  return pts.slice(start).map((p) => ({ x: Number(p.x), y: Number(p.y) }));
}

/** Pose del icono: clamp visual a libre sin tocar el SE(2). */
function displayRobotPose() {
  const raw = mapPoseRaw(odomPose);
  if (!perimeterFitted || !mapGrid) return raw;
  if (cellFree(raw.x, raw.y)) return raw;
  const nf = nearestFreeMap(raw.x, raw.y, 0.45);
  return { x: nf.x, y: nf.y, theta: raw.theta };
}

/**
 * Encaja el perímetro (pista exterior) al carril del Occupancy.
 * SOLO SE(2) rígido, un disparo, luego freeze absoluto (v16).
 * Si el trazo no cierra → infiere rectángulo OBB y lo usa como verdad.
 */
function fitMapToTrailPerimeter({ manual = false, soft = false } = {}) {
  if (!mapMeta || !mapW || !mapH) {
    if (manual) hint.textContent = "Mapa no cargado";
    return false;
  }

  const minPts = soft || manual ? 10 : 24;
  const minSide = soft ? 0.75 : manual ? 0.55 : 0.75;
  const rawLoop = extractLastLoop(trailOdom);
  if (!rawLoop || rawLoop.length < minPts) {
    if (manual) {
      hint.textContent =
        "Necesito más trazo azul (pista exterior; con ~10+ pts ya puedo ajustar)";
    }
    return false;
  }

  const closedCorners = inferClosedRectangle(rawLoop);
  const loop = densifyClosedRect(closedCorners || rawLoop, 0.07);
  const trail = trailOrientedBounds(loop);
  if (trail.width < minSide || trail.height < minSide) {
    if (manual) {
      hint.textContent = "El rastro aún no es un rectángulo claro (≥0.55 m)";
    }
    return false;
  }

  const walls = mapContentBounds();
  const inset = 0.12;
  const lane = {
    minX: walls.minX + inset,
    minY: walls.minY + inset,
    maxX: walls.maxX - inset,
    maxY: walls.maxY - inset,
  };
  const mapWm = Math.max(0.4, lane.maxX - lane.minX);
  const mapHm = Math.max(0.4, lane.maxY - lane.minY);
  const mcx = (lane.minX + lane.maxX) / 2;
  const mcy = (lane.minY + lane.maxY) / 2;

  const scoreCandidate = (yaw) => {
    const { tx, ty, tw, th } = rigidCenterForYaw(loop, yaw, mcx, mcy);
    const free = freeSpaceScore(loop, yaw, tx, ty, 1);
    const sizePen =
      Math.abs(Math.log(tw / mapWm)) + Math.abs(Math.log(th / mapHm));
    const skew = sideAlignRad(loop, yaw);
    // skew manda (anti-rombo); libre + tamaño como freno
    const score = free * 10 - sizePen * 1.2 - skew * 14;
    return { score, yaw, tx, ty, sx: 1, sy: 1, free, tw, th, mapWm, mapHm, skew };
  };

  let best = null;
  for (let deg = 0; deg < 360; deg += 2) {
    const cand = scoreCandidate((deg * Math.PI) / 180);
    if (!best || cand.score > best.score) best = cand;
  }
  if (best) {
    const baseDeg = (best.yaw * 180) / Math.PI;
    for (let d = -4; d <= 4; d += 0.25) {
      const cand = scoreCandidate(((baseDeg + d) * Math.PI) / 180);
      if (cand.score > best.score) best = cand;
    }
  }

  if (!best) return false;
  const minFree = soft ? 0.5 : manual ? 0.3 : 0.5;
  if (best.free < minFree) {
    if (manual) {
      hint.textContent = `Ajuste débil (libre ${(best.free * 100).toFixed(0)}%) — da una vuelta por el perímetro`;
    }
    return false;
  }

  align = {
    yaw: best.yaw,
    tx: best.tx + MAP_ALIGN_NUDGE.tx,
    ty: best.ty + MAP_ALIGN_NUDGE.ty,
    sx: 1,
    sy: 1,
    ready: true,
    source: soft ? "soft" : "perimeter",
  };
  localizePending = false;

  // NO sustituir trailOdom por el rectángulo densificado:
  // mezclarlo con odom vivo generaba saltos de 0.4–0.7 m («trazo loco»).
  // El perímetro cerrado vive en labGeometry (overlay cyan).

  if (!soft) {
    perimeterFitted = true;
    trailCentered = true;
    yawWallSnapped = true;
    yawSnapPasses = 99;
    lastFitPathLen = trailPathLength(trailOdom);
    trailOdom = keepContinuousTrailTail(trailOdom);
  }
  try {
    sessionStorage.setItem("rbot_align_ver", ALIGN_VER);
  } catch {
    /* ignore */
  }
  if (!soft || best.free >= 0.65) {
    lockNorthAlign(soft ? "soft" : "perimeter");
  }
  alignFrozen = true;
  persistTrail();
  if (!soft) {
    void saveTrackPerimeterToApi(closedCorners);
    void loadLabGeometry();
  }

  const deg = ((align.yaw * 180) / Math.PI).toFixed(1);
  const skewDeg = ((best.skew * 180) / Math.PI).toFixed(1);
  const closedNote = closedCorners ? " · rectángulo cerrado" : "";
  if (!soft || manual) {
    hint.textContent = `SE(2) canónico · yaw ${deg}° · skew ${skewDeg}° · libre ${(best.free * 100).toFixed(0)}%${closedNote}`;
  } else {
    hint.textContent = `Auto-ajuste · yaw ${deg}° · libre ${(best.free * 100).toFixed(0)}%`;
  }
  return true;
}
function setView(view) {
  activeView = view;
  document.body.dataset.view = view;
  document.querySelectorAll(".view-tab").forEach((tab) => {
    const on = tab.dataset.view === view;
    tab.classList.toggle("is-active", on);
    tab.setAttribute("aria-selected", on ? "true" : "false");
  });
  if (labStage) labStage.hidden = view !== "lab";
  hint.textContent =
    view === "lab"
      ? "Mapa Gazebo · trayectoria en vivo"
      : "Cámara · actívala al llegar al destino";
  fitAll();
  draw();
}

/** map meters → coords de pantalla (antes del escalado a píxeles). */
function toDisplay(x, y) {
  const c = Math.cos(DISPLAY_YAW);
  const s = Math.sin(DISPLAY_YAW);
  return { x: c * x - s * y, y: s * x + c * y };
}

function startScanLoop() {
  const tick = async () => {
    if (activeView !== "lab") {
      scanTimer = setTimeout(tick, 2000);
      return;
    }
    try {
      scanData = await fetchScan(320);
      const n = scanData?.count || 0;
      // Subir trazo aunque el robot esté parado (diagnóstico / guardar perímetro)
      uploadHmiDebug(true);
      // Ruta planificada (goto A*) para overlay
      try {
        const dbg = await fetchHmiDebug();
        const pp = dbg?.planned_path;
        plannedPath =
          pp && Array.isArray(pp.waypoints) && pp.waypoints.length >= 2
            ? pp
            : null;
      } catch {
        /* ignore */
      }
      // Reubicación automática al arranque / si el align no cuadra
      if (localizePending && !perimeterFitted) {
        hint.textContent = `Ubicando con LiDAR (${n} pts)…`;
        const ok = await localizeInitialPose({ manual: false, force: true });
        if (!ok) await localizeOnMap({ manual: false });
      } else if (plannedPath?.label) {
        const L = Number(plannedPath.length_m) || 0;
        hint.textContent = `Ruta a ${plannedPath.label}: ${L.toFixed(2)} m · ${plannedPath.n || plannedPath.waypoints.length} wp`;
      } else if (perimeterFitted) {
        const now = performance.now();
        // Cada ~8 s: recalibrar carril (traslación) si el LiDAR ve desfase
        if (now - lastLaneRefineMs > 8000) {
          lastLaneRefineMs = now;
          await refineTranslationKeepYaw({ reason: "scan-loop" });
        }
        const mp = mapPose();
        hint.textContent = `Mapa OK · (${mp.x.toFixed(2)}, ${mp.y.toFixed(2)}) · LiDAR ${n}`;
      } else if (align.ready) {
        const mp = mapPose();
        hint.textContent = `Gazebo · (${mp.x.toFixed(2)}, ${mp.y.toFixed(2)}) · LiDAR ${n}`;
      } else {
        hint.textContent = `Mapa listo · LiDAR ${n} pts · dibuja el perímetro`;
      }
    } catch (err) {
      hint.textContent = `LiDAR: ${err.message}`;
    }
    scanTimer = setTimeout(tick, 2500);
  };
  // Dar prioridad al status/WS al abrir la HMI
  scanTimer = setTimeout(() => void tick(), 3000);
}

async function loadMap(mapId) {
  mapMeta = await fetchMapMeta(mapId);
  mapMeta.id = mapId;
  mapZones = Array.isArray(mapMeta.zones) ? mapMeta.zones : [];
  const img = new Image();
  await new Promise((resolve, reject) => {
    img.onload = resolve;
    img.onerror = () => reject(new Error("No se pudo cargar mapa"));
    img.src = ENDPOINTS.mapImage(mapId);
  });
  mapImage = img;
  mapW = img.width;
  mapH = img.height;
  mapGrid = rasterizeMap(img);
  if (!trailOdom.length) restorePersistedTrail();
  validateRestoredAlign();

  // 1) Overlays Occupancy (cyan/naranja) + ubicar ROBOT dentro de la pista
  await loadLabGeometry();
  if (labGeometry?.track?.trail_map_closed?.length >= 4) {
    perimeterFitted = true; // overlays activos
    localizePending = false;
    // Tip provisional dentro del cyan (evita pose fuera mientras llega LiDAR)
    snapRobotTipInsideTrack({ clearTrail: true, announce: false });
    void (async () => {
      try {
        for (let i = 0; i < 10 && !odomLooksValid(); i++) {
          await new Promise((r) => setTimeout(r, 200));
        }
        let ok = false;
        for (let attempt = 0; attempt < 5 && !ok; attempt++) {
          try {
            scanData = await fetchScan(320);
            ok = await localizeInsideTrack({ manual: false, force: true });
          } catch {
            ok = false;
          }
          if (!ok) await new Promise((r) => setTimeout(r, 800));
        }
        if (!ok) {
          // Sin LiDAR: tip en pista (NO SE2 grabado con tip fuera del cyan)
          snapRobotTipInsideTrack({ clearTrail: true, announce: true });
        }
        uploadHmiDebug(true);
        syncLocalizeButton();
        draw();
      } catch {
        snapRobotTipInsideTrack({ clearTrail: true, announce: false });
        draw();
      }
    })();
    syncLocalizeButton();
    fitAll();
    draw();
    return;
  }

  if (applyCanonicalLabAlign({ announce: true })) {
    localizePending = false;
    trailOdom = keepContinuousTrailTail(trailOdom);
    trailMap = [];
    reanchorTranslationToFree({ clearTrail: true });
    if (odomLooksValid() && align.ready) {
      pushTrailMapPoint(mapPoseRaw(odomPose));
    }
    void (async () => {
      try {
        for (let i = 0; i < 8 && !odomLooksValid(); i++) {
          await new Promise((r) => setTimeout(r, 200));
        }
        reanchorTranslationToFree({ clearTrail: false });
        if (odomLooksValid() && align.ready) {
          pushTrailMapPoint(mapPoseRaw(odomPose));
        }
        persistTrail();
        uploadHmiDebug(true);
        syncLocalizeButton();
        draw();
      } catch {
        /* ignore */
      }
    })();
    syncLocalizeButton();
    fitAll();
    draw();
    return;
  }

  // 2) Sin perímetro guardado: flujo LiDAR clásico
  if (alignFrozen && isNavigableAlign(align)) {
    localizePending = false;
    void (async () => {
      try {
        scanData = await fetchScan(320);
        if (!perimeterFitted) {
          const relocated = await verifyOrRelocalizeOnLoad();
          if (!relocated) {
            maybeNudgeTranslationFit({ force: true, reason: "post-load" });
          }
        }
        uploadHmiDebug(true);
        syncLocalizeButton();
        draw();
      } catch {
        /* ignore */
      }
    })();
    syncLocalizeButton();
    fitAll();
    draw();
    return;
  }

  // Invalidar align identidad
  if (
    align.ready &&
    Math.abs(align.tx) < 0.05 &&
    Math.abs(align.ty) < 0.05 &&
    Math.abs(align.yaw) < 0.05 &&
    align.source !== "perimeter" &&
    align.source !== "lidar" &&
    align.source !== "north"
  ) {
    align.ready = false;
  }

  if (isNavigableAlign(align)) {
    alignFrozen = true;
    localizePending = false;
    void (async () => {
      try {
        scanData = await fetchScan(320);
        await verifyOrRelocalizeOnLoad();
        uploadHmiDebug(true);
        draw();
      } catch {
        /* ignore */
      }
    })();
    uploadHmiDebug(true);
  } else if (isClosedPerimeter(trailOdom)) {
    fitMapToTrailPerimeter({ manual: false });
  } else if (!isNavigableAlign(align)) {
    provisionalAlign();
    localizePending = true;
    void (async () => {
      try {
        // Esperar odom antes del primer LiDAR (evita pose inicial basura)
        for (let i = 0; i < 10 && !odomLooksValid(); i++) {
          await new Promise((r) => setTimeout(r, 250));
        }
        scanData = await fetchScan(320);
        await localizeInitialPose({ manual: false, force: true });
        draw();
      } catch {
        /* pending — el scan loop reintenta */
      }
    })();
  }
  if (alignFrozen && !perimeterFitted && trailOdom.length >= 10) {
    maybeNudgeTranslationFit({ force: true, reason: "post-load-noperim" });
  }
  syncLocalizeButton();
  fitAll();
  draw();
  if (isNavigableAlign(align)) uploadHmiDebug(true);
  else uploadHmiDebug();
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
    const g = data[i * 4]; // grayscale PNG
    if (g < 50) grid[i] = 1; // occupied
    else if (g > 240) grid[i] = 0; // free
    else grid[i] = 2; // unknown
  }
  return grid;
}

function fitAll() {
  fitPane(gazeboCanvas);
}

function fitPane(el) {
  if (!el) return;
  const parent = el.parentElement;
  if (!parent) return;
  const w = parent.clientWidth;
  const h = Math.max(1, parent.clientHeight - 28);
  const dpr = window.devicePixelRatio || 1;
  el.width = Math.max(1, Math.floor(w * dpr));
  el.height = Math.max(1, Math.floor(h * dpr));
  el.style.width = `${w}px`;
  el.style.height = `${h}px`;
}

function loop() {
  draw();
  requestAnimationFrame(loop);
}

function draw() {
  if (activeView !== "lab") return;
  drawArena(gctx, gazeboCanvas);
}

/**
 * Dibuja el mapa Occupancy estilo Gazebo (azul + muros amarillos),
 * rotado con DISPLAY_YAW para coincidir con la cámara del lab.
 * Trayectoria + robot + LiDAR opcional.
 */
function drawArena(ctx, canvas) {
  const w = canvas.width;
  const h = canvas.height;
  const dpr = window.devicePixelRatio || 1;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#1a2330";
  ctx.fillRect(0, 0, w, h);

  if (!mapImage || !mapMeta || !mapGrid) {
    ctx.fillStyle = "#71717a";
    ctx.font = `${13 * dpr}px Plus Jakarta Sans`;
    ctx.fillText("Cargando mapa…", 20 * dpr, 30 * dpr);
    return;
  }

  const res = Number(mapMeta.resolution) || 0.05;
  const origin = mapMeta.origin || [0, 0, 0];
  const mapMinX = origin[0];
  const mapMinY = origin[1];
  const mapMaxX = origin[0] + mapW * res;
  const mapMaxY = origin[1] + mapH * res;

  // Bounds en espacio de pantalla (después de DISPLAY_YAW)
  const mapCorners = [
    toDisplay(mapMinX, mapMinY),
    toDisplay(mapMaxX, mapMinY),
    toDisplay(mapMaxX, mapMaxY),
    toDisplay(mapMinX, mapMaxY),
  ];
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const p of mapCorners) {
    minX = Math.min(minX, p.x);
    maxX = Math.max(maxX, p.x);
    minY = Math.min(minY, p.y);
    maxY = Math.max(maxY, p.y);
  }
  if (align.ready) {
    const pts = [mapPose()];
    for (const t of trailMap) pts.push(t);
    for (const t of trailOdom) pts.push(mapPoseFrom(t));
    for (const p of pts) {
      const d = toDisplay(p.x, p.y);
      minX = Math.min(minX, d.x);
      maxX = Math.max(maxX, d.x);
      minY = Math.min(minY, d.y);
      maxY = Math.max(maxY, d.y);
    }
  }
  const margin = 0.18;
  minX -= margin;
  minY -= margin;
  maxX += margin;
  maxY += margin;

  const worldW = Math.max(0.5, maxX - minX);
  const worldH = Math.max(0.5, maxY - minY);
  const pad = 0.92;
  const scale = Math.min(w / worldW, h / worldH) * pad;
  const dw = worldW * scale;
  const dh = worldH * scale;
  const ox = (w - dw) / 2;
  const oy = (h - dh) / 2;
  const view = { minX, minY, maxX, maxY, scale, ox, oy };

  drawColoredMapRotated(ctx, view, mapMinX, mapMinY, mapMaxX, mapMaxY);

  // Perímetro amarillo = muros reales (sin padding gris del PGM)
  const walls = mapContentBounds();
  const wallCorners = [
    toDisplay(walls.minX, walls.minY),
    toDisplay(walls.maxX, walls.minY),
    toDisplay(walls.maxX, walls.maxY),
    toDisplay(walls.minX, walls.maxY),
  ];
  ctx.strokeStyle = "rgba(245, 200, 66, 0.95)";
  ctx.lineWidth = Math.max(3, 5 * dpr);
  ctx.beginPath();
  wallCorners.forEach((c, i) => {
    const p = displayToView(c.x, c.y, view);
    if (i === 0) ctx.moveTo(p.x, p.y);
    else ctx.lineTo(p.x, p.y);
  });
  ctx.closePath();
  ctx.stroke();

  // Overlay: perímetro cerrado canónico + 4 obstáculos Occupancy
  if (labGeometry?.track?.trail_map_closed?.length >= 2) {
    const closed = labGeometry.track.trail_map_closed;
    ctx.beginPath();
    ctx.strokeStyle = "rgba(56, 189, 248, 0.95)";
    ctx.lineWidth = Math.max(2.5, 3.5 * dpr);
    ctx.setLineDash([8 * dpr, 5 * dpr]);
    for (let i = 0; i < closed.length; i++) {
      const p = worldToView(
        { x: Number(closed[i].x), y: Number(closed[i].y) },
        view
      );
      if (i === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    }
    ctx.stroke();
    ctx.setLineDash([]);
  }
  const boxes = labGeometry?.obstacle_boxes || [];
  for (const item of boxes) {
    const b = item.box;
    if (!b) continue;
    const corners = [
      toDisplay(b.minx, b.miny),
      toDisplay(b.maxx, b.miny),
      toDisplay(b.maxx, b.maxy),
      toDisplay(b.minx, b.maxy),
    ].map((c) => displayToView(c.x, c.y, view));
    ctx.beginPath();
    ctx.fillStyle = "rgba(251, 146, 60, 0.28)";
    ctx.strokeStyle = "rgba(251, 146, 60, 0.95)";
    ctx.lineWidth = Math.max(2, 2.5 * dpr);
    corners.forEach((p, i) => {
      if (i === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    });
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
  }

  if (!align.ready) {
    if (!ensureNavigableAlign({ announce: false })) {
      provisionalAlign();
    }
  }

  const pose = displayRobotPose();

  // Fuera de libre: NO rearmar LiDAR de mapa completo (colgaba la HMI).

  if (trailMap.length > 1) {
    ctx.beginPath();
    ctx.strokeStyle = "rgba(52,211,153,0.9)";
    ctx.lineWidth = 2.8 * dpr;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    let started = false;
    for (let i = 0; i < trailMap.length; i++) {
      const p = worldToView(trailMap[i], view);
      if (!started || trailMap[i].gap) {
        ctx.moveTo(p.x, p.y);
        started = true;
      } else {
        ctx.lineTo(p.x, p.y);
      }
    }
    ctx.stroke();
  } else if (trailOdom.length > 1) {
    // fallback breve
    ctx.beginPath();
    ctx.strokeStyle = "rgba(52,211,153,0.9)";
    ctx.lineWidth = 2.8 * dpr;
    for (let i = 0; i < trailOdom.length; i++) {
      const mp = mapPoseFrom(trailOdom[i]);
      const p = worldToView(mp, view);
      if (i === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    }
    ctx.stroke();
  }

  // Ruta A* (evita los 4 bloques) — magenta
  if (plannedPath?.waypoints?.length >= 2) {
    const wps = plannedPath.waypoints;
    ctx.beginPath();
    ctx.strokeStyle = "rgba(244, 114, 182, 0.95)";
    ctx.lineWidth = 2.4 * dpr;
    ctx.setLineDash([6 * dpr, 4 * dpr]);
    ctx.lineJoin = "round";
    for (let i = 0; i < wps.length; i++) {
      const p = worldToView({ x: Number(wps[i].x), y: Number(wps[i].y) }, view);
      if (i === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    }
    ctx.stroke();
    ctx.setLineDash([]);
    for (let i = 0; i < wps.length; i++) {
      const p = worldToView({ x: Number(wps[i].x), y: Number(wps[i].y) }, view);
      ctx.beginPath();
      ctx.fillStyle =
        i === 0
          ? "rgba(52, 211, 153, 0.95)"
          : i === wps.length - 1
            ? "rgba(251, 191, 36, 0.95)"
            : "rgba(244, 114, 182, 0.9)";
      ctx.arc(p.x, p.y, Math.max(3, 3.5 * dpr), 0, Math.PI * 2);
      ctx.fill();
    }
  }

  if (showLidar) {
    drawLidarOnMap(ctx, pose, view, dpr);
  }
  drawZones(ctx, view, dpr);
  const rp = worldToView(pose, view);
  drawRobot(ctx, rp.x, rp.y, pose.theta + DISPLAY_YAW, dpr);
}

function drawZones(ctx, view, dpr) {
  if (!mapZones.length) return;
  for (const z of mapZones) {
    const hw = (Number(z.w) || (Number(z.radius) || 0.12) * 2) / 2;
    const hh = (Number(z.h) || (Number(z.radius) || 0.12) * 2) / 2;
    const corners = [
      { x: z.x - hw, y: z.y - hh },
      { x: z.x + hw, y: z.y - hh },
      { x: z.x + hw, y: z.y + hh },
      { x: z.x - hw, y: z.y + hh },
    ].map((c) => worldToView(c, view));
    ctx.beginPath();
    ctx.moveTo(corners[0].x, corners[0].y);
    for (let i = 1; i < corners.length; i++) ctx.lineTo(corners[i].x, corners[i].y);
    ctx.closePath();
    ctx.strokeStyle = "rgba(251, 191, 36, 0.9)";
    ctx.lineWidth = 1.4 * dpr;
    ctx.setLineDash([3 * dpr, 3 * dpr]);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = "rgba(251, 191, 36, 0.14)";
    ctx.fill();
    const p = worldToView({ x: z.x, y: z.y }, view);
    ctx.fillStyle = "rgba(253, 230, 138, 0.95)";
    ctx.font = `${10 * dpr}px Plus Jakarta Sans`;
    ctx.textAlign = "center";
    ctx.fillText(z.label || z.id, p.x, p.y - Math.max(10, hh * view.scale) - 3 * dpr);
    ctx.textAlign = "left";
  }
}

function displayToView(dx, dy, view) {
  return {
    x: view.ox + (dx - view.minX) * view.scale,
    y: view.oy + (view.maxY - dy) * view.scale,
  };
}

function worldToView(pose, view) {
  const d = toDisplay(pose.x, pose.y);
  return displayToView(d.x, d.y, view);
}

function isOutsideFree(pose, origin, res) {
  const mx = Math.floor((pose.x - origin[0]) / res);
  const my = Math.floor((pose.y - origin[1]) / res);
  if (mx < 1 || my < 1 || mx >= mapW - 1 || my >= mapH - 1) return true;
  const cell = mapGrid[(mapH - 1 - my) * mapW + mx];
  return cell !== 0;
}

/** Occupancy coloreado con transform afín (DISPLAY_YAW incluido vía worldToView). */
function drawColoredMapRotated(ctx, view, mapMinX, mapMinY, mapMaxX, mapMaxY) {
  const tmp = document.createElement("canvas");
  tmp.width = mapW;
  tmp.height = mapH;
  const tctx = tmp.getContext("2d");
  const imgData = tctx.createImageData(mapW, mapH);
  const d = imgData.data;
  for (let i = 0; i < mapGrid.length; i++) {
    const cell = mapGrid[i];
    const c =
      cell === 1 ? GAZEBO.occupied : cell === 0 ? GAZEBO.free : GAZEBO.unknown;
    const o = i * 4;
    d[o] = c[0];
    d[o + 1] = c[1];
    d[o + 2] = c[2];
    d[o + 3] = 255;
  }
  tctx.putImageData(imgData, 0, 0);

  // img (0,0) = top-left = ROS (mapMinX, mapMaxY)
  const p0 = worldToView({ x: mapMinX, y: mapMaxY }, view);
  const px = worldToView({ x: mapMaxX, y: mapMaxY }, view);
  const py = worldToView({ x: mapMinX, y: mapMinY }, view);
  const a = (px.x - p0.x) / mapW;
  const b = (px.y - p0.y) / mapW;
  const c = (py.x - p0.x) / mapH;
  const dd = (py.y - p0.y) / mapH;
  ctx.imageSmoothingEnabled = false;
  ctx.setTransform(a, b, c, dd, p0.x, p0.y);
  ctx.drawImage(tmp, 0, 0);
  ctx.setTransform(1, 0, 0, 1, 0, 0);
}

function drawLidarOnMap(ctx, pose, view, dpr) {
  if (!scanData?.ranges?.length) return;
  const amin = Number(scanData.angle_min) || 0;
  const ainc =
    Number(scanData.angle_increment) ||
    (2 * Math.PI) / scanData.ranges.length;
  const rmax = Math.min(Number(scanData.range_max) || 8, 2.5);
  const robotPx = worldToView(pose, view);

  ctx.fillStyle = "rgba(147, 197, 253, 0.12)";
  ctx.beginPath();
  ctx.moveTo(robotPx.x, robotPx.y);

  const hits = [];
  scanData.ranges.forEach((range, i) => {
    if (range == null || !Number.isFinite(range) || range <= 0 || range > rmax) return;
    const ang = amin + i * ainc + pose.theta + LIDAR_YAW;
    const sc = ((align.sx || 1) + (align.sy || 1)) / 2;
    const wx = pose.x + range * sc * Math.cos(ang);
    const wy = pose.y + range * sc * Math.sin(ang);
    hits.push(worldToView({ x: wx, y: wy }, view));
  });

  if (hits.length) {
    hits.forEach((p) => ctx.lineTo(p.x, p.y));
    ctx.closePath();
    ctx.fill();
  }

  hits.forEach((p) => {
    ctx.fillStyle = "rgba(255,255,255,0.85)";
    ctx.fillRect(p.x - dpr, p.y - dpr, 2.2 * dpr, 2.2 * dpr);
  });
}

function drawRobot(ctx, x, y, theta, dpr) {
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(-theta);
  const r = Math.max(6, 8 * dpr);
  ctx.beginPath();
  ctx.arc(0, 0, r * 1.35, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(0,0,0,0.25)";
  ctx.fill();
  ctx.beginPath();
  ctx.arc(0, 0, r, 0, Math.PI * 2);
  ctx.fillStyle = "#111827";
  ctx.fill();
  ctx.strokeStyle = "#fbbf24";
  ctx.lineWidth = 2 * dpr;
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.lineTo(r * 1.8, 0);
  ctx.stroke();
  ctx.restore();
}

/**
 * Ubica el robot comparando rangos LiDAR vs raycast en el Occupancy.
 * Conserva la trayectoria odom (se reproyecta con el nuevo align).
 */
async function localizeOnMap({ manual = false } = {}) {
  if (localizing) return;
  // El perímetro cerrado manda: no pisar con LiDAR automático
  if (perimeterFitted && align.ready && !manual) return;
  if (!mapGrid || !mapMeta) {
    if (manual) hint.textContent = "Mapa aún no cargado";
    return;
  }
  if (!scanData?.ranges?.length) {
    if (manual) hint.textContent = "Esperando LiDAR…";
    localizePending = true;
    return;
  }

  localizing = true;
  lastLocalizeAttemptMs = performance.now();
  try {
    const res = Number(mapMeta.resolution) || 0.05;
    const origin = mapMeta.origin || [0, 0, 0];
    const rays = sampleRays(scanData);
    if (rays.length < 8) {
      if (manual) hint.textContent = "Pocos hits LiDAR — reintenta cerca de paredes";
      return;
    }

    const freeCells = [];
    for (let my = 1; my < mapH - 1; my++) {
      for (let mx = 1; mx < mapW - 1; mx++) {
        if (mapGrid[(mapH - 1 - my) * mapW + mx] !== 0) continue;
        freeCells.push({
          x: origin[0] + (mx + 0.5) * res,
          y: origin[1] + (my + 0.5) * res,
        });
      }
    }
    if (!freeCells.length) return;

    // Ortogonales + 45° (cubre “mapa girado”)
    const yawMap = [];
    for (let i = 0; i < 16; i++) yawMap.push((i * Math.PI) / 8);

    let best = { score: -1e9, x: 0, y: 0, th: 0 };
    const stride = freeCells.length > 350 ? 2 : 1;
    for (const th of yawMap) {
      for (let i = 0; i < freeCells.length; i += stride) {
        const c = freeCells[i];
        const score = scoreRaycast(c.x, c.y, th, rays, origin, res);
        if (score > best.score) best = { score, x: c.x, y: c.y, th };
      }
    }

    for (let dx = -0.15; dx <= 0.15; dx += 0.025) {
      for (let dy = -0.15; dy <= 0.15; dy += 0.025) {
        for (let dth = -0.25; dth <= 0.25; dth += 0.05) {
          const x = best.x + dx;
          const y = best.y + dy;
          const th = best.th + dth;
          const score = scoreRaycast(x, y, th, rays, origin, res);
          if (score > best.score) best = { score, x, y, th };
        }
      }
    }

    // score raycast ∈ [0, rays.length]; exigir ~35%
    const minScore = rays.length * 0.35;
    if (best.score < minScore) {
      localizePending = true;
      if (manual) {
        hint.textContent = `No ubiqué bien (${best.score.toFixed(1)}/${rays.length}) — pulsa Ubicar cerca de un muro`;
      }
      return;
    }

    seedAlignToMapPose(best.x, best.y, best.th, "lidar", { force: manual });
    localizePending = false;
    if (!trailOdom.length) {
      trailOdom = [{ x: odomPose.x, y: odomPose.y }];
    }
    // Si ya hay un rectángulo de pista, el SE(2) por trazo gana al LiDAR
    if (fitMapToTrailPerimeter({ manual: false })) {
      return;
    }
    const deg = ((best.th * 180) / Math.PI).toFixed(0);
    hint.textContent = `LiDAR (${best.x.toFixed(2)}, ${best.y.toFixed(2)}) · ${deg}° · match ${best.score.toFixed(0)}/${rays.length}`;
  } finally {
    localizing = false;
  }
}

function sampleRays(scan) {
  const rays = [];
  const amin = Number(scan.angle_min) || 0;
  const ainc =
    Number(scan.angle_increment) || (2 * Math.PI) / (scan.ranges?.length || 1);
  const ranges = scan.ranges || [];
  ranges.forEach((range, i) => {
    if (range == null || !Number.isFinite(range) || range < 0.08 || range > 3.5)
      return;
    if (i % 2 !== 0) return; // más densidad para pose inicial
    rays.push({ range, ang: amin + i * ainc + LIDAR_YAW });
  });
  return rays;
}

/** Predice rango hasta ocupación; compara con medida LiDAR. */
function raycastRange(rx, ry, ang, origin, res, maxR) {
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

function scoreRaycast(rx, ry, rth, rays, origin, res, maxR = 3.5) {
  const mx0 = Math.floor((rx - origin[0]) / res);
  const my0 = Math.floor((ry - origin[1]) / res);
  if (mx0 < 0 || my0 < 0 || mx0 >= mapW || my0 >= mapH) return -1e9;
  if (mapGrid[(mapH - 1 - my0) * mapW + mx0] !== 0) return -1e9;
  let score = 0;
  const sigma = 0.11;
  for (const ray of rays) {
    const pred = raycastRange(rx, ry, ray.ang + rth, origin, res, maxR);
    const err = pred - ray.range;
    score += Math.exp(-(err * err) / (sigma * sigma));
  }
  return score;
}

/**
 * Score LiDAR de la pose mapa actual (prueba rumbo y rumbo+π).
 * Bajo → el norte/align no corresponde a donde está el robot.
 */
function lidarScoreAtMapPose(mx, my, mapTh) {
  if (!mapGrid || !mapMeta || !scanData?.ranges?.length) return 0;
  const rays = sampleRays(scanData);
  if (rays.length < 8) return 0;
  const res = Number(mapMeta.resolution) || 0.05;
  const origin = mapMeta.origin || [0, 0, 0];
  // seedAlign aplica LIDAR_HEADING_FLIP; el match busca th «antes» del flip
  const s0 = scoreRaycast(mx, my, mapTh, rays, origin, res);
  const s1 = scoreRaycast(mx, my, mapTh - LIDAR_HEADING_FLIP, rays, origin, res);
  const s2 = scoreRaycast(mx, my, mapTh + Math.PI, rays, origin, res);
  return Math.max(s0, s1, s2);
}

function odomLooksValid() {
  // Tras reconexión el Create3 suele estar en (0,0): eso ES válido para seed LiDAR
  return Number.isFinite(odomPose.x) && Number.isFinite(odomPose.y);
}
