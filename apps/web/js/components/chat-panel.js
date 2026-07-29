/**
 * Panel de chat — texto / voz
 * «detén» siempre se puede enviar (movimiento va en background).
 */

import { sendMessage } from "../api/chat.js";
import { MESSAGE_ROLE } from "../config.js";
import { escapeHtml, getElement, scrollToBottom } from "../utils/dom.js";
import { isLabAnchored, subscribeLab } from "../lab/lab-session.js";

const messagesContainer = getElement("chat-messages");
const chatForm = getElement("chat-form");
const chatInput = getElement("chat-input");
const btnSend = getElement("btn-send");

let loadingMessageId = null;
let pending = 0;

const STOP_RE =
  /\b(det[eé]n(?:te)?|cancela(?:r)?|frena(?:r)?|stop|halt|emergency|e-?stop|para(?:r)?(?!\s+atr))\b/i;

function isStopInstruction(text) {
  const t = (text || "").trim().toLowerCase();
  if (/para\s+atr[aá]s|para\s+atras/.test(t)) return false;
  return STOP_RE.test(t);
}

export function initChatPanel() {
  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = chatInput.value.trim();
    if (!text) return;
    if (!isLabAnchored() && !isStopInstruction(text)) {
      appendMessage(
        MESSAGE_ROLE.ASSISTANT,
        "Primero pulsa «Ubicar en el mapa» para anclar el robot."
      );
      return;
    }
    chatInput.value = "";
    submitInstruction(text);
  });

  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      chatForm.requestSubmit();
    }
  });

  subscribeLab(() => {
    const ok = isLabAnchored();
    if (chatInput) {
      chatInput.placeholder = ok
        ? "Escribe una orden…"
        : "Bloqueado — Ubicar en el mapa primero (salvo «detén»)";
    }
  });

  window.addEventListener("rbot:lab-restart", () => {
    resetChatAfterRestart();
  });
}

/** Limpia el hilo y deja el mensaje de arranque (como Ubicar gate). */
export function resetChatAfterRestart() {
  if (!messagesContainer) return;
  messagesContainer.innerHTML = "";
  appendMessage(
    MESSAGE_ROLE.SYSTEM,
    "Lleva el robot al centro del circuito, Ubica una vez y usa el chat. Si el LiDAR no cuadra → Recarga la página."
  );
}

/**
 * Envía una instrucción (texto o resultado de voz).
 * @param {string} text
 */
export async function submitInstruction(text) {
  appendMessage(MESSAGE_ROLE.USER, text);
  const stop = isStopInstruction(text);
  pending += 1;
  chatInput.disabled = false;
  btnSend.disabled = false;
  if (!stop) {
    document.body.classList.add("is-thinking");
    showLoading();
  }

  try {
    const response = await sendMessage(text);
    removeLoadingMessage();
    document.body.classList.remove("is-thinking");
    appendMessage(MESSAGE_ROLE.ASSISTANT, response.reply, response.intent);
  } catch (error) {
    removeLoadingMessage();
    document.body.classList.remove("is-thinking");
    appendMessage(
      MESSAGE_ROLE.SYSTEM,
      `Error de comunicación: ${error.message}`
    );
  } finally {
    pending = Math.max(0, pending - 1);
    if (pending === 0) {
      removeLoadingMessage();
      document.body.classList.remove("is-thinking");
    }
    chatInput.focus();
  }
}

function appendMessage(role, content, intent = null) {
  const messageEl = document.createElement("div");
  messageEl.className = `message message-${role}`;
  let metaHtml = "";
  if (intent) {
    const conf = Math.round(Number(intent.confidence) * 100);
    metaHtml = `<div class="message-meta">${escapeHtml(intent.provider)} → ${escapeHtml(
      intent.intent
    )} · conf. ${Number.isFinite(conf) ? conf : "—"}%</div>`;
  }
  messageEl.innerHTML = `
    <div class="message-content">${escapeHtml(content)}</div>
    ${metaHtml}
  `;
  messagesContainer.appendChild(messageEl);
  scrollToBottom(messagesContainer);
}

function showLoading() {
  removeLoadingMessage();
  loadingMessageId = `loading-${Date.now()}`;
  const loadingEl = document.createElement("div");
  loadingEl.className = "message message-assistant message-loading";
  loadingEl.id = loadingMessageId;
  loadingEl.innerHTML = `<div class="message-content">Procesando<span class="loading-dots"><span>.</span><span>.</span><span>.</span></span></div>`;
  messagesContainer.appendChild(loadingEl);
  scrollToBottom(messagesContainer);
}

function removeLoadingMessage() {
  if (!loadingMessageId) return;
  document.getElementById(loadingMessageId)?.remove();
  loadingMessageId = null;
}
