/**
 * Cliente WebSocket de telemetría
 */

import { WS_TELEMETRY_PATH } from "../config.js";

/**
 * @param {(payload: object) => void} onStatus
 * @param {(err: Error) => void} [onError]
 */
export function connectTelemetry(onStatus, onError) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const url = `${proto}://${location.host}${WS_TELEMETRY_PATH}`;
  let socket;
  let closed = false;
  let retryMs = 1200;

  function connect() {
    if (closed) return;
    socket = new WebSocket(url);

    socket.addEventListener("open", () => {
      retryMs = 1200;
    });

    socket.addEventListener("message", (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "status" && msg.payload) onStatus(msg.payload);
      } catch (err) {
        onError?.(err);
      }
    });

    socket.addEventListener("close", () => {
      if (closed) return;
      setTimeout(connect, retryMs);
      retryMs = Math.min(retryMs * 1.5, 8000);
    });

    socket.addEventListener("error", () => {
      onError?.(new Error("WebSocket telemetría con error"));
    });
  }

  connect();

  return () => {
    closed = true;
    socket?.close();
  };
}
