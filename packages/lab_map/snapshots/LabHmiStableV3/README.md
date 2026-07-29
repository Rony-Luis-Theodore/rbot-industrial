# LabHmiStableV3 — checkpoint de retorno

Validado **2026-07-28** en lab Nexus:

- Ubicar 1× + botón oculto (anti vistas CAD)
- **Reiniciar** muy fiable (mejor que F5 del navegador)
- Chat secuencias / metros / giros bien en órdenes sueltas
- Flecha con snap UI a cardinal
- Giros con under-aim anti-overshoot

Post-checkpoint (código vivo): Reiniciar soft ×3; el 4º hace recarga
limpia con cache-bust (`lab-v50-stable3`).

## Restaurar
```bash
cp -a packages/lab_map/snapshots/LabHmiStableV3/{constants.js,LabMapEngine.js,LabCanvas.js,lab-session.js,lab-view.js} \
  apps/web/js/lab/
```
Bump `?v=` y Ctrl+F5.
