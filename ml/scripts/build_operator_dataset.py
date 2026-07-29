#!/usr/bin/env python3
"""
Genera dataset Operator v3 para R-Bot (lab Occupancy).

Foco v3:
  - Secuencias con conectores textuales (primero, después, finalmente…)
  - Unidades: m, cm, pulgadas, pies → meters en JSON
  - Ángulos: «gira 45 a la derecha» = grados (sin decir «grados»)
  - SIN rutas a zonas nombradas (almacén, válvula…): unknown educado

Salida:
  ml/datasets/operator_v3_es.jsonl
  ml/datasets/operator_v3_sft.jsonl
  (+ espejo v2 para notebooks antiguos)

Uso:
  python3 ml/scripts/build_operator_dataset.py
"""

from __future__ import annotations

import itertools
import json
import random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_RAW = ROOT / "datasets" / "operator_v3_es.jsonl"
OUT_SFT = ROOT / "datasets" / "operator_v3_sft.jsonl"
# Espejo para notebooks que aún piden v2
OUT_RAW_V2 = ROOT / "datasets" / "operator_v2_es.jsonl"
OUT_SFT_V2 = ROOT / "datasets" / "operator_v2_sft.jsonl"

ACTIONS = {
    "list_topics": "ros2 topic list",
    "list_nodes": "ros2 node list",
    "list_services": "ros2 service list",
    "list_actions": "ros2 action list",
    "navigate": "send_navigation_goal",
    "sequence": "execute_motion_plan",
    "cancel_navigation": "cancel_navigation",
    "return_home": "return_home",
    "get_status": "get_robot_status",
    "get_battery": "get_battery",
    "help": "help",
    "unknown": "unknown_action",
}

INCH_M = 0.0254
FOOT_M = 0.3048

ZONE_UNAVAILABLE_REPLY = (
    "En esta versión no hay rutas a zonas nombradas del mapa. "
    "Usa avances, giros y planes paso a paso con distancias y ángulos."
)

rng = random.Random(42)


def row(text: str, intent: str, destination: str | None = None, reply: str | None = None) -> dict:
    if reply is None:
        reply = _default_reply(intent, destination)
    return {
        "text": text.strip(),
        "intent": intent,
        "destination": destination,
        "reply": reply,
    }


def _default_reply(intent: str, destination: str | None) -> str:
    if intent == "list_topics":
        return "Listo, consulto los topics ROS2."
    if intent == "list_nodes":
        return "Voy a listar los nodos activos."
    if intent == "list_services":
        return "Consulto los servicios disponibles."
    if intent == "list_actions":
        return "Consulto las actions ROS2."
    if intent == "cancel_navigation":
        return "Deteniendo el robot ahora."
    if intent == "return_home":
        return "Regresando a la base / dock."
    if intent == "get_status":
        return "Te muestro el estado actual del robot."
    if intent == "get_battery":
        return "Consulto el nivel de batería."
    if intent == "help":
        return (
            "Habla en lenguaje natural: avanza X metros/cm/pulgadas/pies, "
            "gira N (grados) izquierda/derecha, planes con primero/después/finalmente. "
            "Sin rutas a almacén u otras zonas aún."
        )
    if intent == "sequence":
        return "Ejecuto el plan de movimiento paso a paso."
    if intent == "navigate":
        d = destination or "destino"
        if d == "adelante":
            return "Avanzando."
        if d == "atras":
            return "Retrocediendo."
        if d == "derecha":
            return "Girando a la derecha."
        if d == "izquierda":
            return "Girando a la izquierda."
        if d == "undock":
            return "Desatracando del dock."
        return f"Navegando hacia {d}."
    return ZONE_UNAVAILABLE_REPLY if destination else (
        "Eso queda fuera de lo que puedo hacer con el robot. "
        "Puedo avanzar, girar, detener o consultar estado."
    )


def seq_row(text: str, steps: list, reply: str) -> dict:
    return {
        "text": text.strip(),
        "intent": "sequence",
        "destination": None,
        "steps": steps,
        "reply": reply,
    }


def variants(templates: list[str], **fills) -> list[str]:
    out = []
    keys = list(fills.keys())
    values = [fills[k] if isinstance(fills[k], list) else [fills[k]] for k in keys]
    for combo in itertools.product(*values):
        kw = dict(zip(keys, combo))
        for t in templates:
            out.append(t.format(**kw))
    return out


def build() -> list[dict]:
    data: list[dict] = []

    # --- list_topics ---
    for t in variants(
        [
            "{p} los topics",
            "{p} los topics ros",
            "{p} los topics ros2",
            "qué topics hay",
            "qué topics están activos",
            "topics activos",
            "enséñame los topics",
            "quiero ver los topics",
            "show topics",
            "list ros topics",
            "list topics",
            "dame el listado de topics",
            "puedes listar los topics del create3",
            "necesito el listado de topics",
            "cuáles son los topics publicados",
        ],
        p=["muéstrame", "lista", "lista", "dame", "enséñame"],
    ):
        data.append(row(t, "list_topics"))

    # --- list_nodes ---
    for t in [
        "muéstrame los nodos",
        "lista nodos",
        "qué nodos hay",
        "qué nodos hay activos",
        "nodos ros2",
        "nodos activos ahora",
        "list nodes",
        "show nodes",
        "dame los nodos del sistema",
        "cuáles son los nodos",
    ]:
        data.append(row(t, "list_nodes"))

    # --- list_services / actions ---
    for t in [
        "lista servicios",
        "muéstrame los services",
        "qué servicios hay",
        "list services",
        "servicios ros2",
    ]:
        data.append(row(t, "list_services"))
    for t in [
        "lista actions",
        "muéstrame las actions",
        "qué actions hay",
        "list actions",
        "actions ros2",
    ]:
        data.append(row(t, "list_actions"))

    # --- cancel / home / status / battery / help ---
    for t in [
        "detén",
        "detente",
        "para",
        "parar",
        "stop",
        "frena",
        "cancela",
        "cancelar navegación",
        "halt",
        "para ya",
        "detén el robot",
    ]:
        data.append(row(t, "cancel_navigation"))
    for t in [
        "regresa a la base",
        "vuelve a casa",
        "atraca",
        "dock",
        "return home",
        "ve al dock",
        "regresa al cargador",
    ]:
        data.append(row(t, "return_home"))
    for t in [
        "estado",
        "estado del robot",
        "cómo estás",
        "status",
        "conexión",
        "modo del robot",
        "dame el status",
    ]:
        data.append(row(t, "get_status"))
    for t in [
        "batería",
        "nivel de batería",
        "cuánta batería queda",
        "battery",
        "battery level",
    ]:
        data.append(row(t, "get_battery"))
    for t in [
        "ayuda",
        "help",
        "qué puedes hacer",
        "cómo te hablo",
        "instrucciones",
    ]:
        data.append(row(t, "help"))

    # --- navigate cardinal (sin zonas) ---
    for t in variants(
        ["{p}", "por favor {p}", "robot, {p}", "{p} ahora", "{p} por favor"],
        p=[
            "avanza",
            "adelante",
            "sigue adelante",
            "retrocede",
            "atrás",
            "para atrás",
            "gira a la derecha",
            "gira derecha",
            "gira a la izquierda",
            "gira izquierda",
            "volte a la derecha",
            "volte a la izquierda",
        ],
    ):
        low = t.lower()
        if "derecha" in low:
            data.append(row(t, "navigate", "derecha"))
        elif "izquierda" in low:
            data.append(row(t, "navigate", "izquierda"))
        elif "retro" in low or "atrás" in low or "atras" in low:
            data.append(row(t, "navigate", "atras"))
        else:
            data.append(row(t, "navigate", "adelante"))

    for t in ["undock", "desatraca", "sal del dock", "sal del cargador", "undock now"]:
        data.append(row(t, "navigate", "undock"))

    # --- unknown / fuera de dominio ---
    for t in [
        "hola robot",
        "buenos días",
        "gracias",
        "ok",
        "dale",
        "perfecto",
        "cuéntame un chiste",
        "qué tiempo hace mañana",
        "receta de pasta",
        "abre el navegador",
        "resuelve esta integral",
        "código python hello world",
        "qué piensas de la IA",
        "volume up",
        "silencio",
    ]:
        data.append(row(t, "unknown"))

    # Zonas nombradas → unknown (no delimitadas en mapa v1)
    for t in [
        "ve a almacén",
        "ve al almacen",
        "dirígete a recepción",
        "ve a sala de máquinas",
        "go to warehouse",
        "ve a la fuga de válvula 3",
        "inspecciona válvula 2",
        "ve a bomba 1",
        "pasa por el pasillo norte",
        "navega hasta oficina",
        "ve a almacén y luego a recepción",
        "go to warehouse then office",
    ]:
        data.append(row(t, "unknown", reply=ZONE_UNAVAILABLE_REPLY))

    # --- sequences: unidades ---
    data += _unit_drive_examples()
    data += _angle_turn_examples()
    data += _connector_sequence_examples()
    data += _mixed_metric_sequences()

    # parafraseo industrial corto (sin zonas)
    prefixes = ["", "por favor ", "oiga ", "robot, ", "necesito que ", "quiero que ", "puedes "]
    suffixes = ["", " ahora", " por favor", " ya"]
    cores = [
        ("avanza", "navigate", "adelante"),
        ("adelante", "navigate", "adelante"),
        ("retrocede", "navigate", "atras"),
        ("gira a la derecha", "navigate", "derecha"),
        ("gira a la izquierda", "navigate", "izquierda"),
        ("detén", "cancel_navigation", None),
        ("para", "cancel_navigation", None),
        ("regresa a la base", "return_home", None),
        ("lista los topics", "list_topics", None),
        ("lista nodos", "list_nodes", None),
        ("estado del robot", "get_status", None),
        ("batería", "get_battery", None),
        ("ayuda", "help", None),
    ]
    for pre, suf in itertools.product(prefixes, suffixes):
        for core, intent, dest in cores:
            phrase = f"{pre}{core}{suf}".strip()
            if len(phrase) < 3:
                continue
            data.append(row(phrase, intent, dest))

    seen: set[str] = set()
    unique: list[dict] = []
    for r in data:
        key = r["text"].lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)

    rng.shuffle(unique)
    return unique


def _unit_drive_examples() -> list[dict]:
    rows: list[dict] = []
    # metros
    for m, phrases in [
        (0.8, ["avanza 0.8 metros", "avanza 0,8 m", "adelante 0.8 metros", "avanza cero punto ocho metros"]),
        (0.5, ["avanza 0.5 metros", "avanza medio metro", "adelante 0.5 m"]),
        (1.0, ["avanza 1 metro", "avanza un metro", "adelante 1 m"]),
        (0.4, ["avanza 0.4 metros", "forward 0.4 meters"]),
    ]:
        for p in phrases:
            rows.append(seq_row(p, [{"op": "drive", "meters": m}], f"Avanzo {m} m."))
    # cm
    for cm in (10, 15, 20, 25, 30, 40, 50, 80):
        m = cm / 100.0
        for p in [
            f"avanza {cm} cm",
            f"avanza {cm} centímetros",
            f"adelante {cm} cm",
            f"forward {cm} cm",
        ]:
            rows.append(seq_row(p, [{"op": "drive", "meters": m}], f"Avanzo {cm} cm."))
    # pulgadas / pies
    for inch in (6, 12, 18, 24):
        m = round(inch * INCH_M, 4)
        for p in [
            f"avanza {inch} pulgadas",
            f"adelante {inch} inches",
            f"forward {inch} in",
        ]:
            rows.append(seq_row(p, [{"op": "drive", "meters": m}], f"Avanzo {inch} pulgadas (~{m} m)."))
    for ft in (1, 2, 3):
        m = round(ft * FOOT_M, 4)
        for p in [
            f"avanza {ft} pies",
            f"adelante {ft} feet",
            f"forward {ft} ft",
            f"avanza {ft} pie" if ft == 1 else f"avanza {ft} pies",
        ]:
            rows.append(seq_row(p, [{"op": "drive", "meters": m}], f"Avanzo {ft} pie(s) (~{m} m)."))
    # retroceso con unidades
    rows.append(
        seq_row(
            "retrocede 20 cm",
            [{"op": "drive", "meters": -0.2}],
            "Retrocedo 20 cm.",
        )
    )
    rows.append(
        seq_row(
            "retrocede 0.3 metros",
            [{"op": "drive", "meters": -0.3}],
            "Retrocedo 0.3 m.",
        )
    )
    rows.append(
        seq_row(
            "atrás 12 pulgadas",
            [{"op": "drive", "meters": round(-12 * INCH_M, 4)}],
            "Retrocedo 12 pulgadas.",
        )
    )
    return rows


def _angle_turn_examples() -> list[dict]:
    rows: list[dict] = []
    # Con y sin «grados»
    for deg, side, sign in [
        (45, "derecha", -1),
        (45, "izquierda", 1),
        (90, "derecha", -1),
        (90, "izquierda", 1),
        (30, "derecha", -1),
        (60, "izquierda", 1),
        (180, "derecha", -1),
    ]:
        signed = sign * deg
        phrases = [
            f"gira {deg} grados a la {side}",
            f"gira {deg}° a la {side}",
            f"gira a la {side} {deg} grados",
            f"gira a la {side} en {deg} grados",
            f"gira {deg} a la {side}",  # sin «grados»
            f"volte {deg} a la {side}",
            f"rota {deg} a la {side}",
            f"turn {deg} {('right' if side == 'derecha' else 'left')}",
            f"gira {side} {deg}",
        ]
        for p in phrases:
            rows.append(
                seq_row(
                    p,
                    [{"op": "turn", "degrees": signed}],
                    f"Giro {deg}° a la {side}.",
                )
            )
    rows.append(
        seq_row(
            "espera 5 segundos",
            [{"op": "wait", "seconds": 5}],
            "Espero 5 segundos.",
        )
    )
    rows.append(
        seq_row(
            "espera 2 s",
            [{"op": "wait", "seconds": 2}],
            "Espero 2 segundos.",
        )
    )
    return rows


def _connector_sequence_examples() -> list[dict]:
    """Planes multi-paso con conectores textuales (no solo comas)."""
    rows: list[dict] = []

    triples = [
        (
            "avanza 0.8 metros, gira 90 grados a la derecha, avanza 0.5 metros",
            [
                {"op": "drive", "meters": 0.8},
                {"op": "turn", "degrees": -90},
                {"op": "drive", "meters": 0.5},
            ],
            "Avanzo 0.8 m, giro 90° a la derecha y avanzo 0.5 m.",
        ),
        (
            "en primer lugar avanza 0.8 metros después gira 90 a la derecha por último avanza 0.5 metros",
            [
                {"op": "drive", "meters": 0.8},
                {"op": "turn", "degrees": -90},
                {"op": "drive", "meters": 0.5},
            ],
            "Ejecuto el plan: avance, giro y avance final.",
        ),
        (
            "primero avanza 80 cm luego gira 90 a la derecha finalmente avanza 50 cm",
            [
                {"op": "drive", "meters": 0.8},
                {"op": "turn", "degrees": -90},
                {"op": "drive", "meters": 0.5},
            ],
            "Primero avance, luego giro y finalmente avance.",
        ),
        (
            "avanza 30 cm y luego gira 45 grados a la derecha y avanza 40 cm",
            [
                {"op": "drive", "meters": 0.3},
                {"op": "turn", "degrees": -45},
                {"op": "drive", "meters": 0.4},
            ],
            "Ejecuto avance, giro y segundo avance.",
        ),
        (
            "avanza 30 cm y luego gira a la derecha en 45 grados y avanza en línea recta otros 10 cm y para",
            [
                {"op": "drive", "meters": 0.3},
                {"op": "turn", "degrees": -45},
                {"op": "drive", "meters": 0.1},
                {"op": "stop"},
            ],
            "Avanzo, giro, avanzo 10 cm y paro.",
        ),
        (
            "avanza 20 cm, gira a la izquierda 90 grados y avanza 15 cm",
            [
                {"op": "drive", "meters": 0.2},
                {"op": "turn", "degrees": 90},
                {"op": "drive", "meters": 0.15},
            ],
            "Ejecuto el plan de tres pasos.",
        ),
        (
            "primeramente avanza 25 cm a continuación gira 45 a la izquierda acto seguido avanza 15 cm",
            [
                {"op": "drive", "meters": 0.25},
                {"op": "turn", "degrees": 45},
                {"op": "drive", "meters": 0.15},
            ],
            "Ejecuto avance, giro a la izquierda y avance.",
        ),
        (
            "avanza 40 cm después gira 90 a la derecha y por último retrocede 10 cm",
            [
                {"op": "drive", "meters": 0.4},
                {"op": "turn", "degrees": -90},
                {"op": "drive", "meters": -0.1},
            ],
            "Avanzo, giro a la derecha y retrocedo.",
        ),
        (
            "avanza un pie luego gira 90 a la izquierda finalmente avanza 12 pulgadas",
            [
                {"op": "drive", "meters": round(1 * FOOT_M, 4)},
                {"op": "turn", "degrees": 90},
                {"op": "drive", "meters": round(12 * INCH_M, 4)},
            ],
            "Avanzo un pie, giro y avanzo 12 pulgadas.",
        ),
        (
            "first advance 0.5 meters then turn 90 right finally advance 30 cm",
            [
                {"op": "drive", "meters": 0.5},
                {"op": "turn", "degrees": -90},
                {"op": "drive", "meters": 0.3},
            ],
            "Advance, turn right, then advance again.",
        ),
        (
            "retrocede 10 cm y luego gira a la derecha 45 grados",
            [
                {"op": "drive", "meters": -0.1},
                {"op": "turn", "degrees": -45},
            ],
            "Retrocedo y giro a la derecha.",
        ),
        (
            "avanza un poco 25 cm y detente",
            [
                {"op": "drive", "meters": 0.25},
                {"op": "stop"},
            ],
            "Avanzo 25 cm y me detengo.",
        ),
        (
            "gira 90 a la derecha después avanza 0.5 metros",
            [
                {"op": "turn", "degrees": -90},
                {"op": "drive", "meters": 0.5},
            ],
            "Giro 90° a la derecha y avanzo 0.5 m.",
        ),
        (
            "en primer lugar gira 45 a la izquierda después avanza 60 cm por último espera 2 segundos",
            [
                {"op": "turn", "degrees": 45},
                {"op": "drive", "meters": 0.6},
                {"op": "wait", "seconds": 2},
            ],
            "Giro, avanzo y espero.",
        ),
        (
            "avanza 2 pies seguidamente gira 45 a la derecha y finalmente avanza 6 pulgadas",
            [
                {"op": "drive", "meters": round(2 * FOOT_M, 4)},
                {"op": "turn", "degrees": -45},
                {"op": "drive", "meters": round(6 * INCH_M, 4)},
            ],
            "Avanzo 2 pies, giro y avanzo 6 pulgadas.",
        ),
    ]
    for text, steps, reply in triples:
        rows.append(seq_row(text, steps, reply))

    # Variaciones sistemáticas con conectores
    connectors = [
        ("y luego", "después", "por último"),
        ("luego", "a continuación", "finalmente"),
        ("después", "seguidamente", "por último"),
        (",", "y luego", "y finalmente"),
    ]
    for cm, deg in ((30, 45), (40, 90), (50, 90), (20, 30), (80, 90)):
        for c1, c2, c3 in connectors:
            # 2 pasos
            rows.append(
                seq_row(
                    f"avanza {cm} cm {c1} gira {deg} a la derecha",
                    [
                        {"op": "drive", "meters": cm / 100.0},
                        {"op": "turn", "degrees": -deg},
                    ],
                    f"Avanzo {cm} cm y giro {deg}° a la derecha.",
                )
            )
            rows.append(
                seq_row(
                    f"avanza {cm} cm {c1} gira {deg} grados a la izquierda",
                    [
                        {"op": "drive", "meters": cm / 100.0},
                        {"op": "turn", "degrees": deg},
                    ],
                    f"Avanzo {cm} cm y giro {deg}° a la izquierda.",
                )
            )
            # 3 pasos con ordenadores
            rows.append(
                seq_row(
                    f"primero avanza {cm} cm {c2} gira {deg} a la derecha {c3} avanza {cm // 2} cm",
                    [
                        {"op": "drive", "meters": cm / 100.0},
                        {"op": "turn", "degrees": -deg},
                        {"op": "drive", "meters": (cm // 2) / 100.0},
                    ],
                    "Ejecuto el plan de tres pasos.",
                )
            )
            rows.append(
                seq_row(
                    f"en primer lugar avanza {cm / 100:.2f} metros {c2} gira {deg} a la izquierda "
                    f"{c3} avanza {(cm // 2) / 100:.2f} metros",
                    [
                        {"op": "drive", "meters": cm / 100.0},
                        {"op": "turn", "degrees": deg},
                        {"op": "drive", "meters": (cm // 2) / 100.0},
                    ],
                    "Ejecuto avance, giro y avance final.",
                )
            )

    return rows


def _mixed_metric_sequences() -> list[dict]:
    rows: list[dict] = []
    for cm, deg in ((30, 45), (40, 90), (15, 30)):
        rows.append(
            seq_row(
                f"avanza {cm} cm y gira {deg} grados a la derecha",
                [
                    {"op": "drive", "meters": cm / 100.0},
                    {"op": "turn", "degrees": -deg},
                ],
                f"Avanzo {cm} cm y giro {deg}° a la derecha.",
            )
        )
        rows.append(
            seq_row(
                f"avanza {cm} cm y luego gira a la izquierda en {deg} grados",
                [
                    {"op": "drive", "meters": cm / 100.0},
                    {"op": "turn", "degrees": deg},
                ],
                f"Avanzo {cm} cm y giro {deg}° a la izquierda.",
            )
        )
    return rows


def to_sft(r: dict) -> dict:
    intent = r["intent"]
    params: dict = {}
    if intent == "navigate" and r.get("destination"):
        params["destination"] = r["destination"]
    if intent == "sequence" and r.get("steps"):
        params["steps"] = r["steps"]
    out = {
        "intent": intent,
        "action": ACTIONS.get(intent, "unknown_action"),
        "parameters": params,
        "confidence": 0.95 if intent != "unknown" else 0.25,
        "reply": r.get("reply") or _default_reply(intent, r.get("destination")),
    }
    return {
        "instruction": r["text"],
        "output": json.dumps(out, ensure_ascii=False),
    }


def _write(path: Path, rows: list[dict], *, sft: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(to_sft(r) if sft else r, ensure_ascii=False) + "\n")


def main() -> None:
    rows = build()
    _write(OUT_RAW, rows, sft=False)
    _write(OUT_SFT, rows, sft=True)
    _write(OUT_RAW_V2, rows, sft=False)
    _write(OUT_SFT_V2, rows, sft=True)

    c = Counter(r["intent"] for r in rows)
    n_seq = sum(1 for r in rows if r["intent"] == "sequence")
    print(f"Wrote {len(rows)} rows → {OUT_RAW}")
    print(f"Wrote SFT → {OUT_SFT}")
    print(f"Mirror → {OUT_SFT_V2.name}")
    print(dict(c))
    print(f"sequence examples: {n_seq}")


if __name__ == "__main__":
    main()
