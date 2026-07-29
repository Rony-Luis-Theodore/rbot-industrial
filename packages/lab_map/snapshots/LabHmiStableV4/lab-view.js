/**
 * lab-view — consola Occupancy nueva (no usa viewer.js).
 * Punto de vista: plano de pista + dock de localización.
 */

import { ENDPOINTS } from "../config.js";
import { fetchMaps } from "../api/robot.js";
import { getElement } from "../utils/dom.js";
import { HEADING_UI_FLIP_ENABLED, ARROW_UI_SNAP_RAD } from "./constants.js";
import * as LabMap from "./LabMapEngine.js";
import { drawClosedPoly, drawTrail, toDisplay, worldToView } from "./LabCanvas.js";
import {
  clearLabTrail,
  flipLabHeading,
  getLabState,
  isLabAnchored,
  loadLabMap,
  mapPose,
  relocalizeLab,
  subscribeLab,
  updateLabOdom,
} from "./lab-session.js";

const COLORS = {
  free: [28, 32, 40],
  occ: [210, 180, 90],
  unk: [18, 20, 26],
  robot: "#f8fafc",
  heading: "#38bdf8",
};

let canvas;
let ctx;
let btnUbicar;
let btnClear;
let btnLidar;
let hintEl;
let metaPsi;
let metaTip;
let metaStatus;
let selectMap;
let showLidar = true;
let raf = 0;

export function updateRobotPose(pose) {
  updateLabOdom(pose);
}

export async function applyDefaultMap(mapId) {
  if (mapId) await loadLabMap(mapId);
}

/** Nunca auto-Ubicar: solo el botón manual (checkpoint LabTrayectoriaOK). */
export function requestRelocalize() {
  const s = getLabState();
  if (isLabAnchored()) return;
  s.needsUbicar = true;
  s.hint = "Centro del circuito → Pulsa «Ubicar en el mapa»";
  s.status = "need_ubicar";
  document.body.classList.add("lab-needs-ubicar");
  document.body.classList.remove("lab-anchored");
}

export function resetMappingForRobotSwitch(reason = "") {
  const s = getLabState();
  s.align = LabMap.createEmptyAlign();
  s.alignFrozen = false;
  s.needsUbicar = true;
  s.ubicarLocked = false;
  s.trail = [];
  s.trailOdom = [];
  s.hint = `Sesión reiniciada (${reason}). Pulsa «Ubicar en el mapa».`;
  s.status = "need_ubicar";
  document.body.classList.add("lab-needs-ubicar");
  document.body.classList.remove("lab-anchored");
}

export async function initLabView() {
  canvas = getElement("lab-canvas");
  hintEl = getElement("lab-hint");
  btnUbicar = getElement("btn-ubicar");
  btnClear = getElement("btn-lab-clear");
  btnLidar = getElement("btn-lab-lidar");
  const btnFlip = document.getElementById("btn-lab-flip");
  metaPsi = getElement("lab-meta-psi");
  metaTip = getElement("lab-meta-tip");
  metaStatus = getElement("lab-meta-status");
  selectMap = getElement("lab-map-select");

  if (!canvas) throw new Error("lab-canvas missing");
  ctx = canvas.getContext("2d");

  btnUbicar?.addEventListener("click", () => {
    void relocalizeLab({ reason: "manual", auto: false });
  });
  btnClear?.addEventListener("click", () => clearLabTrail());
  if (btnFlip) {
    if (!HEADING_UI_FLIP_ENABLED) {
      btnFlip.disabled = true;
      btnFlip.title = "Rumbo fijado (validado en lab) — ya no se invierte";
      btnFlip.classList.add("is-locked");
      btnFlip.textContent = "Rumbo fijo";
    } else {
      btnFlip.addEventListener("click", () => {
        void flipLabHeading();
      });
    }
  }
  btnLidar?.addEventListener("click", () => {
    showLidar = !showLidar;
    btnLidar.classList.toggle("is-on", showLidar);
    btnLidar.setAttribute("aria-pressed", showLidar ? "true" : "false");
  });

  window.addEventListener("resize", fitCanvas);
  // El wrap flex cambia de tamaño aunque el window.resize a veces no baste
  if (typeof ResizeObserver !== "undefined") {
    const ro = new ResizeObserver(() => fitCanvas());
    if (canvas.parentElement) ro.observe(canvas.parentElement);
    const arena = document.getElementById("lab-arena");
    if (arena) ro.observe(arena);
  }
  subscribeLab(onState);
  fitCanvas();
  requestAnimationFrame(() => {
    fitCanvas();
    loop();
  });

  try {
    const maps = await fetchMaps();
    const list = maps?.maps || maps || [];
    if (selectMap && Array.isArray(list)) {
      selectMap.innerHTML = "";
      for (const m of list) {
        const id = m.id || m;
        const opt = document.createElement("option");
        opt.value = id;
        opt.textContent = m.label || id;
        selectMap.appendChild(opt);
      }
      selectMap.addEventListener("change", () => {
        void loadLabMap(selectMap.value);
      });
    }
  } catch {
    /* ignore */
  }

  // default map
  const defaultId = selectMap?.value || "laboratorio_kalman";
  await loadLabMap(defaultId);
}

function onState(s) {
  if (hintEl) hintEl.textContent = s.hint || "—";
  const gate = document.getElementById("lab-ubicar-gate");
  if (gate) gate.hidden = !s.needsUbicar;
  if (metaStatus) {
    metaStatus.textContent = statusLabel(s.status);
    metaStatus.dataset.status = s.status;
  }
  if (metaPsi) {
    metaPsi.textContent = LabMap.isNavigableAlign(s.align)
      ? `${((s.align.yaw * 180) / Math.PI).toFixed(0)}°`
      : "—";
  }
  if (metaTip) {
    if (isLabAnchored()) {
      const t = LabMap.projectPose(s.odom, s.align);
      metaTip.textContent = `${t.x.toFixed(2)}, ${t.y.toFixed(2)}`;
    } else {
      metaTip.textContent = "sin ancla";
    }
  }
  if (btnUbicar) {
    const locked = Boolean(s.ubicarLocked) && isLabAnchored();
    btnUbicar.hidden = locked;
    btnUbicar.disabled = Boolean(s.localizing) || !s.mapGrid || locked;
    btnUbicar.classList.toggle("is-busy", Boolean(s.localizing));
    btnUbicar.classList.toggle("is-required", Boolean(s.needsUbicar) && !locked);
  }
}

function statusLabel(st) {
  switch (st) {
    case "ok":
      return "Calzado";
    case "need_ubicar":
      return "Espera Ubicar";
    case "localizing":
      return "Ubicando…";
    case "loading":
      return "Cargando";
    case "error":
      return "Error";
    case "ready":
      return "Listo";
    default:
      return st || "—";
  }
}

function fitCanvas() {
  if (!canvas) return;
  const parent = canvas.parentElement;
  if (!parent) return;
  const w = Math.max(1, Math.floor(parent.clientWidth));
  const h = Math.max(1, Math.floor(parent.clientHeight));
  const dpr = window.devicePixelRatio || 1;
  const bw = Math.max(1, Math.floor(w * dpr));
  const bh = Math.max(1, Math.floor(h * dpr));
  // Solo retocar buffer si cambió (evita borrar el frame al pedo)
  if (canvas.width !== bw || canvas.height !== bh) {
    canvas.width = bw;
    canvas.height = bh;
  }
  canvas.style.width = `${w}px`;
  canvas.style.height = `${h}px`;
}

function loop() {
  fitCanvas();
  draw();
  raf = requestAnimationFrame(loop);
}

function computeView(s) {
  const dpr = window.devicePixelRatio || 1;
  const pad = 28 * dpr;
  // Encuadrar en muros dorados (perímetro real)
  const pts = [];
  const wall = s.wallClosed?.length ? s.wallClosed : s.closed || [];
  for (const p of wall) pts.push(toDisplay(p.x, p.y));
  if (!pts.length && s.mapMeta && s.mapW && s.mapH) {
    const res = Number(s.mapMeta.resolution) || 0.05;
    const origin = s.mapMeta.origin || [0, 0];
    const x0 = origin[0];
    const y0 = origin[1];
    const x1 = origin[0] + s.mapW * res;
    const y1 = origin[1] + s.mapH * res;
    pts.push(toDisplay(x0, y0), toDisplay(x1, y0), toDisplay(x1, y1), toDisplay(x0, y1));
  }
  if (!pts.length) pts.push(toDisplay(-1, -1), toDisplay(1, 1));
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const p of pts) {
    minX = Math.min(minX, p.x);
    minY = Math.min(minY, p.y);
    maxX = Math.max(maxX, p.x);
    maxY = Math.max(maxY, p.y);
  }
  const bw = Math.max(0.4, maxX - minX);
  const bh = Math.max(0.4, maxY - minY);
  const scale = Math.min(
    (canvas.width - 2 * pad) / bw,
    (canvas.height - 2 * pad) / bh
  );
  const viewW = bw * scale;
  const viewH = bh * scale;
  return {
    minX,
    maxY,
    scale,
    ox: (canvas.width - viewW) / 2,
    oy: (canvas.height - viewH) / 2,
    dpr,
  };
}

function draw() {
  if (!ctx || !canvas) return;
  const s = getLabState();
  const dpr = window.devicePixelRatio || 1;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // atmosphere
  const g = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
  g.addColorStop(0, "#10131a");
  g.addColorStop(1, "#0a0c10");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  if (!s.mapGrid || !s.mapMeta) {
    ctx.fillStyle = "rgba(255,255,255,0.45)";
    ctx.font = `${14 * dpr}px "Sora", sans-serif`;
    ctx.fillText("Cargando plano Occupancy…", 28 * dpr, 40 * dpr);
    return;
  }

  const view = computeView(s);
  drawOccupancy(s, view);

  // Perímetro real = muros dorados Occupancy
  if (s.wallClosed?.length) {
    drawClosedPoly(ctx, s.wallClosed, view, view.dpr, {
      stroke: "rgba(56, 189, 248, 0.95)",
      lineWidth: 2.8,
    });
  }
  // Pista interna (solo guía)
  if (s.closed?.length) {
    drawClosedPoly(ctx, s.closed, view, view.dpr, {
      stroke: "rgba(56, 189, 248, 0.28)",
      lineWidth: 1.2,
    });
  }
  for (const ob of s.boxes || []) {
    const b = ob.box || ob;
    if (!b) continue;
    const corners = [
      { x: b.minx, y: b.miny },
      { x: b.maxx, y: b.miny },
      { x: b.maxx, y: b.maxy },
      { x: b.minx, y: b.maxy },
      { x: b.minx, y: b.miny },
    ];
    drawClosedPoly(ctx, corners, view, view.dpr, {
      stroke: "rgba(251, 146, 60, 0.9)",
      lineWidth: 2,
    });
  }
  drawTrail(ctx, isLabAnchored() ? s.trail : [], view, view.dpr);

  if (showLidar && s.scan?.ranges?.length && isLabAnchored()) {
    drawLidar(s, view);
  }

  if (LabMap.isNavigableAlign(s.align) && isLabAnchored()) {
    const pose = mapPose();
    const p = worldToView(pose, view);
    // Flecha = dirección real del avance en pantalla (mismo SE2 que el trazo).
    drawRobot(p.x, p.y, screenHeadingFromMapTheta(pose.theta), view.dpr);
  }
}

/**
 * Ángulo para drawRobot (usa rotate(-θ)): la flecha sigue el avance Occupancy→pantalla.
 * Snap en ejes de pantalla (no solo Occupancy) para quitar el “poquito a un lado”
 * cuando el robot va recto respecto a los muros.
 */
function screenHeadingFromMapTheta(mapTheta) {
  const th = Number(mapTheta) || 0;
  const dx = Math.cos(th);
  const dy = Math.sin(th);
  const d = toDisplay(dx, dy);
  let screen = Math.atan2(d.y, d.x);
  const snap = Number(ARROW_UI_SNAP_RAD) || 0;
  if (snap > 0) {
    const cards = [0, Math.PI / 2, Math.PI, -Math.PI / 2];
    let best = screen;
    let bestD = Infinity;
    for (const c of cards) {
      const delta = Math.abs(LabMap.wrapPi(screen - c));
      if (delta < bestD) {
        bestD = delta;
        best = c;
      }
    }
    if (bestD <= snap) screen = best;
  }
  return screen;
}

function drawOccupancy(s, view) {
  const res = Number(s.mapMeta.resolution) || 0.05;
  const origin = s.mapMeta.origin || [0, 0];
  const tmp = document.createElement("canvas");
  tmp.width = s.mapW;
  tmp.height = s.mapH;
  const tctx = tmp.getContext("2d");
  const img = tctx.createImageData(s.mapW, s.mapH);
  const d = img.data;
  for (let i = 0; i < s.mapGrid.length; i++) {
    const cell = s.mapGrid[i];
    const c = cell === 1 ? COLORS.occ : cell === 0 ? COLORS.free : COLORS.unk;
    const o = i * 4;
    d[o] = c[0];
    d[o + 1] = c[1];
    d[o + 2] = c[2];
    d[o + 3] = 255;
  }
  tctx.putImageData(img, 0, 0);

  // corners of map in world → display → view
  const x0 = origin[0];
  const y0 = origin[1];
  const x1 = origin[0] + s.mapW * res;
  const y1 = origin[1] + s.mapH * res;
  const corners = [
    toDisplay(x0, y0),
    toDisplay(x1, y0),
    toDisplay(x1, y1),
    toDisplay(x0, y1),
  ];
  const vx = corners.map((p) => view.ox + (p.x - view.minX) * view.scale);
  const vy = corners.map((p) => view.oy + (view.maxY - p.y) * view.scale);

  // Approximate affine: draw via transform from image space
  // Image: col→x world, row flipped → y world
  ctx.save();
  // Use path clip of AABB in view
  const minVX = Math.min(...vx);
  const maxVX = Math.max(...vx);
  const minVY = Math.min(...vy);
  const maxVY = Math.max(...vy);
  // Simpler: draw rotated via worldToView of each? Too slow.
  // Map display uses DISPLAY_YAW π/2: image needs rotation.
  const c00 = worldToView({ x: x0, y: y0 }, view);
  const c10 = worldToView({ x: x1, y: y0 }, view);
  const c01 = worldToView({ x: x0, y: y1 }, view);
  // Affine from image (0,H)->(W,0) to world corners
  // We'll drawImage with transform mapping image pixels to view.
  const w = s.mapW;
  const h = s.mapH;
  // At image (0,h) → world (x0,y0); (w,h)→(x1,y0); (0,0)→(x0,y1)
  const p00 = worldToView({ x: x0, y: y1 }, view); // img top-left
  const p10 = worldToView({ x: x1, y: y1 }, view);
  const p01 = worldToView({ x: x0, y: y0 }, view);
  const a = (p10.x - p00.x) / w;
  const b = (p10.y - p00.y) / w;
  const c = (p01.x - p00.x) / h;
  const dlt = (p01.y - p00.y) / h;
  const e = p00.x;
  const f = p00.y;
  ctx.setTransform(a, b, c, dlt, e, f);
  ctx.imageSmoothingEnabled = false;
  ctx.globalAlpha = 0.92;
  ctx.drawImage(tmp, 0, 0);
  ctx.restore();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  void minVX;
  void maxVX;
  void minVY;
  void maxVY;
}

function drawLidar(s, view) {
  const pose = LabMap.projectPose(s.odom, s.align);
  const amin = Number(s.scan.angle_min) || 0;
  const ranges = s.scan.ranges || [];
  const ainc =
    Number(s.scan.angle_increment) || (2 * Math.PI) / Math.max(ranges.length, 1);
  const LIDAR_YAW = -Math.PI / 2;
  ctx.save();
  ctx.fillStyle = "rgba(125, 211, 252, 0.55)";
  for (let i = 0; i < ranges.length; i += 3) {
    const r = ranges[i];
    if (r == null || !Number.isFinite(r) || r < 0.08 || r > 3.5) continue;
    const ang = pose.theta + amin + i * ainc + LIDAR_YAW;
    const hx = pose.x + Math.cos(ang) * r;
    const hy = pose.y + Math.sin(ang) * r;
    const p = worldToView({ x: hx, y: hy }, view);
    ctx.fillRect(p.x - view.dpr, p.y - view.dpr, 2.2 * view.dpr, 2.2 * view.dpr);
  }
  ctx.restore();
}

function drawRobot(x, y, theta, dpr) {
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(-theta);
  const r = Math.max(7, 9 * dpr);
  ctx.beginPath();
  ctx.arc(0, 0, r * 1.4, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(0,0,0,0.35)";
  ctx.fill();
  ctx.beginPath();
  ctx.arc(0, 0, r, 0, Math.PI * 2);
  ctx.fillStyle = COLORS.robot;
  ctx.fill();
  ctx.strokeStyle = COLORS.heading;
  ctx.lineWidth = 2.4 * dpr;
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.lineTo(r * 2.1, 0);
  ctx.stroke();
  ctx.restore();
}

// Compat exports used by robot-session / teleop wiring
export async function initViewer() {
  return initLabView();
}
