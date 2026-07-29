/**
 * =============================================================================
 * R-Bot — Componente: Event Log (components/event-log.js)
 * =============================================================================
 *
 * Propósito:
 *   Muestra el registro de eventos del sistema en el panel lateral.
 *
 * Conexión con el resto:
 *   - GET /api/v1/robot/events
 *   - index.html: #event-log
 *
 * Escalabilidad:
 *   - Reemplazar polling por WebSocket push.
 *   - Agregar filtros por nivel y fuente.
 * =============================================================================
 */

import { fetchEvents } from "../api/robot.js";
import { EVENTS_POLL_INTERVAL } from "../config.js";
import { escapeHtml, formatTime, getElement, scrollToBottom } from "../utils/dom.js";

const eventLogContainer = getElement("event-log");

/** IDs de eventos ya renderizados (evita duplicados en polling) */
const renderedIds = new Set();

/**
 * Inicializa polling del registro de eventos.
 */
export function initEventLog() {
  updateEvents();
  setInterval(updateEvents, EVENTS_POLL_INTERVAL);
}

/**
 * Consulta y renderiza eventos nuevos.
 */
async function updateEvents() {
  try {
    const events = await fetchEvents(30);
    renderEvents(events);
  } catch {
    // Silencioso en polling — el status panel ya muestra desconexión
  }
}

/**
 * Renderiza lista de eventos (solo agrega los nuevos).
 * @param {Array} events - Lista de EventLogResponse
 */
function renderEvents(events) {
  if (!events || events.length === 0) return;

  // Remover mensaje vacío
  const empty = eventLogContainer.querySelector(".event-empty");
  if (empty) empty.remove();

  // Renderizar en orden cronológico (API retorna más reciente primero)
  const sorted = [...events].reverse();

  for (const event of sorted) {
    if (renderedIds.has(event.id)) continue;
    renderedIds.add(event.id);

    const entry = document.createElement("div");
    entry.className = `event-entry event-${event.level}`;
    entry.innerHTML = `
      <span class="event-time">${formatTime(event.timestamp)}</span>
      <div>
        <div class="event-message">${escapeHtml(event.message)}</div>
        <span class="event-source">${escapeHtml(event.source)}</span>
      </div>
    `;
    eventLogContainer.appendChild(entry);
  }

  scrollToBottom(eventLogContainer);

  // Limitar IDs en memoria
  if (renderedIds.size > 200) {
    const ids = Array.from(renderedIds);
    ids.slice(0, ids.length - 100).forEach((id) => renderedIds.delete(id));
  }
}

/** Expone refresh manual para llamar después de enviar chat */
export function refreshEvents() {
  updateEvents();
}
