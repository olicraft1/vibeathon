"""Local speech engine: faster-whisper for ASR + optional Gemini text MT.

100% offline transcription (any whisper language → original text, and any
language → English via whisper's built-in "translate" task). Spanish/Portuguese
output needs a translation engine: GEMINI_API_KEY (free tier) enables it via
the text MT helper; without it, those languages are marked unavailable.

Audio is segmented with the session's client-side VAD: partial transcripts are
emitted every few seconds while someone speaks, and a final at utterance end.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import numpy as np

from ..audio import pcm16_to_float, SAMPLE_RATE
from .base import Engine, EngineConfig
from .mt import translate_texts

if TYPE_CHECKING:
    from ..config import Settings

MAX_WINDOW_SEC = 28.0  # whisper's effective context is 30s
PARTIAL_EVERY_SEC = 3.5
PRE_ROLL_SEC = 0.4

# One whisper model per (size, device, compute) — shared by all sessions so 10
# stages don't load 10 copies in RAM.
_MODEL_CACHE: dict[tuple[str, str, str], object] = {}


def _get_model(settings: "Settings"):
    key = (settings.whisper_model, settings.whisper_device, settings.whisper_compute)
    if key not in _MODEL_CACHE:
        from faster_whisper import WhisperModel

        _MODEL_CACHE[key] = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute,
        )
    return _MODEL_CACHE[key]


class WhisperLocalEngine(Engine):
    name = "whisper"

    def __init__(self, cfg: EngineConfig, settings: "Settings") -> None:
        super().__init__(cfg)
        self.settings = settings
        self._model = None
        self._buf = bytearray()
        self._buf_t0 = 0.0
        self._last_partial_at = 0.0
        self._busy = False
        self._in_speech = False
        self._last_final_t = -1.0
        self._warned_no_mt = False

    async def start(self) -> None:
        self.status(f"loading whisper model '{self.settings.whisper_model}'…")
        self._model = await asyncio.to_thread(_get_model, self.settings)
        self.status(f"whisper '{self.settings.whisper_model}' ready (local, offline)")

    async def feed(self, pcm: bytes, t: float) -> None:
        self.last_t = t + len(pcm) / 2 / SAMPLE_RATE
        if not self._buf:
            self._buf_t0 = t
        self._buf += pcm
        # cap the rolling window
        max_bytes = int(MAX_WINDOW_SEC * SAMPLE_RATE * 2)
        if len(self._buf) > max_bytes:
            drop = len(self._buf) - max_bytes
            del self._buf[: drop - (drop % 2)]
            self._buf_t0 = t - MAX_WINDOW_SEC
        # speculative partials while speech continues
        if (
            self._in_speech
            and not self._busy
            and (self.last_t - self._buf_t0) >= PARTIAL_EVERY_SEC
            and (self.last_t - self._last_partial_at) >= PARTIAL_EVERY_SEC
        ):
            await self._transcribe_and_emit(partial=True)

    def note_vad(self, event: str, t: float) -> None:
        self._in_speech = event == "speech_start"

    async def on_utterance_end(self, t: float) -> None:
        while self._busy:  # let a running partial finish first
            await asyncio.sleep(0.02)
        self._in_speech = False
        await self._transcribe_and_emit(partial=False, t1=t)

    async def stop(self) -> None:
        if self._buf and (self.last_t - self._last_final_t) > 0.3:
            await self._transcribe_and_emit(partial=False)

    # ------------------------------------------------------------------
    def _slice_window(self) -> np.ndarray:
        data = bytes(self._buf)
        window = data[-int(MAX_WINDOW_SEC * SAMPLE_RATE * 2) :]
        return pcm16_to_float(window)

    def _prompt(self) -> str | None:
        if not self.cfg.glossary:
            return None
        return "Tech glossary & proper nouns: " + ", ".join(self.cfg.glossary[:40])

    def _run_whisper(self, audio: np.ndarray, task: str) -> tuple[str | None, str]:
        language = self.cfg.src_lang if self.cfg.src_lang != "auto" else None
        if task == "translate":
            language = None  # whisper detects source and translates → English
        segments, info = self._model.transcribe(
            audio,
            language=language,
            task=task,
            beam_size=1,
            initial_prompt=self._prompt(),
            vad_filter=False,
            condition_on_previous_text=False,
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        lang = getattr(info, "language", None) if task == "transcribe" else "en"
        return lang, text

    async def _transcribe_and_emit(self, *, partial: bool, t1: float | None = None) -> None:
        if self._busy or not self._buf or self._model is None:
            return
        self._busy = True
        try:
            audio = self._slice_window()
            lang, text = await asyncio.to_thread(self._run_whisper, audio, "transcribe")
            if not text:
                return
            lang = lang or (
                self.cfg.src_lang if self.cfg.src_lang != "auto" else "src"
            )
            texts = {lang: text}
            targets = [o for o in self.cfg.outputs if o and o != lang]
            want_en = "en" in targets and lang != "en"
            if want_en and not partial:
                _, en_text = await asyncio.to_thread(self._run_whisper, audio, "translate")
                if en_text:
                    texts["en"] = en_text
                targets = [o for o in targets if o != "en"]
            if targets and not partial:
                if self.settings.gemini_api_key:
                    mt = await translate_texts(
                        text, targets, self.cfg.glossary, self.settings
                    )
                    texts.update(mt)
                elif not self._warned_no_mt:
                    self._warned_no_mt = True
                    self.status(
                        "translations to "
                        + "/".join(targets)
                        + " need GEMINI_API_KEY (transcription-only mode)"
                    )
            self.emit(
                "partial" if partial else "final",
                texts,
                src_lang=lang,
                t0=self._buf_t0,
                t1=self.last_t if t1 is None else t1,
            )
            if partial:
                self._last_partial_at = time.monotonic()
            else:
                self._last_final_t = self.last_t
                # keep a short pre-roll so the next utterance keeps context
                keep = int(PRE_ROLL_SEC * SAMPLE_RATE * 2)
                self._buf = bytearray(bytes(self._buf)[-keep:])
                self._buf_t0 = max(0.0, self.last_t - PRE_ROLL_SEC)
        finally:
            self._busy = False
