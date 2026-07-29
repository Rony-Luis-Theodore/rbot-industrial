"""
=============================================================================
R-Bot — Servicio: Orquestador de Chat (ChatOrchestrator)
=============================================================================

Propósito:
    Núcleo de la lógica de negocio del chat. Coordina el flujo completo:
    instrucción del usuario → LLM → acción ROS → respuesta al operario.

Qué hace:
    1. Recibe mensaje del usuario.
    2. Envía al LLMService para detectar intención.
    3. Ejecuta acción ROS correspondiente según la intención.
    4. Construye respuesta legible para el frontend.
    5. Registra eventos en EventLogger.

Conexión con el resto:
    - POST /api/v1/chat delega aquí (NO contiene lógica de negocio).
    - Depende de LLMService y ROSService (interfaces, no implementaciones).
    - Usa EventLogger para trazabilidad.

Principio SOLID:
    - Single Responsibility: solo orquesta, no implementa LLM ni ROS.
    - Open/Closed: nuevas intenciones se agregan en _execute_ros_action().
    - Dependency Inversion: depende de abstracciones (interfaces).

Para el integrante del LLM:
    NO modificar este archivo al conectar el LLM real.
    Solo implementar LLMService.process_user_instruction().
=============================================================================
"""

from typing import Any, Optional

from app.core.constants import (
    EVENT_LEVEL_ERROR,
    EVENT_LEVEL_INFO,
    EVENT_LEVEL_SUCCESS,
    INTENT_CANCEL_NAVIGATION,
    INTENT_GET_BATTERY,
    INTENT_GET_STATUS,
    INTENT_HELP,
    INTENT_LIST_ACTIONS,
    INTENT_LIST_NODES,
    INTENT_LIST_SERVICES,
    INTENT_LIST_TOPICS,
    INTENT_NAVIGATE,
    INTENT_RETURN_HOME,
    INTENT_SEQUENCE,
    INTENT_UNKNOWN,
)
from app.domain.interfaces.llm_service import LLMService
from app.domain.interfaces.ros_service import ROSService
from app.domain.models.chat import LLMIntent
from app.schemas.chat import ChatResponse, LLMIntentResponse
from app.services.event_logger import EventLogger
from app.services.motion_commands import try_parse_motion_command


class ChatOrchestrator:
    """
    Orquestador central del flujo conversacional R-Bot.

    Coordina LLM + ROS sin acoplarse a implementaciones concretas.
    """

    def __init__(
        self,
        llm_service: LLMService,
        ros_service: ROSService,
        event_logger: EventLogger,
    ):
        """
        Args:
            llm_service: Adapter LLM inyectado.
            ros_service: Adapter ROS inyectado.
            event_logger: Servicio de registro de eventos.
        """
        self._llm = llm_service
        self._ros = ros_service
        self._logger = event_logger

    async def process_message(self, message: str) -> ChatResponse:
        """
        Procesa un mensaje del operario de principio a fin.

        Args:
            message: Instrucción en lenguaje natural.

        Returns:
            ChatResponse con respuesta textual, intención y datos ROS.
        """
        self._logger.log(
            f"Instrucción recibida: \"{message[:80]}{'...' if len(message) > 80 else ''}\"",
            level=EVENT_LEVEL_INFO,
            source="chat",
        )

        # Paso 1: mandos obvios (gira/avanza/detén) sin depender del LLM
        llm_intent = try_parse_motion_command(message)
        intent_provider = "motion_guard"
        if llm_intent is not None:
            self._logger.log(
                f"Motion guard: {llm_intent.intent} → {llm_intent.parameters}",
                level=EVENT_LEVEL_INFO,
                source="motion_guard",
                metadata={"confidence": llm_intent.confidence},
            )
        else:
            llm_intent = await self._llm.process_user_instruction(message)
            intent_provider = self._llm.get_provider_name()
            self._logger.log(
                f"LLM [{intent_provider}] detectó: {llm_intent.intent} → {llm_intent.action}",
                level=EVENT_LEVEL_INFO,
                source="llm",
                metadata={"confidence": llm_intent.confidence},
            )

        # Paso 2: Ejecutar acción ROS según intención
        ros_data = await self._execute_ros_action(llm_intent)

        # Paso 3: Construir respuesta legible
        reply = self._build_reply(message, llm_intent, ros_data)

        self._logger.log(
            f"Respuesta generada para operario",
            level=EVENT_LEVEL_SUCCESS,
            source="chat",
        )

        return ChatResponse(
            reply=reply,
            intent=LLMIntentResponse(
                intent=llm_intent.intent,
                action=llm_intent.action,
                parameters=llm_intent.parameters,
                confidence=llm_intent.confidence,
                provider=intent_provider,
            ),
            ros_data=ros_data,
        )

    async def _execute_ros_action(self, intent: LLMIntent) -> Optional[Any]:
        """
        Mapea intención LLM a método ROSService correspondiente.

        Args:
            intent: Intención estructurada del LLM.

        Returns:
            Datos resultantes de la acción ROS, o None si no aplica.
        """
        intent_map = {
            INTENT_LIST_TOPICS: self._ros.get_topics,
            INTENT_LIST_NODES: self._ros.get_nodes,
            INTENT_LIST_SERVICES: self._ros.get_services,
            INTENT_LIST_ACTIONS: self._ros.get_actions,
            INTENT_CANCEL_NAVIGATION: self._ros.cancel_navigation,
            INTENT_RETURN_HOME: self._ros.return_home,
        }

        if intent.intent in intent_map:
            result = await intent_map[intent.intent]()
            self._logger.log(
                f"ROS ejecutó: {intent.action}",
                level=EVENT_LEVEL_SUCCESS,
                source="ros",
            )
            # Convertir dataclass a dict si es necesario
            if hasattr(result, "__dataclass_fields__"):
                from dataclasses import asdict
                return asdict(result)
            return result

        if intent.intent == INTENT_NAVIGATE:
            destination = intent.parameters.get("destination", "destino")
            result = await self._ros.send_navigation_goal(destination)
            self._logger.log(
                f"Navegación enviada a: {destination}",
                level=EVENT_LEVEL_SUCCESS,
                source="ros",
            )
            return result

        if intent.intent == INTENT_SEQUENCE:
            steps = intent.parameters.get("steps") or []
            result = await self._ros.execute_motion_plan(steps)
            self._logger.log(
                f"Plan multi-paso ({len(steps)} ops)",
                level=EVENT_LEVEL_SUCCESS,
                source="ros",
            )
            return result

        if intent.intent == INTENT_GET_STATUS:
            status = await self._ros.get_status()
            from dataclasses import asdict

            data = asdict(status) if hasattr(status, "__dataclass_fields__") else status
            self._logger.log("Estado consultado", level=EVENT_LEVEL_INFO, source="ros")
            return data

        if intent.intent == INTENT_GET_BATTERY:
            status = await self._ros.get_status()
            pct = getattr(status, "battery_percent", None)
            if pct is None and isinstance(status, dict):
                pct = status.get("battery_percent")
            self._logger.log("Batería consultada", level=EVENT_LEVEL_INFO, source="ros")
            return {"battery_percent": pct}

        if intent.intent == INTENT_HELP:
            return {"ok": True}

        if intent.intent == INTENT_UNKNOWN:
            self._logger.log(
                "Intención no reconocida por el LLM",
                level=EVENT_LEVEL_ERROR,
                source="llm",
            )
            return None

        return None

    def _build_reply(
        self,
        message: str,
        intent: LLMIntent,
        ros_data: Optional[Any],
    ) -> str:
        """
        Construye respuesta textual amigable para el operario.
        Prioriza reply del modelo fine-tuned cuando aporta datos ROS.
        """
        llm_reply = (intent.reply or "").strip()

        if intent.intent == INTENT_UNKNOWN:
            return llm_reply or (
                "Eso queda fuera de lo que puedo hacer con el robot. "
                "Puedo moverlo (avanzar, girar, planes paso a paso), "
                "llevarlo a una zona del lab, detenerlo o consultar estado y batería. "
                "Cuéntame qué movimiento necesitas, en lenguaje natural."
            )

        if intent.intent == INTENT_HELP:
            return llm_reply or (
                "Habla como con un operador: por ejemplo combina avances y giros "
                "con distancias y ángulos, o pide ir a una zona del lab. "
                "También puedo detener el robot y decirte estado o batería. "
                "Si el tema no es navegación, te lo digo y no invento comandos."
            )

        if intent.intent == INTENT_GET_STATUS and ros_data:
            conn = ros_data.get("connection", "—")
            mode = ros_data.get("mode", "—")
            batt = ros_data.get("battery_percent", "—")
            pos = ros_data.get("position") or {}
            base = (
                f"Estado: {conn} · modo {mode} · batería {batt}% · "
                f"pose ({pos.get('x', 0):.2f}, {pos.get('y', 0):.2f})"
            )
            return f"{llm_reply} {base}".strip() if llm_reply else base

        if intent.intent == INTENT_GET_BATTERY and ros_data:
            pct = ros_data.get("battery_percent", "—")
            base = f"Batería: {pct}%"
            return f"{llm_reply} {base}".strip() if llm_reply else base

        if intent.intent == INTENT_LIST_TOPICS and ros_data:
            items = ros_data.get("items", [])
            return f"Topics activos ({len(items)}):\n" + "\n".join(f"  • {t}" for t in items)

        if intent.intent == INTENT_LIST_NODES and ros_data:
            items = ros_data.get("items", [])
            return f"Nodos activos ({len(items)}):\n" + "\n".join(f"  • {n}" for n in items)

        if intent.intent == INTENT_LIST_SERVICES and ros_data:
            items = ros_data.get("items", [])
            return f"Servicios disponibles ({len(items)}):\n" + "\n".join(f"  • {s}" for s in items)

        if intent.intent == INTENT_LIST_ACTIONS and ros_data:
            items = ros_data.get("items", [])
            return f"Actions disponibles ({len(items)}):\n" + "\n".join(f"  • {a}" for a in items)

        if intent.intent == INTENT_NAVIGATE and ros_data:
            return ros_data.get(
                "message",
                llm_reply
                or f"Navegando hacia {intent.parameters.get('destination', 'destino')}...",
            )

        if intent.intent == INTENT_SEQUENCE and ros_data:
            return ros_data.get(
                "message",
                llm_reply or "Ejecución terminada.",
            )

        if intent.intent == INTENT_CANCEL_NAVIGATION and ros_data:
            return ros_data.get("message", llm_reply or "Navegación cancelada.")

        if intent.intent == INTENT_RETURN_HOME and ros_data:
            return ros_data.get("message", llm_reply or "Regresando a la base...")

        return llm_reply or intent.raw_response or f"Acción procesada: {intent.action}"
