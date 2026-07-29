#!/bin/bash
# =============================================================================
# Arranque HMI R-Bot Industrial (API + web)
# Por defecto: modo mock (sin ROS ni Ollama obligatorios).
# =============================================================================
set -eo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$HOME/.local/bin:$PATH"
API_DIR="$ROOT/apps/api"

# Mock por defecto si no hay .env
if [ ! -f "$API_DIR/.env" ]; then
  cp "$API_DIR/.env.example" "$API_DIR/.env"
  echo "→ Creado apps/api/.env desde .env.example (mock)"
fi

# Cargar .env de forma segura (solo KEY=VALUE simples)
set -a
# shellcheck disable=SC1091
source "$API_DIR/.env" 2>/dev/null || true
set +a

LLM_PROVIDER="${LLM_PROVIDER:-mock}"
ROS_PROVIDER="${ROS_PROVIDER:-mock}"
MODEL="${OLLAMA_MODEL:-qwen2.5:1.5b}"

echo "→ Root: $ROOT"
echo "→ LLM_PROVIDER=$LLM_PROVIDER  ROS_PROVIDER=$ROS_PROVIDER"

# ROS/Kalman solo si pediste rclpy
if [ "$ROS_PROVIDER" = "rclpy" ]; then
  export ROS_HOME="${ROS_HOME:-$HOME/Documents/Proyectos/.ros_home}"
  mkdir -p "$ROS_HOME/log"
  set +e
  if [ -f /var/lib/kalman/env.bash ]; then
    # shellcheck disable=SC1091
    source /var/lib/kalman/env.bash >/dev/null 2>&1
  fi
  # shellcheck disable=SC1091
  source /opt/ros/humble/setup.bash >/dev/null 2>&1
  if [ -n "${ROS_WS_SETUP:-}" ] && [ -f "$ROS_WS_SETUP" ]; then
    # shellcheck disable=SC1091
    source "$ROS_WS_SETUP" >/dev/null 2>&1
  elif [ -f "$ROOT/packages/ros_ws/install/setup.bash" ]; then
    # shellcheck disable=SC1091
    source "$ROOT/packages/ros_ws/install/setup.bash" >/dev/null 2>&1
  fi
  set -e
  if [ -f /var/lib/kalman/env.bash ] && command -v ros2 >/dev/null; then
    echo "→ Reiniciando ros2 daemon"
    ros2 daemon stop >/dev/null 2>&1 || true
    sleep 0.5
    ros2 daemon start >/dev/null 2>&1 || true
  fi
fi

# Ollama solo si LLM_PROVIDER=ollama
if [ "$LLM_PROVIDER" = "ollama" ]; then
  if command -v ollama >/dev/null; then
    if ! curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
      echo "→ ollama serve"
      nohup ollama serve > /tmp/ollama-serve.log 2>&1 &
      for _ in $(seq 1 30); do
        curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break
        sleep 1
      done
    fi
    if ! ollama list 2>/dev/null | grep -q "$MODEL"; then
      echo "→ ollama pull $MODEL (o crea rbot-operator con Modelfile)"
      ollama pull "$MODEL" || true
    fi
  else
    echo "⚠ ollama no encontrado — la API caerá a MockLLM"
  fi
fi

if [ -f /tmp/rbot-api.pid ] && kill -0 "$(cat /tmp/rbot-api.pid)" 2>/dev/null; then
  kill "$(cat /tmp/rbot-api.pid)" 2>/dev/null || true
  sleep 1
fi
if command -v pgrep >/dev/null; then
  while read -r p; do
    [ -n "$p" ] || continue
    kill "$p" 2>/dev/null || true
  done < <(pgrep -f '^python3 -m uvicorn app.main:app' || true)
fi
sleep 1

echo "→ API + HMI en :8000"
cd "$API_DIR"
# Preferir venv local si existe
if [ -x "$API_DIR/.venv/bin/python" ]; then
  PY="$API_DIR/.venv/bin/python"
else
  PY=python3
fi
nohup "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/rbot-api.log 2>&1 &
echo $! > /tmp/rbot-api.pid
sleep 2
curl -s http://127.0.0.1:8000/api/v1/health || true
echo
echo "UI:   http://127.0.0.1:8000"
echo "Docs: http://127.0.0.1:8000/docs"
echo "Logs: /tmp/rbot-api.log"
