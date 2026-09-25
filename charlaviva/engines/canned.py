"""Canned engine: deterministic caption replay with zero models/credentials.

Used as the last-resort fallback (no Gemini key, no faster-whisper) and by the
test-suite. It consumes the same audio timestamps as real engines and emits the
pre-authored cues bundled with the sample talks, so the full pipeline — sessions,
WebSockets, UI, exports, monitoring — can be exercised anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base import Engine, EngineConfig


@dataclass
class Cue:
    t0: float
    t1: float
    texts: dict[str, str]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Cue":
        return cls(t0=float(d["t0"]), t1=float(d["t1"]), texts=dict(d.get("texts") or {}))


class CannedEngine(Engine):
    name = "canned"

    def __init__(self, cfg: EngineConfig, cues: list[Cue], duration: float | None = None) -> None:
        super().__init__(cfg)
        self.cues = sorted(cues, key=lambda c: c.t0)
        self.duration = duration or (self.cues[-1].t1 if self.cues else 0.0)
        self._emitted_partial: set[tuple[int, int]] = set()
        self._emitted_final: set[tuple[int, int]] = set()

    def _cycle_of(self, t: float) -> int:
        return int(t // self.duration) if self.duration > 0 else 0

    async def feed(self, pcm: bytes, t: float) -> None:
        self.last_t = t + len(pcm) / 2 / 16000
        if self.duration <= 0:
            return
        cycle = self._cycle_of(t)
        local_t = t - cycle * self.duration
        for idx, cue in enumerate(self.cues):
            key = (cycle, idx)
            if key not in self._emitted_partial and local_t >= cue.t0:
                self._emitted_partial.add(key)
                self.emit(
                    "partial",
                    dict(cue.texts),
                    src_lang=next(iter(cue.texts), None),
                    t0=cue.t0 + cycle * self.duration,
                    t1=self.last_t,
                )
            if key not in self._emitted_final and local_t >= cue.t1:
                self._emitted_final.add(key)
                self.emit(
                    "final",
                    dict(cue.texts),
                    src_lang=next(iter(cue.texts), None),
                    t0=cue.t0 + cycle * self.duration,
                    t1=cue.t1 + cycle * self.duration,
                )
            if cue.t0 > local_t:
                break
        # keep memory bounded on very long loops
        if len(self._emitted_final) > 4096:
            oldest = self._cycle_of(t) - 1
            self._emitted_final = {k for k in self._emitted_final if k[0] >= oldest}
            self._emitted_partial = {k for k in self._emitted_partial if k[0] >= oldest}
