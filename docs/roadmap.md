# Roadmap — R-Bot Industrial

## Hecho

- [x] Backend hexagonal FastAPI + frontend base
- [x] Bridge ROS real Create3 (topics, status, cmd_vel, dock attempt)
- [x] Ollama local (qwen2.5:1.5b) + fallback mock
- [x] Monorepo GitHub-ready
- [x] HMI v1: mapa + telemetría + voz/texto + E-STOP
- [x] WebSocket de telemetría
- [x] Mando manual (teleop) en HMI — pad + WASD + límites de velocidad
- [x] Perfiles robot: Auto / R-Bot / Nexus / Simulación (domain + mapa)

## Próximo (v1.1)

- [ ] OccupancyGrid live (rosbridge / proxy FastAPI)
- [ ] Capa LiDAR `/scan` con throttle
- [ ] Alinear pose con mapa correcto del laboratorio (compañero ROS)
- [ ] Waypoints industriales + Nav2
- [ ] Confirmación humana para misiones críticas
- [ ] Historial de chat en cliente
- [ ] Lanzar Gazebo/Nav2 desde la HMI (hoy: scripts + perfil Sim)

## ML

- [x] Dataset de intents industriales (ES) — `ml/datasets/intents_es.jsonl`
- [x] Notebook Colab QLoRA + Modelfile Ollama — ver `docs/ml-pipeline.md`
- [x] Voz: Web Speech + fallback Whisper (`POST /api/v1/voice/transcribe`)
- [ ] Fine-tune Whisper-small dominio planta → CPU
- [ ] Detector visión fugas/peligros → ONNX

## Producto

- [ ] Auth de operarios
- [ ] Persistencia eventos / conversaciones (BD)
- [ ] Multi-robot
- [ ] Streaming cámara
- [ ] Tests automatizados API + bridge ROS
