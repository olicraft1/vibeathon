"""Engine factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Engine, EngineConfig

if TYPE_CHECKING:
    from ..config import Settings
    from .canned import Cue


def create_engine(
    cfg: EngineConfig,
    settings: "Settings",
    cues: list["Cue"] | None = None,
    duration: float | None = None,
    name: str | None = None,
) -> Engine:
    """Create an engine by explicit name or from settings (auto: gemini→whisper→canned)."""
    from ..config import resolve_engine

    chosen = (name or "auto").lower()
    if chosen in ("auto", ""):
        chosen = resolve_engine(settings)

    if chosen == "gemini":
        from .gemini_live import GeminiLiveEngine

        return GeminiLiveEngine(cfg, settings)
    if chosen == "whisper":
        from .whisper_local import WhisperLocalEngine

        return WhisperLocalEngine(cfg, settings)
    if chosen == "canned":
        from .canned import CannedEngine

        return CannedEngine(cfg, cues or [], duration=duration)
    raise ValueError(f"unknown engine {chosen!r} (use auto|gemini|whisper|canned)")


__all__ = ["Engine", "EngineConfig", "create_engine"]
