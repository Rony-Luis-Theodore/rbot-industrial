# packages/

## lab_map
Código Occupancy / SE2 / overlays del lab. Incluye mapas vendored en `lab_map/maps/` para demo sin ROS.

## ros_ws (opcional, no en git)
Para lab real o Gazebo, enlaza tu workspace ROS 2:

```bash
# Ejemplo (Linux)
ln -s ~/Documents/Proyectos/_local/ros/upnrobot-ros-main \
  packages/ros_ws
```

O exporta:
```bash
export ROS_WS_SETUP=~/Documents/Proyectos/_local/ros/upnrobot-ros-main/install/setup.bash
export ROS_MAP_DIR=~/Documents/Proyectos/_local/ros/upnrobot-ros-main/src/kalman_bringup/map
```
