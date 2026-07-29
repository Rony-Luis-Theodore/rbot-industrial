# Export ML — Sonar Operator (Ollama)

Los **binarios** (`.gguf`) **no van en git**. Están en **GitHub Releases**.

## Descargar Operator v3 (v1.0.0)

Release: https://github.com/Rony-Luis-Theodore/rbot-industrial/releases/tag/v1.0.0

```bash
cd rbot-industrial
mkdir -p ml/export
gh release download v1.0.0 \
  -R Rony-Luis-Theodore/rbot-industrial \
  -p 'rbot-operator-q4_k_m.gguf' \
  -D ml/export
```

O descarga manual del asset `rbot-operator-q4_k_m.gguf` (~1.8 GB) a `ml/export/`.

## Crear el modelo en Ollama

```bash
cd ml/export
# Modelfile espera: FROM ./rbot-operator-q4_k_m.gguf
ollama create rbot-operator -f Modelfile.rbot-operator
```

## Activar en Sonar

En `apps/api/.env`:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=rbot-operator
```

Reinicia la API. El chat usará Ollama para lo que el motion guard no resuelva;
si Ollama falla, hay fallback a mock.

### Sin GGUF (baseline)

```bash
ollama pull qwen2.5:1.5b
# OLLAMA_MODEL=qwen2.5:1.5b
```

Entrenar de nuevo: [`../COLAB_NOW.md`](../COLAB_NOW.md).
