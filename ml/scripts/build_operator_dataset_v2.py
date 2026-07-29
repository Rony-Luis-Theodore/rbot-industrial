"""
Dataset v2: zonas del lab + planes multi-paso para fine-tune Colab.

Uso:
  python ml/scripts/build_operator_dataset_v2.py
  → escribe ml/data/intents_es_v2.jsonl

Luego súbelo a Colab (notebook 01) con UPLOAD=True o pégalo embebido.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "ml" / "data" / "intents_es_v2.jsonl"

ZONES = [
    ("almacen", "almacén", "warehouse"),
    ("sala_maquinas", "sala de máquinas", "machine room"),
    ("recepcion", "recepción", "reception"),
    ("oficina", "oficina", "office"),
    ("centro", "centro", "center"),
    ("pasillo_norte", "pasillo norte", "north corridor"),
    ("pasillo_sur", "pasillo sur", "south corridor"),
    ("pasillo_este", "pasillo este", "east corridor"),
    ("pasillo_oeste", "pasillo oeste", "west corridor"),
]


def row(user: str, intent: str, action: str, parameters: dict, reply: str, conf: float = 0.92):
    return {
        "instruction": user,
        "intent": intent,
        "action": action,
        "parameters": parameters,
        "confidence": conf,
        "reply": reply,
    }


def main() -> None:
    rows = []

    # Zonas
    for zid, label, en in ZONES:
        for phrase in (
            f"voy a {label}",
            f"ve a {label}",
            f"dirígete a {label}",
            f"navega hasta {label}",
            f"go to {en}",
            f"lleva el robot a {label}",
        ):
            rows.append(
                row(
                    phrase,
                    "navigate",
                    "send_navigation_goal",
                    {"destination": zid},
                    f"Voy a {label}.",
                )
            )

    # Métricas
    rows += [
        row(
            "avanza 30 cm",
            "sequence",
            "execute_motion_plan",
            {"steps": [{"op": "drive", "meters": 0.3}]},
            "Avanzo 30 cm.",
        ),
        row(
            "avanza 0.4 metros",
            "sequence",
            "execute_motion_plan",
            {"steps": [{"op": "drive", "meters": 0.4}]},
            "Avanzo 0.4 m.",
        ),
        row(
            "gira 45 grados a la derecha",
            "sequence",
            "execute_motion_plan",
            {"steps": [{"op": "turn", "degrees": -45}]},
            "Giro 45° a la derecha.",
        ),
        row(
            "volte a la izquierda 90 grados",
            "sequence",
            "execute_motion_plan",
            {"steps": [{"op": "turn", "degrees": 90}]},
            "Giro 90° a la izquierda.",
        ),
        row(
            "espera 5 segundos",
            "sequence",
            "execute_motion_plan",
            {"steps": [{"op": "wait", "seconds": 5}]},
            "Espero 5 segundos.",
        ),
    ]

    # Planes mixtos
    rows += [
        row(
            "ve a almacén, espera 5 segundos y luego dirígete a recepción",
            "sequence",
            "execute_motion_plan",
            {
                "steps": [
                    {"op": "goto", "destination": "almacen"},
                    {"op": "wait", "seconds": 5},
                    {"op": "goto", "destination": "recepcion"},
                ]
            },
            "Voy al almacén, espero 5 s y luego a recepción.",
        ),
        row(
            "avanza 30 cm y luego gira 45 grados a la derecha y avanza otros 40 cm",
            "sequence",
            "execute_motion_plan",
            {
                "steps": [
                    {"op": "drive", "meters": 0.3},
                    {"op": "turn", "degrees": -45},
                    {"op": "drive", "meters": 0.4},
                ]
            },
            "Ejecuto avance, giro y segundo avance.",
        ),
        row(
            "go to warehouse then wait 3 seconds then go to office",
            "sequence",
            "execute_motion_plan",
            {
                "steps": [
                    {"op": "goto", "destination": "almacen"},
                    {"op": "wait", "seconds": 3},
                    {"op": "goto", "destination": "oficina"},
                ]
            },
            "Going to warehouse, waiting, then office.",
        ),
        row(
            "pasa por el pasillo norte y después ve a sala de máquinas",
            "sequence",
            "execute_motion_plan",
            {
                "steps": [
                    {"op": "goto", "destination": "pasillo_norte"},
                    {"op": "goto", "destination": "sala_maquinas"},
                ]
            },
            "Paso por el pasillo norte y voy a sala de máquinas.",
        ),
    ]

    # Básicos + unknown fuera de dominio
    rows += [
        row("avanza", "navigate", "send_navigation_goal", {"destination": "adelante"}, "Avanzo."),
        row("detén", "cancel_navigation", "cancel_navigation", {}, "Deteniendo."),
        row("qué tiempo hace", "unknown", "unknown_action", {}, "Eso está fuera de mi dominio."),
        row("hazme un café", "unknown", "unknown_action", {}, "No puedo preparar café."),
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Wrote {len(rows)} rows → {OUT}")


if __name__ == "__main__":
    main()
