/**
 * Telemetría → chips de la topbar + eventos
 *
 * No importa viewer.js aquí (evita ciclos / fallos de arranque).
 * La pose se engancha con bindPoseUpdater desde app.js.
 */

import { emergencyStop, fetchEvents, fetchStatus } from "../api/robot.js";
import { POLL_EVENTS_MS } from "../config.js";
import { escapeHtml, getElement } from "../utils/dom.js";
import { connectTelemetry } from "../ws/telemetry-client.js";

const elConn = getElement("kpi-connection");
const elBatt = getElement("kpi-battery");
const elMode = getElement("kpi-mode");
const elPose = getElement("kpi-pose");
const kpiProfile = document.getElementById("kpi-profile");
const chipLink = getElement("chip-link");
const chipBatt = getElement("chip-batt");
const btnEstop = document.getElementById("btn-estop");
const eventList = document.getElementById("event-list");

let lastOkMs = 0;
const bootMs = Date.now();
/** @type {null | ((pose: object|null) => void)} */
let poseUpdater = null;
let pollBusy = false;
/** Histeresis: no pintar "disconnected" por un status puntual. */
let badConnStreak = 0;
let lastShownConn = "conectando…";

/** Engancha updateRobotPose sin import circular. */
export function bindPoseUpdater(fn) {
  poseUpdater = typeof fn === "function" ? fn : null;
}

export function initTelemetry() {
  elConn.textContent = "conectando…";
  setTone(chipLink, "warn");

  btnEstop?.addEventListener("click", async () => {
    const ok = window.confirm("¿Activar E-STOP?");
    if (!ok) return;
    try {
      const res = await emergencyStop();
      pushEvent("warning", res.message || "E-STOP");
    } catch (err) {
      pushEvent("error", err.message);
    }
  });

  connectTelemetry(
    (status) => {
      try {
        lastOkMs = Date.now();
        renderStatus(status);
        poseUpdater?.(status.position || null);
      } catch (err) {
        console.error("telemetría WS:", err);
      }
    },
    () => {
      if (lastOkMs && Date.now() - lastOkMs > 20000) {
        setTone(chipLink, "bad");
        elConn.textContent = "sin enlace";
        lastShownConn = "sin enlace";
      }
    }
  );

  const poll = async () => {
    if (pollBusy) return;
    if (lastOkMs && Date.now() - lastOkMs < 2500) return;
    pollBusy = true;
    try {
      const status = await fetchStatus();
      lastOkMs = Date.now();
      renderStatus(status);
      poseUpdater?.(status.position || null);
    } catch (err) {
      console.warn("poll status:", err);
      const waited = Date.now() - (lastOkMs || bootMs);
      if (waited > 20000) {
        setTone(chipLink, "bad");
        elConn.textContent = "sin enlace";
        lastShownConn = "sin enlace";
      }
    } finally {
      pollBusy = false;
    }
  };
  void poll();
  setInterval(poll, 2500);

  if (eventList) {
    refreshEvents();
    setInterval(refreshEvents, POLL_EVENTS_MS);
  }
}

/** La sesión Kalman ya prueba que el lab está activo — no esperar odom. */
export function markSessionOnline(session) {
  if (!session) return;
  if (kpiProfile) {
    const d = session.domain_id != null ? ` · d${session.domain_id}` : "";
    kpiProfile.textContent = `${session.label || "Robot"}${d}`;
  }
  if (session.mode === "lab" && session.kalman?.active) {
    if (!lastOkMs) {
      elConn.textContent = "connected";
      setTone(chipLink, "ok");
    }
  } else if (session.mode === "sim" && !lastOkMs) {
    elConn.textContent = "sim";
    setTone(chipLink, "warn");
  }
}

function renderStatus(s) {
  if (!s) return;

  const raw = String(s.connection || "").toLowerCase();
  let shown = raw || "—";
  if (raw === "connected" || raw === "degraded") {
    badConnStreak = 0;
    shown = raw === "degraded" ? "connected" : raw; // degraded visual = connected estable
  } else if (raw === "disconnected") {
    badConnStreak += 1;
    // Exige 4 lecturas malas (~8–10 s) antes de pintar rojo
    if (badConnStreak < 4 && lastShownConn && lastShownConn !== "sin enlace") {
      shown = "connected";
    } else {
      shown = "disconnected";
    }
  }
  lastShownConn = shown;
  elConn.textContent = shown;
  setTone(
    chipLink,
    shown === "connected" ? "ok" : shown === "degraded" ? "warn" : "bad"
  );

  // No empujar pose basura al viewer cuando el enlace está caído de verdad
  const p = s.position || {};
  const px = Number(p.x);
  const py = Number(p.y);
  if (shown === "disconnected" && (!Number.isFinite(px) || !Number.isFinite(py))) {
    /* skip pose text */
  } else {
    elPose.textContent = `${fmt(p.x)}, ${fmt(p.y)}`;
  }

  const batt = Number(s.battery_percent);
  const showBatt = Number.isFinite(batt) && batt > 0;
  elBatt.textContent = showBatt ? `${batt.toFixed(0)}%` : "—";
  setTone(chipBatt, showBatt ? (batt >= 40 ? "ok" : batt >= 20 ? "warn" : "bad") : null);

  elMode.textContent = s.mode || "—";

  if (s.robot_label && kpiProfile) {
    const d = s.ros_domain_id != null ? ` · d${s.ros_domain_id}` : "";
    kpiProfile.textContent = `${s.robot_label}${d}`;
  }
}

function setTone(el, tone) {
  if (!el) return;
  el.classList.remove("is-ok", "is-warn", "is-bad");
  if (tone) el.classList.add(`is-${tone}`);
}

function fmt(n) {
  const v = Number(n);
  return Number.isFinite(v) ? v.toFixed(2) : "—";
}

async function refreshEvents() {
  if (!eventList) return;
  try {
    const events = await fetchEvents(20);
    eventList.innerHTML = events
      .map(
        (e) =>
          `<li class="lvl-${escapeHtml(e.level)}">${escapeHtml(e.message)}</li>`
      )
      .join("");
  } catch {
    /* ignore */
  }
}

function pushEvent(level, message) {
  if (!eventList) return;
  const li = document.createElement("li");
  li.className = `lvl-${level}`;
  li.textContent = message;
  eventList.prepend(li);
}
