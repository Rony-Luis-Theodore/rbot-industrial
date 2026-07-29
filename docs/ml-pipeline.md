# Pipeline ML — R-Bot Industrial (Operator v2)

Objetivo: un LLM **usable como chat de operación**, no solo un clasificador débil de 1.5B.

## Qué cambió respecto a v1

| | v1 (antes) | v2 (ahora) |
|--|------------|------------|
| Modelo | Qwen2.5-1.5B | **Qwen2.5-3B-Instruct** |
| Dataset | ~135 frases | **~800** (`operator_v2_*.jsonl`) |
| Salida | intent JSON | intent + **reply** en español |
| Intents nuevos | — | `get_status`, `get_battery`, `help` |
| Notebook | `01_finetune_…` | **`03_finetune_operator_colab.ipynb`** |

Los mandos críticos (avanza / gira / detén) siguen cubiertos por `motion_commands` en la API; el LLM cubre parafraseo, destinos y conversación.

## 1. Dataset

```bash
python3 ml/scripts/build_operator_dataset.py
# → ml/datasets/operator_v2_es.jsonl
# → ml/datasets/operator_v2_sft.jsonl
```

Amplía el generador o edita el JSONL con frases reales del lab (fugas, bombas, alias del equipo).

## 2. Entrenar en Google Colab (GPU)

1. Sube `ml/notebooks/03_finetune_operator_colab.ipynb`
2. Runtime → **T4 GPU**
3. Sube `operator_v2_sft.jsonl`
4. Entrena LoRA 3B (~30–60 min en T4)
5. Merge a Drive: `MyDrive/rbot-industrial-ml/rbot-operator-merged`

Smoke test en el notebook: avanza, para atrás, batería, ayuda, chiste→unknown.

## 3. Export GGUF

Usa `02_export_gguf_colab.ipynb` apuntando a `rbot-operator-merged`.  
Copia el `.gguf` a `ml/export/rbot-operator-q4_k_m.gguf`.

## 4. Ollama + API

```bash
cd ~/Documents/Proyectos/rbot-industrial/ml/export
# Sin GGUF aún (baseline fuerte):
# edita Modelfile.rbot-operator → FROM qwen2.5:3b
ollama pull qwen2.5:3b
ollama create rbot-operator -f Modelfile.rbot-operator
```

`apps/api/.env`:
```
LLM_PROVIDER=ollama
OLLAMA_MODEL=rbot-operator
```

Reinicia el stack. Prueba en el chat: *“cuánta batería”*, *“qué puedo decirte”*, *“ve a la bomba 3”*.

## 5. Validación rápida

| Frase | Esperado |
|-------|----------|
| avanza un poco | navigate / adelante + reply |
| para atrás | navigate / atras |
| gira a la derecha | navigate / derecha |
| detén | cancel_navigation |
| estado del robot | get_status |
| batería | get_battery |
| ayuda | help |
| cuéntame un chiste | unknown |

## 6. Voz

Sin cambios: Web Speech + Whisper (`docs` sección anterior / `voice` API).

## Nota de producto

Si Colab no está disponible hoy, `OLLAMA_MODEL=qwen2.5:3b` ya mejora mucho el chat frente a 1.5B; el fine-tune v2 especializa el JSON y el tono de planta.
