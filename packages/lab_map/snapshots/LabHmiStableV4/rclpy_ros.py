"""
=============================================================================
R-Bot — Adapter ROS: puente real vía CLI ros2 (Create3 / laboratorio Kalman)
=============================================================================

Propósito:
    Conectar FastAPI con el robot R-Bot real (Create3 + LiDAR) sin ejecutar
    rclpy en el hilo de uvicorn.

Qué hace:
    - Introspección: ros2 topic/node/service/action list
    - Estado: /battery_state + /odom
    - Movimiento: publica /cmd_vel (avance / parada)
    - return_home: intenta action /dock (requiere irobot_create_msgs)

Conexión con el resto:
    - Se activa con ROS_PROVIDER=rclpy en .env
    - Respeta el contrato de domain/interfaces/ros_service.py
    - ChatOrchestrator no necesita cambios

Arquitectura:
    Opción B de docs/ros-integration.md (subprocess CLI).
    Cada llamada hereda el entorno Kalman (CycloneDDS + ROS_DOMAIN_ID).

Robot observado en laboratorio:
    Topics: /cmd_vel, /scan, /odom, /battery_state, /imu, ...
    Actions: /dock, /undock (servidas vía zenoh_bridge)
=============================================================================
"""

from __future__ import annotations

import asyncio
import math
import os
import re
import signal
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.constants import (
    CONNECTION_CONNECTED,
    CONNECTION_DEGRADED,
    CONNECTION_DISCONNECTED,
    ROBOT_MODE_IDLE,
    ROBOT_MODE_MANUAL,
    ROBOT_MODE_NAVIGATING,
)
from app.domain.interfaces.ros_service import ROSService
from app.domain.models.robot import RobotPosition, RobotStatus, ROSResourceList


class RclpyROSService(ROSService):
    """
    Adapter ROS2 real usando la CLI `ros2` (seguro con FastAPI/asyncio).

    Nota: el nombre histórico del archivo es rclpy_ros; la implementación
    actual usa subprocess para no bloquear el event loop con spin de rclpy.
    """

    # Destinos simbólicos que se traducen a movimiento /cmd_vel
    _FORWARD_ALIASES = {
        "adelante",
        "avanza",
        "avanzar",
        "recto",
        "forward",
        "frente",
        "linea recta",
        "línea recta",
        "destino_no_especificado",
    }
    _BACKWARD_ALIASES = {
        "atras",
        "atrás",
        "retrocede",
        "retroceder",
        "reverse",
        "backward",
        "back",
        "para atras",
        "para atrás",
        "marcha atras",
        "marcha atrás",
    }
    _TURN_LEFT_ALIASES = {
        "izquierda",
        "left",
        "giro izquierda",
        "gira izquierda",
        "turn left",
        "a la izquierda",
    }
    _TURN_RIGHT_ALIASES = {
        "derecha",
        "right",
        "giro derecha",
        "gira derecha",
        "turn right",
        "a la derecha",
    }

    def __init__(
        self,
        domain_id: int = 0,
        drive_speed: float = 0.12,
        drive_duration_s: float = 2.0,
        *,
        rmw: str = "rmw_fastrtps_cpp",
        source_kalman: bool = True,
        require_battery: bool = True,
        profile_id: str = "rbot",
        workspace_setup: Optional[str] = None,
    ):
        """
        Args:
            domain_id: ROS_DOMAIN_ID (lab Kalman o 42 en sim).
            drive_speed: Velocidad lineal m/s para avances de prueba.
            drive_duration_s: Segundos publicando /cmd_vel en avance.
            rmw: RMW_IMPLEMENTATION (Cyclone o FastRTPS según lab).
            source_kalman: Si True, source /var/lib/kalman/env.bash.
            require_battery: Create3 tiene /battery_state; Nexus a menudo no.
            profile_id: rbot | nexus | sim
            workspace_setup: setup.bash del ws local (sim / Nav2).
        """
        self._domain_id = domain_id
        self._drive_speed = drive_speed
        self._drive_duration_s = drive_duration_s
        self._rmw = rmw
        self._source_kalman = source_kalman
        self._require_battery = require_battery
        self._profile_id = profile_id
        self._workspace_setup = workspace_setup
        self._mode = ROBOT_MODE_IDLE
        self._is_navigating = False
        self._current_goal: Optional[str] = None
        self._last_daemon_refresh: float = 0.0
        self._motion_cancel = asyncio.Event()
        self._motion_gen: int = 0
        self._motion_proc: Optional[asyncio.subprocess.Process] = None
        self._motion_task: Optional[asyncio.Task] = None
        self._lidar_powered: bool = False
        self._env = self._build_ros_env()
        # Mando unificado: Gazebo diff-drive y Create3/Nexus escuchan /cmd_vel.
        self._cmd_vel_topic = "/cmd_vel"
        self._cmd_vel_qos: List[str] = []
        # Odom cache + dead-reckon (el echo CLI no aguanta el ritmo del goto)
        self._odom_cache: Optional[RobotPosition] = None
        self._odom_cache_mono: float = 0.0
        self._odom_lock = asyncio.Lock()
        self._last_link_ok_mono: float = 0.0
        self._ros_cli_lock = asyncio.Lock()
        # No marcar disconnected por un echo fallido aislado (Husarnet / CLI)
        self._link_grace_s: float = 30.0
        self._odom_refresh_min_s: float = 2.5

    def _build_ros_env(self) -> Dict[str, str]:
        """Construye el entorno de proceso para comandos ros2."""
        env = os.environ.copy()
        env["ROS_DOMAIN_ID"] = str(self._domain_id)
        env["RMW_IMPLEMENTATION"] = self._rmw
        env.setdefault("ROS_IPV6", "on")

        # Perfiles Kalman (Nexus/Create3): FastDDS + Husarnet IPv6
        if self._source_kalman:
            env.pop("CYCLONEDDS_URI", None)
            env["ROS_IPV6"] = "on"
            fastdds = "/var/lib/kalman/fastdds.xml"
            if os.path.isfile(fastdds):
                env["FASTRTPS_DEFAULT_PROFILES_FILE"] = fastdds
        elif "cyclone" in self._rmw:
            cyclonedds = "/var/lib/kalman/cyclonedds.xml"
            if os.path.isfile(cyclonedds):
                env["CYCLONEDDS_URI"] = f"file://{cyclonedds}"
        else:
            env.pop("CYCLONEDDS_URI", None)
            sim_xml = os.path.expanduser(
                "~/Documents/Proyectos/rbot-industrial/scripts/fastdds_sim_udp.xml"
            )
            if os.path.isfile(sim_xml):
                env["FASTRTPS_DEFAULT_PROFILES_FILE"] = sim_xml

        ros_home = os.path.expanduser("~/Documents/Proyectos/.ros_home")
        os.makedirs(os.path.join(ros_home, "log"), exist_ok=True)
        env["ROS_HOME"] = ros_home

        humble_bin = "/opt/ros/humble/bin"
        if os.path.isdir(humble_bin):
            env["PATH"] = f"{humble_bin}:{env.get('PATH', '')}"
        env.setdefault("AMENT_PREFIX_PATH", "/opt/ros/humble")
        env.setdefault("LD_LIBRARY_PATH", "/opt/ros/humble/lib:" + env.get("LD_LIBRARY_PATH", ""))
        env.setdefault("PYTHONPATH", "/opt/ros/humble/lib/python3.10/site-packages:" + env.get("PYTHONPATH", ""))

        return env

    def _compose_sourced_cmd(self, args: List[str]) -> str:
        parts = [
            "source /opt/ros/humble/setup.bash >/dev/null 2>&1",
        ]
        if self._workspace_setup and os.path.isfile(self._workspace_setup):
            parts.append(
                f"source {self._shell_quote(self._workspace_setup)} >/dev/null 2>&1"
            )
        if self._source_kalman:
            parts.append(
                "if [ -f /var/lib/kalman/env.bash ]; then "
                "source /var/lib/kalman/env.bash >/dev/null 2>&1; fi"
            )
        else:
            # Forzar dominio/RMW de sim (evitar que quede pegado el lab)
            parts.append(f"export ROS_DOMAIN_ID={self._domain_id}")
            parts.append(f"export RMW_IMPLEMENTATION={self._shell_quote(self._rmw)}")
            parts.append("unset CYCLONEDDS_URI")
            parts.append("unset ROS_IPV6")
            sim_xml = os.path.expanduser(
                "~/Documents/Proyectos/rbot-industrial/scripts/fastdds_sim_udp.xml"
            )
            if os.path.isfile(sim_xml):
                parts.append(
                    f"export FASTRTPS_DEFAULT_PROFILES_FILE={self._shell_quote(sim_xml)}"
                )
        parts.append("ros2 " + " ".join(self._shell_quote(a) for a in args))
        return "; ".join(parts)

    async def _run_ros2(
        self,
        args: List[str],
        timeout: float = 20.0,
        input_text: Optional[str] = None,
    ) -> tuple[int, str, str]:
        """
        Ejecuta `ros2 ...` de forma asíncrona.

        Returns:
            (returncode, stdout, stderr)
        """
        sourced = self._compose_sourced_cmd(args)
        proc = await asyncio.create_subprocess_exec(
            "bash",
            "-lc",
            sourced,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if input_text is not None else None,
            env=self._env,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(input=input_text.encode() if input_text else None),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return 124, "", f"Timeout ejecutando: ros2 {' '.join(args)}"

        return (
            proc.returncode or 0,
            stdout_b.decode(errors="replace"),
            stderr_b.decode(errors="replace"),
        )

    @staticmethod
    def _shell_quote(value: str) -> str:
        """Escapa un argumento para bash -lc."""
        return "'" + value.replace("'", "'\"'\"'") + "'"

    async def _list_resource(self, resource: str) -> ROSResourceList:
        """Lista topics/nodes/services/actions vía CLI."""
        code, out, err = await self._run_ros2([resource, "list"], timeout=25.0)
        if code != 0:
            raise RuntimeError(err.strip() or f"ros2 {resource} list falló ({code})")
        items = [line.strip() for line in out.splitlines() if line.strip()]
        return ROSResourceList(resource_type=resource + "s" if not resource.endswith("s") else resource, items=items)

    async def get_topics(self) -> ROSResourceList:
        """Equivalente a: ros2 topic list"""
        code, out, err = await self._run_ros2(["topic", "list"], timeout=25.0)
        if code != 0:
            raise RuntimeError(err.strip() or "ros2 topic list falló")
        items = [line.strip() for line in out.splitlines() if line.strip()]
        return ROSResourceList(resource_type="topics", items=items)

    async def get_nodes(self) -> ROSResourceList:
        """Equivalente a: ros2 node list"""
        code, out, err = await self._run_ros2(["node", "list"], timeout=25.0)
        if code != 0:
            raise RuntimeError(err.strip() or "ros2 node list falló")
        items = [line.strip() for line in out.splitlines() if line.strip()]
        return ROSResourceList(resource_type="nodes", items=items)

    async def get_services(self) -> ROSResourceList:
        """Equivalente a: ros2 service list"""
        code, out, err = await self._run_ros2(["service", "list"], timeout=30.0)
        if code != 0:
            raise RuntimeError(err.strip() or "ros2 service list falló")
        items = [line.strip() for line in out.splitlines() if line.strip()]
        return ROSResourceList(resource_type="services", items=items)

    async def get_actions(self) -> ROSResourceList:
        """Equivalente a: ros2 action list"""
        code, out, err = await self._run_ros2(["action", "list"], timeout=25.0)
        if code != 0:
            raise RuntimeError(err.strip() or "ros2 action list falló")
        items = [line.strip() for line in out.splitlines() if line.strip()]
        return ROSResourceList(resource_type="actions", items=items)

    async def refresh_discovery(self, *, force: bool = False) -> bool:
        """
        Reinicia el ros2 daemon tras reconectar Kalman/Husarnet.

        Sin esto, `ros2 topic list` puede quedar vacío aunque Husarnet esté OK.
        """
        if not self._source_kalman:
            return False
        now = time.monotonic()
        if not force and (now - self._last_daemon_refresh) < 45.0:
            return False
        cmd = (
            "source /opt/ros/humble/setup.bash >/dev/null 2>&1; "
            "if [ -f /var/lib/kalman/env.bash ]; then "
            "source /var/lib/kalman/env.bash >/dev/null 2>&1; fi; "
            "ros2 daemon stop >/dev/null 2>&1 || true; "
            "sleep 0.5; "
            "ros2 daemon start >/dev/null 2>&1; "
            "sleep 1"
        )
        proc = await asyncio.create_subprocess_exec(
            "bash",
            "-lc",
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._env,
        )
        await asyncio.wait_for(proc.communicate(), timeout=15.0)
        self._last_daemon_refresh = now
        return proc.returncode == 0

    def _note_odom(self, pose: RobotPosition, *, from_ros: bool = False) -> None:
        # (0,0) desde HMI/fallback no debe pisar odom real; el Create3 SÍ puede
        # estar en el origen tras undock/reconexión — aceptar si viene de /odom.
        if (
            not from_ros
            and abs(float(pose.x)) < 1e-6
            and abs(float(pose.y)) < 1e-6
            and self._odom_cache is not None
            and (
                abs(float(self._odom_cache.x)) > 0.02
                or abs(float(self._odom_cache.y)) > 0.02
            )
        ):
            return
        self._odom_cache = pose
        self._odom_cache_mono = time.monotonic()
        self._last_link_ok_mono = self._odom_cache_mono

    @staticmethod
    def _wrap_pi(a: float) -> float:
        return (float(a) + math.pi) % (2.0 * math.pi) - math.pi

    def _integrate_cmd(self, lin_x: float, ang_z: float, dt: float) -> None:
        """Dead-reckon odom para la HMI mientras publicamos /cmd_vel."""
        if dt <= 0 or self._odom_cache is None:
            return
        p = self._odom_cache
        th = float(p.theta) + float(ang_z) * dt
        # Integración simple (suficiente a 0.1–0.2 m/s)
        x = float(p.x) + float(lin_x) * math.cos(float(p.theta)) * dt
        y = float(p.y) + float(lin_x) * math.sin(float(p.theta)) * dt
        # Normalizar yaw
        th = self._wrap_pi(th)
        # Dead-reckon: actualiza pose pero NO el enlace (solo echo real)
        self._odom_cache = RobotPosition(x=x, y=y, theta=th, frame_id="odom")
        self._odom_cache_mono = time.monotonic()

    @staticmethod
    def _is_zero_odom(pose: Optional[RobotPosition]) -> bool:
        if pose is None:
            return True
        return abs(float(pose.x)) < 1e-6 and abs(float(pose.y)) < 1e-6

    def _cached_odom(self, max_age_s: float = 8.0) -> Optional[RobotPosition]:
        if self._odom_cache is None:
            return None
        if (time.monotonic() - self._odom_cache_mono) > max_age_s:
            return None
        if self._is_zero_odom(self._odom_cache):
            return None
        return self._odom_cache

    def _link_age_s(self) -> float:
        if self._last_link_ok_mono <= 0:
            return 1e9
        return time.monotonic() - self._last_link_ok_mono

    async def get_status(self) -> RobotStatus:
        """Lee odometría (+ batería solo si el perfil la requiere).

        Conexión «pegajosa»: un echo fallido no pasa a disconnected de golpe
        (evita parpadeo en la HMI con Husarnet / CLI saturada).
        """
        now = time.monotonic()
        # Si el último status era (0,0), no cachear 2s — forzar relectura
        cached = getattr(self, "_status_cache", None)
        ttl = 0.6 if self._is_navigating else 2.0
        if cached and self._is_zero_odom(cached[1].position):
            ttl = 0.0
        if cached and (now - cached[0]) < ttl:
            return cached[1]

        inflight = getattr(self, "_status_inflight", None)
        if inflight is not None and not inflight.done():
            return await inflight

        async def _load() -> RobotStatus:
            position: Optional[RobotPosition] = None
            cache_bad = self._odom_cache is None or self._is_zero_odom(
                self._odom_cache
            )
            odom_stale = cache_bad or (
                (time.monotonic() - self._odom_cache_mono) >= self._odom_refresh_min_s
            )

            # Durante nav: permitir dead-reckon corto, pero refrescar /odom real
            # cada ~0.9 s para que la HMI no se desincronice del Create3.
            if self._is_navigating and not cache_bad:
                age = time.monotonic() - self._odom_cache_mono
                if age < 0.9:
                    position = self._cached_odom(max_age_s=30.0)
                else:
                    position = None  # forzar echo abajo
            elif not odom_stale:
                position = self._cached_odom(
                    max_age_s=self._odom_refresh_min_s + 0.5
                )

            if position is None or self._is_zero_odom(position):
                async with self._ros_cli_lock:
                    position = await self._read_odom_position(timeout=4.0)
                if position is None and self._source_kalman:
                    await self.refresh_discovery(force=False)
                    async with self._ros_cli_lock:
                        position = await self._read_odom_position(timeout=4.0)

            if position is None:
                position = self._cached_odom(max_age_s=45.0)

            # Fallback HMI (nunca (0,0))
            if position is None:
                try:
                    from app.services.hmi_state import get_odom_fallback

                    fb = get_odom_fallback()
                    if fb and (
                        abs(float(fb["x"])) > 1e-6 or abs(float(fb["y"])) > 1e-6
                    ):
                        position = RobotPosition(
                            x=float(fb["x"]),
                            y=float(fb["y"]),
                            theta=float(fb["theta"]),
                            frame_id="odom",
                        )
                except Exception:  # noqa: BLE001
                    pass

            battery: Optional[float] = None
            if (
                self._require_battery
                and not self._is_navigating
                and self._link_age_s() < self._link_grace_s
            ):
                # Batería poco frecuente: no bloquear el status
                if not hasattr(self, "_last_batt_mono") or (
                    time.monotonic() - float(getattr(self, "_last_batt_mono", 0))
                ) > 12.0:
                    async with self._ros_cli_lock:
                        battery = await self._read_battery_percent()
                    self._last_batt_mono = time.monotonic()
                    if battery is not None:
                        self._last_batt_val = battery
                else:
                    battery = getattr(self, "_last_batt_val", None)

            age = self._link_age_s()
            # Enlace = eco /odom reciente (aunque la pose sea 0,0 tras reset)
            if age <= self._link_grace_s and self._last_link_ok_mono > 0:
                connection = CONNECTION_CONNECTED
                if (
                    self._require_battery
                    and battery is None
                    and getattr(self, "_last_batt_val", None) is None
                    and not self._is_navigating
                    and age > 10.0
                ):
                    connection = CONNECTION_DEGRADED
            elif position is not None and not self._is_zero_odom(position):
                connection = CONNECTION_DEGRADED
            else:
                connection = CONNECTION_DISCONNECTED

            status = RobotStatus(
                connection=connection,
                battery_percent=(
                    battery
                    if battery is not None
                    else float(getattr(self, "_last_batt_val", 0.0) or 0.0)
                ),
                mode=self._mode,
                position=position
                if position is not None
                else RobotPosition(x=0.0, y=0.0, theta=0.0, frame_id="odom"),
                is_navigating=self._is_navigating,
                current_goal=self._current_goal,
                last_updated=datetime.utcnow(),
            )
            self._status_cache = (time.monotonic(), status)
            return status

        task = asyncio.create_task(_load())
        self._status_inflight = task
        try:
            return await task
        finally:
            if getattr(self, "_status_inflight", None) is task:
                self._status_inflight = None

    async def _read_battery_percent(self) -> Optional[float]:
        """Parsea percentage de /battery_state (0–1 → 0–100)."""
        code, out, _ = await self._run_ros2(
            ["topic", "echo", "/battery_state", "--once"],
            timeout=3.0,
        )
        if code != 0:
            return None
        match = re.search(r"percentage:\s*([0-9.]+)", out)
        if not match:
            return None
        value = float(match.group(1))
        # Create3 reporta 0–1; normalizar a porcentaje
        return round(value * 100.0, 1) if value <= 1.5 else round(value, 1)

    async def _read_odom_position(self, timeout: float = 4.0) -> Optional[RobotPosition]:
        """Parsea pose de /odom y actualiza cache."""
        code, out, _ = await self._run_ros2(
            ["topic", "echo", "/odom", "--once"],
            timeout=timeout,
        )
        if code != 0:
            return None

        x_m = re.search(r"position:\s*\n\s*x:\s*([-\d.]+)", out)
        y_m = re.search(r"position:\s*\n\s*x:\s*[-\d.]+\s*\n\s*y:\s*([-\d.]+)", out)
        # Fallback más simple línea a línea bajo pose.pose.position
        if not x_m:
            xs = re.findall(r"^\s+x:\s*([-\d.eE]+)", out, re.MULTILINE)
            ys = re.findall(r"^\s+y:\s*([-\d.eE]+)", out, re.MULTILINE)
            zs_orient = re.findall(r"orientation:\s*\n(?:.*\n){2}\s+z:\s*([-\d.eE]+)", out)
            ws = re.findall(r"orientation:\s*\n(?:.*\n){3}\s+w:\s*([-\d.eE]+)", out)
            if not xs or not ys:
                return None
            x, y = float(xs[0]), float(ys[0])
            # orientation z,w si disponibles
            theta = 0.0
            if zs_orient and ws:
                zq, wq = float(zs_orient[0]), float(ws[0])
                theta = math.atan2(2.0 * wq * zq, 1.0 - 2.0 * zq * zq)
            pose = RobotPosition(x=x, y=y, theta=theta, frame_id="odom")
            self._note_odom(pose, from_ros=True)
            return pose

        x = float(x_m.group(1))
        y = float(y_m.group(1)) if y_m else 0.0
        zq_m = re.search(r"orientation:\s*\n\s*x:.*\n\s*y:.*\n\s*z:\s*([-\d.]+)\s*\n\s*w:\s*([-\d.]+)", out)
        theta = 0.0
        if zq_m:
            zq, wq = float(zq_m.group(1)), float(zq_m.group(2))
            theta = math.atan2(2.0 * wq * zq, 1.0 - 2.0 * zq * zq)
        pose = RobotPosition(x=x, y=y, theta=theta, frame_id="odom")
        self._note_odom(pose, from_ros=True)
        return pose

    async def send_navigation_goal(self, destination: str) -> Dict[str, Any]:
        """
        Traduce destino simbólico a movimiento /cmd_vel o actions Create3.

        - adelante → avance sostenido
        - izquierda / derecha → giro en sitio (~90°)
        - undock → action /undock (Create3)
        - otros → mensaje claro (waypoints Nav2 pendientes)
        """
        dest = (destination or "").strip().lower()

        if dest in self._FORWARD_ALIASES or any(
            a in dest for a in ("adelante", "avanza", "recto", "forward")
        ):
            offline = await self._offline_motion_error(destination or "adelante")
            if offline:
                return offline
            return await self._drive_linear(
                speed=self._drive_speed,
                duration_s=self._drive_duration_s,
                label=destination or "adelante",
                kind="avance",
            )

        if dest in self._BACKWARD_ALIASES or any(
            a in dest for a in ("atras", "atrás", "retrocede", "reverse", "backward")
        ):
            offline = await self._offline_motion_error(destination or "atras")
            if offline:
                return offline
            return await self._drive_linear(
                speed=-self._drive_speed,
                duration_s=self._drive_duration_s,
                label=destination or "atras",
                kind="retroceso",
            )

        if dest in self._TURN_LEFT_ALIASES or any(
            a in dest for a in ("izquierda", "left")
        ):
            offline = await self._offline_motion_error(destination or "izquierda")
            if offline:
                return offline
            return await self._drive_turn(direction="left", label=destination or "izquierda")

        if dest in self._TURN_RIGHT_ALIASES or any(
            a in dest for a in ("derecha", "right")
        ):
            offline = await self._offline_motion_error(destination or "derecha")
            if offline:
                return offline
            return await self._drive_turn(direction="right", label=destination or "derecha")

        if any(k in dest for k in ("undock", "desatraque", "desacoplar", "salir de base")):
            return await self._send_create_action(
                action="/undock",
                type_candidates=[
                    "irobot_create_msgs/action/Undock",
                ],
                goal="{}",
                label=destination,
            )

        # Zonas del lab (voy a recepción / ve a sala de máquinas / centro…)
        from app.services.hmi_state import get_align
        from app.services.lab_zones import resolve_zone, zone_goal_xy

        zone = resolve_zone(dest)
        if zone:
            offline = await self._offline_motion_error(destination or zone["label"])
            if offline:
                return offline
            align = get_align()
            if not align:
                return {
                    "success": False,
                    "message": (
                        f"Zona '{zone['label']}' reconocida, pero aún no hay «norte» "
                        "del mapa en la HMI (LiDAR/perímetro). Espera a que el trazo "
                        "azul coincida con el lab y reintenta «voy a …»."
                    ),
                    "goal": zone["id"],
                    "details": {"reason": "no_align", "zone": zone["id"]},
                }
            gx, gy = zone_goal_xy(zone)
            return await self._drive_to_map_xy(
                gx, gy, align=align, label=zone["label"], zone_id=zone["id"]
            )

        return {
            "success": False,
            "message": (
                f"Destino '{destination}' no reconocido. "
                "Prueba: avanza, retrocede, gira izquierda/derecha, detén, "
                "o «voy a» recepción / sala de máquinas / almacén / oficina / centro / "
                "pasillo norte / pasillo sur."
            ),
            "goal": destination,
            "details": {"reason": "no_waypoint"},
        }

    async def _offline_motion_error(self, goal: str) -> Optional[Dict[str, Any]]:
        """Si no hay /odom del robot ni fallback HMI, no fingir movimiento."""
        if await self._read_odom_position() is not None:
            return None
        from app.services.hmi_state import get_odom_fallback

        if get_odom_fallback() is not None:
            return None
        if self._source_kalman:
            await self.refresh_discovery(force=True)
            if await self._read_odom_position() is not None:
                return None
            if get_odom_fallback() is not None:
                return None
        return {
            "success": False,
            "message": (
                f"Sin enlace ROS con el robot (perfil {self._profile_id}, "
                f"domain {self._domain_id}). "
                "Reconecta la sesión Kalman, elige Nexus en la interfaz "
                "y espera a que el panel diga 'connected'."
            ),
            "goal": goal,
            "details": {"reason": "disconnected", "domain_id": self._domain_id},
        }

    async def _abort_motion(self) -> None:
        """Cancela publicación de movimiento en curso (si hay)."""
        try:
            from app.services.hmi_state import clear_planned_path

            clear_planned_path()
        except Exception:  # noqa: BLE001
            pass
        self._motion_gen += 1
        self._motion_cancel.set()
        proc = self._motion_proc
        if proc is not None and proc.returncode is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError, OSError):
                    pass
        self._motion_proc = None
        task = self._motion_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._motion_task = None

    async def _spawn_cmd_vel_burst(
        self,
        twist_yaml: str,
        *,
        rate_hz: int,
        n_msgs: int,
        timeout: float,
        lin_x: float = 0.0,
        ang_z: float = 0.0,
        integrate: bool = True,
    ) -> int:
        """Publica un burst de /cmd_vel; permite abortar matando el process group."""
        args = [
            "topic",
            "pub",
            "-r",
            str(rate_hz),
            "-t",
            str(n_msgs),
            *self._cmd_vel_qos,
            self._cmd_vel_topic,
            "geometry_msgs/msg/Twist",
            twist_yaml,
        ]
        sourced = self._compose_sourced_cmd(args)
        proc = await asyncio.create_subprocess_exec(
            "bash",
            "-lc",
            sourced,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._env,
            start_new_session=True,
        )
        self._motion_proc = proc
        dt = float(n_msgs) / max(1.0, float(rate_hz))
        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
            await proc.wait()
            if integrate:
                self._integrate_cmd(lin_x, ang_z, dt)
            return 124
        finally:
            if self._motion_proc is proc:
                self._motion_proc = None
        if integrate:
            self._integrate_cmd(lin_x, ang_z, dt)
        # Publicar cmd_vel con éxito ⇒ enlace vivo (no invalidar status a lo loco)
        if (proc.returncode or 0) == 0:
            self._last_link_ok_mono = time.monotonic()
        return proc.returncode or 0

    async def _open_loop_turn(self, radians: float, *, gen: int) -> None:
        """
        Giro en sitio cerrado con /odom hacia un yaw objetivo.

        Se apunta un poco corto y se frena pronto: la inercia del Create3
        suele pasarse 3–8° si el goal es exacto y la velocidad alta.
        """
        if abs(radians) < 0.05:
            return
        # Sub-apuntar ~10% (Create3 se pasa un poco con 0.94 en lab)
        aim_frac = 0.90
        signed = float(radians) * aim_frac
        sign = 1.0 if signed >= 0 else -1.0

        start = await self._read_odom_position(timeout=2.2)
        if start is None:
            start = self._cached_odom(max_age_s=12.0)
        if start is None:
            await self._timed_turn_fallback(radians, gen=gen)
            return

        th0 = float(start.theta)
        goal_th = self._wrap_pi(th0 + signed)
        ang_cmd = 0.30
        rate_hz = 20
        deadline = time.monotonic() + max(5.0, (abs(signed) / max(0.12, ang_cmd)) * 3.2 + 2.5)
        stall_rounds = 0
        last_err = 1e9

        while time.monotonic() < deadline:
            if self._motion_gen != gen or self._motion_cancel.is_set():
                break
            pose = self._cached_odom(max_age_s=30.0)
            if pose is None:
                pose = await self._read_odom_position(timeout=1.5)
            if pose is None:
                stall_rounds += 1
                if stall_rounds > 8:
                    break
                await asyncio.sleep(0.08)
                continue
            err = self._wrap_pi(goal_th - float(pose.theta))
            # Parar antes (inercia) y si se pasó de sentido
            if abs(err) <= 0.07:
                break
            if err * sign < 0 and abs(err) < 0.35:
                break
            if abs(abs(err) - abs(last_err)) < 0.01:
                stall_rounds += 1
            else:
                stall_rounds = 0
            last_err = abs(err)
            # Rampa: lento cerca del objetivo
            if abs(err) > 0.55:
                spd = ang_cmd
            elif abs(err) > 0.25:
                spd = max(0.14, ang_cmd * 0.55)
            else:
                spd = max(0.10, ang_cmd * 0.32)
            if stall_rounds >= 5:
                spd = min(0.42, ang_cmd * 1.15)
                stall_rounds = 0
            n = 3 if abs(err) > 0.35 else 2
            twist = (
                "{linear: {x: 0.0, y: 0.0, z: 0.0}, "
                "angular: {x: 0.0, y: 0.0, z: %.3f}}"
            ) % (spd * sign)
            await self._spawn_cmd_vel_burst(
                twist,
                rate_hz=rate_hz,
                n_msgs=n,
                timeout=(n / rate_hz) + 4.0,
                lin_x=0.0,
                ang_z=spd * sign,
                integrate=False,
            )

        await self._publish_stop()
        await self._read_odom_position(timeout=2.0)

    async def _timed_turn_fallback(self, radians: float, *, gen: int) -> None:
        """Sin odom: tiempo acotado; un poco corto por inercia."""
        scale = 0.92
        ang_speed_assumed = 0.55  # rad/s reales estimados
        sign = 1.0 if radians >= 0 else -1.0
        duration = (abs(radians) * scale) / ang_speed_assumed
        twist = (
            "{linear: {x: 0.0, y: 0.0, z: 0.0}, "
            "angular: {x: 0.0, y: 0.0, z: %.3f}}"
        ) % (0.26 * sign)
        rate_hz = 20
        total = max(1, int(duration * rate_hz))
        published = 0
        while published < total:
            if self._motion_gen != gen or self._motion_cancel.is_set():
                break
            n = min(3, total - published)
            await self._spawn_cmd_vel_burst(
                twist,
                rate_hz=rate_hz,
                n_msgs=n,
                timeout=(n / rate_hz) + 4.0,
                lin_x=0.0,
                ang_z=0.28 * sign,
                integrate=False,
            )
            published += n
        await self._publish_stop()

    async def _timed_drive_fallback(self, meters: float, *, gen: int) -> None:
        """Sin odom: tiempo corto (robot suele ir más rápido que 0.12 m/s)."""
        # Asumir ~0.35 m/s real para no pasarse de metros
        speed_cmd = min(0.10, float(self._drive_speed))
        assumed = 0.35
        if meters < 0:
            speed_cmd = -speed_cmd
        duration = abs(meters) / assumed
        twist = (
            "{linear: {x: %.3f, y: 0.0, z: 0.0}, "
            "angular: {x: 0.0, y: 0.0, z: 0.0}}"
        ) % speed_cmd
        rate_hz = 12
        total = max(1, int(duration * rate_hz))
        published = 0
        while published < total:
            if self._motion_gen != gen or self._motion_cancel.is_set():
                break
            n = min(3, total - published)
            await self._spawn_cmd_vel_burst(
                twist,
                rate_hz=rate_hz,
                n_msgs=n,
                timeout=(n / rate_hz) + 4.0,
                lin_x=speed_cmd,
                ang_z=0.0,
                integrate=False,
            )
            published += n
        await self._publish_stop()

    async def _open_loop_drive(
        self,
        meters: float,
        *,
        gen: int,
        align: Optional[Dict[str, float]] = None,
    ) -> None:
        """
        Avance cerrado con /odom (distancia real), no por reloj.
        Si hay align, para al detectar muro / salida de libre (evita empujar la pared).
        """
        if abs(meters) < 0.04:
            return
        target = abs(float(meters))
        sign = 1.0 if meters >= 0 else -1.0
        speed = min(0.12, float(self._drive_speed))

        start = await self._read_odom_position(timeout=2.2)
        if start is None:
            start = self._cached_odom(max_age_s=12.0)
        if start is None:
            await self._timed_drive_fallback(meters, gen=gen)
            return

        x0, y0 = float(start.x), float(start.y)
        rate_hz = 12
        deadline = time.monotonic() + max(4.0, (target / max(0.06, speed)) * 2.5 + 2.0)
        hit_wall = False

        while time.monotonic() < deadline:
            if self._motion_gen != gen or self._motion_cancel.is_set():
                break
            pose = self._cached_odom(max_age_s=30.0)
            traveled = 0.0
            if pose is not None:
                traveled = math.hypot(float(pose.x) - x0, float(pose.y) - y0)
            remaining = target - traveled
            if remaining <= 0.04:
                break
            # Seguridad Occupancy solo si el align es creíble:
            # si al empezar ya estamos "en muro" o sin libre delante, el align
            # está mal → no abortar el avance métrico (el chat pide metros reales).
            if align and pose is not None and traveled >= 0.06:
                from app.services.lab_zones import odom_to_map
                from app.services.map_service import free_ahead, is_map_free

                mx, my, mth = odom_to_map(pose.x, pose.y, pose.theta, align)
                if is_map_free(mx, my):
                    ahead_th = mth if sign >= 0 else self._wrap_pi(mth + math.pi)
                    if not free_ahead(mx, my, ahead_th, 0.14):
                        hit_wall = True
                        break
                # si !is_map_free al inicio del check → ignore (align dudoso)
            spd = speed if remaining > 0.18 else max(0.05, speed * 0.45)
            n = 3 if remaining > 0.15 else 2
            twist = (
                "{linear: {x: %.3f, y: 0.0, z: 0.0}, "
                "angular: {x: 0.0, y: 0.0, z: 0.0}}"
            ) % (spd * sign)
            await self._spawn_cmd_vel_burst(
                twist,
                rate_hz=rate_hz,
                n_msgs=n,
                timeout=(n / rate_hz) + 4.0,
                lin_x=spd * sign,
                ang_z=0.0,
                integrate=False,
            )
            pose2 = await self._read_odom_position(timeout=1.8)
            if pose2 is None:
                # Sin confirmación: no sumar dead-reckon como si hubiera avanzado
                await asyncio.sleep(0.12)
                pose2 = await self._read_odom_position(timeout=2.0)
            if pose2 is None:
                continue
            if align:
                from app.services.lab_zones import odom_to_map
                from app.services.map_service import is_map_free

                mx, my, _mth = odom_to_map(
                    pose2.x, pose2.y, pose2.theta, align
                )
                if not is_map_free(mx, my):
                    hit_wall = True
                    break
            traveled = math.hypot(float(pose2.x) - x0, float(pose2.y) - y0)
            if traveled >= target - 0.03:
                break

        await self._publish_stop()
        await self._read_odom_position(timeout=2.0)
        if hit_wall:
            self._status_cache = None

    async def _drive_linear(
        self,
        *,
        speed: float,
        duration_s: float,
        label: str,
        kind: str,
    ) -> Dict[str, Any]:
        """Avanza o retrocede en background (cancelable con «detén»)."""
        await self._abort_motion()
        self._motion_cancel = asyncio.Event()
        gen = self._motion_gen
        self._mode = ROBOT_MODE_MANUAL
        self._is_navigating = True
        self._current_goal = label

        twist = (
            "{linear: {x: %.3f, y: 0.0, z: 0.0}, "
            "angular: {x: 0.0, y: 0.0, z: 0.0}}"
        ) % speed
        rate_hz = 10
        chunk = 2
        total = max(1, int(duration_s * rate_hz))
        verb = "Avance" if speed >= 0 else "Retroceso"

        async def worker() -> None:
            published = 0
            try:
                while published < total:
                    if self._motion_gen != gen or self._motion_cancel.is_set():
                        break
                    n = min(chunk, total - published)
                    await self._spawn_cmd_vel_burst(
                        twist,
                        rate_hz=rate_hz,
                        n_msgs=n,
                        timeout=(n / rate_hz) + 8.0,
                        lin_x=speed,
                        ang_z=0.0,
                    )
                    published += n
            finally:
                await self._publish_stop()
                if self._motion_gen == gen:
                    self._mode = ROBOT_MODE_IDLE
                    self._is_navigating = False
                    self._current_goal = None

        self._motion_task = asyncio.create_task(worker())
        return {
            "success": True,
            "message": (
                f"{verb} en curso (~{duration_s:.1f}s a {abs(speed):.2f} m/s). "
                "Di «detén» para parar."
            ),
            "goal": label,
            "details": {
                "topic": self._cmd_vel_topic,
                "speed": speed,
                "duration_s": duration_s,
                "async": True,
                "kind": kind,
            },
        }

    async def _align_map_heading(
        self,
        desired_map_th: float,
        *,
        align: Dict[str, float],
        gen: int,
        tol_rad: float = 0.09,
        max_rounds: int = 10,
    ) -> bool:
        """
        Gira hasta que el rumbo mapa (odom real → SE2) coincida con desired_map_th.
        Tras cada micro-giro relee /odom; no avanza si la HMI «cree» que ya giró.
        """
        from app.services.lab_zones import odom_to_map

        for _ in range(max_rounds):
            if self._motion_gen != gen or self._motion_cancel.is_set():
                return False
            pose = await self._read_odom_position(timeout=2.2)
            if pose is None:
                pose = self._cached_odom(max_age_s=6.0)
            if pose is None:
                await asyncio.sleep(0.15)
                continue
            _mx, _my, mth = odom_to_map(pose.x, pose.y, pose.theta, align)
            err = self._wrap_pi(desired_map_th - mth)
            if abs(err) <= tol_rad:
                await self._publish_stop()
                # Confirmación extra: segunda lectura
                pose2 = await self._read_odom_position(timeout=2.0)
                if pose2 is None:
                    return True
                _a, _b, mth2 = odom_to_map(pose2.x, pose2.y, pose2.theta, align)
                err2 = self._wrap_pi(desired_map_th - mth2)
                return abs(err2) <= tol_rad + 0.03

            # Corregir solo el error medido (odom real), no un delta «teórico»
            # Limitar paso para no pasarse si el Create3 es rápido
            step = max(-0.55, min(0.55, err))
            await self._open_loop_turn(step, gen=gen)
            await self._publish_stop()
            # Obliga a odom fresco antes de decidir otra ronda
            await self._read_odom_position(timeout=2.2)
        return False

    async def _approach_map_waypoint(
        self,
        wx: float,
        wy: float,
        *,
        align: Dict[str, float],
        gen: int,
        arrive_m: float = 0.14,
        max_step_m: float = 0.28,
        max_rounds: int = 18,
    ) -> bool:
        """
        Acerca al waypoint: alinea rumbo a la trayectoria → avanza un poco →
        relee odom real y compara pose mapa. No pasa al siguiente tramo hasta
        coincidir (o agotar intentos / muro).
        """
        from app.services.lab_zones import odom_to_map
        from app.services.map_service import free_ahead, is_map_free, path_clear

        for _ in range(max_rounds):
            if self._motion_gen != gen or self._motion_cancel.is_set():
                return False

            pose = await self._read_odom_position(timeout=2.2)
            if pose is None:
                pose = self._cached_odom(max_age_s=6.0)
            if pose is None:
                await asyncio.sleep(0.2)
                continue

            mx, my, mth = odom_to_map(pose.x, pose.y, pose.theta, align)
            if not is_map_free(mx, my):
                await self._publish_stop()
                return False

            dist = math.hypot(wx - mx, wy - my)
            if dist <= arrive_m:
                # Verificar otra vez con odom fresco
                pose2 = await self._read_odom_position(timeout=2.0)
                if pose2 is None:
                    return True
                mx2, my2, _ = odom_to_map(pose2.x, pose2.y, pose2.theta, align)
                return math.hypot(wx - mx2, wy - my2) <= arrive_m + 0.04

            desired = math.atan2(wy - my, wx - mx)
            heading_err = abs(self._wrap_pi(desired - mth))

            # 1) Alinear rumbo a la línea de trayectoria y verificar
            if heading_err > 0.10:
                ok = await self._align_map_heading(
                    desired, align=align, gen=gen, tol_rad=0.09
                )
                if not ok:
                    continue
                # Releer tras alineación confirmada
                continue

            # 2) Seguridad: no avanzar hacia muro
            if not free_ahead(mx, my, desired, 0.14):
                await self._publish_stop()
                return False
            if not path_clear(mx, my, wx, wy) and dist > arrive_m * 2.5:
                # Tramo largo bloqueado: solo acercamiento corto si hay libre delante
                step = min(0.12, dist * 0.4)
            else:
                # Pasos cortos: obliga a re-verificar odom entre avances
                step = min(dist, max_step_m, 0.22)

            if step < 0.04:
                return dist <= arrive_m + 0.06

            # 3) Avance corto + verificación obligatoria con odom real
            before = (mx, my)
            await self._open_loop_drive(step, gen=gen, align=align)
            await self._publish_stop()

            pose3 = await self._read_odom_position(timeout=2.2)
            if pose3 is None:
                # Sin confirmación real → no dar por hecho el avance
                await asyncio.sleep(0.25)
                pose3 = await self._read_odom_position(timeout=2.5)
            if pose3 is None:
                continue

            mx3, my3, mth3 = odom_to_map(pose3.x, pose3.y, pose3.theta, align)
            progressed = math.hypot(mx3 - before[0], my3 - before[1])
            # Si casi no avanzó en mapa pero se ordenó step, reintentar (sub-movimiento)
            if progressed < step * 0.25 and dist > arrive_m * 1.5:
                # Posible odom lento o ruedas patinando: micro-corrección de rumbo
                desired2 = math.atan2(wy - my3, wx - mx3)
                if abs(self._wrap_pi(desired2 - mth3)) > 0.12:
                    await self._align_map_heading(
                        desired2, align=align, gen=gen, tol_rad=0.10
                    )
                continue

            # Rumbo se desviaría del trazo → corregir antes del siguiente avance
            desired3 = math.atan2(wy - my3, wx - mx3)
            if abs(self._wrap_pi(desired3 - mth3)) > 0.14 and math.hypot(
                wx - mx3, wy - my3
            ) > arrive_m:
                await self._align_map_heading(
                    desired3, align=align, gen=gen, tol_rad=0.09
                )

        # Última lectura
        pose = await self._read_odom_position(timeout=2.0)
        if pose is None:
            return False
        mx, my, _ = odom_to_map(pose.x, pose.y, pose.theta, align)
        return math.hypot(wx - mx, wy - my) <= arrive_m + 0.08

    async def _follow_map_waypoints(
        self,
        waypoints: list,
        *,
        align: Dict[str, float],
        gen: int,
        arrive_m: float = 0.14,
        max_step_m: float = 0.28,
    ) -> None:
        """
        Sigue waypoints Occupancy con sinergia lab↔HMI:
        alinear rumbo al trazo → verificar odom real → avanzar → verificar pose mapa.
        No pasa al siguiente waypoint hasta que la realidad coincida.
        """
        pts = [(float(p[0]), float(p[1])) for p in waypoints]
        if len(pts) < 2:
            return

        for wx, wy in pts[1:]:
            if self._motion_gen != gen or self._motion_cancel.is_set():
                break
            ok = await self._approach_map_waypoint(
                wx,
                wy,
                align=align,
                gen=gen,
                arrive_m=arrive_m,
                max_step_m=max_step_m,
            )
            # Resync HMI con odom real tras cada waypoint
            await self._read_odom_position(timeout=2.0)
            if not ok:
                # No forzar el resto de la ruta si este tramo falló (evita chocar)
                break

    async def _drive_to_map_xy(
        self,
        goal_x: float,
        goal_y: float,
        *,
        align: Dict[str, float],
        label: str,
        zone_id: str,
        arrive_m: float = 0.14,
        max_s: float = 45.0,
    ) -> Dict[str, Any]:
        """
        Navegación a (x,y) mapa con A* (rodea los 4 bloques Occupancy).

        - Planifica waypoints en libre inflado.
        - Ejecuta giro+avance open-loop por tramo.
        - Publica la ruta a la HMI para dibujo.
        """
        from app.services.hmi_state import (
            clear_planned_path,
            get_odom_fallback,
            set_planned_path,
        )
        from app.services.lab_zones import odom_to_map
        from app.services.map_service import is_map_free, nearest_free_xy, plan_path
        from app.domain.models.robot import RobotPosition

        async def read_pose(*, allow_fallback: bool = True) -> Optional[RobotPosition]:
            pose = await self._read_odom_position(timeout=3.5)
            if pose is not None:
                return pose
            cached = self._cached_odom(max_age_s=6.0)
            if cached is not None:
                return cached
            if not allow_fallback:
                return None
            fb = get_odom_fallback()
            if not fb:
                return None
            pose = RobotPosition(
                x=float(fb["x"]),
                y=float(fb["y"]),
                theta=float(fb["theta"]),
                frame_id="odom",
            )
            self._note_odom(pose)
            return pose

        # Preferir odom ROS real (evita mezclar sim/HMI con lab)
        probe = await read_pose(allow_fallback=False)
        used_fallback = False
        if probe is None:
            probe = await read_pose(allow_fallback=True)
            used_fallback = probe is not None
        if probe is None:
            return {
                "success": False,
                "message": (
                    f"No pude leer /odom para ir a {label}. "
                    "Revisa la conexión Kalman y reintenta."
                ),
                "goal": zone_id,
                "details": {"reason": "no_odom"},
            }

        mx0, my0, mth0 = odom_to_map(probe.x, probe.y, probe.theta, align)
        snapped_start = False

        # Pose fuera de libre (p. ej. odom tras choque): proyectar al Occupancy
        if not is_map_free(mx0, my0):
            snapped = nearest_free_xy(mx0, my0, max_r_m=0.65)
            if not snapped:
                return {
                    "success": False,
                    "message": (
                        f"La pose en mapa ({mx0:.2f},{my0:.2f}) está fuera del lab y "
                        "no hay celda libre cercana. Teleopera un poco hacia el "
                        "perímetro libre o pulsa Ajustar mapa / LiDAR, luego reintenta."
                    ),
                    "goal": zone_id,
                    "details": {
                        "reason": "pose_not_free",
                        "from_xy": [mx0, my0],
                        "map_xy": [goal_x, goal_y],
                    },
                }
            mx0, my0 = float(snapped[0]), float(snapped[1])
            snapped_start = True

        # Nota: mirar a un muro NO es error — el follower gira in-place hacia el
        # primer waypoint de la ruta A* y luego avanza. No rechazar por rumbo.

        dist0 = math.hypot(goal_x - mx0, goal_y - my0)
        if dist0 <= arrive_m:
            clear_planned_path()
            return {
                "success": True,
                "message": f"Ya estás en {label} (≤ {arrive_m:.2f} m).",
                "goal": zone_id,
                "details": {"kind": "zone_goto", "already_there": True},
            }

        planned = plan_path(mx0, my0, goal_x, goal_y, inflate_m=0.08, max_step_m=0.36)
        if not planned.get("ok") or not planned.get("waypoints"):
            clear_planned_path()
            return {
                "success": False,
                "message": (
                    f"No hay ruta libre hasta {label} evitando obstáculos "
                    f"(desde {mx0:.2f},{my0:.2f}). "
                    "Acércate al perímetro libre o elige un pasillo intermedio."
                ),
                "goal": zone_id,
                "details": {
                    "reason": planned.get("reason") or "no_path",
                    "from_xy": [mx0, my0],
                    "map_xy": [goal_x, goal_y],
                },
            }

        waypoints = planned["waypoints"]
        if len(waypoints) >= 2:
            wx1, wy1 = float(waypoints[1][0]), float(waypoints[1][1])
            desired0 = math.atan2(wy1 - my0, wx1 - mx0)
            err0 = (desired0 - mth0 + math.pi) % (2 * math.pi) - math.pi
        else:
            err0 = 0.0

        await self._abort_motion()
        # Publicar ruta DESPUÉS del abort (abort limpia planned_path)
        set_planned_path(
            waypoints,
            zone_id=zone_id,
            label=label,
            length_m=float(planned.get("length_m") or 0.0),
            mode=str(planned.get("mode") or "astar"),
        )
        self._motion_cancel = asyncio.Event()
        gen = self._motion_gen
        self._mode = ROBOT_MODE_NAVIGATING
        self._is_navigating = True
        self._current_goal = label
        self._note_odom(probe)
        self._status_cache = None

        max_step = 0.28 if self._source_kalman else 0.40
        path_len = float(planned.get("length_m") or dist0)
        n_wp = len(waypoints)

        async def worker() -> None:
            try:
                await self._follow_map_waypoints(
                    waypoints,
                    align=align,
                    gen=gen,
                    arrive_m=arrive_m,
                    max_step_m=max_step,
                )
            finally:
                await self._publish_stop()
                try:
                    fresh = await self._read_odom_position(timeout=3.5)
                    if fresh is not None:
                        self._note_odom(fresh)
                except Exception:  # noqa: BLE001
                    pass
                # Mantener la ruta dibujada unos segundos; limpia al llegar idle
                if self._motion_gen == gen:
                    self._mode = ROBOT_MODE_IDLE
                    self._is_navigating = False
                    self._current_goal = None
                self._status_cache = None

        self._motion_task = asyncio.create_task(worker())
        fb_note = " · odom HMI" if used_fallback else ""
        snap_note = " · inicio proyectado a libre" if snapped_start else ""
        mode = planned.get("mode") or "astar"
        return {
            "success": True,
            "message": (
                f"Voy a {label}: ruta {path_len:.2f} m · {n_wp} waypoints "
                f"({mode}, evita bloques)"
                f"{f', giro inicial {math.degrees(err0):+.0f}°' if abs(err0) > 0.1 else ''} "
                f"mapa ({mx0:.2f},{my0:.2f}) → ({goal_x:.2f},{goal_y:.2f})"
                f"{snap_note}{fb_note}. Di «detén» para parar."
            ),
            "goal": zone_id,
            "details": {
                "kind": "zone_goto",
                "zone": zone_id,
                "map_xy": [goal_x, goal_y],
                "from_xy": [mx0, my0],
                "dist_m": path_len,
                "turn_deg": round(math.degrees(err0), 1),
                "waypoints": [[float(a), float(b)] for a, b in waypoints],
                "n_waypoints": n_wp,
                "plan_mode": mode,
                "snapped_start": snapped_start,
                "used_odom_fallback": used_fallback,
                "async": True,
                "mode": "odom_closed_loop",
                "align_source": align.get("source"),
            },
        }

    async def execute_motion_plan(self, steps: list) -> Dict[str, Any]:
        """Ejecuta goto/drive/turn/wait en serie (cancelable con «detén»)."""
        from app.services.hmi_state import get_align
        from app.services.lab_zones import resolve_zone, zone_goal_xy
        from app.services.motion_plan import normalize_steps

        plan = normalize_steps(steps)
        if not plan:
            return {
                "success": False,
                "message": "Plan vacío o no válido.",
                "details": {"reason": "empty_plan"},
            }

        offline = await self._offline_motion_error("plan")
        if offline:
            return offline

        await self._abort_motion()
        self._motion_cancel = asyncio.Event()
        gen = self._motion_gen
        self._mode = ROBOT_MODE_NAVIGATING
        self._is_navigating = True
        self._current_goal = f"plan({len(plan)})"

        async def run_drive(meters: float) -> None:
            align = get_align()
            await self._open_loop_drive(
                float(meters),
                gen=gen,
                align=align if isinstance(align, dict) else None,
            )

        async def run_turn(degrees: float) -> None:
            await self._open_loop_turn(math.radians(float(degrees)), gen=gen)

        async def worker() -> None:
            try:
                for step in plan:
                    if self._motion_gen != gen or self._motion_cancel.is_set():
                        break
                    op = step.get("op")
                    if op == "wait":
                        await asyncio.sleep(float(step.get("seconds") or 1.0))
                    elif op == "drive":
                        await run_drive(float(step.get("meters") or 0.2))
                    elif op == "turn":
                        await run_turn(float(step.get("degrees") or 90.0))
                    elif op == "goto":
                        zone = resolve_zone(str(step.get("destination") or ""))
                        align = get_align()
                        if not zone or not align:
                            continue
                        gx, gy = zone_goal_xy(zone)
                        from app.services.hmi_state import set_planned_path
                        from app.services.lab_zones import odom_to_map
                        from app.services.map_service import plan_path

                        pose = self._cached_odom(max_age_s=15.0)
                        if pose is None:
                            pose = await self._read_odom_position(timeout=2.0)
                        if pose is None:
                            continue
                        mx, my, _mth = odom_to_map(pose.x, pose.y, pose.theta, align)
                        planned = plan_path(mx, my, gx, gy, inflate_m=0.08, max_step_m=0.36)
                        if not planned.get("ok") or not planned.get("waypoints"):
                            continue
                        set_planned_path(
                            planned["waypoints"],
                            zone_id=zone["id"],
                            label=zone["label"],
                            length_m=float(planned.get("length_m") or 0.0),
                            mode=str(planned.get("mode") or "astar"),
                        )
                        await self._follow_map_waypoints(
                            planned["waypoints"],
                            align=align,
                            gen=gen,
                            arrive_m=0.14,
                            max_step_m=0.28 if self._source_kalman else 0.40,
                        )
                    elif op == "stop":
                        break
            finally:
                await self._publish_stop()
                if self._motion_gen == gen:
                    self._mode = ROBOT_MODE_IDLE
                    self._is_navigating = False
                    self._current_goal = None

        # Esperar el plan: el chat responde con «ejecución terminada» (no se queda al 92%).
        cancelled = False
        try:
            await worker()
            cancelled = self._motion_cancel.is_set()
        except Exception:
            cancelled = True
            await self._publish_stop()
            self._mode = ROBOT_MODE_IDLE
            self._is_navigating = False
            self._current_goal = None
            raise

        summary = ", ".join(f"{s.get('op')}" for s in plan[:6])
        if cancelled:
            msg = (
                f"Plan interrumpido ({len(plan)} pasos: {summary}"
                f"{'…' if len(plan) > 6 else ''})."
            )
        else:
            msg = (
                f"Ejecución terminada ({len(plan)} pasos: {summary}"
                f"{'…' if len(plan) > 6 else ''})."
            )
        return {
            "success": not cancelled,
            "message": msg,
            "goal": "motion_plan",
            "details": {
                "kind": "sequence",
                "steps": plan,
                "async": False,
                "mode": "odom_closed_loop",
                "cancelled": cancelled,
            },
        }

    async def _drive_turn(self, *, direction: str, label: str) -> Dict[str, Any]:
        """Giro en sitio ~90° en background (cancelable)."""
        await self._abort_motion()
        self._motion_cancel = asyncio.Event()
        gen = self._motion_gen
        self._mode = ROBOT_MODE_MANUAL
        self._is_navigating = True
        self._current_goal = label

        ang_speed = 0.40
        sign = 1.0 if direction == "left" else -1.0
        duration_s = (math.pi / 2.0) / ang_speed
        twist = (
            "{linear: {x: 0.0, y: 0.0, z: 0.0}, "
            "angular: {x: 0.0, y: 0.0, z: %.3f}}"
        ) % (ang_speed * sign)
        rate_hz = 20
        chunk = 4
        total = max(1, int(duration_s * rate_hz))
        side = "izquierda" if direction == "left" else "derecha"

        async def worker() -> None:
            published = 0
            try:
                while published < total:
                    if self._motion_gen != gen or self._motion_cancel.is_set():
                        break
                    n = min(chunk, total - published)
                    await self._spawn_cmd_vel_burst(
                        twist,
                        rate_hz=rate_hz,
                        n_msgs=n,
                        timeout=(n / rate_hz) + 8.0,
                        lin_x=0.0,
                        ang_z=ang_speed * sign,
                    )
                    published += n
            finally:
                await self._publish_stop()
                if self._motion_gen == gen:
                    self._mode = ROBOT_MODE_IDLE
                    self._is_navigating = False
                    self._current_goal = None

        self._motion_task = asyncio.create_task(worker())
        return {
            "success": True,
            "message": f"Giro a la {side} en curso (~90°). Di «detén» para parar.",
            "goal": label,
            "details": {
                "topic": self._cmd_vel_topic,
                "direction": direction,
                "angular_z": ang_speed * sign,
                "duration_s": duration_s,
                "async": True,
            },
        }

    def _pub_cmd_vel_args(self, twist_yaml: str, *, burst: bool = False) -> List[str]:
        """Argumentos ros2 topic pub para el topic de mando del perfil."""
        # En lab y sim, --once es demasiado corto para el diff-drive (demos Kalman usan 10–20 Hz).
        # Burst breve (~0.3 s @ 20 Hz) para teleop continuo desde la HMI.
        if burst:
            return [
                "topic",
                "pub",
                "-r",
                "20",
                "-t",
                "8",
                *self._cmd_vel_qos,
                self._cmd_vel_topic,
                "geometry_msgs/msg/Twist",
                twist_yaml,
            ]
        return [
            "topic",
            "pub",
            "--once",
            *self._cmd_vel_qos,
            self._cmd_vel_topic,
            "geometry_msgs/msg/Twist",
            twist_yaml,
        ]

    async def _publish_stop(self) -> None:
        """Publica Twist cero en el topic de mando del perfil."""
        stop = "{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"
        await self._run_ros2(self._pub_cmd_vel_args(stop, burst=False), timeout=10.0)

    async def publish_cmd_vel(
        self,
        linear_x: float,
        angular_z: float,
    ) -> Dict[str, Any]:
        """
        Teleoperación: un Twist en /cmd_vel (lab) o /cmd_vel_teleop (sim+Nav2).
        """
        lin = max(-0.25, min(0.25, float(linear_x)))
        ang = max(-1.2, min(1.2, float(angular_z)))

        if abs(lin) < 1e-4 and abs(ang) < 1e-4:
            await self._publish_stop()
            self._mode = ROBOT_MODE_IDLE
            self._current_goal = None
            return {
                "success": True,
                "message": "Teleop stop",
                "details": {
                    "linear_x": 0.0,
                    "angular_z": 0.0,
                    "topic": self._cmd_vel_topic,
                },
            }

        twist = (
            "{linear: {x: %.4f, y: 0.0, z: 0.0}, "
            "angular: {x: 0.0, y: 0.0, z: %.4f}}"
        ) % (lin, ang)

        use_burst = True  # Nexus/Create3/sim necesitan publicación sostenida (no --once)
        code, out, err = await self._run_ros2(
            self._pub_cmd_vel_args(twist, burst=use_burst),
            timeout=12.0 if use_burst else 8.0,
        )
        ok = code == 0
        if ok:
            self._mode = ROBOT_MODE_MANUAL
            self._is_navigating = False
            self._current_goal = "teleop"
        return {
            "success": ok,
            "message": (
                f"{self._cmd_vel_topic} publicado"
                if ok
                else (err.strip() or out.strip() or "fallo cmd_vel")
            ),
            "details": {
                "linear_x": lin,
                "angular_z": ang,
                "returncode": code,
                "topic": self._cmd_vel_topic,
                "burst": use_burst,
            },
        }

    async def cancel_navigation(self) -> Dict[str, Any]:
        """Detiene el robot: aborta avance/giro en curso y publica Twist cero."""
        was = self._is_navigating
        await self._abort_motion()
        await self._publish_stop()
        self._mode = ROBOT_MODE_IDLE
        self._is_navigating = False
        self._current_goal = None
        return {
            "success": True,
            "message": f"Robot detenido ({self._cmd_vel_topic} = 0).",
            "goal": None,
            "details": {"was_navigating": was, "topic": self._cmd_vel_topic},
        }

    async def return_home(self) -> Dict[str, Any]:
        """Intenta atracar con la action /dock del Create3."""
        self._mode = ROBOT_MODE_NAVIGATING
        self._is_navigating = True
        self._current_goal = "dock / base"

        result = await self._send_create_action(
            action="/dock",
            type_candidates=[
                "irobot_create_msgs/action/DockServo",
                "irobot_create_msgs/action/Dock",
            ],
            goal="{}",
            label="base",
        )

        self._mode = ROBOT_MODE_IDLE
        self._is_navigating = False
        self._current_goal = None
        return result

    async def _send_create_action(
        self,
        action: str,
        type_candidates: List[str],
        goal: str,
        label: str,
    ) -> Dict[str, Any]:
        """
        Envía una action Create3. Si faltan los mensajes en el PC alumno,
        devuelve instrucciones claras (sin tumbar la API).
        """
        last_err = ""
        for action_type in type_candidates:
            code, out, err = await self._run_ros2(
                ["action", "send_goal", action, action_type, goal],
                timeout=60.0,
            )
            combined = (out + "\n" + err).strip()
            if code == 0 and "Unknown" not in combined and "not available" not in combined.lower():
                return {
                    "success": True,
                    "message": f"Action {action} enviada ({action_type}).",
                    "goal": label,
                    "details": {"action": action, "type": action_type, "output": combined[-500:]},
                }
            last_err = combined or f"code={code}"

        return {
            "success": False,
            "message": (
                f"No se pudo ejecutar {action}. "
                "En el PC alumno falta el paquete de mensajes Create3. "
                "Cuando apt esté libre, instala: "
                "sudo apt install ros-humble-irobot-create-msgs "
                f"(detalle: {last_err[:200]})"
            ),
            "goal": label,
            "details": {"action": action, "error": last_err[:500]},
        }

    async def ensure_lidar_powered(self) -> bool:
        """Enciende /lidar_power en Nexus (apagado por defecto en el lab)."""
        if self._lidar_powered or not self._source_kalman:
            return self._lidar_powered
        code, _, _ = await self._run_ros2(
            [
                "topic",
                "pub",
                "-t",
                "2",
                "/lidar_power",
                "std_msgs/msg/Bool",
                "{data: true}",
            ],
            timeout=6.0,
        )
        self._lidar_powered = code == 0
        return self._lidar_powered

    async def get_laser_scan(self, max_points: int = 360) -> Dict[str, Any]:
        """
        Lee /scan y reduce puntos para la HMI (evita payloads enormes).
        """
        if self._source_kalman:
            await self.ensure_lidar_powered()

        code, out, err = await self._run_ros2(
            ["topic", "echo", "/scan", "--once"],
            timeout=15.0,
        )
        if code != 0:
            # Reintento tras forzar power
            if self._source_kalman:
                self._lidar_powered = False
                await self.ensure_lidar_powered()
                await asyncio.sleep(1.0)
                code, out, err = await self._run_ros2(
                    ["topic", "echo", "/scan", "--once"],
                    timeout=15.0,
                )
            if code != 0:
                raise RuntimeError(err.strip() or "No se pudo leer /scan (¿LiDAR apagado?)")

        def _f(key: str, default: float = 0.0) -> float:
            m = re.search(rf"{key}:\s*([-\d.eE]+|\.inf|-.inf)", out)
            if not m:
                return default
            raw = m.group(1)
            if "inf" in raw:
                return float("inf") if not raw.startswith("-") else float("-inf")
            return float(raw)

        angle_min = _f("angle_min")
        angle_max = _f("angle_max")
        angle_increment = _f("angle_increment", 0.01)
        range_min = _f("range_min", 0.15)
        range_max = _f("range_max", 12.0)
        frame_m = re.search(r"frame_id:\s*['\"]?([^\s'\"]+)", out)
        frame_id = frame_m.group(1) if frame_m else "laser"

        # Extraer bloque ranges
        ranges_block = re.search(r"ranges:\s*\n((?:\s*-\s*.+\n)+)", out)
        values: List[Optional[float]] = []
        if ranges_block:
            for line in ranges_block.group(1).splitlines():
                item = line.strip().lstrip("-").strip()
                if not item:
                    continue
                if "inf" in item:
                    values.append(None)
                else:
                    try:
                        values.append(float(item))
                    except ValueError:
                        values.append(None)

        # Downsample
        n = len(values)
        if n == 0:
            raise RuntimeError("LaserScan vacío")
        step = max(1, n // max(32, min(max_points, 720)))
        compact: List[Optional[float]] = []
        for i in range(0, n, step):
            v = values[i]
            if v is None or not math.isfinite(v):
                compact.append(None)
            elif v < range_min or v > range_max:
                compact.append(None)
            else:
                compact.append(round(v, 3))

        return {
            "frame_id": frame_id,
            "angle_min": angle_min,
            "angle_max": angle_max,
            "angle_increment": angle_increment * step,
            "range_min": range_min,
            "range_max": range_max,
            "ranges": compact,
            "count": len(compact),
            "original_count": n,
        }

    def get_provider_name(self) -> str:
        return f"rclpy:{self._profile_id}@domain{self._domain_id}"
