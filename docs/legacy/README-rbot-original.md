# R-Bot Intelligent Control

Sistema de control inteligente para el robot autónomo **R-Bot**. Permite a operarios sin conocimientos de ROS2 controlar el robot mediante **lenguaje natural**, traducido automáticamente a acciones ROS2 por una capa LLM.

> Proyecto universitario — Laboratorio remoto 24/7

---

## Descripción

R-Bot permanece conectado en un laboratorio remoto. Los integrantes del proyecto se conectan vía SSH/WiFi a una computadora Ubuntu con ROS2. Esta plataforma web agrega una capa de Inteligencia Artificial para que cualquier operario pueda:

- Consultar el estado del robot
- Listar topics, nodos, servicios y actions
- Enviar objetivos de navegación ("Ve a la estación A")
- Cancelar navegación o regresar a base

**El operario nunca escribe comandos ROS2.**

---

## Dos arquitecturas en paralelo

El repo incluye **dos implementaciones** (ninguna elimina a la otra) para comparar:

| Versión | Carpeta | Puerto | Enfoque |
|---------|---------|--------|---------|
| **A — Hexagonal** (oficial) | `backend/` + `frontend/` | **8000** | Capas, interfaces LLM/ROS, escalable |
| **B — Estilo chatbot UCV** | `rbot-ucv-style/` | **8001** | Monolítica como el proyecto del compañero |
| Referencia original | `CHATBOT_UCV-master/` | — | Chatbot RAG UCV (no modificar) |

Comparación detallada: [docs/comparison-hexagonal-vs-ucv.md](docs/comparison-hexagonal-vs-ucv.md)

### Versión A — Hexagonal

```
Frontend (HTML/CSS/JS)  →  FastAPI REST API  →  ChatOrchestrator
                                                      ↓
                                              LLMService + ROSService
                                                      ↓
                                              Adapters (Mock / Real)
```

Documentación: [docs/architecture.md](docs/architecture.md)

### Versión B — Estilo UCV (rápida)

```bash
cd rbot-ucv-style
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python app.py
# → http://127.0.0.1:8001
```

---

## Estructura de carpetas

```
r-bot/
├── backend/
│   ├── app/
│   │   ├── main.py              # Entry point FastAPI
│   │   ├── api/                 # Capa HTTP (routers, deps)
│   │   ├── core/                # Config, constantes, excepciones
│   │   ├── domain/              # Entidades + interfaces (contratos)
│   │   ├── schemas/             # DTOs Pydantic (HTTP)
│   │   ├── services/            # Lógica de aplicación (orquestador)
│   │   ├── adapters/            # Implementaciones LLM y ROS
│   │   ├── factories/           # Factory de servicios
│   │   └── utils/               # Helpers
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── index.html
│   ├── css/                     # Estilos modulares
│   ├── js/                      # ES Modules por componente
│   └── assets/
├── rbot-ucv-style/              # Versión B: monolítica estilo chatbot UCV
│   ├── app.py
│   ├── chat.py
│   ├── profile.json
│   └── static/index.html
├── CHATBOT_UCV-master/          # Código original del compañero (referencia)
├── docs/
│   ├── architecture.md
│   ├── comparison-hexagonal-vs-ucv.md
│   ├── llm-integration.md       # Guía para integrante LLM
│   └── ros-integration.md       # Guía para integrante ROS2
└── README.md
```

---

## Tecnologías

| Componente | Tecnología |
|------------|------------|
| Backend | Python 3.10+, FastAPI, Pydantic, Uvicorn |
| Frontend | HTML5, CSS3, JavaScript (ES Modules) |
| LLM | Interfaz abstracta — Mock activo (OpenAI/Ollama/Gemini preparados) |
| ROS2 | Interfaz abstracta — Mock activo (rclpy preparado) |

---

## Instalación

### Requisitos

- Python 3.10 o superior
- pip

### Pasos

```bash
# 1. Clonar / entrar al proyecto
cd "Proyecto R-bot"

# 2. Crear entorno virtual
cd backend
python3 -m venv venv
source venv/bin/activate        # Linux/macOS
# venv\Scripts\activate         # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
cp .env.example .env
```

---

## Ejecución

```bash
# Desde backend/ con el venv activado
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Abrir en el navegador:

| URL | Descripción |
|-----|-------------|
| http://localhost:8000 | Interfaz web |
| http://localhost:8000/docs | Swagger API |
| http://localhost:8000/api/v1/health | Health check |

---

## API REST

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/api/v1/chat` | Enviar instrucción en lenguaje natural |
| GET | `/api/v1/robot/status` | Estado del robot |
| GET | `/api/v1/robot/topics` | Topics ROS2 |
| GET | `/api/v1/robot/nodes` | Nodos ROS2 |
| GET | `/api/v1/robot/services` | Servicios ROS2 |
| GET | `/api/v1/robot/actions` | Actions ROS2 |
| GET | `/api/v1/robot/events` | Registro de eventos |
| GET | `/api/v1/health` | Health check |

### Ejemplo

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Muéstrame los topics"}'
```

---

## Conectar un LLM real

1. Leer [docs/llm-integration.md](docs/llm-integration.md)
2. Implementar `LLMService` en `adapters/llm/`
3. Registrar en `factories/service_factory.py`
4. Configurar `LLM_PROVIDER` en `.env`

**No modificar** routers ni `ChatOrchestrator`.

---

## Conectar ROS2 real

1. Leer [docs/ros-integration.md](docs/ros-integration.md)
2. Implementar `RclpyROSService` en `adapters/ros/rclpy_ros.py`
3. Configurar `ROS_PROVIDER=rclpy` en `.env`

**No modificar** routers ni `ChatOrchestrator`.

---

## Buenas prácticas del equipo

### División de responsabilidades

| Integrante | Trabaja en | NO toca |
|------------|-----------|---------|
| Infraestructura web | `frontend/`, `api/`, `services/` | `adapters/llm/` |
| LLM | `adapters/llm/`, `domain/interfaces/` | `api/`, frontend |
| ROS2 | `adapters/ros/`, `domain/interfaces/` | `api/`, frontend |

### Convenciones

- **Comentarios**: cada archivo documenta propósito, función y conexiones
- **Interfaces**: todo adapter implementa su contrato en `domain/interfaces/`
- **Configuración**: providers se cambian en `.env`, no en código
- **Commits**: mensajes claros por módulo (`feat(llm): ...`, `feat(ros): ...`)

### Escalabilidad preparada

- WebSockets → `api/v1/ws.py`
- Voz → `adapters/voice/`
- Autenticación → `api/deps.py` + middleware
- Base de datos → `adapters/repositories/`
- Multi-robot → `robot_id` en modelos

---

## Licencia

Proyecto académico — uso educativo.
