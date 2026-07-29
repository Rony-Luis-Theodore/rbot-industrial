/**
 * LabCanvas — solo transform Occupancy → pantalla (DISPLAY_YAW).
 * No contiene SE2 ni localización.
 */

import { DISPLAY_YAW } from "./constants.js";

export function toDisplay(x, y) {
  const c = Math.cos(DISPLAY_YAW);
  const s = Math.sin(DISPLAY_YAW);
  return { x: c * x - s * y, y: s * x + c * y };
}

export function displayToView(dx, dy, view) {
  return {
    x: view.ox + (dx - view.minX) * view.scale,
    y: view.oy + (view.maxY - dy) * view.scale,
  };
}

export function worldToView(pose, view) {
  const d = toDisplay(pose.x, pose.y);
  return displayToView(d.x, d.y, view);
}

export function drawTrail(ctx, trailMap, view, dpr) {
  if (!trailMap || trailMap.length < 2) return;
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
}

export function drawClosedPoly(ctx, closed, view, dpr, style = {}) {
  if (!closed || closed.length < 2) return;
  ctx.beginPath();
  ctx.strokeStyle = style.stroke || "rgba(34,211,238,0.95)";
  ctx.lineWidth = (style.lineWidth || 2.4) * dpr;
  for (let i = 0; i < closed.length; i++) {
    const p = worldToView({ x: Number(closed[i].x), y: Number(closed[i].y) }, view);
    if (i === 0) ctx.moveTo(p.x, p.y);
    else ctx.lineTo(p.x, p.y);
  }
  ctx.closePath();
  ctx.stroke();
}
