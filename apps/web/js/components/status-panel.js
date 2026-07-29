/**
 * =============================================================================
 * R-Bot — Componente: Status Panel (components/status-panel.js)
 * =============================================================================
 *
 * Propósito:
 *   Actualiza el panel lateral con estado del robot (batería, modo, posición).
 *
 * Conexión con el resto:
 *   - api/robot.js para polling de estado.
 *   - index.html: elementos #status-*, #battery-fill, #connection-pill
 * =============================================================================
 */

import { fetchHealth, fetchRobotStatus } from "../api/robot.js";
import { STATUS_POLL_INTERVAL } from "../config.js";
import { getElement } from "../utils/dom.js";

/** Referencias DOM del panel de estado */
const els = {
  connection: getElement("status-connection"),
  battery: getElement("status-battery"),
  mode: getElement("status-mode"),
  position: getElement("status-position"),
  goal: getElement("status-goal"),
  batteryFill: getElement("battery-fill"),
  connectionPill: getElement("connection-pill"),
  connectionText: getElement("connection-text"),
  providerBadge: getElement("provider-badge"),
};

/**
 * Inicializa polling periódico del estado del robot.
 */
export function initStatusPanel() {
  updateStatus();
  setInterval(updateStatus, STATUS_POLL_INTERVAL);
}

/**
 * Consulta y renderiza el estado actual del robot.
 */
async function updateStatus() {
  try {
    const [status, health] = await Promise.all([
      fetchRobotStatus(),
      fetchHealth(),
    ]);

    renderStatus(status);
    renderConnection(status.connection);
    els.providerBadge.textContent = `LLM: ${health.llm_provider} | ROS: ${health.ros_provider}`;
  } catch {
    renderConnection("disconnected");
    els.connectionText.textContent = "Sin conexión";
  }
}

/**
 * Renderiza datos de estado en el panel lateral.
 * @param {object} status - RobotStatusResponse del backend
 */
function renderStatus(status) {
  els.connection.textContent = capitalize(status.connection);
  els.battery.textContent = `${status.battery_percent.toFixed(1)}%`;
  els.mode.textContent = capitalize(status.mode);
  els.position.textContent = `x:${status.position.x.toFixed(2)} y:${status.position.y.toFixed(2)} θ:${status.position.theta.toFixed(2)}`;
  els.goal.textContent = status.current_goal || "Ninguno";

  // Barra de batería con colores semáforo
  const pct = status.battery_percent;
  els.batteryFill.style.width = `${pct}%`;
  els.batteryFill.className = "battery-fill";
  if (pct < 20) els.batteryFill.classList.add("low");
  else if (pct < 50) els.batteryFill.classList.add("medium");
}

/**
 * Actualiza indicador de conexión en el header.
 * @param {string} connection - connected | disconnected | degraded
 */
function renderConnection(connection) {
  els.connectionPill.className = "status-pill";
  if (connection === "connected") {
    els.connectionPill.classList.add("connected");
    els.connectionText.textContent = "Conectado";
  } else {
    els.connectionPill.classList.add("disconnected");
    els.connectionText.textContent = connection === "degraded" ? "Degradado" : "Desconectado";
  }
}

/** Capitaliza primera letra */
function capitalize(str) {
  if (!str) return "—";
  return str.charAt(0).toUpperCase() + str.slice(1);
}
