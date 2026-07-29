"""
=============================================================================
R-Bot — WebSocket: telemetría en tiempo real
=============================================================================
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.deps import get_robot_status_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/telemetry")
async def telemetry_ws(websocket: WebSocket) -> None:
    """Stream de telemetría hacia la HMI (~8 Hz) para que el trazo no vaya atrasado."""
    await websocket.accept()
    status_service = get_robot_status_service()
    try:
        while True:
            try:
                status = await status_service.get_status()
                payload = status.model_dump(mode="json")
                await websocket.send_json({"type": "status", "payload": payload})
            except WebSocketDisconnect:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("Telemetría WS: %s", exc)
                try:
                    await websocket.send_json(
                        {"type": "error", "message": str(exc)}
                    )
                except Exception:  # noqa: BLE001
                    break
            await asyncio.sleep(0.12)
    except WebSocketDisconnect:
        logger.info("Cliente telemetría desconectado")
    except Exception as exc:  # noqa: BLE001
        logger.info("Telemetría WS cerrada: %s", exc)
