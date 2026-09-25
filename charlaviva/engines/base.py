"""Engine interface: audio in → caption events out."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

from ..events import CaptionEvent

EventHandler = Callable[[CaptionEvent], None]


@dataclass
class EngineConfig:
    src_lang: str = "auto"  # 'auto' or ISO code
    outputs: list[str] = field(default_factory=lambda: ["es", "en"])
    glossary: list[str] = field(default_factory=list)
    on_event: EventHandler = lambda e: None


class Engine(ABC):
    """Turns a continuous PCM16/16kHz stream into multilingual caption events.

    Contract:
      feed()      — called with every audio chunk in order (t = chunk start, sec)
      on_utterance_end() — client-side VAD detected end of speech (hybrid VAD)
      stop()      — stream is over, emit everything pending
    Engines call self.emit(...) whenever they have partial or final captions.
    """

    name = "base"

    def __init__(self, cfg: EngineConfig) -> None:
        self.cfg = cfg
        self.on_event = cfg.on_event
        self.last_t = 0.0
        self._utt_id = 0
        self._seq = 0

    # -- lifecycle -----------------------------------------------------
    async def start(self) -> None:  # noqa: B027
        """Optional async setup (connections, model loading)."""

    async def stop(self) -> None:
        """Flush pending work and release resources."""

    # -- audio in ------------------------------------------------------
    @abstractmethod
    async def feed(self, pcm: bytes, t: float) -> None:
        ...

    async def on_utterance_end(self, t: float) -> None:
        """Client VAD fired a speech boundary (good moment to finalize)."""

    def note_vad(self, event: str, t: float) -> None:
        """Informative hook: 'speech_start' / 'speech_end' from the client VAD."""

    # -- captions out --------------------------------------------------
    def emit(
        self,
        kind: str,
        texts: dict[str, str],
        *,
        src_lang: str | None = None,
        t1: float | None = None,
        t0: float | None = None,
        meta: dict[str, Any] | None = None,
    ) -> CaptionEvent:
        t1 = self.last_t if t1 is None else t1
        ev = CaptionEvent(
            utt_id=self._utt_id,
            kind=kind,
            texts={k: v for k, v in texts.items() if v and k},
            src_lang=src_lang or (self.cfg.src_lang if self.cfg.src_lang != "auto" else None),
            t0=t0 if t0 is not None else max(0.0, t1 - 1.0),
            t1=t1,
            engine=self.name,
            meta=meta or {},
        )
        if kind == "final":
            self._utt_id += 1
        self.on_event(ev)
        return ev

    def status(self, message: str, **meta: Any) -> None:
        self.on_event(
            CaptionEvent(
                utt_id=self._utt_id,
                kind="status",
                texts={"status": message},
                t1=self.last_t,
                engine=self.name,
                meta=meta,
            )
        )
