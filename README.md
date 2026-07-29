# R-Bot Industrial · v1.0

HMI de operación para el laboratorio Occupancy (**Circuito**) + chat en lenguaje natural + teleop.

**Checkpoint / release:** `LabHmiStableV4` — primera versión pública  
(tema Sonar, Operator v3, Circuito Occupancy).

Autor: [Rony Luis Palacios](https://github.com/Rony-Luis-Theodore) · Universidad Nacional de Piura · IEEE Student Branch  
Powered by: UNP IEEE / IEEE RAS · **Kalman Robotics**

---

## Alcance de esta versión (léelo antes de operar)

### Laboratorio remoto (Kalman)

Para mover el robot **de verdad** hace falta una sesión del **laboratorio remoto de Kalman Robotics**:

1. Entra al lab con el **enlace / credenciales que te brindan** para la sesión.
2. Conéctate al robot que te asignen (Create3 / Nexus u otro según el slot).
3. En tu máquina: entorno ROS 2 acorde al lab + `ROS_PROVIDER=rclpy` en `.env`  
   (detalle: [`docs/lab-ros.md`](docs/lab-ros.md)).
4. Arranca la HMI → elige perfil **Nexus** (recomendado en v1) → **Ubicar**.

Sin esa conexión remota, la app sigue siendo útil en **modo mock** (interfaz + chat simulado, sin robot).

### Nexus vs R-Bot en v1

| | **Nexus** (v1 lista) | **R-Bot** (pendiente de mapa) |
|--|----------------------|------------------------------|
| Mapa Occupancy / RViz / Gazebo | Sí: trabajamos con el mapa del lab al alcance | Aún **no** teníamos el mapa equivalente para calzar LiDAR igual |
| Ubicar + circuito + chat métrico | **Soportado y validado** | Selector existe; **no está validado** al mismo nivel |
| Misma ciencia (pose LiDAR, odom, chat → motion) | Ya en el código | Se podrá **reutilizar** cuando el compañero aporte / integre el mapa de R-Bot |

**Conclusión v1:** esta release **opera correctamente con Nexus** en el lab Kalman.  
R-Bot queda listo a nivel de arquitectura HMI/API; falta el mapa y el calce fino (tarea del compañero). Cuando suban ese mapa, se aplica la **misma** tubería (Ubicar, escala odom, Operator, teleop).

### Qué sí puedes hacer (v1 · Nexus + lab)

- Ver el plano Occupancy del circuito y el tip LiDAR.
- **Ubicar** la pose una vez (mejor desde el **centro del circuito**).
- Órdenes de chat: avanzar / retroceder / girar (con metros, cm, pies, pulgadas y grados).
- Secuencias multi-paso con conectores (*primero… luego… por último…*).
- Parar (`detén` / `para`).
- Teleop básico (panel Conducir) y emergencia.
- Modo mock sin robot para ensayar la UI.

### Qué aún no (v1)

- Rutas / waypoints **predeterminados** → planeado para **v2**.
- Navegación a **zonas nombradas** (almacén, válvula, pasillo…) sin mapa semántico.
- Cámara en vivo en el rail (placeholder).
- Operación R-Bot al mismo nivel que Nexus (falta mapa Occupancy propio).
- El modelo GGUF `rbot-operator` (~1.8 GB) **no va en git**; Ollama es opcional (en mock el parser local basta).

### Próxima versión (v2 · orientación)

- **Rutas predeterminadas** (planes fijos / demos de recorrido).
- Integración R-Bot cuando exista el mapa del compañero.
- Mejoras de UX sobre el mismo Circuito.

---

## Cómo usar la interfaz

1. **Perfil robot** (arriba): en lab real elige **Nexus**. `Auto` detecta si puede; `Simulación` / mock para demo.
2. **Centro del circuito:** mueve el robot al centro **antes** de Ubicar — el LiDAR lee mejor y el calce suele salir a la primera.
3. **Ubicar en el mapa** (una vez): ancla la pose; el botón se oculta.  
   Si el tip no cuadra → **recarga la página**, vuelve al centro y Ubica otra vez.  
   *No hay botón «Reiniciar»*: el ancla se limpia con refresh del navegador.
4. **LiDAR** (dock): muestra/oculta el tip. **Limpiar trazo** borra el rastro dibujado.
5. **Chat:** texto o **Voz** → Enviar. Órdenes en español (ver ejemplos abajo).
6. **Rail izquierdo:** Mapa · Conducir (joystick/panel) · Cámara (próximamente).
7. **Chips de estado:** conexión, batería, modo, pose aproximada.

Ventana recomendada ≥ **1100×640**; por debajo puede haber scroll.

---

## Qué decirle al chat (ejemplos)

Funciona mejor con frases claras. Unidades y conectores están soportados.

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

**Útil saber**
- Si dices «gira 45 a la derecha» **sin** la palabra *grados*, igual se interpreta como grados.
- cm → m automáticamente; también pulgadas y pies.
- «para atrás» = retroceder (no es cancelar). «detén» / «para» solo = parada.
- Aún **no**: «ve al almacén», «ruta A», waypoints nombrados (eso va hacia v2 / mapa semántico).

---

## Inicio rápido (demo sin robot)

```bash
cd rbot-industrial/apps/api
cp .env.example .env          # LLM_PROVIDER=mock, ROS_PROVIDER=mock
python3 -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

O: `bash scripts/start-stack.sh` · Windows: `.\scripts\start-hmi.ps1`  
Abre **http://127.0.0.1:8000**

### Lab real (Nexus + Kalman)

1. Sesión remota Kalman (enlace del lab).
2. ROS 2 + dominio DDS según te indiquen.
3. `.env` con `ROS_PROVIDER=rclpy` (ver [`docs/lab-ros.md`](docs/lab-ros.md)).
4. Perfil **Nexus** en la HMI → centro → Ubicar → chat.

---

## Qué incluye el repo (runtime v1)

| Pieza | Ruta |
|-------|------|
| API FastAPI | `apps/api/` |
| HMI Occupancy (Sonar) | `apps/web/` |
| Mapa demo Occupancy | `packages/lab_map/maps/` |
| Trazos / perímetro circuito | `apps/api/app/services/lab_obstacle_traces/` |
| Chat mock / Ollama | `apps/api/app/adapters/llm/` |
| Dataset + Colab Operator v3 | `ml/` |
| Checkpoint lab | `packages/lab_map/snapshots/LabHmiStableV4/` |

**No va en git (pesado / local):** GGUF Ollama, workspace ROS (`packages/ros_ws`), `.env` real, tokens del lab.  
Con el repo + Python basta para **mock**. Para robot: sesión Kalman + ROS en tu máquina (no sustituible por el zip del repo).

---

## Opcional

- Ollama + `rbot-operator`: [`ml/COLAB_NOW.md`](ml/COLAB_NOW.md)
- Robot / Kalman / ROS 2: [`docs/lab-ros.md`](docs/lab-ros.md)
- Getting started: [`docs/getting-started.md`](docs/getting-started.md)

---

## Licencia / equipo

Proyecto universitario — equipo R-Bot.  
Stack: FastAPI · HMI web · Ollama (opcional) · ROS 2 Humble (opcional, lab Kalman).
