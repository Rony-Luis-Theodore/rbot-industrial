# Arquitectura — R-Bot Industrial

## 1. Objetivo

Plataforma de control e inspección para plantas industriales: el operario habla o escribe; el sistema traduce a acciones ROS 2 seguras y muestra estado espacial (mapa, LiDAR, pose) y telemetría fiable.

## 2. Capas

```text
┌─────────────────────────────────────────────────────────┐
│  apps/web — HMI industrial                              │
│  Mapa · telemetría · chat texto/voz · E-STOP · eventos  │
└───────────────────────────┬─────────────────────────────┘
                            │ REST + WebSocket
┌───────────────────────────▼─────────────────────────────┐
│  apps/api — FastAPI (Ports & Adapters)                  │
│  ChatOrchestrator · EventLogger · factories             │
│  Ports: LLMService · ROSService                         │
└─────────────┬───────────────────────────┬───────────────┘
              │                           │
   ┌──────────▼──────────┐     ┌──────────▼──────────────┐
   │ Adapters LLM        │     │ Adapters ROS            │
   │ mock · ollama       │     │ mock · rclpy(CLI)       │
   │ (openai/gemini stub)│     │ Nav2/waypoints (futuro) │
   └─────────────────────┘     └──────────┬──────────────┘
                                          │
                               ┌──────────▼──────────────┐
                               │ Robot / Lab             │
                               │ Create3 · /scan · /map  │
                               │ Husarnet · CycloneDDS   │
                               └─────────────────────────┘
```

## 3. Flujo de una instrucción

1. HMI captura texto o STT (voz → texto).
2. `POST /api/v1/chat` → `ChatOrchestrator`.
3. `LLMService.process_user_instruction()` → `LLMIntent`.
4. Orquestador llama el método de `ROSService` correspondiente.
5. Respuesta + `ros_data` al operario; evento en `EventLogger`.
6. Telemetría continua por `WS /api/v1/ws/telemetry`.

## 4. Mapa en la HMI (sin RViz embebido)

| Fuente | Uso |
|--------|-----|
| Mapa estático `*.pgm` + `*.yaml` (kalman_bringup) | Overlay de pose en HMI v1 |
| Topic `/map` OccupancyGrid (Cartographer/Nav2) | Live via rosbridge / proxy (v1.1) |
| Topic `/scan` | Capa LiDAR (throttle) |
| RViz / Gazebo | Solo ingeniería en laboratorio |

## 5. Pipeline ML (Colab → local)

| Artefacto | Colab (GPU) | Local (CPU) |
|-----------|-------------|-------------|
| Clasificador / LLM intents | LoRA / QLoRA | Ollama GGUF / ONNX |
| Whisper STT dominio | Fine-tune small | faster-whisper / whisper.cpp |
| Detector fugas/peligros | YOLO/Seg | ONNX Runtime |

Notebooks en `ml/notebooks/`. Export en `ml/export/`.

## 6. Rol de ros2ai

`third_party/ros2ai` es una CLI de referencia (NL → `ros2 …`).  
En producción industrial **no** se usa `ros2 ai exec` sin allowlist. El núcleo es el orquestador con tools tipadas.

## 7. Principios

- DIP: orquestador no conoce Ollama ni Create3.
- Seguridad: parada, rate-limit de `/cmd_vel`, auditoría.
- Offline-first lab: Ollama local; cloud LLM opcional.
- Una HMI de operación, no un dashboard genérico.
