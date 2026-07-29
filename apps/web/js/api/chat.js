import { ENDPOINTS } from "../config.js";
import { apiFetch } from "./client.js";

/** @param {string} message */
export function sendMessage(message) {
  return apiFetch(ENDPOINTS.chat, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}
