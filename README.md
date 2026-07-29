# R-Bot Industrial · v1.0

HMI de operación para el robot **R-Bot** (lab Occupancy + chat NL + teleop).

**Checkpoint / release:** `LabHmiStableV4` — primera versión pública del programa
(tema Sonar, Operator v3, Circuito Occupancy).

Autor: [Rony Luis Palacios](https://github.com/Rony-Luis-Theodore) · Universidad Nacional de Piura · IEEE Student Branch  
Powered by: UNP IEEE / IEEE RAS · Kalman Robotics

La **v1 pública** puede correr en **modo mock**: clonas el repo, arrancas la API y ves la interfaz
**sin ROS, sin robot y sin GPU**.

---

## Inicio rápido (Linux / macOS)

```bash
cd rbot-industrial/apps/api
cp .env.example .env          # LLM_PROVIDER=mock, ROS_PROVIDER=mock
python3 -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

O con el script del monorepo:

```bash
bash scripts/start-stack.sh
```

Abre **http://127.0.0.1:8000**

## Inicio rápido (Windows)

```powershell
cd rbot-industrial
.\scripts\start-hmi.ps1
```

---

## Qué incluye (v1)

| Pieza | Ruta |
|-------|------|
| API FastAPI | `apps/api/` |
| HMI Occupancy (Sonar) | `apps/web/` |
| Lab map / SE2 | `packages/lab_map/` (+ mapa demo) |
| Chat mock / Ollama | `apps/api/app/adapters/llm/` |
| Dataset + Colab Operator v3 | `ml/` |
| Checkpoint lab | `packages/lab_map/snapshots/LabHmiStableV4/` |

### Destacado v1
- Ubicar 1× (recomendado: centro del circuito) · reanclar = refresh
- Escala odom afinada · flecha con snap de visualización
- Chat: secuencias, conectores, m/cm/pulgadas/pies, ángulos implícitos
- Layout fijo mapa \| chat con adaptación hasta 1100×640

---

## Opcional

- **Ollama** + modelo `rbot-operator` (GGUF fuera del git): [`ml/COLAB_NOW.md`](ml/COLAB_NOW.md)
- **Robot / Kalman / ROS 2** (Linux): [`docs/lab-ros.md`](docs/lab-ros.md)
- Getting started: [`docs/getting-started.md`](docs/getting-started.md)

---

## Estructura

```text
rbot-industrial/
├── apps/api/          # FastAPI
├── apps/web/          # HMI Sonar
├── packages/lab_map/  # Occupancy + mapas + snapshots
├── ml/                # notebooks, datasets jsonl, Modelfiles
├── docs/
├── scripts/           # start-stack.sh, start-hmi.ps1
└── README.md
```

Artefactos locales pesados (GGUF ≈1.8 GB, workspace ROS, zips) **no van en git**
(viven p. ej. en `Documents/Proyectos/_local/` o `ml/export/*.gguf` ignorado).

---

## Publicar en GitHub

Perfil: [github.com/Rony-Luis-Theodore](https://github.com/Rony-Luis-Theodore)

```bash
# 1) Autenticación (una vez)
gh auth login          # o SSH: ssh -T git@github.com

# 2) Crear repo vacío en GitHub (vía web o):
gh repo create rbot-industrial --public --source=. --remote=origin --push

# Alternativa manual:
git remote add origin https://github.com/Rony-Luis-Theodore/rbot-industrial.git
git push -u origin main
```

En **Cursor**: Settings → Account / Integrations → conectar GitHub (PRs, Copilot).  
Para `git push` hace falta la misma cuenta autenticada en la terminal (`gh` o SSH).

---

## Licencia / equipo

Proyecto universitario — equipo R-Bot.  
Stack: FastAPI · HMI web · Ollama (opcional) · ROS 2 Humble (opcional, lab).
