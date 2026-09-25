"""Session & SessionManager: one live stage = one session.

Each session owns: an audio source → client VAD → engine → caption bus.
Many sessions run concurrently as independent asyncio tasks, which is how we
put 5, 10 or more stages in parallel on a single node.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .audio import EnergyVAD
from .config import SAMPLES_DIR, Settings
from .engines import EngineConfig, create_engine
from .events import CaptionEvent
from .sources import AudioSource, MicSource, build_source

log = logging.getLogger("charlaviva.session")

MAX_HISTORY = 2000
QUEUE_SIZE = 256


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:32] or "session"
    return f"{slug}-{uuid.uuid4().hex[:6]}"


@dataclass
class SessionSpec:
    name: str
    source: dict
    src_lang: str = "auto"
    outputs: list[str] = field(default_factory=lambda: ["es", "en"])
    glossary: list[str] = field(default_factory=list)
    engine: str | None = None  # override: auto|gemini|whisper|canned

    @classmethod
    def from_dict(cls, d: dict[str, Any], defaults: tuple[str, ...] = ("es", "en")) -> "SessionSpec":
        gloss = d.get("glossary") or []
        if isinstance(gloss, str):
            gloss = [g.strip() for g in re.split(r"[,\n]", gloss) if g.strip()]
        outputs = d.get("outputs") or list(defaults)
        return cls(
            name=str(d.get("name") or "session"),
            source=dict(d.get("source") or {"type": "file", "path": ""}),
            src_lang=str(d.get("src_lang") or d.get("language") or "auto"),
            outputs=[str(o).lower()[:2] for o in outputs if o],
            glossary=[str(g) for g in gloss][:40],
            engine=(d.get("engine") or None),
        )


class SessionMetrics:
    def __init__(self) -> None:
        self.started_at: float | None = None
        self.stopped_at: float | None = None
        self.chunks_in = 0
        self.audio_sec = 0.0
        self.finals = 0
        self.partials = 0
        self.latencies: deque[int] = deque(maxlen=200)
        self.errors: deque[dict[str, Any]] = deque(maxlen=20)
        self.engine_label = "-"

    def record_error(self, message: str) -> None:
        self.errors.append({"t": time.time(), "message": message})

    def latency_percentile(self, p: float) -> int:
        if not self.latencies:
            return 0
        data = sorted(self.latencies)
        idx = min(len(data) - 1, int(len(data) * p))
        return data[idx]

    def to_dict(self) -> dict[str, Any]:
        now = time.time()
        uptime = 0.0
        if self.started_at:
            uptime = (self.stopped_at or now) - self.started_at
        return {
            "engine": self.engine_label,
            "uptime_s": round(uptime, 1),
            "chunks_in": self.chunks_in,
            "audio_s": round(self.audio_sec, 1),
            "finals": self.finals,
            "partials": self.partials,
            "latency_avg_ms": int(sum(self.latencies) / len(self.latencies)) if self.latencies else 0,
            "latency_p50_ms": self.latency_percentile(0.50),
            "latency_p90_ms": self.latency_percentile(0.90),
            "latency_last_ms": self.latencies[-1] if self.latencies else 0,
            "errors": list(self.errors),
        }


class Session:
    def __init__(self, spec: SessionSpec, settings: Settings) -> None:
        self.id = _slug(spec.name)
        self.spec = spec
        self.settings = settings
        self.state = "created"  # created | running | stopped | error
        self.error: str | None = None
        self.metrics = SessionMetrics()
        self.history: list[CaptionEvent] = []
        self.partial: CaptionEvent | None = None
        self.subscribers: set[asyncio.Queue] = set()
        self.source: AudioSource = build_source(spec.source)
        self._task: asyncio.Task | None = None
        self._seq = 0
        self._wall_start: float | None = None

    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        last_texts: dict[str, str] = {}
        src_lang = self.spec.src_lang
        for ev in reversed(self.history):
            if ev.kind == "final":
                last_texts = ev.texts
                src_lang = ev.src_lang or src_lang
                break
        return {
            "id": self.id,
            "name": self.spec.name,
            "state": self.state,
            "error": self.error,
            "src_lang": src_lang,
            "outputs": self.spec.outputs,
            "glossary": self.spec.glossary,
            "engine": self.spec.engine or "auto",
            "source": {**self.spec.source, "desc": self.source.describe()},
            "last_texts": last_texts,
            "stats": self.metrics.to_dict(),
        }

    # ------------------------------------------------------------------
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_SIZE)
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)

    def _fanout(self, payload: dict[str, Any]) -> None:
        dead = []
        for q in self.subscribers:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                try:  # drop oldest to keep live view fresh
                    q.get_nowait()
                    q.put_nowait(payload)
                except Exception:
                    dead.append(q)
            except Exception:
                dead.append(q)
        for q in dead:
            self.subscribers.discard(q)

    def publish(self, ev: CaptionEvent) -> None:
        ev.seq = self._seq
        self._seq += 1
        if ev.t0 <= 0:
            ev.t0 = ev.estimated_t0()
        if self._wall_start is not None and ev.kind != "status":
            ev.latency_ms = max(
                0, int((time.monotonic() - (self._wall_start + ev.t1)) * 1000)
            )
            self.metrics.latencies.append(ev.latency_ms)
        if ev.kind == "final":
            self.metrics.finals += 1
            self.partial = None
            self.history.append(ev)
            if len(self.history) > MAX_HISTORY:
                del self.history[: len(self.history) - MAX_HISTORY]
        elif ev.kind == "partial":
            self.metrics.partials += 1
            self.partial = ev
        else:  # status
            self.history.append(ev)
        self._fanout({"type": "caption", "event": ev.to_dict()})

    def snapshot_events(self) -> list[dict[str, Any]]:
        events = [e.to_dict() for e in self.history if e.kind in ("final", "status")]
        if self.partial:
            events.append(self.partial.to_dict())
        return events

    # ------------------------------------------------------------------
    def _load_cues(self) -> tuple[list, float]:
        """Pre-authored cues for canned mode: <file>.cues.json next to the audio."""
        from .engines.canned import Cue

        src = self.spec.source
        if src.get("type", "file") != "file":
            return [], 0.0
        path = Path(src.get("path") or "")
        for candidate in (path.with_suffix(path.suffix + ".cues.json"), path.with_suffix(".cues.json")):
            if candidate.exists():
                data = json.loads(candidate.read_text(encoding="utf-8"))
                return [Cue.from_dict(c) for c in data.get("cues", [])], float(data.get("duration") or 0)
        return [], 0.0

    async def run(self) -> None:
        self.state = "running"
        self.error = None
        self._wall_start = time.monotonic()
        self.metrics.started_at = time.time()
        self.metrics.stopped_at = None

        from .config import resolve_engine

        engine_name = (self.spec.engine or "auto").lower()
        resolved = engine_name if engine_name != "auto" else resolve_engine(self.settings)

        cfg = EngineConfig(
            src_lang=self.spec.src_lang,
            outputs=self.spec.outputs,
            glossary=self.spec.glossary,
            on_event=self.publish,
        )
        cues, cue_duration = ([], 0.0)
        try:
            if resolved == "canned":
                cues, cue_duration = self._load_cues()
                engine = create_engine(
                    cfg, self.settings, cues=cues, duration=cue_duration, name="canned"
                )
            else:
                engine = create_engine(cfg, self.settings, name=resolved)
        except Exception as err:
            self.state = "error"
            self.error = str(err)
            self.metrics.record_error(str(err))
            self.publish(
                CaptionEvent(
                    utt_id=0, kind="status", texts={"status": f"engine error: {err}"}, engine="session"
                )
            )
            return

        self.metrics.engine_label = engine.name
        vad = EnergyVAD(silence_ms=self.settings.vad_silence_ms)
        try:
            try:
                await engine.start()
            except Exception as start_err:
                # e.g. whisper model can't be downloaded in this environment —
                # degrade to the bundled captions when the source has them.
                cues, cue_duration = self._load_cues()
                if not cues or resolved == "canned":
                    raise
                self.metrics.record_error(f"{resolved} unavailable: {start_err}")
                self.publish(
                    CaptionEvent(
                        utt_id=0,
                        kind="status",
                        texts={
                            "status": f"{resolved} engine unavailable — showing the bundled captions (canned fallback)"
                        },
                        engine="session",
                    )
                )
                engine = create_engine(
                    cfg, self.settings, cues=cues, duration=cue_duration, name="canned"
                )
                self.metrics.engine_label = engine.name
                await engine.start()
            async for pcm, t in self.source.chunks():
                self.metrics.chunks_in += 1
                self.metrics.audio_sec = t
                for vad_event in vad.feed(pcm):
                    engine.note_vad(vad_event, t)
                    if vad_event == "speech_end":
                        await engine.on_utterance_end(t)
                await engine.feed(pcm, t)
            for vad_event in vad.flush():
                engine.note_vad(vad_event, self.metrics.audio_sec)
                if vad_event == "speech_end":
                    await engine.on_utterance_end(self.metrics.audio_sec)
            await engine.stop()
        except asyncio.CancelledError:
            await engine.stop()
            raise
        except Exception as err:
            log.exception("session %s failed", self.id)
            self.state = "error"
            self.error = str(err)
            self.metrics.record_error(str(err))
        finally:
            if self.state == "running":
                self.state = "stopped"
            self.metrics.stopped_at = time.time()
            self.publish(
                CaptionEvent(
                    utt_id=0,
                    kind="status",
                    texts={"status": "stream ended" if self.state == "stopped" else f"error: {self.error}"},
                    engine=engine.name,
                )
            )

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        if isinstance(self.source, MicSource):
            self.source.close()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self.state == "running":
            self.state = "stopped"


class SessionManager:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self.sessions: dict[str, Session] = {}

    def create(self, spec_dict: dict[str, Any], autostart: bool = True) -> Session:
        spec = SessionSpec.from_dict(spec_dict, defaults=self.settings.default_outputs)
        session = Session(spec, self.settings)
        self.sessions[session.id] = session
        if autostart:
            session.start()
        return session

    def get(self, sid: str) -> Session | None:
        return self.sessions.get(sid)

    def list(self) -> list[Session]:
        return list(self.sessions.values())

    async def stop(self, sid: str) -> bool:
        session = self.sessions.get(sid)
        if not session:
            return False
        await session.stop()
        return True

    async def delete(self, sid: str) -> bool:
        session = self.sessions.pop(sid, None)
        if not session:
            return False
        await session.stop()
        return True

    async def stop_all(self) -> None:
        for session in list(self.sessions.values()):
            await session.stop()


def demo_session_specs(sessions: int = 2) -> list[dict[str, Any]]:
    """The bundled sample stages used by `charlaviva demo` (and tests)."""
    samples = [
        {
            "name": "Escenario A · Scaling Open Source (EN)",
            "path": str(SAMPLES_DIR / "talk_en.mp3"),
            "src_lang": "en",
            "glossary": ["Nerdearla", "Kubernetes", "GitHub Actions", "Prometheus", "Grafana", "YAML"],
        },
        {
            "name": "Escenario B · Accesibilidad (ES)",
            "path": str(SAMPLES_DIR / "talk_es.mp3"),
            "src_lang": "es",
            "glossary": ["Nerdearla", "Whisper", "Gemini", "PyCon", "DevFest", "MIT"],
        },
        {
            "name": "Escenario C · Postgres (EN)",
            "path": str(SAMPLES_DIR / "talk_en2.mp3"),
            "src_lang": "en",
            "glossary": ["Postgres", "JSON", "latency"],
        },
    ]
    specs = []
    for s in samples[: max(1, min(sessions, len(samples)))]:
        specs.append(
            {
                "name": s["name"],
                "source": {"type": "file", "path": s["path"], "loop": True, "speed": 1.0},
                "src_lang": s["src_lang"],
                "outputs": ["es", "en"],
                "glossary": s["glossary"],
            }
        )
    return specs
