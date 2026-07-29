# LabHmiStableV1 — checkpoint de retorno

Guardado **2026-07-28** tras restaurar LabHmiChatV1 y validar en lab:
interfaz HMI actual, chat/LLM y escala de metros/giros (API) que calzan con la realidad.

## Qué incluye
- SE2 LabHmiChatV1 / LabTrayectoriaOK (`7/6`, `HEADING_BIAS=π`, `LOCALIZE_MIRROR_X`, `LOCALIZE_INVERT_LR`)
- Gate Ubicar obligatorio
- HMI oscura + rail + chat LLM (`rbot-operator`)
- Avance/giro cerrados por odom en API (`odom_scale` giros 1:1)

## Archivos
Copia de `apps/web/js/lab/*` + `packages/lab_map/src/lab_map/constants.py`.

## Restaurar
```bash
cp -a packages/lab_map/snapshots/LabHmiStableV1/{constants.js,LabMapEngine.js,LabCanvas.js,lab-session.js,lab-view.js} \
  apps/web/js/lab/
cp -a packages/lab_map/snapshots/LabHmiStableV1/constants.py \
  packages/lab_map/src/lab_map/constants.py
```
Bump `?v=` en `apps/web/index.html` y Ctrl+F5.

## No tocar sin petición
Constantes SE2 / orientación (`LIDAR_YAW`, `HEADING_BIAS`, `MIRROR_X`, `INVERT_LR`, escala mapa).

## Problema conocido (documentado al guardar)
Re-pulsar **Ubicar** varias veces reinventaba el marco (efecto vista CAD).

## Fix posterior (apps/web, no en este snapshot)
`lab-v45-reubicar`: re-Ubicar con prior tip (deshacer MIRROR en búsqueda + cardinal anclado).
Si ese fix falla, restaurar este snapshot y NO copiar el LabMapEngine/lab-session post-v45.
