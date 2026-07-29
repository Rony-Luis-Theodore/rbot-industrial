/**
 * =============================================================================
 * R-Bot — Componente: Sidebar (components/sidebar.js)
 * =============================================================================
 *
 * Propósito:
 *   Orquestador del panel lateral. Inicializa sub-componentes.
 *
 * Conexión con el resto:
 *   - status-panel.js: estado del robot
 *   - event-log.js: registro de eventos
 *   - Futuro: mapa, LiDAR, cámara
 * =============================================================================
 */

import { initEventLog } from "./event-log.js";
import { initStatusPanel } from "./status-panel.js";

/**
 * Inicializa todos los componentes del sidebar.
 */
export function initSidebar() {
  initStatusPanel();
  initEventLog();
}
