# Colab ahora — Operator v3

Dataset y notebooks listos en el repo. Entrenar de nuevo para conectar:
conectores textuales, unidades (m/cm/pulgadas/pies), ángulos sin «grados»,
secuencias multi-paso. **Sin** rutas a zonas nombradas.

## 1) En el PC (regenerar dataset)

```bash
cd ~/Documents/Proyectos/rbot-industrial
python3 ml/scripts/build_operator_dataset.py
```

Sube a Colab:
- `ml/notebooks/03_finetune_operator_colab.ipynb`
- `ml/datasets/operator_v3_sft.jsonl`  ← **preferido**
- (también se escribe espejo `operator_v2_sft.jsonl` con el mismo contenido)
- Después: `ml/notebooks/02_export_gguf_colab.ipynb`

## 2) Google Colab

1. Abre [colab.research.google.com](https://colab.research.google.com)
2. Sube / abre `03_finetune_operator_colab.ipynb`
3. **Runtime → Change runtime type → T4 GPU**
4. Ejecuta celdas en orden
5. Cuando pida dataset: sube **`operator_v3_sft.jsonl`**
6. Merge en Drive: `MyDrive/rbot-industrial-ml/rbot-operator-merged`
7. `02_export_gguf_colab.ipynb` → `rbot-operator-q4_k_m.gguf`

Smoke tests en notebook / chat tras desplegar:
- `en primer lugar avanza 0.8 metros después gira 90 a la derecha por último avanza 0.5 metros` → `sequence`
- `gira 45 a la derecha` → `turn` −45 (sin palabra grados)
- `avanza 2 pies` → `drive` ~0.61 m
- `ve a almacén` → `unknown` (zonas no disponibles)

## 3) Volver al PC

```bash
# Copia el .gguf a ml/export/ o _local/ml-models/

cd ~/Documents/Proyectos/rbot-industrial/ml/export
ollama create rbot-operator -f Modelfile.rbot-operator

# apps/api/.env:
#   LLM_PROVIDER=ollama
#   OLLAMA_MODEL=rbot-operator

bash ~/Documents/Proyectos/start-rbot.sh
```

## 4) Probar en chat

- «primero avanza 80 cm luego gira 90 a la derecha finalmente avanza 50 cm»
- «avanza 12 pulgadas»
- «gira 45 a la izquierda»
- «cuéntame un chiste» → fuera de dominio

El motion_guard / parser local cubre mandos obvios aunque el LLM dude.
