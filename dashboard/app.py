"""FastAPI dashboard: static mobile UI + WebSocket live state."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from can_reader.state import SharedState

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(state: SharedState) -> FastAPI:
    app = FastAPI(title="Sonata CAN Dashboard", docs_url=None, redoc_url=None)
    app.state.shared = state  # type: ignore[attr-defined]

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/state")
    async def api_state() -> dict:
        return state.snapshot()

    @app.websocket("/ws")
    async def ws_feed(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            while True:
                await websocket.send_json(state.snapshot())
                await asyncio.sleep(0.1)  # ~10 Hz
        except WebSocketDisconnect:
            log.debug("WebSocket client disconnected")
        except Exception as exc:  # noqa: BLE001
            log.debug("WebSocket closed: %s", exc)

    return app
