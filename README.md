# Sonar · v1.0

**Consola remota de operación** para robots de robótica autónoma y monitoreo  
(Occupancy + chat en lenguaje natural + teleop).

Empezó orientado a **R-Bot**; hoy opera también **Nexus** (y el mismo diseño sirve para más perfiles).  
El enfoque **industrial** es el rubro donde encaja primero: planta, zonas y vigilancia remota.

**Release oficial:** v1.0 · checkpoint `LabHmiStableV4`  
Autor: [Rony Luis Palacios](https://github.com/Rony-Luis-Theodore) · UNP · IEEE Student Branch  
Powered by: UNP IEEE / IEEE RAS · **Kalman Robotics**

---

## Qué es Sonar (visión)

Sonar permite que **un operario, desde cualquier lugar**, controle robots pensados para
autonomía y monitoreo sobre un **mapa Occupancy** de la zona que le interesa.

- En el laboratorio universitario, el “sitio” es el **lab remoto de Kalman** y el mapa es el del circuito.
- Si se lleva a una empresa, el laboratorio remoto se convierte en **las instalaciones**,
  el mapa pasa a ser el **de la planta (o de un área)**, y el operario puede trabajar
  desde la oficina u otro sitio del mundo.
- Por eso la HMI admite **elegir mapas**: cada uno corresponde a la zona que se quiere monitorear
  o recorrer (planta completa, área particular, etc.).
- Sobre ese mapa se dan tareas: desplazamientos, giros, secuencias y, más adelante,
  destinos / puntos de vista / rutas fijas.

En resumen: **misma ciencia** (pose LiDAR, odometría, chat → movimiento), distinto “lugar”
según el mapa y el robot conectado.

---

## Alcance de la v1.0 (oficial)

### Laboratorio remoto (Kalman)

Para mover el robot **de verdad**:

1. Entra al lab con el **enlace / acceso** que te brindan para la sesión.
2. Conéctate al robot asignado (p. ej. Nexus).
3. En **Linux**, ten **ROS 2** listo (ver abajo) y `ROS_PROVIDER=rclpy` en `.env`.
4. Arranca Sonar → perfil **Nexus** → **Ubicar**.

Sin sesión remota, el modo **mock** sirve para ensayar la interfaz y el chat (sin robot).

### Linux + ROS 2 (obligatorio para el lab)

El navegador solo es la consola. La **conexión al robot del laboratorio** pasa por ROS 2
en una máquina **Linux** (recomendado: **Ubuntu 22.04 + ROS 2 Humble**).

Resumen (detalle completo: [`docs/lab-ros.md`](docs/lab-ros.md)):

1. Instala / usa el entorno ROS 2 Humble del lab (o la imagen que indique Kalman).
2. Compila o enlaza el workspace ROS (`install/setup.bash`).
3. Configura `ROS_DOMAIN_ID` (y red/DDS) **como te indiquen en la sesión**.
4. En `apps/api/.env`:

```env
ROS_PROVIDER=rclpy
ROBOT_PROFILE=nexus
ROS_DOMAIN_ID=20
```

5. En una terminal con el entorno ROS cargado (`source …/setup.bash`):

```bash
bash scripts/start-stack.sh
```

6. Abre http://127.0.0.1:8000 → perfil **Nexus** → centro del circuito → **Ubicar**.

> **Windows / macOS:** puedes ver la HMI en **mock**. Para el robot real del lab Kalman
> hace falta el puente ROS en **Linux**.

### Robots en v1

| | **Nexus** | **R-Bot** |
|--|-----------|-----------|
| Estado v1 | **Validado** (mapa Occupancy / RViz / Gazebo al alcance) | Selector listo; **se espera el mapa de R-Bot para poder continuar** al mismo nivel |
| Ubicar + chat métrico | Sí | Misma tubería cuando exista el mapa |

### Qué sí puedes hacer

- Plano Occupancy + tip LiDAR.
- **Ubicar** una vez (mejor desde el **centro del circuito**).
- Chat: avanzar / retroceder / girar (m, cm, pies, pulgadas, grados) y secuencias.
- Parar, teleop básico y emergencia.
- Demo mock sin robot.

### Qué aún no

- Rutas / waypoints **predeterminados** → **v2**.
- Zonas nombradas (“ve al almacén”) sin mapa semántico.
- Cámara en vivo (placeholder).
- R-Bot al mismo nivel que Nexus hasta tener su mapa.
- GGUF `rbot-operator` fuera de git (Ollama opcional).

### Hacia v2

- Rutas predeterminadas.
- Mapa de R-Bot + más zonas / destinos sobre el selector de mapas.

---

## Cómo usar la interfaz

1. **Perfil robot:** en lab real → **Nexus**.
2. **Centro del circuito** antes de Ubicar (mejor LiDAR).
3. **Ubicar en el mapa** una vez; si no cuadra → **recarga la página** y Ubica otra vez.
4. **LiDAR** / **Limpiar trazo** en el dock.
5. **Chat** (texto o voz) — ejemplos abajo.
6. Rail: Mapa · Conducir · Cámara (próximamente).

Ventana recomendada ≥ **1100×640**.

---

## Qué decirle al chat (ejemplos)

**Un paso**
```text
avanza 50 cm
avanza 0.8 metros
retrocede 30 cm
gira 90 a la derecha
gira 45 grados a la izquierda
detén
```

**Secuencias**
```text
avanza 0.8 metros, gira 90 grados a la derecha, avanza 0.5 metros
en primer lugar avanza 80 cm después gira 90 a la derecha por último avanza 50 cm
avanza 2 pies luego gira 90 a la izquierda finalmente avanza 12 pulgadas
primero avanza 40 cm, luego gira 90 a la izquierda, a continuación avanza 1 metro
```

- «gira 45 a la derecha» vale aunque no diga *grados*.
- «para atrás» = retroceder; «detén» / «para» = parada.
- Aún no: destinos por nombre de zona / “ruta A”.

---

## Inicio rápido (demo sin robot)

```bash
cd rbot-industrial/apps/api
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

O: `bash scripts/start-stack.sh` · Windows: `.\scripts\start-hmi.ps1`  
→ **http://127.0.0.1:8000**

Lab real: sección **Linux + ROS 2** arriba + [`docs/lab-ros.md`](docs/lab-ros.md).

---

## Chat con Ollama (Operator v3)

Por defecto el repo arranca en **`mock`**: el *motion guard* cubre avance/giro/secuencias
sin instalar nada. Para el modelo fine-tune **Operator v3**:

1. Instala [Ollama](https://ollama.com) y déjalo corriendo.
2. Descarga el GGUF desde la Release (~1.8 GB):  
   https://github.com/Rony-Luis-Theodore/rbot-industrial/releases/tag/v1.0.0
3. Crea el modelo e activa el proveedor:

```bash
cd rbot-industrial/ml/export
# coloca aquí rbot-operator-q4_k_m.gguf (o: gh release download …)
ollama create rbot-operator -f Modelfile.rbot-operator
```

```env
# apps/api/.env
LLM_PROVIDER=ollama
OLLAMA_MODEL=rbot-operator
OLLAMA_BASE_URL=http://127.0.0.1:11434
```

Detalle: [`ml/export/README.md`](ml/export/README.md).

---

## Repo (runtime v1.0)

| Pieza | Ruta |
|-------|------|
| API FastAPI | `apps/api/` |
| HMI Occupancy | `apps/web/` |
| Mapas Occupancy | `packages/lab_map/maps/` |
| Trazos / perímetro | `apps/api/app/services/lab_obstacle_traces/` |
| Chat mock / Ollama | `apps/api/app/adapters/llm/` |
| Dataset + Colab | `ml/` |
| Checkpoint | `packages/lab_map/snapshots/LabHmiStableV4/` |

Fuera de git: GGUF (ver **Releases**), workspace ROS, `.env` real, tokens del lab.  
Carpeta técnica del monorepo: `rbot-industrial` · producto: **Sonar**.

**Release v1.0.0 (GGUF):** https://github.com/Rony-Luis-Theodore/rbot-industrial/releases/tag/v1.0.0

---

## Docs

- Lab Linux / ROS / Kalman: [`docs/lab-ros.md`](docs/lab-ros.md)
- Getting started: [`docs/getting-started.md`](docs/getting-started.md)
- Ollama / Operator: [`ml/COLAB_NOW.md`](ml/COLAB_NOW.md)

---

## Licencia

Proyecto universitario — línea R-Bot / Sonar.  
Stack: FastAPI · HMI web · Ollama (opcional) · ROS 2 Humble (lab, Linux).
