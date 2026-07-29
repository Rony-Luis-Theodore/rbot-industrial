"""
=============================================================================
R-Bot — Adapter ROS: Mock (implementación simulada)
=============================================================================

Propósito:
    Implementación simulada de ROSService con datos ficticios realistas.
    Permite desarrollar y probar frontend/backend sin ROS2 instalado.

Qué hace:
    - Retorna topics, nodes, services y actions simulados típicos de Nav2.
    - Simula estado del robot (batería, posición, modo).
    - Simula navegación con cambios de estado en memoria.

Conexión con el resto:
    - Implementa domain/interfaces/ros_service.py.
    - Instanciado cuando ROS_PROVIDER=mock.
    - Reemplazado por RclpyROSService cuando se conecte ROS2 real.

Para el integrante de ROS2:
    Los datos simulados aquí son referencia de la estructura esperada.
    RclpyROSService debe retornar los mismos tipos de domain/models.
=============================================================================
"""

from datetime import datetime
from typing import Any, Dict, Optional
import math

from app.core.constants import (
    CONNECTION_CONNECTED,
    ROBOT_MODE_IDLE,
    ROBOT_MODE_MANUAL,
    ROBOT_MODE_NAVIGATING,
)
from app.domain.interfaces.ros_service import ROSService
from app.domain.models.robot import RobotPosition, RobotStatus, ROSResourceList


class MockROSService(ROSService):
    """
    Servicio ROS2 simulado con datos de navegación autónoma típicos.
    """

    # Datos simulados de introspección ROS2 (Nav2 + sensores comunes)
    _MOCK_TOPICS = [
        "/scan",
        "/map",
        "/odom",
        "/cmd_vel",
        "/goal_pose",
        "/amcl_pose",
        "/tf",
        "/tf_static",
        "/plan",
        "/local_costmap/costmap",
        "/global_costmap/costmap",
        "/battery_state",
    ]

    _MOCK_NODES = [
        "/robot_state_publisher",
        "/laser_scan_matcher",
        "/amcl",
        "/controller_server",
        "/planner_server",
        "/behavior_server",
        "/bt_navigator",
        "/waypoint_follower",
        "/velocity_smoother",
        "/rbot_web_bridge",
    ]

    _MOCK_SERVICES = [
        "/global_costmap/clear_entirely_global_costmap",
        "/local_costmap/clear_entirely_local_costmap",
        "/controller_server/set_parameters",
        "/planner_server/set_parameters",
        "/amcl/set_initial_pose",
    ]

    _MOCK_ACTIONS = [
        "/navigate_to_pose",
        "/follow_waypoints",
        "/compute_path_to_pose",
        "/spin",
        "/backup",
        "/wait",
    ]

    def __init__(self):
        """Inicializa estado simulado del robot en memoria."""
        self._mode = ROBOT_MODE_IDLE
        self._is_navigating = False
        self._current_goal: Optional[str] = None
        self._battery = 87.5
        self._position = RobotPosition(x=2.35, y=-1.12, theta=0.78)

    async def get_status(self) -> RobotStatus:
        """Retorna estado simulado del robot."""
        return RobotStatus(
            connection=CONNECTION_CONNECTED,
            battery_percent=self._battery,
            mode=self._mode,
            position=self._position,
            is_navigating=self._is_navigating,
            current_goal=self._current_goal,
            last_updated=datetime.utcnow(),
        )

    async def get_topics(self) -> ROSResourceList:
        """Simula: ros2 topic list"""
        return ROSResourceList(resource_type="topics", items=self._MOCK_TOPICS.copy())

    async def get_nodes(self) -> ROSResourceList:
        """Simula: ros2 node list"""
        return ROSResourceList(resource_type="nodes", items=self._MOCK_NODES.copy())

    async def get_services(self) -> ROSResourceList:
        """Simula: ros2 service list"""
        return ROSResourceList(resource_type="services", items=self._MOCK_SERVICES.copy())

    async def get_actions(self) -> ROSResourceList:
        """Simula: ros2 action list"""
        return ROSResourceList(resource_type="actions", items=self._MOCK_ACTIONS.copy())

    async def send_navigation_goal(self, destination: str) -> Dict[str, Any]:
        """
        Simula envío de objetivo de navegación / giro.

        Actualiza estado interno a 'navigating' (o ajusta theta en giros).
        """
        dest = (destination or "").strip().lower()
        self._mode = ROBOT_MODE_NAVIGATING
        self._is_navigating = True
        self._current_goal = destination
        self._battery = max(0, self._battery - 0.5)

        if any(k in dest for k in ("derecha", "right")):
            self._position = RobotPosition(
                x=self._position.x,
                y=self._position.y,
                theta=self._position.theta - 1.57,
            )
            msg = "[MOCK] Giro a la derecha (~90°) ejecutado"
        elif any(k in dest for k in ("izquierda", "left")):
            self._position = RobotPosition(
                x=self._position.x,
                y=self._position.y,
                theta=self._position.theta + 1.57,
            )
            msg = "[MOCK] Giro a la izquierda (~90°) ejecutado"
        elif any(k in dest for k in ("atras", "atrás", "retrocede", "reverse", "backward")):
            self._position = RobotPosition(
                x=self._position.x - 0.25,
                y=self._position.y,
                theta=self._position.theta,
            )
            msg = f"[MOCK] Retroceso ejecutado ({destination})"
        elif any(k in dest for k in ("adelante", "avanza", "forward")):
            self._position = RobotPosition(
                x=self._position.x + 0.25,
                y=self._position.y,
                theta=self._position.theta,
            )
            msg = f"[MOCK] Avance ejecutado ({destination})"
        else:
            from app.services.lab_zones import resolve_zone, zone_goal_xy

            zone = resolve_zone(dest)
            if zone:
                gx, gy = zone_goal_xy(zone)
                self._position = RobotPosition(x=gx, y=gy, theta=self._position.theta)
                msg = f"[MOCK] Navegación a {zone['label']} ({gx:.2f}, {gy:.2f})"
            else:
                msg = f"[MOCK] Navegación iniciada hacia: {destination}"

        return {
            "success": True,
            "message": msg,
            "goal": destination,
            "details": {
                "action": "navigate_to_pose",
                "status": "accepted",
            },
        }

    async def execute_motion_plan(self, steps: list) -> Dict[str, Any]:
        from app.services.lab_zones import resolve_zone, zone_goal_xy
        from app.services.motion_plan import normalize_steps

        plan = normalize_steps(steps)
        self._mode = ROBOT_MODE_NAVIGATING
        self._is_navigating = True
        self._current_goal = f"plan({len(plan)})"
        for step in plan:
            op = step.get("op")
            if op == "goto":
                zone = resolve_zone(str(step.get("destination") or ""))
                if zone:
                    gx, gy = zone_goal_xy(zone)
                    self._position = RobotPosition(x=gx, y=gy, theta=self._position.theta)
            elif op == "drive":
                m = float(step.get("meters") or 0)
                self._position = RobotPosition(
                    x=self._position.x + m,
                    y=self._position.y,
                    theta=self._position.theta,
                )
            elif op == "turn":
                deg = float(step.get("degrees") or 0)
                self._position = RobotPosition(
                    x=self._position.x,
                    y=self._position.y,
                    theta=self._position.theta + math.radians(deg),
                )
        self._mode = ROBOT_MODE_IDLE
        self._is_navigating = False
        return {
            "success": True,
            "message": f"[MOCK] Plan ejecutado ({len(plan)} pasos).",
            "goal": "motion_plan",
            "details": {"steps": plan, "mock": True},
        }

    async def cancel_navigation(self) -> Dict[str, Any]:
        """Simula cancelación de navegación activa."""
        was_navigating = self._is_navigating
        self._mode = ROBOT_MODE_IDLE
        self._is_navigating = False
        self._current_goal = None

        return {
            "success": True,
            "message": "[MOCK] Navegación cancelada" if was_navigating else "[MOCK] No había navegación activa",
            "goal": None,
            "details": {"was_navigating": was_navigating},
        }

    async def return_home(self) -> Dict[str, Any]:
        """Simula retorno a base/home."""
        return await self.send_navigation_goal("Base / Home")

    async def publish_cmd_vel(
        self,
        linear_x: float,
        angular_z: float,
    ) -> Dict[str, Any]:
        """Simula teleop /cmd_vel y actualiza pose aproximada."""
        self._mode = ROBOT_MODE_MANUAL if (linear_x or angular_z) else ROBOT_MODE_IDLE
        self._is_navigating = False
        self._current_goal = "teleop" if (linear_x or angular_z) else None
        # Integración simple para que el panel muestre movimiento
        self._position = RobotPosition(
            x=self._position.x + linear_x * 0.15,
            y=self._position.y + angular_z * 0.05,
            theta=self._position.theta + angular_z * 0.15,
        )
        self._battery = max(0, self._battery - 0.01)
        return {
            "success": True,
            "message": f"[MOCK] cmd_vel lin={linear_x:.3f} ang={angular_z:.3f}",
            "details": {"linear_x": linear_x, "angular_z": angular_z},
        }

    async def get_laser_scan(self, max_points: int = 360) -> Dict[str, Any]:
        """Scan simulado circular con obstáculos ficticios."""
        import math as _m
        n = max(32, min(max_points, 360))
        ranges = []
        for i in range(n):
            ang = -_m.pi + (2 * _m.pi) * i / n
            # Paredes de caja + un pilar
            r = 2.2 / max(0.2, abs(_m.cos(ang)) + abs(_m.sin(ang)) * 0.35)
            if abs(ang) < 0.25:
                r = min(r, 1.1)
            ranges.append(round(min(8.0, r), 3))
        return {
            "frame_id": "mock_laser",
            "angle_min": -3.14159,
            "angle_max": 3.14159,
            "angle_increment": (2 * 3.14159) / n,
            "range_min": 0.15,
            "range_max": 12.0,
            "ranges": ranges,
            "count": n,
        }

    def get_provider_name(self) -> str:
        return "mock"
