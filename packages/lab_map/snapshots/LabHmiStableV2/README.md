# LabHmiStableV2 — checkpoint de retorno

Guardado **2026-07-28** tras validación en lab Nexus:
- Primer Ubicar estable; botón se oculta (anti vistas CAD)
- Recargar página = sesión limpia + Ubicar de nuevo (buena tasa)
- Chat con trayectorias combinadas (sequence) OK
- Sin botón «Soltar ancla»

## Archivos
Copia de `apps/web/js/lab/*` en el momento del checkpoint.

## Restaurar
```bash
cp -a packages/lab_map/snapshots/LabHmiStableV2/{constants.js,LabMapEngine.js,LabCanvas.js,lab-session.js,lab-view.js} \
  apps/web/js/lab/
```
Bump `?v=` en `apps/web/index.html` y Ctrl+F5.
