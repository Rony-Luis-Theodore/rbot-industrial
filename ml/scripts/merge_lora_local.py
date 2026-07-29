#!/usr/bin/env python3
"""Fusiona ml/export/rbot-intent-lora con Qwen2.5-1.5B → rbot-intent-merged."""

from __future__ import annotations

from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parents[1] / "export"
ADAPTER = ROOT / "rbot-intent-lora"
OUT = ROOT / "rbot-intent-merged"
BASE = "Qwen/Qwen2.5-1.5B-Instruct"


def main() -> None:
    if not (ADAPTER / "adapter_model.safetensors").exists():
        raise SystemExit(f"Falta adaptador en {ADAPTER}")

    print("Cargando base (FP16 CPU — puede tardar)…")
    tok = AutoTokenizer.from_pretrained(ADAPTER if (ADAPTER / "tokenizer.json").exists() else BASE)
    model = AutoModelForCausalLM.from_pretrained(
        BASE,
        torch_dtype=torch.float16,
        device_map="cpu",
        low_cpu_mem_usage=True,
        trust_remote_code=True,
    )
    print("Aplicando LoRA…")
    model = PeftModel.from_pretrained(model, str(ADAPTER))
    model = model.merge_and_unload()
    OUT.mkdir(parents=True, exist_ok=True)
    print("Guardando", OUT)
    model.save_pretrained(OUT, safe_serialization=True)
    tok.save_pretrained(OUT)
    print("OK — comprueba que existan model*.safetensors (~3 GB)")


if __name__ == "__main__":
    main()
