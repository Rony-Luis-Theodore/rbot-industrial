# ML — R-Bot Industrial

| Ruta | Contenido |
|------|-----------|
| `datasets/operator_v3_sft.jsonl` | **SFT v3** (conectores, unidades, ángulos) |
| `datasets/operator_v3_es.jsonl` | Dataset v3 crudo |
| `datasets/operator_v2_sft.jsonl` | Espejo v3 (compat notebooks) |
| `notebooks/03_finetune_operator_colab.ipynb` | **Qwen2.5-3B LoRA** |
| `notebooks/02_export_gguf_colab.ipynb` | Merge HF → GGUF |
| `export/Modelfile.rbot-operator` | SYSTEM prompt Operator v3 |
| `scripts/build_operator_dataset.py` | Regenerar dataset v3 |

## Arranque rápido (Colab → PC)

```bash
# 1) Regenerar dataset
python3 ml/scripts/build_operator_dataset.py

# 2) Colab: notebooks/03_finetune_operator_colab.ipynb (GPU T4)
#    sube operator_v3_sft.jsonl → entrena → merge a Drive

# 3) Export GGUF: 02_export_gguf_colab.ipynb
#    (Drive: rbot-operator-merged)

# 4) En el PC
cd ml/export
ollama create rbot-operator -f Modelfile.rbot-operator

# 5) apps/api/.env
# LLM_PROVIDER=ollama
# OLLAMA_MODEL=rbot-operator
```

**Arranque Colab ahora:** [`COLAB_NOW.md`](COLAB_NOW.md)
