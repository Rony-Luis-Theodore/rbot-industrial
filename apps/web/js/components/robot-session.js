/**
 * Selector de perfil: Auto / R-Bot / Nexus / Simulación
 */

import { fetchSession, setSession } from "../api/robot.js";
import { getElement } from "../utils/dom.js";
import { markSessionOnline } from "./telemetry.js";
import {
  applyDefaultMap,
  requestRelocalize,
  resetMappingForRobotSwitch,
} from "../lab/lab-view.js";

const select = getElement("robot-profile");
const logoName = document.querySelector(".logo-name");
const logoSub = document.querySelector(".logo-sub");
const chipProfile = getElement("chip-profile");
const kpiProfile = getElement("kpi-profile");

let current = null;

export async function initRobotSession() {
  if (!select) return;

  select.addEventListener("change", async () => {
    const profile = select.value;
    select.disabled = true;
    try {
      const prevMode = current?.mode;
      const session = await setSession(profile);
      // sim ↔ lab: invalidar norte/trazo (odom distinto → choque si se reutiliza)
      if (prevMode && session.mode && prevMode !== session.mode) {
        resetMappingForRobotSwitch(`${prevMode}→${session.mode}`);
      }
      applySession(session);
      await applyDefaultMap(session.default_map_id);
      requestRelocalize();
    } catch (err) {
      console.error(err);
      if (current) select.value = current.profile === "auto" ? "auto" : current.profile;
      window.alert(err.message || "No se pudo cambiar de robot");
    } finally {
      select.disabled = false;
    }
  });

  try {
    const session = await fetchSession();
    // Prefill select: mostrar perfil resuelto, opción auto disponible
    fillSelect(session);
    applySession(session);
    await applyDefaultMap(session.default_map_id);
    requestRelocalize();
  } catch (err) {
    console.error("Sesión robot:", err);
    if (kpiProfile) kpiProfile.textContent = "sin sesión";
  }
}

function fillSelect(session) {
  const profiles = session.available_profiles || [];
  select.innerHTML = "";
  const auto = document.createElement("option");
  auto.value = "auto";
  auto.textContent = "Auto (Kalman)";
  select.appendChild(auto);
  for (const p of profiles) {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = p.label;
    select.appendChild(opt);
  }
  // Mostrar el perfil efectivo (sim/nexus/rbot). Si el usuario quiere Auto,
  // puede elegirlo manualmente; así no se controla Nexus creyendo que es Gazebo.
  const active = session.profile || "sim";
  select.value = [...select.options].some((o) => o.value === active)
    ? active
    : "auto";
}

function applySession(session) {
  current = session;
  if (logoName) logoName.textContent = session.label || "R-Bot";
  if (logoSub) {
    const lab = session.kalman?.laboratory_name;
    if (session.mode === "sim") {
      logoSub.textContent = "Simulación · domain " + session.domain_id;
    } else if (lab) {
      logoSub.textContent = lab + " · domain " + session.domain_id;
    } else {
      logoSub.textContent = "Lab · domain " + session.domain_id;
    }
  }
  if (kpiProfile) {
    const peer = session.peers_hint ? ` · ${session.peers_hint.split("/")[0].trim()}` : "";
    kpiProfile.textContent = `${session.label} · d${session.domain_id}${peer}`;
  }
  if (chipProfile) {
    chipProfile.classList.toggle("is-ok", session.mode === "lab");
    chipProfile.classList.toggle("is-warn", session.mode === "sim");
  }
  document.title = `${session.label || "R-Bot"} · Operations`;
  document.body.dataset.robot = session.profile || "";
  document.body.dataset.robotMode = session.mode || "";
  markSessionOnline(session);
}

export function getCurrentSession() {
  return current;
}
