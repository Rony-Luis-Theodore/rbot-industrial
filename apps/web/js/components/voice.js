/**
 * Voz → texto → mismo pipeline de chat.
 *
 * Chrome/Edge: Web Speech si está disponible; si falla → Whisper.
 * Firefox: siempre grabación + Whisper (no tiene Web Speech fiable).
 *
 * Atajos: Alt+V | Shift+click = forzar Whisper
 */

import { ENDPOINTS } from "../config.js";
import { getElement } from "../utils/dom.js";
import { submitInstruction } from "./chat-panel.js";

const btnVoice = getElement("btn-voice");
const chatInput = getElement("chat-input");

/** @type {HTMLElement|null} */
let statusEl = null;

/** @type {{ stop: () => void, promise: Promise<Blob|null> } | null} */
let activeRecording = null;

const isFirefox = /firefox/i.test(navigator.userAgent);

export function initVoice() {
  // Sin banner de mic: el navegador pide permiso al pulsar Voz.
  void refreshVoiceBackendStatus();

  const SpeechRecognition =
    window.SpeechRecognition || window.webkitSpeechRecognition;

  if (SpeechRecognition && !isFirefox) {
    initWebSpeech(SpeechRecognition);
  } else {
    initMediaFallbackOnly();
  }

  window.addEventListener("keydown", (e) => {
    if (e.altKey && e.code === "KeyV") {
      e.preventDefault();
      btnVoice.click();
    }
  });
}

function ensureStatusEl() {
  /* no-op: UI sin mensaje de micrófono */
}

function setStatus(_msg, _tone = "info") {
  /* silencioso — feedback solo en el botón Voz */
}

async function refreshVoiceBackendStatus() {
  try {
    const res = await fetch("/api/v1/voice/status");
    if (!res.ok) return;
    const data = await res.json();
    if (!data.ready) {
      setStatus(data.detail || "Whisper no listo en la API", "warn");
    }
  } catch {
    /* ignore */
  }
}

function initWebSpeech(SpeechRecognition) {
  const recognition = new SpeechRecognition();
  recognition.lang = pickLang();
  recognition.interimResults = true;
  recognition.continuous = false;
  recognition.maxAlternatives = 3;

  let listening = false;
  let finalTranscript = "";
  let skipSubmitOnEnd = false;

  btnVoice.addEventListener("click", async (ev) => {
    if (ev.shiftKey) {
      if (listening) {
        skipSubmitOnEnd = true;
        try {
          recognition.stop();
        } catch {
          /* ignore */
        }
      }
      void toggleRecordAndTranscribe();
      return;
    }

    if (activeRecording) {
      activeRecording.stop();
      return;
    }

    if (listening) {
      recognition.stop();
      return;
    }

    finalTranscript = "";
    skipSubmitOnEnd = false;

    const micOk = await ensureMicPermission();
    if (!micOk) return;

    try {
      recognition.start();
    } catch (err) {
      setStatus(`Web Speech falló · grabando con Whisper… (${err.message})`, "warn");
      void toggleRecordAndTranscribe();
    }
  });

  recognition.addEventListener("start", () => {
    listening = true;
    setListeningUi(true, "Escuchando…");
    setStatus("Escuchando… habla ahora", "ok");
  });

  recognition.addEventListener("result", (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const piece = event.results[i][0].transcript;
      if (event.results[i].isFinal) finalTranscript += piece;
      else interim += piece;
    }
    const preview = (finalTranscript || interim).trim();
    if (preview) chatInput.value = preview;
  });

  recognition.addEventListener("end", () => {
    listening = false;
    setListeningUi(false);
    if (skipSubmitOnEnd) return;

    const text = (finalTranscript || chatInput.value || "").trim();
    if (text) {
      setStatus(`Oí: “${text}”`, "ok");
      chatInput.value = "";
      void submitInstruction(text);
      return;
    }
    setStatus("Sin texto · grabando con Whisper…", "warn");
    void toggleRecordAndTranscribe();
  });

  recognition.addEventListener("error", (event) => {
    listening = false;
    setListeningUi(false);
    const code = event.error || "error";
    const map = {
      "not-allowed":
        "Mic bloqueado. En Chrome: candado/ⓘ de la URL → Sitio → Micrófono → Permitir (o chrome://settings/content/microphone).",
      "no-speech": "No se detectó habla",
      aborted: "Reconocimiento cancelado",
      network: "Error de red del servicio de voz del navegador",
      "service-not-allowed": "Servicio de voz no permitido en este contexto",
      "audio-capture": "No hay micrófono disponible",
    };
    setStatus(map[code] || `Error de voz: ${code}`, "error");

    if (
      code === "network" ||
      code === "service-not-allowed" ||
      code === "no-speech"
    ) {
      setStatus("Cambiando a grabación Whisper…", "warn");
      void toggleRecordAndTranscribe();
    }
  });
}

function initMediaFallbackOnly() {
  btnVoice.addEventListener("click", () => {
    void toggleRecordAndTranscribe();
  });
}

async function ensureMicPermission() {
  if (!window.isSecureContext && location.hostname !== "localhost" && location.hostname !== "127.0.0.1") {
    setStatus(
      "Abre la HMI en http://127.0.0.1:8000 (no file:// ni IP sin HTTPS). El mic requiere contexto seguro.",
      "error"
    );
    return false;
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    setStatus("Este navegador no permite micrófono", "error");
    return false;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        channelCount: 1,
      },
    });
    stream.getTracks().forEach((t) => t.stop());
    return true;
  } catch (err) {
    const name = err?.name || "";
    if (name === "NotAllowedError" || name === "PermissionDeniedError") {
      setStatus(
        "Permiso de mic denegado. Firefox: candado → Permisos → Micrófono. Chrome: ⓘ junto a la URL o chrome://settings/content/microphone → Permitir para 127.0.0.1.",
        "error"
      );
    } else {
      setStatus(`No se pudo abrir el mic: ${err.message || name}`, "error");
    }
    return false;
  }
}

function pickLang() {
  const nav = (navigator.language || "es").toLowerCase();
  if (nav.startsWith("es")) {
    if (nav.includes("mx")) return "es-MX";
    if (nav.includes("us")) return "es-US";
    return "es-ES";
  }
  return "es-ES";
}

function setListeningUi(on, label = "Grabando…") {
  btnVoice.setAttribute("aria-pressed", on ? "true" : "false");
  btnVoice.textContent = on ? label : "Voz";
}

function pickRecorderMime() {
  const candidates = isFirefox
    ? ["audio/ogg;codecs=opus", "audio/webm;codecs=opus", "audio/webm", "audio/ogg"]
    : ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"];
  for (const t of candidates) {
    if (window.MediaRecorder?.isTypeSupported?.(t)) return t;
  }
  return "";
}

/**
 * Toggle: primer click inicia, segundo detiene (máx 10 s).
 */
async function toggleRecordAndTranscribe() {
  if (activeRecording) {
    activeRecording.stop();
    return;
  }

  const micOk = await ensureMicPermission();
  if (!micOk) return;

  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        channelCount: 1,
      },
    });
  } catch {
    setStatus("Permiso de micrófono denegado", "error");
    return;
  }

  const mime = pickRecorderMime();
  const recorder = mime
    ? new MediaRecorder(stream, { mimeType: mime })
    : new MediaRecorder(stream);
  const chunks = [];
  let maxTimer = null;

  recorder.addEventListener("dataavailable", (e) => {
    if (e.data.size > 0) chunks.push(e.data);
  });

  const blobPromise = new Promise((resolve) => {
    recorder.addEventListener("stop", () => {
      stream.getTracks().forEach((t) => t.stop());
      if (maxTimer) clearTimeout(maxTimer);
      activeRecording = null;
      setListeningUi(false);
      const type = recorder.mimeType || mime || "audio/webm";
      const blob = new Blob(chunks, { type });
      resolve(blob.size >= 400 ? blob : null);
    });
  });

  activeRecording = {
    stop: () => {
      if (recorder.state !== "inactive") {
        try {
          recorder.requestData?.();
        } catch {
          /* ignore */
        }
        recorder.stop();
      }
    },
    promise: blobPromise,
  };

  setListeningUi(true, "Detener");
  setStatus("Grabando… habla ahora y pulsa Detener (mín. 2 s, máx 10 s)", "ok");
  recorder.start(250);

  maxTimer = setTimeout(() => {
    if (recorder.state !== "inactive") recorder.stop();
  }, 10000);

  const blob = await blobPromise;
  if (!blob) {
    setStatus("Grabación vacía — habla más fuerte o revisa el mic del sistema", "warn");
    return;
  }

  setStatus("Transcribiendo con Whisper…", "info");
  try {
    const text = await uploadTranscribe(blob);
    if (!text) {
      setStatus("Sin texto en la transcripción", "warn");
      return;
    }
    chatInput.value = text;
    setStatus(`Oí: “${text}”`, "ok");
    chatInput.value = "";
    await submitInstruction(text);
  } catch (err) {
    setStatus(String(err.message || err), "error");
  }
}

async function uploadTranscribe(blob) {
  const form = new FormData();
  const ext = blob.type.includes("ogg") ? "ogg" : "webm";
  form.append("audio", blob, `utterance.${ext}`);
  const res = await fetch(ENDPOINTS.voiceTranscribe, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = j.detail || JSON.stringify(j);
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  const data = await res.json();
  return (data.text || "").trim();
}
