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

## Arranque rápido (Release → Ollama → PC)

```bash
# 1) Descargar GGUF de la Release v1.0.0
gh release download v1.0.0 \
  -R Rony-Luis-Theodore/rbot-industrial \
  -p 'rbot-operator-q4_k_m.gguf' \
  -D ml/export

# 2) Crear modelo
cd ml/export && ollama create rbot-operator -f Modelfile.rbot-operator

# 3) apps/api/.env
# LLM_PROVIDER=ollama
# OLLAMA_MODEL=rbot-operator
```

Release: https://github.com/Rony-Luis-Theodore/rbot-industrial/releases/tag/v1.0.0

## Re-entrenar (Colab)

```bash
# 1) Regenerar dataset
python3 ml/scripts/build_operator_dataset.py

# 2) Colab: notebooks/03_finetune_operator_colab.ipynb (GPU T4)
#    sube operator_v3_sft.jsonl → entrena → merge a Drive

# 3) Export GGUF: 02_export_gguf_colab.ipynb
```

**Arranque Colab ahora:** [`COLAB_NOW.md`](COLAB_NOW.md)  
**Instalar desde Release:** [`export/README.md`](export/README.md)
