# Lab real (Linux + ROS 2) — opcional

Esta guía es para conectar la HMI al robot / sesión Kalman.
**No hace falta** para ver la interfaz en mock.

## Requisitos

- Ubuntu 22.04 + ROS 2 Humble (o imagen Kalman)
- Workspace tipo `upnrobot-ros` compilado (`install/setup.bash`)
- Dominio DDS / Husarnet según el lab

## Enlazar el workspace (fuera de git)

El symlink `packages/ros_ws` **no se sube** al repositorio. Ejemplo:

```bash
ln -s ~/Documents/Proyectos/_local/ros/upnrobot-ros-main \
  ~/Documents/Proyectos/rbot-industrial/packages/ros_ws
```

O sin symlink:

```bash
export ROS_WS_SETUP=~/Documents/Proyectos/_local/ros/upnrobot-ros-main/install/setup.bash
export ROS_MAP_DIR=~/Documents/Proyectos/_local/ros/upnrobot-ros-main/src/kalman_bringup/map
```

## `.env` lab

```env
LLM_PROVIDER=ollama
OLLAMA_MODEL=rbot-operator
ROS_PROVIDER=rclpy
ROBOT_PROFILE=auto
ROS_DOMAIN_ID=20
```

## Arranque

1. Sesión Kalman / `source` del entorno ROS del lab (según tu institución).
2. `bash scripts/start-stack.sh`
3. Abre http://127.0.0.1:8000 → **Ubicar en el mapa**

Scripts Gazebo/Nav2 opcionales pueden vivir en tu máquina bajo `_local/scripts-ros/`
(no forman parte del camino v1 público).

## Seguridad

- No commits de tokens Kalman ni `.env` reales.
- Parada de emergencia en la HMI (`cmd_vel = 0`).
