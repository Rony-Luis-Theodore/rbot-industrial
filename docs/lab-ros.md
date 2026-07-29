# Lab real (Linux + ROS 2) — Kalman Robotics

Para **mover el robot** necesitas la sesión del **laboratorio remoto de Kalman Robotics**
(el enlace / acceso que te den para tu turno). Sin eso, usa la HMI en mock.

**v1 validada con Nexus.** R-Bot comparte la misma HMI/API, pero el mapa Occupancy
fino de R-Bot aún lo integra el compañero; hasta entonces elige perfil **Nexus**.

## Requisitos

- Acceso a la sesión remota Kalman (enlace del robot / lab)
- Ubuntu 22.04 + ROS 2 Humble (o imagen/entorno que indique Kalman)
- Workspace tipo `upnrobot-ros` compilado (`install/setup.bash`)
- Dominio DDS / red del lab según te indiquen

## Enlazar el workspace (fuera de git)

El symlink `packages/ros_ws` **no se sube** al repositorio. Ejemplo:

```bash
ln -s ~/Documents/Proyectos/_local/ros/upnrobot-ros-main \
  ~/Documents/Proyectos/rbot-industrial/packages/ros_ws
```

O sin symlink:

```bash
export ROS_WS_SETUP=~/ruta/a/upnrobot-ros/install/setup.bash
export ROS_MAP_DIR=~/ruta/a/upnrobot-ros/src/kalman_bringup/map
```

## `.env` lab

```env
LLM_PROVIDER=ollama          # o mock si solo pruebas teleop/parseo
OLLAMA_MODEL=rbot-operator   # opcional
ROS_PROVIDER=rclpy
ROBOT_PROFILE=nexus          # v1: preferir Nexus
ROS_DOMAIN_ID=20             # el que te indiquen en la sesión
```

## Arranque

1. Conéctate a la sesión Kalman (enlace del lab).
2. `source` del entorno ROS / workspace.
3. `bash scripts/start-stack.sh`
4. Abre http://127.0.0.1:8000
5. Perfil **Nexus** → lleva el robot al **centro del circuito** → **Ubicar en el mapa** → chat.

## Seguridad

- No commits de tokens Kalman ni `.env` reales.
- Parada de emergencia en la HMI (`cmd_vel = 0`).
