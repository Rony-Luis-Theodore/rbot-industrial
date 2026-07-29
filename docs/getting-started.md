# Getting started — Sonar v1.0

## Requisitos

- Python **3.10+**
- Navegador moderno
- (Opcional) [Ollama](https://ollama.com)
- (Lab real) Sesión **Kalman Robotics** + **Linux + ROS 2** — [lab-ros.md](lab-ros.md)

**v1.0:** validado con **Nexus**. Se espera el mapa de R-Bot para poder continuar al mismo nivel.  
Visión y alcance: [README](../README.md).

## Demo mock (cualquier SO)

```bash
cd apps/api
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- UI: http://127.0.0.1:8000  
- API docs: http://127.0.0.1:8000/docs  

```text
avanza 50 cm
gira 90 a la derecha
avanza 0.8 metros, gira 90 grados a la derecha, avanza 0.5 metros
detén
```

Mapa demo: `packages/lab_map/maps/laboratorio_kalman`.

| SO | Comando |
|----|---------|
| Linux / macOS | `bash scripts/start-stack.sh` |
| Windows | `.\scripts\start-hmi.ps1` |

## Lab real → Linux + ROS

El robot del laboratorio **requiere ROS 2 en Linux**. Guía: [lab-ros.md](lab-ros.md).

## Ollama (Operator v3 desde Release)

1. Instala Ollama (`http://127.0.0.1:11434`).
2. Descarga el GGUF: https://github.com/Rony-Luis-Theodore/rbot-industrial/releases/tag/v1.0.0  
   → `ml/export/rbot-operator-q4_k_m.gguf`
3. `cd ml/export && ollama create rbot-operator -f Modelfile.rbot-operator`
4. En `apps/api/.env`:

```env
LLM_PROVIDER=ollama
OLLAMA_MODEL=rbot-operator
ROS_PROVIDER=mock
```

5. Reinicia la API.

Sin GGUF: `ollama pull qwen2.5:1.5b` y `OLLAMA_MODEL=qwen2.5:1.5b`.  
Detalle: [ml/export/README.md](../ml/export/README.md).

## Ubicar

Mock: pose simulada.  
Lab (Nexus): **centro del circuito** → **Ubicar** una vez → si no cuadra, **recarga** y repite.

Checkpoint: `LabHmiStableV4` · release **Sonar v1.0**.
