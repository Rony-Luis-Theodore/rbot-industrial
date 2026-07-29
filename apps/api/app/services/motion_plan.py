"""
Plan de movimiento multi-paso (goto / drive / turn / wait).

El LLM puede devolver intent=sequence con parameters.steps, o el mock
puede parsear frases mixtas a esta estructura.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.services.lab_zones import resolve_zone

# Factores a metros (robot / odom lab).
_INCH_M = 0.0254
_FOOT_M = 0.3048


def _distance_to_meters(val: float, unit_raw: str, num_token: str, clause: str) -> float:
    """Convierte número + unidad (o heurística sin unidad) a metros."""
    u = (unit_raw or "").lower().strip()
    t = (clause or "").lower()
    if u.startswith("c") or "cent" in u:
        return val / 100.0
    if u in ("in", "inch", "inches") or u.startswith("pulg"):
        return val * _INCH_M
    if u in ("ft", "feet", "foot") or u.startswith("pie"):
        return val * _FOOT_M
    if u.startswith("m") or u in ("metro", "metros"):
        return val
    # Refuerzo por palabras en la cláusula
    if re.search(r"pulgada|inch", t):
        return val * _INCH_M
    if re.search(r"\bpie(?:s)?\b|\bfeet\b|\bfoot\b|\bft\b", t):
        return val * _FOOT_M
    if re.search(r"cent[ií]metro", t):
        return val / 100.0
    if re.search(r"\bmetros?\b", t):
        return val
    # Sin unidad: enteros ≥5 → cm hablados; decimal o <5 → metros
    if "." in num_token or "," in num_token:
        return val
    if val >= 5:
        return val / 100.0
    return val


def normalize_steps(raw_steps: Any) -> List[Dict[str, Any]]:
    """Normaliza steps heterogéneos del LLM a ops canónicas."""
    if not isinstance(raw_steps, list):
        return []
    out: List[Dict[str, Any]] = []
    for step in raw_steps:
        if not isinstance(step, dict):
            continue
        op = str(step.get("op") or step.get("action") or step.get("type") or "").strip().lower()
        if op in ("goto", "navigate", "go", "ve", "ir"):
            dest = step.get("destination") or step.get("destino") or step.get("zone") or ""
            zone = resolve_zone(str(dest))
            out.append(
                {
                    "op": "goto",
                    "destination": zone["id"] if zone else str(dest).strip().lower(),
                }
            )
        elif op in ("wait", "espera", "sleep", "pause"):
            sec = step.get("seconds") or step.get("sec") or step.get("s") or 1
            try:
                sec_f = float(sec)
            except (TypeError, ValueError):
                sec_f = 1.0
            out.append({"op": "wait", "seconds": max(0.1, min(120.0, sec_f))})
        elif op in ("drive", "avance", "avanza", "forward", "move"):
            dist = step.get("meters") or step.get("m") or step.get("distance")
            if dist is None and step.get("cm") is not None:
                try:
                    dist = float(step["cm"]) / 100.0
                except (TypeError, ValueError):
                    dist = 0.2
            if dist is None and step.get("inches") is not None:
                try:
                    dist = float(step["inches"]) * _INCH_M
                except (TypeError, ValueError):
                    dist = 0.2
            if dist is None and step.get("feet") is not None:
                try:
                    dist = float(step["feet"]) * _FOOT_M
                except (TypeError, ValueError):
                    dist = 0.2
            try:
                dist_f = float(dist if dist is not None else 0.2)
            except (TypeError, ValueError):
                dist_f = 0.2
            out.append({"op": "drive", "meters": max(-2.0, min(2.0, dist_f))})
        elif op in ("turn", "gira", "rotate", "giro"):
            deg = step.get("degrees") or step.get("deg") or step.get("angle")
            direction = str(step.get("direction") or "").lower()
            try:
                deg_f = float(deg) if deg is not None else 90.0
            except (TypeError, ValueError):
                deg_f = 90.0
            if direction in ("left", "izquierda", "ccw") or deg_f > 0 and "izq" in direction:
                # left = positive in ROS yaw
                if deg_f < 0:
                    deg_f = -deg_f
                if direction in ("left", "izquierda", "ccw"):
                    pass
                elif direction in ("right", "derecha", "cw"):
                    deg_f = -abs(deg_f)
            if direction in ("right", "derecha", "cw"):
                deg_f = -abs(deg_f)
            elif direction in ("left", "izquierda", "ccw"):
                deg_f = abs(deg_f)
            out.append({"op": "turn", "degrees": max(-360.0, min(360.0, deg_f))})
        elif op in ("stop", "cancel", "deten"):
            out.append({"op": "stop"})
        # ignore unknown ops silently
    return out


def parse_compound_instruction(text: str) -> Optional[List[Dict[str, Any]]]:
    """
    Heurística para instrucciones mixtas sin LLM:
    «ve a almacén, espera 5 s y luego ve a recepción»
    «avanza 30 cm y gira 45° a la derecha y avanza 40 cm»
    """
    raw = (text or "").strip()
    if not raw:
        return None
    # Partir por conectores (incl. «y» delante de otro verbo de movimiento)
    parts = re.split(
        r"\s*(?:,|;|"
        r"\ben\s+primer\s+lugar\b|\bprimeramente\b|\bprimero\b|"
        r"\bpor\s+[uú]ltimo\b|\bfinalmente\b|\ba\s+continuaci[oó]n\b|"
        r"\bacto\s+seguido\b|\bseguidamente\b|\btras\s+eso\b|"
        r"\by\s+luego\b|\bluego\b|\bafterwards\b|\bthen\b|"
        r"\by\s+despu[eé]s\b|\bdespu[eé]s\b|\band\s+then\b|"
        r"\by\s+(?=avanza|adelante|gira|volte|rota|espera|wait|ve\s|voy\s|retrocede|dir[ií]gete|navega|para\b|det[eé]n|stop)"
        r")\s*",
        raw,
        flags=re.IGNORECASE,
    )
    parts = [p.strip() for p in parts if p and p.strip()]
    if len(parts) < 2:
        # Una sola cláusula puede ser drive/turn con medida
        one = _parse_clause(parts[0] if parts else raw)
        return [one] if one and one.get("op") in ("drive", "turn", "wait", "goto") else None

    steps: List[Dict[str, Any]] = []
    for part in parts:
        step = _parse_clause(part)
        if step:
            steps.append(step)
    return steps if len(steps) >= 2 else (steps if steps else None)


def _parse_clause(clause: str) -> Optional[Dict[str, Any]]:
    t = clause.strip().lower()
    if not t:
        return None

    # Parada al final de un plan («… y para»)
    if re.fullmatch(
        r"(?:y\s+)?(?:det[eé]n(?:te)?|para(?:r)?|stop|halt|frena(?:r)?)",
        t,
    ):
        return {"op": "stop"}

    m = re.search(
        r"(?:espera|wait|paus[ae])\s+(\d+(?:[.,]\d+)?)\s*(s|seg|segs|segundo|segundos|sec|seconds)?",
        t,
    )
    if m:
        return {"op": "wait", "seconds": float(m.group(1).replace(",", "."))}

    # «avanza 30 cm» / «avanza 0.3 metros» / «adelante 12 pulgadas» / «2 pies»
    m = re.search(
        r"(?:avanza|avanzar|adelante|forward|retrocede|atr[aá]s)"
        r"(?:\s+en\s+l[ií]nea\s+recta)?(?:\s+(?:hacia\s+)?(?:adelante|atr[aá]s|forward|back))?"
        r"(?:\s+otros?)?"
        r"\s+(\d+(?:[.,]\d+)?)\s*"
        r"(cm|cent[ií]metro(?:s)?|m|metro(?:s)?|in|inch(?:es)?|pulgada(?:s)?|ft|feet|foot|pie(?:s)?)?",
        t,
    )
    if m:
        val = float(m.group(1).replace(",", "."))
        unit_raw = (m.group(2) or "").lower()
        meters = _distance_to_meters(val, unit_raw, m.group(1), t)
        if re.search(r"retrocede|atr[aá]s|back", t):
            meters = -abs(meters)
        return {"op": "drive", "meters": meters}

    # «gira a la derecha en 45 grados» / «gira 45° a la derecha» / «gira derecha 45»
    m = re.search(
        r"(?:gira|girar|volte[ae]|rota|rotar|turn)\s+"
        r"(?:a\s+la\s+|hacia\s+)?"
        r"(izquierda|derecha|left|right)\s+"
        r"(?:en\s+|unos\s+|de\s+)?"
        r"(\d+(?:[.,]\d+)?)\s*(?:°|deg|grados|degrees)?",
        t,
    )
    if not m:
        m = re.search(
            r"(?:gira|girar|volte[ae]|rota|rotar|turn)\s+"
            r"(\d+(?:[.,]\d+)?)\s*(?:°|deg|grados|degrees)?\s*"
            r"(?:a\s+la\s+|hacia\s+)?(izquierda|derecha|left|right)",
            t,
        )
        if m:
            deg = float(m.group(1).replace(",", "."))
            direction = (m.group(2) or "").lower()
            if direction in ("derecha", "right"):
                deg = -abs(deg)
            else:
                deg = abs(deg)
            return {"op": "turn", "degrees": deg}
    else:
        direction = (m.group(1) or "").lower()
        deg = float(m.group(2).replace(",", "."))
        if direction in ("derecha", "right"):
            deg = -abs(deg)
        else:
            deg = abs(deg)
        return {"op": "turn", "degrees": deg}

    m = re.search(
        r"(?:gira|volte[ae]|rota|turn)\s+"
        r"(?:a\s+la\s+)?"
        r"(izquierda|derecha|left|right)?\s*"
        r"(?:unos\s+)?(\d+(?:[.,]\d+)?)\s*(?:°|deg|grados|degrees)?"
        r"|"
        r"(?:gira|volte[ae]|rota|turn)\s+"
        r"(\d+(?:[.,]\d+)?)\s*(?:°|deg|grados|degrees)?\s*"
        r"(?:a\s+la\s+)?(izquierda|derecha|left|right)?",
        t,
    )
    if m:
        if m.group(2) is not None:
            direction = (m.group(1) or "").lower()
            deg = float(m.group(2).replace(",", "."))
        else:
            deg = float((m.group(3) or "90").replace(",", "."))
            direction = (m.group(4) or "").lower()
        if not direction:
            if re.search(r"derecha|right", t):
                direction = "derecha"
            elif re.search(r"izquierda|left", t):
                direction = "izquierda"
        if direction in ("derecha", "right"):
            deg = -abs(deg)
        else:
            deg = abs(deg)
        return {"op": "turn", "degrees": deg}

    # Giro 90 sin ángulo
    if re.search(r"(?:gira|volte[ae]|rota).{0,20}(izquierda|left)", t):
        return {"op": "turn", "degrees": 90.0}
    if re.search(r"(?:gira|volte[ae]|rota).{0,20}(derecha|right)", t):
        return {"op": "turn", "degrees": -90.0}

    m = re.search(
        r"(?:voy a|ve a|ve al|ir a|ir al|dir[ií]gete a|navega a|navega al|go to)\s+(.+)",
        t,
    )
    if m:
        dest = m.group(1).strip().rstrip(".")
        zone = resolve_zone(dest)
        return {"op": "goto", "destination": zone["id"] if zone else dest}

    zone = resolve_zone(t)
    if zone:
        return {"op": "goto", "destination": zone["id"]}

    return None
