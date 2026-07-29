/**
 * Configuración HMI R-Bot Industrial
 */

export const API_BASE_URL = "";

export const ENDPOINTS = {
  chat: "/api/v1/chat",
  health: "/api/v1/health",
  status: "/api/v1/robot/status",
  events: "/api/v1/robot/events",
  emergencyStop: "/api/v1/robot/emergency_stop",
  teleop: "/api/v1/robot/teleop",
  scan: "/api/v1/robot/scan",
  voiceTranscribe: "/api/v1/voice/transcribe",
  session: "/api/v1/robot/session",
  maps: "/api/v1/robot/maps",
  mapMeta: (id) => `/api/v1/robot/maps/${encodeURIComponent(id)}`,
  mapImage: (id) => `/api/v1/robot/maps/${encodeURIComponent(id)}/image`,
  hmiDebug: "/api/v1/robot/hmi_debug",
  trackPerimeter: "/api/v1/robot/lab_traces/track_perimeter",
  labTraces: "/api/v1/robot/lab_traces",
  anchorTranslation: "/api/v1/robot/lab_traces/anchor_translation",
  liveAlign: "/api/v1/robot/lab_traces/live_align",
  labGeometry: "/api/v1/robot/lab/geometry",
  labSessionAlign: "/api/v1/robot/lab/session/align",
};

export const WS_TELEMETRY_PATH = "/api/v1/ws/telemetry";

export const MESSAGE_ROLE = {
  USER: "user",
  ASSISTANT: "assistant",
  SYSTEM: "system",
};

export const POLL_EVENTS_MS = 8000;
