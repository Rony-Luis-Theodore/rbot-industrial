/**
 * Constantes lab Occupancy — espejo de packages/lab_map/constants.py
 *
 * CHECKPOINT VALIDADO: LabHmiStableV4 (packages/lab_map/snapshots/).
 * Escala afinada · Ubicar centro · Operator v3 · HMI Sonar (murciélago).
 * SE2 / orientación: NO TOCAR sin petición explícita del usuario.
 */

export const LIDAR_YAW = -Math.PI / 2;
export const LIDAR_HEADING_FLIP = 0;
export const HEADING_LOCKED = true;
export const HEADING_UI_FLIP_ENABLED = false;
export const DISPLAY_YAW = Math.PI / 2;
export const PERIMETER_YAW_META = 1.570083462815548;
/** @locked LabTrayectoriaOK */
export const MAP_ALIGN_NUDGE = { tx: -0.06, ty: 0.0 };
/** @locked LabTrayectoriaOK — base; V3+ tip un poco adelantado → −4% mapa */
export const LOCALIZE_OUTWARD_M = 0.14;
/** @locked LabTrayectoriaOK */
export const LOCALIZE_MIRROR_X = true;
/** @locked LabTrayectoriaOK — F/B */
export const HEADING_BIAS_RAD = Math.PI;
/**
 * Escala odom→Occupancy.
 * LabTrayectoriaOK: 7/6. En lab el tip iba un poco adelantado (choque sim
 * al final de tramos largos) → factor 0.96 (~4% menos recorrido en mapa).
 */
export const ODOM_TO_MAP_SCALE = (7 / 6) * 0.96;
/** @locked LabTrayectoriaOK — giros izq/der (base) */
export const ODOM_Y_SIGN = -1;
/**
 * Capa de corrección HMI: invierte izq/der tras cada Ubicar / proyección.
 * Tip LiDAR se acepta; solo se refleja la quiralidad SE2 (pedido explícito).
 */
export const LOCALIZE_INVERT_LR = true;
/** Signo Y efectivo = ODOM_Y_SIGN × (−1 si LOCALIZE_INVERT_LR). */
export function effectiveOdomYSign() {
  return LOCALIZE_INVERT_LR ? -ODOM_Y_SIGN : ODOM_Y_SIGN;
}
/** Obligatorio pulsar Ubicar tras cargar / odom-reset (sin auto). */
export const REQUIRE_MANUAL_UBICAR = true;
/**
 * Tras un Ubicar OK el botón se oculta (1 ancla / sesión).
 * Evita re-Ubicar = “vistas CAD” / cardinales distintos.
 * Para reanclar: recarga la página (F5 / refresh del navegador).
 */
export const UBICAR_ONCE_PER_SESSION = true;
/**
 * Solo dibujo: si el rumbo en pantalla está cerca de un eje (recto / 90°),
 * la flecha se pinta en ese eje (corrige el “poquito a un lado” sin tocar SE2).
 */
export const ARROW_UI_SNAP_RAD = 0.32; // ~18°
export const REAL_CIRCUIT_M = {
  wallMapW: 1.6,
  wallMapH: 1.5,
  wallRealW: 1.6 * ((7 / 6) * 0.96),
  wallRealH: 1.5 * ((7 / 6) * 0.96),
  obstacleMap: 0.2,
  obstacleReal: 0.2 * ((7 / 6) * 0.96),
};
export const TRAIL_MAX_STEP_M = 0.55;
export const TRAIL_MIN_STEP_M = 0.015;
export const TRAIL_MAX_POINTS = 900;
export const LOCALIZE_SCORE_MIN_FRAC = 0.12;
export const REFINE_T_RADIUS_M = 0.4;
export const TRACK_INTERVAL_MS = 1600;
export const TRACK_XY_RADIUS_M = 0.28;
export const TRACK_YAW_RADIUS_RAD = 0.35;
export const TRACK_MIN_IMPROVE = 1.15;
export const TRACK_FLIP_IMPROVE = 1.08;
export const SESSION_SOURCE = "lidar_in_track";
export const ALIGN_VER = "lab-hmi-stable-v4";
export const NORTH_VER = "lab-north-v1";
export const CHECKPOINT_NAME = "LabHmiStableV4";
