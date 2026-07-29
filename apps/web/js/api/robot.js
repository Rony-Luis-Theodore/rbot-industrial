import { ENDPOINTS } from "../config.js";
import { apiFetch } from "./client.js";

export function sendMessage(message) {
  return apiFetch(ENDPOINTS.chat, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

export function fetchHealth() {
  return apiFetch(ENDPOINTS.health);
}

export function fetchStatus() {
  return apiFetch(ENDPOINTS.status);
}

export function fetchEvents(limit = 30) {
  return apiFetch(`${ENDPOINTS.events}?limit=${limit}`);
}

export function emergencyStop() {
  return apiFetch(ENDPOINTS.emergencyStop, { method: "POST" });
}

export function sendTeleop(linear_x, angular_z) {
  return apiFetch(ENDPOINTS.teleop, {
    method: "POST",
    body: JSON.stringify({ linear_x, angular_z }),
  });
}

export function fetchScan(max_points = 360) {
  return apiFetch(`${ENDPOINTS.scan}?max_points=${max_points}`);
}

export function fetchMaps() {
  return apiFetch(ENDPOINTS.maps);
}

export function fetchMapMeta(id) {
  return apiFetch(ENDPOINTS.mapMeta(id));
}

export function fetchHmiDebug() {
  return apiFetch(ENDPOINTS.hmiDebug);
}

export function fetchSession() {
  return apiFetch(ENDPOINTS.session);
}

export function setSession(profile) {
  return apiFetch(ENDPOINTS.session, {
    method: "POST",
    body: JSON.stringify({ profile }),
  });
}
