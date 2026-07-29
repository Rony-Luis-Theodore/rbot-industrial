/**
 * Bootstrap HMI R-Bot — consola Lab Occupancy (lab-view, no viewer monolito)
 */

import { initChatPanel } from "./components/chat-panel.js";
import { initRobotSession } from "./components/robot-session.js";
import { bindPoseUpdater, initTelemetry } from "./components/telemetry.js";
import { initTeleop } from "./components/teleop.js";
import { initVoice } from "./components/voice.js";
import {
  initLabView,
  updateRobotPose,
} from "./lab/lab-view.js";

async function bootstrap() {
  document.body.dataset.view = "lab";

  initTelemetry();
  bindPoseUpdater(updateRobotPose);
  initChatPanel();
  initVoice();
  initTeleop();
  initRailNav();

  try {
    await initRobotSession();
  } catch (err) {
    console.error("Sesión:", err);
  }

  initLabView().catch((err) => console.error("Lab view:", err));
}

/**
 * Rail: mapa / cámara = vista principal.
 * Chat siempre visible. Control = panel que se muestra u oculta.
 */
function initRailNav() {
  const buttons = [...document.querySelectorAll(".rail-btn[data-rail]")];
  if (!buttons.length) return;

  const panelDrive = document.getElementById("panel-drive");
  const side = document.getElementById("side-panel");
  const labArena = document.getElementById("lab-arena");
  const cameraEmpty = document.getElementById("camera-empty");
  const btnDrive = buttons.find((b) => b.dataset.rail === "drive");
  const btnMap = buttons.find((b) => b.dataset.rail === "map");
  const btnCamera = buttons.find((b) => b.dataset.rail === "camera");

  let driveVisible = true;
  let mainView = "map";

  const syncLayout = () => {
    if (panelDrive) panelDrive.hidden = !driveVisible;
    if (side) side.hidden = false;
    side?.classList.toggle("only-chat", !driveVisible);
    side?.classList.remove("only-drive");

    btnDrive?.classList.toggle("is-on", driveVisible);
    btnDrive?.setAttribute("aria-pressed", driveVisible ? "true" : "false");

    const showMap = mainView === "map";
    if (labArena) labArena.hidden = !showMap;
    if (cameraEmpty) cameraEmpty.hidden = showMap;
    btnMap?.classList.toggle("is-active", showMap);
    btnMap?.setAttribute("aria-pressed", showMap ? "true" : "false");
    btnCamera?.classList.toggle("is-active", !showMap);
    btnCamera?.setAttribute("aria-pressed", showMap ? "false" : "true");

    window.dispatchEvent(new Event("resize"));
  };

  for (const btn of buttons) {
    btn.addEventListener("click", () => {
      const key = btn.dataset.rail;
      if (key === "map") {
        mainView = "map";
      } else if (key === "camera") {
        mainView = "camera";
      } else if (key === "drive") {
        driveVisible = !driveVisible;
      } else if (key === "profile") {
        document.getElementById("robot-profile")?.focus();
        return;
      }
      syncLayout();
    });
  }

  syncLayout();
}

document.addEventListener("DOMContentLoaded", () => {
  bootstrap().catch((err) => {
    console.error("Fallo al iniciar HMI:", err);
  });
});
