"""Caption events — the unit of text that flows from engines to the audience."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Rough speaking rate used to estimate utterance start when unknown (~15 chars/s).
CHARS_PER_SEC = 15.0


@dataclass
class CaptionEvent:
    """One caption utterance in one or more languages.

    kind:
      - "partial": in-progress utterance, may still change (UI shows it dimmed)
      - "final":   confirmed utterance (UI locks it in)
      - "status":  engine/session notices ("listening", "engine ready", ...)
    """

    utt_id: int
    kind: str
    texts: dict[str, str]  # lang code -> caption text (empty string = unavailable)
    src_lang: str | None = None
    t0: float = 0.0  # seconds on the session audio timeline (utterance start)
    t1: float = 0.0  # seconds on the session audio timeline (utterance end)
    latency_ms: int = 0
    engine: str = ""
    seq: int = 0  # assigned by the publisher
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "utt_id": self.utt_id,
            "kind": self.kind,
            "texts": self.texts,
            "src_lang": self.src_lang,
            "t0": round(self.t0, 3),
            "t1": round(self.t1, 3),
            "latency_ms": self.latency_ms,
            "engine": self.engine,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CaptionEvent":
        return cls(
            utt_id=d["utt_id"],
            kind=d["kind"],
            texts=dict(d.get("texts") or {}),
            src_lang=d.get("src_lang"),
            t0=float(d.get("t0") or 0.0),
            t1=float(d.get("t1") or 0.0),
            latency_ms=int(d.get("latency_ms") or 0),
            engine=d.get("engine") or "",
            seq=int(d.get("seq") or 0),
            meta=dict(d.get("meta") or {}),
        )

    def estimated_t0(self) -> float:
        """Fallback start time from the longest text when the source can't tell us."""
        longest = max((len(t) for t in self.texts.values()), default=0)
        return max(0.0, self.t1 - max(1.0, longest / CHARS_PER_SEC))
