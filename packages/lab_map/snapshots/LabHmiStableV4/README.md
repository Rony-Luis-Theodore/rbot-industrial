# LabHmiStableV4 — v1.0 (primera release)

Checkpoint / cara de producto **2026-07-28**.

## Lab / Occupancy
- Escala odom `(7/6)×0.96` · `LOCALIZE_OUTWARD_M=0.14`
- Ubicar 1× · sin Reiniciar · reanclar = refresh del navegador
- Centro del circuito recomendado en UI
- Flecha: snap visual en ejes de pantalla (~18°)
- Giros: under-aim `0.90`
- Título **Circuito** · HMI Sonar (murciélago + Powered by)
- Canvas del mapa se adapta al contenedor (solo visualización)
- Layout mapa \| chat fijo; scrollbars solo bajo 1100×640

## LLM Operator v3
- Dataset conectores / unidades / ángulos (sin zonas nombradas)
- Motion guard + normalizer · Modelfile / prompt Ollama v3
- GGUF `rbot-operator` **fuera de git** (`ml/export/*.gguf`)

## Restaurar lab JS
```bash
cp -a packages/lab_map/snapshots/LabHmiStableV4/{constants.js,LabMapEngine.js,LabCanvas.js,lab-session.js,lab-view.js} \
  apps/web/js/lab/
```
También incluye `ollama_llm.py`, `motion_*.py`, `rclpy_ros.py`, `constants.py`.
Bump `?v=` en `apps/web/index.html` y Ctrl+F5.
