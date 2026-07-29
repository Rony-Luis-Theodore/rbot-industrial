"""
Comandos de movimiento obvios (avanza / retrocede / gira / detén / zonas / planes).

Se resuelven ANTES del LLM para que un operario sin ROS nunca reciba
"no puedo girar" ante una instrucción trivial, y para planes multi-paso.
"""

from __future__ import annotations

import re
from typing import Optional

from app.core.constants import (
    INTENT_CANCEL_NAVIGATION,
    INTENT_NAVIGATE,
    INTENT_RETURN_HOME,
    INTENT_SEQUENCE,
    INTENT_UNKNOWN,
)
from app.domain.models.chat import LLMIntent
from app.services.lab_zones import resolve_zone
from app.services.motion_plan import normalize_steps, parse_compound_instruction


def is_stop_phrase(instruction: str) -> bool:
    """True si el texto es una parada (útil en la HMI para no bloquear el chat)."""
    text = (instruction or "").strip().lower()
    if not text:
        return False
    if re.search(r"para\s+atr[aá]s|para\s+atras", text):
        return False
    return bool(
        re.search(
            r"\b(det[eé]n(?:te)?|cancela(?:r)?|frena(?:r)?|stop|halt|emergency|"
            r"e-?stop|para(?:r)?(?!\s+atr))\b",
            text,
        )
    )


def try_parse_motion_command(instruction: str) -> Optional[LLMIntent]:
    """
    Si el texto es un mando básico o plan multi-paso, devuelve LLMIntent.
    Si no, None (sigue el flujo LLM).
    """
    text = (instruction or "").strip().lower()
    if not text:
        return None

    # Plan compuesto ANTES de mandos sueltos
    compound = parse_compound_instruction(instruction)
    if compound and any(s.get("op") == "goto" for s in compound):
        return _intent(
            INTENT_UNKNOWN,
            "unknown_action",
            {},
            raw="motion_guard:zone_unavailable",
            confidence=0.9,
            reply=(
                "En esta versión no hay rutas a zonas nombradas del mapa. "
                "Usa avances, giros y planes con distancias y ángulos."
            ),
        )
    if compound and len(compound) >= 2:
        return _intent(
            INTENT_SEQUENCE,
            "execute_motion_plan",
            {"steps": normalize_steps(compound)},
            raw="motion_guard:sequence",
            confidence=0.92,
        )
    if compound and len(compound) == 1:
        step = compound[0]
        if step.get("op") == "goto":
            # Zonas nombradas no delimitadas en mapa v1
            return _intent(
                INTENT_UNKNOWN,
                "unknown_action",
                {},
                raw="motion_guard:zone_unavailable",
                confidence=0.9,
                reply=(
                    "En esta versión no hay rutas a zonas nombradas del mapa. "
                    "Usa avances, giros y planes con distancias y ángulos."
                ),
            )
        if step.get("op") in ("drive", "turn", "wait"):
            return _intent(
                INTENT_SEQUENCE,
                "execute_motion_plan",
                {"steps": [step]},
                raw="motion_guard:metric",
            )

    if re.search(
        r"\b(retrocede|retroceder|atr[aá]s|atras|reverse|backward|back)\b"
        r"|para\s+atr[aá]s|para\s+atras|marcha\s+atr[aá]s",
        text,
    ) and not re.search(r"\d", text):
        return _intent(
            INTENT_NAVIGATE,
            "send_navigation_goal",
            {"destination": "atras"},
            raw="motion_guard:backward",
        )

    if is_stop_phrase(text):
        return _intent(
            INTENT_CANCEL_NAVIGATION,
            "cancel_navigation",
            {},
            raw="motion_guard:stop",
        )

    if re.search(r"\b(regresa|vuelve|atra(c|q)|dock|base|home)\b", text):
        if re.search(r"regresa|vuelve|atra|dock|home|a\s+la\s+base|a\s+base", text):
            return _intent(
                INTENT_RETURN_HOME,
                "return_home",
                {},
                raw="motion_guard:home",
            )

    if re.search(r"(gira|volte|rota|turn).{0,40}\d+", text):
        one = parse_compound_instruction(instruction)
        if one:
            return _intent(
                INTENT_SEQUENCE,
                "execute_motion_plan",
                {"steps": normalize_steps(one)},
                raw="motion_guard:turn_deg",
            )

    if re.search(
        r"(gira|girar|rota|rotar|vuelta|turn|spin).{0,24}(derecha|right)"
        r"|(derecha|right).{0,12}(gira|girar|rota|turn)",
        text,
    ) or re.search(r"^(derecha|right)$", text):
        return _intent(
            INTENT_NAVIGATE,
            "send_navigation_goal",
            {"destination": "derecha"},
            raw="motion_guard:turn_right",
        )

    if re.search(
        r"(gira|girar|rota|rotar|vuelta|turn|spin).{0,24}(izquierda|left)"
        r"|(izquierda|left).{0,12}(gira|girar|rota|turn)",
        text,
    ) or re.search(r"^(izquierda|left)$", text):
        return _intent(
            INTENT_NAVIGATE,
            "send_navigation_goal",
            {"destination": "izquierda"},
            raw="motion_guard:turn_left",
        )

    if re.search(r"(avanza|adelante|forward|retrocede).{0,20}\d+", text):
        one = parse_compound_instruction(instruction)
        if one:
            return _intent(
                INTENT_SEQUENCE,
                "execute_motion_plan",
                {"steps": normalize_steps(one)},
                raw="motion_guard:drive_m",
            )

    if re.search(
        r"\b(avanza|avanzar|adelante|recto|forward|l[ií]nea\s+recta)\b",
        text,
    ) and not re.search(
        r"\b(estaci[oó]n|fuga|inspecci[oó]n|ve a|voy a|ir a|navega|almac[eé]n|"
        r"recepci|oficina|sala|pasillo|centro)\b",
        text,
    ):
        return _intent(
            INTENT_NAVIGATE,
            "send_navigation_goal",
            {"destination": "adelante"},
            raw="motion_guard:forward",
        )

    if re.search(
        r"\b(voy a|ve a|ve al|ir a|ir al|dir[ií]gete|navega a|go to)\b",
        text,
    ):
        m = re.search(
            r"(?:voy a|ve a|ve al|ir a|ir al|dir[ií]gete a|navega a|navega al|go to)"
            r"\s+(?:la\s+|el\s+|al\s+)?(.+)",
            text,
            re.I,
        )
        dest = m.group(1).strip().rstrip(".") if m else text
        zone = resolve_zone(dest)
        if zone:
            return _intent(
                INTENT_UNKNOWN,
                "unknown_action",
                {},
                raw="motion_guard:zone_unavailable",
                confidence=0.9,
                reply=(
                    "En esta versión no hay rutas a zonas nombradas del mapa. "
                    "Usa avances, giros y planes con distancias y ángulos."
                ),
            )

    return None


def _intent(
    intent: str,
    action: str,
    parameters: dict,
    *,
    raw: str,
    confidence: float = 0.99,
    reply: str = "",
) -> LLMIntent:
    return LLMIntent(
        intent=intent,
        action=action,
        parameters=parameters,
        confidence=confidence,
        raw_response=raw,
        reply=reply,
    )
