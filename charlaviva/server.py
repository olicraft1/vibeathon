"""CharlaViva HTTP + WebSocket server (FastAPI).

Pages:      /        audience view      /admin   production monitor
            /overlay OBS browser-source captions
API:        /api/…   sessions, captions, exports, metrics
WebSockets: /ws/captions/{id}  live caption events
            /ws/audio/{id}     browser microphone PCM ingest
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .config import WEB_ROOT, Settings, resolve_engine
from .export import CONTENT_TYPES, EXPORTERS
from .session import SessionManager, demo_session_specs

DEFAULT_GLOSSARY_HINT = ["Nerdearla", "Kubernetes", "Gemini", "Whisper"]


class SourceSpec(BaseModel):
    type: Literal["file", "stream", "mic"] = "file"
    path: str = ""
    url: str = ""
    speed: float = 1.0
    loop: bool = False


class SessionCreate(BaseModel):
    name: str = "session"
    source: SourceSpec = Field(default_factory=SourceSpec)
    src_lang: str = "auto"
    outputs: list[str] = Field(default_factory=lambda: ["es", "en"])
    glossary: list[str] = Field(default_factory=list)
    engine: str | None = None
    autostart: bool = True


def create_app(
    manager: SessionManager | None = None,
    demo_specs: list[dict[str, Any]] | None = None,
) -> FastAPI:
    settings = Settings.from_env()
    manager = manager or SessionManager(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # demo sessions are created here: the event loop is already running
        if demo_specs:
            for spec in demo_specs:
                manager.create(spec)
        yield
        await manager.stop_all()

    app = FastAPI(title="CharlaViva", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.manager = manager
    app.state.settings = settings

    # ---------------- pages & static ----------------
    if WEB_ROOT.exists():
        app.mount("/static", StaticFiles(directory=str(WEB_ROOT)), name="static")

    def page(name: str) -> FileResponse:
        path = WEB_ROOT / name
        if not path.exists():
            raise HTTPException(404, f"{name} not found")
        return FileResponse(path)

    @app.get("/")
    async def index() -> FileResponse:
        return page("index.html")

    @app.get("/admin")
    async def admin() -> FileResponse:
        return page("admin.html")

    @app.get("/overlay")
    async def overlay() -> FileResponse:
        return page("overlay.html")

    # ---------------- meta ----------------
    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        has_whisper = False
        try:
            import faster_whisper  # noqa: F401

            has_whisper = True
        except ImportError:
            pass
        return {
            "ok": True,
            "version": __version__,
            "engine_default": resolve_engine(settings),
            "gemini_configured": bool(settings.gemini_api_key),
            "whisper_available": has_whisper,
            "sessions": len(manager.sessions),
        }

    @app.get("/api/config")
    async def config() -> dict[str, Any]:
        return {
            "default_outputs": list(settings.default_outputs),
            "engine_default": resolve_engine(settings),
            "engines": ["auto", "gemini", "whisper", "canned"],
            "languages": ["es", "en", "pt", "fr"],
            "glossary_hint": DEFAULT_GLOSSARY_HINT,
        }

    # ---------------- sessions ----------------
    @app.get("/api/sessions")
    async def list_sessions() -> list[dict[str, Any]]:
        return [s.to_dict() for s in manager.list()]

    @app.post("/api/sessions", status_code=201)
    async def create_session(body: SessionCreate) -> dict[str, Any]:
        session = manager.create(body.model_dump(), autostart=body.autostart)
        return session.to_dict()

    @app.post("/api/demo")
    async def load_demo(n: int = Query(2, ge=1, le=3)) -> list[dict[str, Any]]:
        """Start the bundled sample sessions (handy for judges & rehearsals)."""
        created = [manager.create(spec) for spec in demo_session_specs(n)]
        return [s.to_dict() for s in created]

    def _session_or_404(sid: str):
        session = manager.get(sid)
        if not session:
            raise HTTPException(404, f"session {sid!r} not found")
        return session

    @app.get("/api/sessions/{sid}")
    async def get_session(sid: str) -> dict[str, Any]:
        return _session_or_404(sid).to_dict()

    @app.post("/api/sessions/{sid}/start")
    async def start_session(sid: str) -> dict[str, Any]:
        session = _session_or_404(sid)
        session.start()
        return session.to_dict()

    @app.post("/api/sessions/{sid}/stop")
    async def stop_session(sid: str) -> dict[str, Any]:
        session = _session_or_404(sid)
        await session.stop()
        return session.to_dict()

    @app.delete("/api/sessions/{sid}")
    async def delete_session(sid: str) -> dict[str, bool]:
        return {"deleted": await manager.delete(sid)}

    @app.get("/api/sessions/{sid}/captions")
    async def captions(sid: str, since: int = Query(0)) -> dict[str, Any]:
        session = _session_or_404(sid)
        events = [e.to_dict() for e in session.history if e.seq >= since]
        return {"session": sid, "events": events}

    @app.get("/api/sessions/{sid}/metrics")
    async def metrics(sid: str) -> dict[str, Any]:
        return _session_or_404(sid).metrics.to_dict()

    @app.get("/api/sessions/{sid}/export")
    async def export(
        sid: str,
        format: str = Query("srt", pattern="^(srt|vtt|txt)$"),
        lang: str | None = Query(None, description="es|en|pt or omit for bilingual"),
    ) -> Response:
        session = _session_or_404(sid)
        text = EXPORTERS[format](session.history, lang=lang)
        filename = f"{session.id}-{lang or 'all'}.{format}"
        media = CONTENT_TYPES[format] if format != "srt" else "text/plain"
        return Response(
            content=text,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # ---------------- websockets ----------------
    @app.websocket("/ws/captions/{sid}")
    async def ws_captions(ws: WebSocket, sid: str) -> None:
        session = manager.get(sid)
        if not session:
            await ws.close(code=4404)
            return
        await ws.accept()
        queue = session.subscribe()
        recv_task = asyncio.create_task(ws.receive_text())
        try:
            await ws.send_text(
                json.dumps({"type": "hello", "session": session.to_dict()})
            )
            await ws.send_text(
                json.dumps({"type": "history", "events": session.snapshot_events()})
            )
            while True:
                # pump caption events; answer client pings when they show up
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=1.0)
                    await ws.send_text(json.dumps(payload))
                except asyncio.TimeoutError:
                    pass
                if recv_task.done():
                    msg = recv_task.result()  # may raise WebSocketDisconnect
                    if msg == "ping":
                        await ws.send_text("pong")
                    recv_task = asyncio.create_task(ws.receive_text())
        except (WebSocketDisconnect, RuntimeError, asyncio.CancelledError):
            pass
        finally:
            if not recv_task.done():
                recv_task.cancel()
            session.unsubscribe(queue)

    @app.websocket("/ws/audio/{sid}")
    async def ws_audio(ws: WebSocket, sid: str) -> None:
        """Browser microphone ingest: binary PCM16/16k mono frames."""
        session = manager.get(sid)
        if not session:
            await ws.close(code=4404)
            return
        await ws.accept()
        source = session.source
        if not hasattr(source, "push"):
            await ws.send_text(json.dumps({"error": "session source is not a microphone"}))
            await ws.close(code=4400)
            return
        try:
            while True:
                message = await ws.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                data = message.get("bytes")
                if data:
                    source.push(data)
                elif message.get("text") == '{"type":"end"}':
                    break
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            source.close()

    return app


app = None  # created lazily by uvicorn factory / cli


def get_app() -> FastAPI:
    global app
    if app is None:
        app = create_app()
    return app
