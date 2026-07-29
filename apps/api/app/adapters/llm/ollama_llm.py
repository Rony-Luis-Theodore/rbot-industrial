"""
=============================================================================
R-Bot — Adapter LLM: Ollama (modelos locales)
=============================================================================

Propósito:
    Traducir instrucciones en lenguaje natural a LLMIntent usando un modelo
    local servido por Ollama (sin API keys externas).

Qué hace:
    - Envía system prompt + instrucción del operario a Ollama (/api/chat).
    - Exige respuesta JSON con intent, action, parameters, confidence.
    - Valida y normaliza el intent a las constantes del dominio.
    - Si Ollama falla o el JSON es inválido, hace fallback al MockLLM.

Conexión con el resto:
    - Implementa domain/interfaces/llm_service.py.
    - Se activa con LLM_PROVIDER=ollama en .env.
    - Usa OLLAMA_BASE_URL y OLLAMA_MODEL desde config.

Requisitos:
    1. Ollama instalado y corriendo (`ollama serve`).
    2. Modelo descargado (recomendado en 8 GB RAM: qwen2.5:1.5b o gemma2:2b).
       Ejemplo: ollama pull qwen2.5:1.5b
=============================================================================
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

import httpx

from app.adapters.llm.mock_llm import MockLLMService
from app.core.constants import (
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
from app.core.exceptions import LLMProcessingError
from app.domain.interfaces.llm_service import LLMService
from app.domain.models.chat import LLMIntent

logger = logging.getLogger(__name__)

# Mapa intent → acción ROS canónica
_INTENT_ACTIONS: Dict[str, str] = {
    INTENT_LIST_TOPICS: "ros2 topic list",
    INTENT_LIST_NODES: "ros2 node list",
    INTENT_LIST_SERVICES: "ros2 service list",
    INTENT_LIST_ACTIONS: "ros2 action list",
    INTENT_NAVIGATE: "send_navigation_goal",
    INTENT_SEQUENCE: "execute_motion_plan",
    INTENT_CANCEL_NAVIGATION: "cancel_navigation",
    INTENT_RETURN_HOME: "return_home",
    INTENT_GET_STATUS: "get_robot_status",
    INTENT_GET_BATTERY: "get_battery",
    INTENT_HELP: "help",
    INTENT_UNKNOWN: "unknown_action",
}

_VALID_INTENTS = set(_INTENT_ACTIONS.keys())

_SYSTEM_PROMPT = """Eres el copiloto conversacional del robot industrial R-Bot (Nexus / Create3 + ROS2).
El operario habla en español o inglés, como en un chatbot: frases naturales, no menús de comandos.
Debes:
1) Clasificar UNA intención
2) Escribir una reply breve y natural en español (nunca listas de «di exactamente…»)

Intenciones válidas (campo "intent"):
- list_topics, list_nodes, list_services, list_actions
- navigate: un solo movimiento cardinal (params.destination)
- sequence: plan multi-paso o cualquier orden con distancia/ángulo (params.steps)
- cancel_navigation: detener / parar / frenar
- return_home: regresar a base / atracar / dock
- get_status: estado / conexión / modo del robot
- get_battery: nivel de batería
- help: orientación general
- unknown: fuera de dominio O rutas a zonas nombradas (almacén, válvula, pasillo…) — aún no hay mapa de zonas

Reglas navigate (un solo paso sin métrica):
- avanza/adelante → "adelante"
- retrocede/atrás → "atras"
- gira derecha → "derecha" | gira izquierda → "izquierda"
- undock → "undock"
NO uses navigate hacia almacén/oficina/válvula/etc.: usa unknown con reply educada.

Reglas sequence (varios pasos U órdenes métricas):
Usa intent=sequence y parameters.steps. Cada step:
- {"op":"drive","meters":0.3}  (negativo = atrás)
- {"op":"turn","degrees":45}   (positivo=izquierda, negativo=derecha)
- {"op":"wait","seconds":5}
- {"op":"stop"}
NO uses op=goto en esta versión.

Unidades → siempre meters en JSON:
- cm / centímetros → /100 (30 cm → 0.3)
- m / metros → tal cual (0.8 metros → 0.8)
- pulgadas / inches / in → ×0.0254
- pies / feet / ft / pie → ×0.3048

Ángulos: si hay número junto a gira/volte/rota + izquierda/derecha, son GRADOS
aunque no digan «grados» («gira 45 a la derecha» → turn -45).

Conectores de secuencia (partir en steps):
primero / en primer lugar / primeramente / luego / después / a continuación /
acto seguido / seguidamente / por último / finalmente / then / and then / comas.

Ejemplos → sequence:
- "avanza 0.8 metros, gira 90 grados a la derecha, avanza 0.5 metros"
- "en primer lugar avanza 80 cm después gira 90 a la derecha por último avanza 50 cm"
- "gira 45 a la derecha"  (sin palabra grados)
- "avanza 2 pies luego gira 90 a la izquierda finalmente avanza 12 pulgadas"

NUNCA uses unknown para giros, avance, retroceso o planes mixtos métricos.
"para atrás" NO es cancel: es navigate "atras".
"detén"/"para"(solo) → cancel_navigation.

Responde ÚNICAMENTE JSON válido (sin markdown):
{"intent":"...","action":"...","parameters":{},"confidence":0.0,"reply":"..."}
"""


class OllamaLLMService(LLMService):
    """
    Adapter LLM local vía Ollama con salida JSON estructurada.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:1.5b",
        timeout_s: float = 120.0,
        fallback_to_mock: bool = True,
    ):
        """
        Args:
            base_url: URL del servidor Ollama.
            model: Nombre del modelo local.
            timeout_s: Timeout HTTP por petición.
            fallback_to_mock: Si True, usa MockLLM cuando Ollama falla.
        """
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_s = timeout_s
        self._fallback_to_mock = fallback_to_mock
        self._mock = MockLLMService()

    async def process_user_instruction(self, instruction: str) -> LLMIntent:
        """
        Clasifica la instrucción del operario con Ollama.

        Returns:
            LLMIntent listo para ChatOrchestrator.
        """
        try:
            raw = await self._chat(instruction)
            parsed = self._parse_json(raw)
            intent = self._normalize(parsed, raw)
            if intent.intent == INTENT_UNKNOWN and self._fallback_to_mock:
                # Refuerzo: keywords del mock si el modelo duda
                mock_intent = await self._mock.process_user_instruction(instruction)
                if mock_intent.intent != INTENT_UNKNOWN:
                    mock_intent.raw_response = f"OLLAMA(unknown)→MOCK | {raw[:200]}"
                    return mock_intent
            return intent
        except Exception as exc:  # noqa: BLE001 — capturar y degradar con gracia
            logger.warning("Ollama falló (%s). Fallback mock=%s", exc, self._fallback_to_mock)
            if self._fallback_to_mock:
                mock_intent = await self._mock.process_user_instruction(instruction)
                mock_intent.raw_response = f"OLLAMA_ERROR→MOCK ({exc}) | {mock_intent.raw_response}"
                return mock_intent
            raise LLMProcessingError(f"Ollama no disponible: {exc}") from exc

    def get_provider_name(self) -> str:
        return f"ollama:{self._model}"

    async def _chat(self, instruction: str) -> str:
        """Llama a POST /api/chat de Ollama (stream=false)."""
        payload = {
            "model": self._model,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,
                "num_predict": 360,
            },
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": instruction},
            ],
        }
        url = f"{self._base_url}/api/chat"
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
        content = (data.get("message") or {}).get("content") or data.get("response") or ""
        if not content.strip():
            raise LLMProcessingError("Ollama devolvió respuesta vacía")
        return content

    def _parse_json(self, raw: str) -> Dict[str, Any]:
        """Extrae el primer objeto JSON de la respuesta del modelo."""
        text = raw.strip()
        # Quitar fences ```json ... ```
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence:
            text = fence.group(1)
        else:
            brace = re.search(r"\{.*\}", text, re.DOTALL)
            if brace:
                text = brace.group(0)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMProcessingError(f"JSON inválido de Ollama: {exc}") from exc
        if not isinstance(data, dict):
            raise LLMProcessingError("La respuesta JSON no es un objeto")
        return data

    def _normalize(self, data: Dict[str, Any], raw: str) -> LLMIntent:
        """Valida intent/action/parameters y aplica defaults seguros."""
        intent = str(data.get("intent") or INTENT_UNKNOWN).strip().lower()
        # Alias frecuentes del modelo
        aliases = {
            "list_topic": INTENT_LIST_TOPICS,
            "topics": INTENT_LIST_TOPICS,
            "nodes": INTENT_LIST_NODES,
            "list_node": INTENT_LIST_NODES,
            "services": INTENT_LIST_SERVICES,
            "actions": INTENT_LIST_ACTIONS,
            "stop": INTENT_CANCEL_NAVIGATION,
            "cancel": INTENT_CANCEL_NAVIGATION,
            "home": INTENT_RETURN_HOME,
            "dock": INTENT_RETURN_HOME,
            "go": INTENT_NAVIGATE,
            "move": INTENT_NAVIGATE,
            "drive": INTENT_NAVIGATE,
            "sequence": INTENT_SEQUENCE,
            "plan": INTENT_SEQUENCE,
            "multi": INTENT_SEQUENCE,
            "execute_plan": INTENT_SEQUENCE,
            "execute_motion_plan": INTENT_SEQUENCE,
            "status": INTENT_GET_STATUS,
            "battery": INTENT_GET_BATTERY,
            "help": INTENT_HELP,
            "ayuda": INTENT_HELP,
        }
        intent = aliases.get(intent, intent)
        if intent not in _VALID_INTENTS:
            intent = INTENT_UNKNOWN

        action = str(data.get("action") or _INTENT_ACTIONS[intent]).strip()
        # Acciones alias del fine-tune
        action_aliases = {
            "execute_plan": "execute_motion_plan",
            "drive": "send_navigation_goal",
            "move": "send_navigation_goal",
            "go": "send_navigation_goal",
        }
        action = action_aliases.get(action, action)
        if not action:
            action = _INTENT_ACTIONS[intent]

        parameters: Dict[str, Any] = {}
        raw_params = data.get("parameters") or {}
        if isinstance(raw_params, dict):
            parameters = dict(raw_params)

        # Si trae steps[], forzar sequence aunque el intent diga navigate/drive
        steps_raw = parameters.get("steps") or parameters.get("plan")
        if isinstance(steps_raw, list) and steps_raw:
            intent = INTENT_SEQUENCE

        # navigate con meters (sin destination) → sequence drive
        if intent == INTENT_NAVIGATE:
            meters = parameters.get("meters")
            if meters is None and parameters.get("m") is not None:
                meters = parameters.get("m")
            if meters is None and parameters.get("cm") is not None:
                try:
                    meters = float(parameters["cm"]) / 100.0
                except (TypeError, ValueError):
                    meters = None
            dest_probe = (
                parameters.get("destination")
                or parameters.get("destino")
                or parameters.get("goal")
            )
            if meters is not None and not dest_probe:
                intent = INTENT_SEQUENCE
                parameters = {"steps": [{"op": "drive", "meters": float(meters)}]}
                action = _INTENT_ACTIONS[intent]

        if intent == INTENT_NAVIGATE:
            dest = parameters.get("destination") or parameters.get("destino") or parameters.get("goal")
            if not dest:
                dest = "adelante"
            dest_s = str(dest).strip().lower()
            if any(k in dest_s for k in ("derecha", "right")) and not any(
                z in dest_s for z in ("sala", "recep", "almacen", "almacén", "oficina", "centro", "pasillo")
            ):
                dest_s = "derecha"
            elif any(k in dest_s for k in ("izquierda", "left")) and not any(
                z in dest_s for z in ("sala", "recep", "almacen", "almacén", "oficina", "centro", "pasillo")
            ):
                dest_s = "izquierda"
            elif any(
                k in dest_s
                for k in ("atras", "atrás", "retrocede", "reverse", "backward", "back")
            ):
                dest_s = "atras"
            elif any(k in dest_s for k in ("adelante", "avanza", "forward", "recto")):
                dest_s = "adelante"
            else:
                from app.services.lab_zones import resolve_zone

                zone = resolve_zone(dest_s)
                if zone:
                    # Zonas nombradas aún no delimitadas → unknown educado
                    intent = INTENT_UNKNOWN
                    action = _INTENT_ACTIONS[intent]
                    parameters = {}
                    reply_zone = (
                        "En esta versión no hay rutas a zonas nombradas del mapa. "
                        "Usa avances, giros y planes con distancias y ángulos."
                    )
                    try:
                        confidence = float(data.get("confidence", 0.7))
                    except (TypeError, ValueError):
                        confidence = 0.7
                    return LLMIntent(
                        intent=intent,
                        action=action,
                        parameters=parameters,
                        confidence=max(0.0, min(1.0, confidence)),
                        raw_response=raw[:1000],
                        reply=str(data.get("reply") or reply_zone).strip() or reply_zone,
                    )
            parameters = {"destination": dest_s}
            action = _INTENT_ACTIONS[intent]

        if intent == INTENT_SEQUENCE:
            from app.services.motion_plan import normalize_steps

            steps = parameters.get("steps") or parameters.get("plan") or []
            parameters = {"steps": normalize_steps(steps)}
            action = _INTENT_ACTIONS[intent]
            if not parameters["steps"]:
                # Degradar a navigate adelante si el modelo falló el schema
                intent = INTENT_NAVIGATE
                action = _INTENT_ACTIONS[intent]
                parameters = {"destination": "adelante"}

        try:
            confidence = float(data.get("confidence", 0.7))
        except (TypeError, ValueError):
            confidence = 0.7
        confidence = max(0.0, min(1.0, confidence))

        reply = str(data.get("reply") or "").strip()

        return LLMIntent(
            intent=intent,
            action=action,
            parameters=parameters,
            confidence=confidence,
            raw_response=raw[:1000],
            reply=reply,
        )
