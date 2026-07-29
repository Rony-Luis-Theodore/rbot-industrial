# Plan LLM — Operator v3 (lab Occupancy)

## Alcance de esta versión
- Avances / giros / esperas / stop en `sequence`
- Conectores: primero, en primer lugar, después, por último, finalmente…
- Unidades: m, cm, pulgadas, pies → `meters`
- Ángulos implícitos: «gira 45 a la derecha»
- **Fuera de alcance:** rutas a zonas (almacén, válvula, pasillos…) → `unknown`

## Estado
| Pieza | Estado |
|-------|--------|
| Prompt Ollama + Modelfile | v3 |
| Dataset `operator_v3_sft.jsonl` | regenerable con `build_operator_dataset.py` |
| Parser local `motion_plan.py` | conectores + unidades |
| Fine-tune Colab | notebook 03 listo |
| Export GGUF | notebook 02 |

## Colab
Ver [`COLAB_NOW.md`](COLAB_NOW.md).
