# Getting started

## Requisitos

- Python **3.10+**
- Navegador moderno
- (Opcional) [Ollama](https://ollama.com) para LLM local
- (Opcional, solo Linux lab) ROS 2 Humble + robot/Kalman — ver [lab-ros.md](lab-ros.md)

## Demo mock (recomendado)

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

Con `LLM_PROVIDER=mock` el chat entiende órdenes tipo *avanza 30 cm*, *gira 90 izquierda*,
secuencias y parada, sobre un robot simulado en memoria.

El mapa Occupancy `laboratorio_kalman` viene en `packages/lab_map/maps/`.

### Scripts

| SO | Comando |
|----|---------|
| Linux / macOS | `bash scripts/start-stack.sh` |
| Windows | `.\scripts\start-hmi.ps1` |

## Ollama (sin robot)

1. Instala Ollama y asegúrate de que responde en `http://127.0.0.1:11434`.
2. En `apps/api/.env`:

```env
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5:1.5b
ROS_PROVIDER=mock
```

3. `ollama pull qwen2.5:1.5b` y reinicia la API.

### Modelo `rbot-operator` (fine-tune)

Si tienes el GGUF local (no va en git; ~1.8 GB):

```bash
# Ajusta FROM en ml/export/Modelfile.rbot-operator a la ruta del .gguf
ollama create rbot-operator -f ml/export/Modelfile.rbot-operator
```

```env
OLLAMA_MODEL=rbot-operator
```

## Ubicar en el mapa

En modo mock la pose es simulada. En lab real: mira un muro y pulsa **Ubicar en el mapa**
(checkpoint `LabHmiStableV1`). Detalle ROS: [lab-ros.md](lab-ros.md).
