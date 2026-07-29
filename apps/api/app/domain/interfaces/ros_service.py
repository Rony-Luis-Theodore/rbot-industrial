"""
=============================================================================
R-Bot — Contrato abstracto: ROSService (Port)
=============================================================================

Propósito:
    Define la interfaz que TODO adapter ROS2 debe implementar.
    Separa la lógica de negocio de la comunicación con ROS2.

Qué hace:
    - Declara métodos para introspección del grafo ROS (topics, nodes, etc.).
    - Declara métodos para navegación autónoma y control.

Conexión con el resto:
    - Implementaciones en app/adapters/ros/ (mock_ros, rclpy_ros).
    - ChatOrchestrator invoca ROSService según la intención del LLM.
    - Routers de /robot/* delegan directamente a ROSService.

Para el integrante de ROS2:
    1. Implementar RclpyROSService heredando ROSService.
    2. Usar rclpy o subprocess según la arquitectura elegida.
    3. Registrar en service_factory.py con ROS_PROVIDER=rclpy.

    IMPORTANTE: rclpy NO debe ejecutarse en el hilo principal de FastAPI.
    Considerar un nodo ROS2 dedicado con comunicación IPC (ver docs/ros-integration.md).
=============================================================================
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from app.domain.models.robot import (
    ROSActionInfo,
    ROSNodeInfo,
    ROSResourceList,
    ROSServiceInfo,
    ROSTopicInfo,
    RobotStatus,
)


class ROSService(ABC):
    """
    Interfaz abstracta para comunicación con ROS2.

    Todo adapter ROS debe implementar esta clase base.
    """

    @abstractmethod
    async def get_status(self) -> RobotStatus:
        """
        Obtiene el estado operativo actual del robot.

        Returns:
            RobotStatus con conexión, batería, modo, posición, etc.
        """
        pass

    @abstractmethod
    async def get_topics(self) -> ROSResourceList:
        """
        Lista los topics ROS2 activos.

        Equivalente a: ros2 topic list

        Returns:
            ROSResourceList con nombres de topics.
        """
        pass

    @abstractmethod
    async def get_nodes(self) -> ROSResourceList:
        """
        Lista los nodos ROS2 activos.

        Equivalente a: ros2 node list

        Returns:
            ROSResourceList con nombres de nodos.
        """
        pass

    @abstractmethod
    async def get_services(self) -> ROSResourceList:
        """
        Lista los servicios ROS2 disponibles.

        Equivalente a: ros2 service list

        Returns:
            ROSResourceList con nombres de servicios.
        """
        pass

    @abstractmethod
    async def get_actions(self) -> ROSResourceList:
        """
        Lista las actions ROS2 disponibles.

        Equivalente a: ros2 action list

        Returns:
            ROSResourceList con nombres de actions.
        """
        pass

    @abstractmethod
    async def send_navigation_goal(self, destination: str) -> Dict[str, Any]:
        """
        Envía un objetivo de navegación autónoma.

        Args:
            destination: Nombre simbólico o coordenadas del destino
                         (ej: 'Estación A', 'bomba 3', 'base').

        Returns:
            Diccionario con resultado de la operación (success, message, goal).
        """
        pass

    async def execute_motion_plan(self, steps: list) -> Dict[str, Any]:
        """
        Ejecuta un plan multi-paso (goto / drive / turn / wait).
        Implementación por defecto: no soportado.
        """
        return {
            "success": False,
            "message": "Este backend ROS no soporta planes multi-paso.",
            "details": {"reason": "not_implemented", "steps": steps},
        }

    @abstractmethod
    async def cancel_navigation(self) -> Dict[str, Any]:
        """
        Cancela la navegación autónoma en curso.

        Returns:
            Diccionario con resultado de la cancelación.
        """
        pass

    @abstractmethod
    async def return_home(self) -> Dict[str, Any]:
        """
        Ordena al robot regresar a la base/home.

        Returns:
            Diccionario con resultado de la operación.
        """
        pass

    @abstractmethod
    async def publish_cmd_vel(
        self,
        linear_x: float,
        angular_z: float,
    ) -> Dict[str, Any]:
        """
        Publica un Twist en /cmd_vel (teleoperación manual).

        Args:
            linear_x: Velocidad lineal m/s (adelante +, atrás -).
            angular_z: Velocidad angular rad/s.

        Returns:
            Diccionario con success/message/details.
        """
        pass

    @abstractmethod
    async def get_laser_scan(self, max_points: int = 360) -> Dict[str, Any]:
        """
        Lee un LaserScan de /scan (LiDAR) y lo compacta para la HMI.

        Returns:
            Dict con angle_min/max/increment, range_min/max, ranges (lista).
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """
        Retorna el identificador del adapter ROS activo.

        Returns:
            Nombre del provider (ej: 'mock', 'rclpy').
        """
        pass
