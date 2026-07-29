/**
 * Teleoperación manual — mando en HMI
 *
 * Flujo:
 * 1. Obligatorio Ubicar en el mapa (gate LabTrayectoriaOK).
 * 2. Operario pulsa "Tomar control" (arma el mando).
 * 3. WASD / flechas / pad envían /teleop ~10 Hz.
 * 4. Al soltar o desarmar → cmd_vel = 0.
 * 5. E-STOP global también desarma.
 */

import { emergencyStop, sendTeleop } from "../api/robot.js";
import { getElement } from "../utils/dom.js";
import { isLabAnchored, subscribeLab } from "../lab/lab-session.js";

const btnArm = getElement("btn-teleop-arm");
const pad = getElement("teleop-pad");
const hint = getElement("teleop-hint");
const speedInput = getElement("teleop-speed");

const LINEAR = { fwd: 1, back: -1, left: 0, right: 0, stop: 0 };
const ANGULAR = { fwd: 0, back: 0, left: 1, right: -1, stop: 0 };

let armed = false;
let keys = new Set();
let timer = null;
let inFlight = false;

export function initTeleop() {
  btnArm.addEventListener("click", toggleArm);

  pad.querySelectorAll(".tp-btn").forEach((btn) => {
    const dir = btn.dataset.dir;
    const start = (e) => {
      e.preventDefault();
      if (!armed || !isLabAnchored()) return;
      if (dir === "stop") {
        keys.clear();
        void publish(0, 0);
        return;
      }
      keys.add(dir);
      ensureLoop();
    };
    const end = (e) => {
      e.preventDefault();
      keys.delete(dir);
      if (keys.size === 0) void publish(0, 0);
    };
    btn.addEventListener("pointerdown", start);
    btn.addEventListener("pointerup", end);
    btn.addEventListener("pointerleave", end);
    btn.addEventListener("pointercancel", end);
  });

  window.addEventListener("keydown", onKeyDown);
  window.addEventListener("keyup", onKeyUp);
  window.addEventListener("blur", () => {
    keys.clear();
    if (armed) void publish(0, 0);
  });

  subscribeLab(() => {
    if (!isLabAnchored() && armed) setArmed(false);
    syncArmEnabled();
  });
  syncArmEnabled();
}

function toggleArm() {
  if (!armed && !isLabAnchored()) {
    if (hint) hint.textContent = "Primero pulsa «Ubicar en el mapa»";
    return;
  }
  setArmed(!armed);
}

function setArmed(value) {
  if (value && !isLabAnchored()) {
    if (hint) hint.textContent = "Primero pulsa «Ubicar en el mapa»";
    return;
  }
  armed = value;
  const panel = document.getElementById("panel-drive");
  const body = document.getElementById("teleop-body");
  btnArm.setAttribute("aria-pressed", armed ? "true" : "false");
  btnArm.setAttribute("aria-expanded", armed ? "true" : "false");
  btnArm.textContent = armed ? "Cerrar mando" : "Tomar control";
  if (body) body.hidden = !armed;
  panel?.classList.toggle("is-open", armed);
  if (hint) {
    hint.textContent = armed
      ? "Mantén WASD / flechas o el pad · suelta para parar"
      : isLabAnchored()
        ? "Pulsa Tomar control para mostrar el mando"
        : "Bloqueado — Pulsa «Ubicar en el mapa» primero";
  }
  document.body.classList.toggle("teleop-armed", armed);
  keys.clear();
  stopLoop();
  void publish(0, 0);
}

function syncArmEnabled() {
  const ok = isLabAnchored();
  if (btnArm) {
    btnArm.disabled = !ok;
    btnArm.title = ok
      ? "Mostrar / ocultar mando"
      : "Primero pulsa «Ubicar en el mapa»";
  }
  if (!ok && hint && !armed) {
    hint.textContent = "Bloqueado — Pulsa «Ubicar en el mapa» primero";
  }
}

function onKeyDown(e) {
  if (!armed || !isLabAnchored()) return;
  // No interferir si escribe en el chat
  const tag = (e.target && e.target.tagName) || "";
  if (tag === "TEXTAREA" || tag === "INPUT") return;

  const dir = keyToDir(e.code);
  if (!dir) return;
  e.preventDefault();
  if (dir === "stop") {
    keys.clear();
    void publish(0, 0);
    return;
  }
  keys.add(dir);
  ensureLoop();
}

function onKeyUp(e) {
  if (!armed) return;
  const dir = keyToDir(e.code);
  if (!dir || dir === "stop") return;
  keys.delete(dir);
  if (keys.size === 0) void publish(0, 0);
}

function keyToDir(code) {
  switch (code) {
    case "ArrowUp":
    case "KeyW":
      return "fwd";
    case "ArrowDown":
    case "KeyS":
      return "back";
    case "ArrowLeft":
    case "KeyA":
      return "left";
    case "ArrowRight":
    case "KeyD":
      return "right";
    case "Space":
      return "stop";
    default:
      return null;
  }
}

function ensureLoop() {
  if (timer) return;
  timer = setInterval(() => {
    if (!armed || keys.size === 0) {
      stopLoop();
      return;
    }
    const { lin, ang } = computeTwist();
    void publish(lin, ang);
  }, 120);
}

function stopLoop() {
  if (timer) {
    clearInterval(timer);
    timer = null;
  }
}

function computeTwist() {
  const speed = Number(speedInput.value) || 0.12;
  let lin = 0;
  let ang = 0;
  // Mejorar giro en sitio (Create3 responde mejor con angular más alto)
  for (const d of keys) {
    lin += LINEAR[d] * speed;
    ang += ANGULAR[d] * Math.max(0.55, speed * 5.5);
  }
  lin = Math.max(-0.25, Math.min(0.25, lin));
  ang = Math.max(-1.2, Math.min(1.2, ang));
  return { lin, ang };
}

async function publish(linear_x, angular_z) {
  if (inFlight) return;
  inFlight = true;
  try {
    await sendTeleop(linear_x, angular_z);
  } catch (err) {
    console.warn("teleop:", err.message);
    // Fallo de enlace: intentar parada de seguridad
    if (Math.abs(linear_x) > 0 || Math.abs(angular_z) > 0) {
      try {
        await emergencyStop();
      } catch {
        /* ignore */
      }
    }
  } finally {
    inFlight = false;
  }
}
