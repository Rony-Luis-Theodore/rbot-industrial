# Export ML — R-Bot (Modelfiles para Ollama)

Los **binarios** (`.gguf`, LoRA, merges HF) **no van en git**.

En la máquina de desarrollo suelen estar en:

`~/Documents/Proyectos/_local/ml-models/`

## Crear `rbot-operator`

```bash
# Opción A: GGUF local
# Edita Modelfile.rbot-operator:
#   FROM /ruta/absoluta/_local/ml-models/rbot-operator-q4_k_m.gguf
ollama create rbot-operator -f Modelfile.rbot-operator

# Opción B: baseline mientras no tengas GGUF
# Cambia a: FROM qwen2.5:3b
ollama pull qwen2.5:3b
```

Ver `../README.md` y `../../docs/ml-pipeline.md`.
