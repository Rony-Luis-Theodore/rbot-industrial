# LabHmiStableV4 — Sonar v1.0 (release oficial)

Checkpoint de producto **Sonar v1.0** (2026-07-28).

## Producto
- Nombre: **Sonar** — consola remota Occupancy + chat + teleop (Nexus / R-Bot / más)
- Vertical: operación industrial / monitoreo autónomo a distancia

## Lab / Occupancy
- Escala odom `(7/6)×0.96` · `LOCALIZE_OUTWARD_M=0.14`
- Ubicar 1× · sin Reiniciar · reanclar = refresh del navegador
- Centro del circuito recomendado en UI
- Flecha: snap visual en ejes de pantalla (~18°)
- Giros: under-aim `0.90`
- Título **Circuito** · HMI Sonar
- Layout mapa \| chat; scrollbars solo bajo 1100×640

## LLM Operator v3
- Dataset conectores / unidades / ángulos (sin zonas nombradas)
- Motion guard + normalizer · Modelfile / prompt Ollama v3
- GGUF fuera de git (`ml/export/*.gguf`)

## Restaurar lab JS
```bash
cp -a packages/lab_map/snapshots/LabHmiStableV4/{constants.js,LabMapEngine.js,LabCanvas.js,lab-session.js,lab-view.js} \
  apps/web/js/lab/
```
También: `ollama_llm.py`, `motion_*.py`, `rclpy_ros.py`, `constants.py`.  
Bump `?v=` en `apps/web/index.html` y Ctrl+F5.
