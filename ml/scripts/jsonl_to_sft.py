#!/usr/bin/env python3
"""Convierte ml/datasets/intents_es.jsonl → formato SFT (instruction/output JSON)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

INTENT_ACTIONS = {
    "list_topics": "ros2 topic list",
    "list_nodes": "ros2 node list",
    "list_services": "ros2 service list",
    "list_actions": "ros2 action list",
    "navigate": "send_navigation_goal",
    "cancel_navigation": "cancel_navigation",
    "return_home": "return_home",
    "unknown": "unknown_action",
}


def to_sft(row: dict) -> dict:
    intent = row.get("intent") or "unknown"
    dest = row.get("destination")
    params: dict = {}
    if intent == "navigate" and dest:
        params["destination"] = dest
    out = {
        "intent": intent,
        "action": INTENT_ACTIONS.get(intent, "unknown_action"),
        "parameters": params,
        "confidence": 0.95 if intent != "unknown" else 0.3,
    }
    return {
        "instruction": row["text"],
        "output": json.dumps(out, ensure_ascii=False),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--in",
        dest="inp",
        default=str(
            Path(__file__).resolve().parents[1] / "datasets" / "intents_es.jsonl"
        ),
    )
    ap.add_argument(
        "--out",
        default=str(
            Path(__file__).resolve().parents[1] / "datasets" / "intents_sft.jsonl"
        ),
    )
    args = ap.parse_args()
    inp = Path(args.inp)
    out = Path(args.out)
    n = 0
    with inp.open(encoding="utf-8") as fin, out.open("w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            fout.write(json.dumps(to_sft(row), ensure_ascii=False) + "\n")
            n += 1
    print(f"wrote {n} → {out}")


if __name__ == "__main__":
    main()
