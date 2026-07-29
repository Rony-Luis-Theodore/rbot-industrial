/**
 * Vista de mapa OccupancyGrid (PGM→PNG) + overlay de pose del robot
 */

import { ENDPOINTS } from "../config.js";
import { fetchMapMeta, fetchMaps } from "../api/robot.js";
import { getElement } from "../utils/dom.js";

const canvas = getElement("map-canvas");
const select = getElement("map-select");
const hint = getElement("map-hint");
const ctx = canvas.getContext("2d");

let mapImage = null;
let mapMeta = null;
let robotPose = null;

/**
 * Inicializa selector de mapas y render loop.
 */
export async function initMapView() {
  window.addEventListener("resize", fitCanvas);
  fitCanvas();

  try {
    const maps = await fetchMaps();
    select.innerHTML = "";
    if (!maps.length) {
      hint.textContent = "Sin mapas en workspace · usa pose libre";
      draw();
      return;
    }
    for (const m of maps) {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = m.id;
      select.appendChild(opt);
    }
    select.addEventListener("change", () => loadMap(select.value));
    const preferred =
      maps.find((m) => m.id.includes("laboratorio"))?.id || maps[0].id;
    select.value = preferred;
    await loadMap(preferred);
  } catch (err) {
    hint.textContent = `Mapa offline: ${err.message}`;
    draw();
  }

  requestAnimationFrame(loop);
}

/** @param {object|null} pose */
export function updateRobotPose(pose) {
  robotPose = pose;
}

async function loadMap(mapId) {
  hint.textContent = `Cargando ${mapId}…`;
  mapMeta = await fetchMapMeta(mapId);
  const img = new Image();
  img.crossOrigin = "anonymous";
  await new Promise((resolve, reject) => {
    img.onload = resolve;
    img.onerror = () => reject(new Error("No se pudo cargar PNG del mapa"));
    img.src = ENDPOINTS.mapImage(mapId);
  });
  mapImage = img;
  hint.textContent = `res ${mapMeta.resolution ?? "?"} m/px · origen [${(mapMeta.origin || []).slice(0, 2).join(", ")}]`;
  draw();
}

function fitCanvas() {
  const parent = canvas.parentElement;
  if (!parent) return;
  const w = parent.clientWidth;
  const h = parent.clientHeight;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(w * dpr));
  canvas.height = Math.max(1, Math.floor(h * dpr));
  canvas.style.width = `${w}px`;
  canvas.style.height = `${h}px`;
  draw();
}

function loop() {
  draw();
  requestAnimationFrame(loop);
}

function draw() {
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#0a0c0f";
  ctx.fillRect(0, 0, w, h);

  if (!mapImage) {
    ctx.fillStyle = "#6b7382";
    ctx.font = `${14 * (window.devicePixelRatio || 1)}px IBM Plex Sans`;
    ctx.fillText("Esperando mapa OccupancyGrid…", 24, 40);
    if (robotPose) drawRobotFallback(w, h);
    return;
  }

  const scale = Math.min(w / mapImage.width, h / mapImage.height);
  const dw = mapImage.width * scale;
  const dh = mapImage.height * scale;
  const ox = (w - dw) / 2;
  const oy = (h - dh) / 2;
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(mapImage, ox, oy, dw, dh);

  if (robotPose && mapMeta) {
    const px = worldToPixel(robotPose, mapImage, mapMeta, ox, oy, scale);
    if (px) drawRobot(px.x, px.y, robotPose.theta || 0, scale);
  }
}

function worldToPixel(pose, img, meta, ox, oy, scale) {
  const res = Number(meta.resolution);
  const origin = meta.origin || [0, 0, 0];
  if (!res || Number.isNaN(res)) return null;
  // PGM: origen es esquina inferior izquierda del mapa en metros
  const mx = (pose.x - origin[0]) / res;
  const my = (pose.y - origin[1]) / res;
  const imgX = mx;
  const imgY = img.height - my;
  return {
    x: ox + imgX * scale,
    y: oy + imgY * scale,
  };
}

function drawRobot(x, y, theta, scale) {
  const r = Math.max(6, 10 * (window.devicePixelRatio || 1));
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(-(theta || 0));
  ctx.beginPath();
  ctx.arc(0, 0, r, 0, Math.PI * 2);
  ctx.fillStyle = "#f59e0b";
  ctx.fill();
  ctx.beginPath();
  ctx.moveTo(r * 0.2, 0);
  ctx.lineTo(r * 1.8, 0);
  ctx.strokeStyle = "#38bdf8";
  ctx.lineWidth = 2 * (window.devicePixelRatio || 1);
  ctx.stroke();
  ctx.restore();
}

function drawRobotFallback(w, h) {
  // Sin mapa: proyectar pose relativa al centro
  const x = w / 2 + (robotPose.x || 0) * 40;
  const y = h / 2 - (robotPose.y || 0) * 40;
  drawRobot(x, y, robotPose.theta || 0, 1);
}
