"""
=============================================================================
R-Bot — Adapter LLM: Mock (implementación simulada)
=============================================================================

Propósito:
    Implementación de prueba de LLMService que simula respuestas del LLM
    sin conectar ningún modelo de IA real.

Qué hace:
    - Analiza palabras clave en la instrucción del usuario.
    - Devuelve LLMIntent con intención y acción ROS equivalente simulada.
    - Prefijo "MOCK ->" en raw_response para identificar respuestas simuladas.

Conexión con el resto:
    - Implementa domain/interfaces/llm_service.py.
    - Instanciado por service_factory cuando LLM_PROVIDER=mock.
    - Reemplazado por OpenAI/Ollama/etc. cambiando solo .env y factory.

Para el integrante del LLM:
    Este adapter es referencia de QUÉ debe devolver process_user_instruction().
    La lógica de keywords aquí es temporal — el LLM real usará NLP.
=============================================================================
"""

import re
from typing import Dict, Optional, Tuple

from app.core.constants import (
    INTENT_CANCEL_NAVIGATION,
    INTENT_LIST_ACTIONS,
    INTENT_LIST_NODES,
    INTENT_LIST_SERVICES,
    INTENT_LIST_TOPICS,
    INTENT_NAVIGATE,
    INTENT_RETURN_HOME,
    INTENT_UNKNOWN,
)
from app.domain.interfaces.llm_service import LLMService
from app.domain.models.chat import LLMIntent


class MockLLMService(LLMService):
    """
    Servicio LLM simulado basado en coincidencia de palabras clave.

    Traduce instrucciones comunes a intenciones ROS sin usar IA real.
    """

    # Orden importa: parada y listados antes que navegación genérica.
    # Mapa de patrones regex → (intent, action_template)
    _PATTERNS: Dict[str, Tuple[str, str]] = {
        r"topic": (INTENT_LIST_TOPICS, "ros2 topic list"),
        r"nodo|node": (INTENT_LIST_NODES, "ros2 node list"),
        r"servicio|service": (INTENT_LIST_SERVICES, "ros2 service list"),
        r"accion|action": (INTENT_LIST_ACTIONS, "ros2 action list"),
        r"retrocede|retroceder|atr[aá]s|atras|reverse|backward|para\s+atr": (
            INTENT_NAVIGATE,
            "send_navigation_goal",
        ),
        r"det[eé]n|cancela|parar|frena|stop|halt": (INTENT_CANCEL_NAVIGATION, "cancel_navigation"),
        r"regresa|vuelve|atra(c|q)|dock|base|home|inicio": (INTENT_RETURN_HOME, "return_home"),
        r"gira|girar|rota|rotar|vuelta|turn\s+(left|right)|izquierda|derecha": (
            INTENT_NAVIGATE,
            "send_navigation_goal",
        ),
        r"avanza|adelante|recto|forward|ve a|voy a|ir a|navega|dir[ií]gete|revisar|fuga|undock|desatra|sala|recepci|almac[eé]n|oficina|centro|pasillo": (
            INTENT_NAVIGATE,
            "send_navigation_goal",
        ),
    }

    async def process_user_instruction(self, instruction: str) -> LLMIntent:
        """
        Simula el procesamiento LLM mediante análisis de keywords.

        Args:
            instruction: Texto del operario en lenguaje natural.

        Returns:
            LLMIntent con intención detectada y acción ROS simulada.
        """
        instruction_lower = instruction.lower().strip()
        intent, action = self._match_intent(instruction_lower)

        parameters: Dict[str, str] = {}
        if intent == INTENT_NAVIGATE:
            parameters["destination"] = self._extract_destination(instruction)

        raw_response = f"MOCK -> {action}"
        if parameters:
            raw_response += f" | params: {parameters}"

        return LLMIntent(
            intent=intent,
            action=action,
            parameters=parameters,
            confidence=0.85 if intent != INTENT_UNKNOWN else 0.3,
            raw_response=raw_response,
        )

    def get_provider_name(self) -> str:
        """Retorna identificador del proveedor mock."""
        return "mock"

    def _match_intent(self, instruction: str) -> Tuple[str, str]:
        """
        Busca coincidencia de patrones en la instrucción.

        Args:
            instruction: Texto normalizado en minúsculas.

        Returns:
            Tupla (intent, action). Si no hay match, retorna unknown.
        """
        for pattern, (intent, action) in self._PATTERNS.items():
            if re.search(pattern, instruction, re.IGNORECASE):
                return intent, action
        return INTENT_UNKNOWN, "unknown_action"

    def _extract_destination(self, instruction: str) -> str:
        """
        Extrae destino de navegación del texto (heurística simple).

        Args:
            instruction: Texto original del usuario.

        Returns:
            Destino extraído o cadena genérica si no se detecta.
        """
        text = instruction.lower()
        if re.search(
            r"(gira|girar|rota|turn|vuelta).{0,24}(derecha|right)|(derecha|right).{0,12}(gira|turn)",
            text,
        ):
            return "derecha"
        if re.search(
            r"(gira|girar|rota|turn|vuelta).{0,24}(izquierda|left)|(izquierda|left).{0,12}(gira|turn)",
            text,
        ):
            return "izquierda"
        if re.search(
            r"retrocede|retroceder|atr[aá]s|atras|reverse|backward|para\s+atr",
            text,
        ):
            return "atras"
        if re.search(r"avanza|adelante|recto|forward|l[ií]nea\s+recta", text):
            return "adelante"
        if re.search(r"undock|desatra|desacoplar", text):
            return "undock"

        from app.services.lab_zones import resolve_zone

        # Patrones comunes: "voy a X", "ve a X", "ir a X"
        patterns = [
            r"(?:voy a|ve a|ir a|navega a|dirígete a)\s+(?:la\s+|el\s+|al\s+)?(.+)",
            r"revisar\s+(?:la\s+)?(.+)",
            r"fuga\s+(?:de\s+)?(?:la\s+)?(.+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, instruction, re.IGNORECASE)
            if match:
                raw = match.group(1).strip().rstrip(".")
                zone = resolve_zone(raw)
                return zone["id"] if zone else raw

        # "sala de máquinas" sin verbo
        zone = resolve_zone(text)
        if zone:
            return zone["id"]
        return "destino_no_especificado"
