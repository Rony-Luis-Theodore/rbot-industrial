# Lab real — Linux + ROS 2 + Kalman Robotics

Para **mover el robot** hace falta:

1. Sesión del **laboratorio remoto de Kalman** (enlace / acceso de tu turno).
2. Máquina **Linux** con **ROS 2** (puente hacia el robot).
3. Sonar con `ROS_PROVIDER=rclpy`.

Sin eso, usa la HMI en **mock** (cualquier SO).

**v1.0:** operación validada con **Nexus**.  
Se espera el mapa de R-Bot para poder continuar al mismo nivel; hasta entonces usa perfil **Nexus**.

---

## Por qué Linux

La HMI (navegador) no habla sola con el robot del lab.  
**ROS 2 (rclpy)** en Linux publica/suscribe `cmd_vel`, odom, LiDAR, etc. sobre el dominio DDS
de la sesión Kalman. En Windows/macOS puedes demos mock; el lab real → **Linux**.

Recomendado: **Ubuntu 22.04 LTS + ROS 2 Humble**.

---

## Requisitos

- Acceso a la sesión remota Kalman
- Ubuntu 22.04 + ROS 2 Humble (o imagen/entorno que indique Kalman)
- Workspace tipo `upnrobot-ros` con `install/setup.bash`
- `ROS_DOMAIN_ID` / red DDS según la sesión

### Comprobar ROS (ejemplo)

```bash
source /opt/ros/humble/setup.bash
# y el workspace del lab, p. ej.:
# source ~/ruta/upnrobot-ros/install/setup.bash
echo "ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0}"
ros2 topic list    # debería listar tópicos si ya hay sesión/robot
```

---

## Enlazar el workspace (fuera de git)

`packages/ros_ws` **no se sube** al repo.

```bash
ln -s ~/Documents/Proyectos/_local/ros/upnrobot-ros-main \
  ~/Documents/Proyectos/rbot-industrial/packages/ros_ws
```

O variables:

```bash
export ROS_WS_SETUP=~/ruta/a/upnrobot-ros/install/setup.bash
export ROS_MAP_DIR=~/ruta/a/upnrobot-ros/src/kalman_bringup/map
```

---

## `.env` lab (Sonar)

```env
APP_NAME=Sonar
APP_VERSION=1.0.0
LLM_PROVIDER=ollama          # o mock
OLLAMA_MODEL=rbot-operator   # opcional
ROS_PROVIDER=rclpy
ROBOT_PROFILE=nexus
ROS_DOMAIN_ID=20             # el de tu sesión
```

---

## Arranque paso a paso

1. Abre el **enlace del lab** Kalman y asegúrate de que el robot está en tu sesión.
2. Terminal Linux: `source` de ROS Humble + workspace.
3. `cd` al monorepo y arranca:

```bash
bash scripts/start-stack.sh
```

4. Navegador: http://127.0.0.1:8000  
5. Perfil **Nexus** → robot al **centro del circuito** → **Ubicar en el mapa** → chat.

Si no hay tópicos / no conecta: revisa `ROS_DOMAIN_ID`, red del lab y que el workspace esté *sourced* en la **misma** terminal que lanza la API.

---

## Seguridad

- No subas tokens Kalman ni `.env` reales.
- Usa la parada de emergencia de la HMI (`cmd_vel = 0`).
