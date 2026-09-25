"""Gemini Live engine: one bidirectional stream per session.

Two modes (GEMINI_MODE):

- ``caption`` (default): a general live model (e.g. gemini-3.8-live) listens to
  the audio and emits tagged caption lines — transcription + translations in a
  single connection. Parsed by :class:`charlaviva.engines.parser.CaptionBlockParser`.

- ``transcribe``: a specialized live-ASR model (e.g. gemini-3.5-transcribe-live)
  provides low-latency source transcription via ``input_audio_transcription``;
  finished utterances are translated with the text MT helper.

Hybrid VAD: our client-side energy VAD fires ``audio_stream_end`` at utterance
boundaries so the model finalizes captions without waiting for its own VAD.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from .base import Engine, EngineConfig
from .mt import get_client, translate_texts
from .parser import CaptionBlockParser

if TYPE_CHECKING:
    from ..config import Settings

log = logging.getLogger("charlaviva.gemini")

# Tried in order if the configured model is unavailable.
FALLBACK_LIVE_MODELS = [
    "gemini-3.8-live",
    "gemini-2.5-flash-native-audio",
    "gemini-2.0-flash-live-001",
]
FALLBACK_TRANSCRIBE_MODELS = [
    "gemini-3.5-transcribe-live",
    "gemini-2.5-flash-native-audio",
    "gemini-2.0-flash-live-001",
]

LANG_NAMES = {"es": "Spanish", "en": "English", "pt": "Portuguese", "fr": "French"}

CAPTIONER_PROMPT = """\
You are CharlaViva, a live captioner and simultaneous interpreter at a technology \
conference. You receive a CONTINUOUS AUDIO stream from a stage microphone.

YOUR ONLY JOB: emit live captions for what you hear. Never answer the speakers. \
Never comment. Never chat. Never use markdown.

For EVERY complete utterance, immediately output EXACTLY this block of lines, in \
this order, with NO blank lines and NO extra text:

[{src}] verbatim transcription in the same language as the audio
[es] Spanish translation
[en] English translation

Rules:
- Always emit the first line tagged with the real ISO code of the spoken language \
(es, en, pt, fr, …).
- Then one line per requested translation target (skip a target when it equals the \
spoken language).
- Emit the block the moment the utterance completes — latency beats polish.
- Transcribe verbatim; translate faithfully, keep the speaker's register short \
and caption-like.
- Technical terms and proper nouns MUST match this glossary: {glossary}
- If the audio is silent, music or unintelligible, output nothing at all.
- Output pure caption lines like: [en] Hello everyone, welcome to the stage.

Requested translation targets for this session: {targets}.
"""


def _merge_transcript(acc: str, new: str) -> str:
    """Robustly merge a transcription update that may be cumulative or delta."""
    if not new:
        return acc
    if not acc:
        return new
    if new.startswith(acc):
        return new
    if acc.endswith(new):
        return acc
    return acc + new


def _merge_delta(acc: str, new: str) -> tuple[str, str]:
    """Merge an update that may be cumulative or delta. Returns (new_acc, delta)."""
    if not new:
        return acc, ""
    if not acc:
        return new, new
    if new.startswith(acc):
        return new, new[len(acc) :]
    if acc.endswith(new):
        return acc, ""
    return acc + new, new


class GeminiLiveEngine(Engine):
    name = "gemini"

    def __init__(self, cfg: EngineConfig, settings: "Settings") -> None:
        super().__init__(cfg)
        self.settings = settings
        self.mode = settings.gemini_mode if settings.gemini_mode in ("caption", "transcribe") else "caption"
        self._ctx = None
        self._session = None
        self._receiver: asyncio.Task | None = None
        self._send_lock = asyncio.Lock()
        self._model_used = ""
        # caption mode
        self._parser = CaptionBlockParser(on_partial=self._on_partial, on_final=self._on_final)
        self._model_acc = ""
        # transcribe mode
        self._input_acc = ""
        self._input_t0 = 0.0
        self._translate_tasks: set[asyncio.Task] = set()

    # ------------------------------------------------------------------
    def _system_prompt(self) -> str:
        targets = [o for o in self.cfg.outputs if o]
        names = ", ".join(f"{LANG_NAMES.get(t, t)} ({t})" for t in targets) or "Spanish (es)"
        return CAPTIONER_PROMPT.format(
            glossary=", ".join(self.cfg.glossary[:40]) or "(none)",
            targets=names,
        )

    def _candidates(self) -> list[str]:
        base = (
            [self.settings.gemini_model]
            if self.mode == "caption"
            else [self.settings.gemini_transcribe_model]
        )
        pool = FALLBACK_LIVE_MODELS if self.mode == "caption" else FALLBACK_TRANSCRIBE_MODELS
        seen, out = set(), []
        for m in base + pool:
            if m and m not in seen:
                seen.add(m)
                out.append(m)
        return out

    async def start(self) -> None:
        from google import genai
        from google.genai import types

        client = get_client(self.settings) or genai.Client(
            api_key=self.settings.gemini_api_key
        )

        vocab = list(dict.fromkeys(self.cfg.glossary))[:100] or None
        transcription = types.AudioTranscriptionConfig()
        if self.mode == "transcribe":
            try:
                transcription = types.AudioTranscriptionConfig(
                    language_codes=[] if self.cfg.src_lang == "auto" else [self.cfg.src_lang],
                    **({"custom_vocabulary": vocab} if vocab else {}),
                )
            except Exception:  # older SDK/model without custom_vocabulary
                transcription = types.AudioTranscriptionConfig()

        kwargs: dict[str, Any] = {
            "response_modalities": ["TEXT"],
            "input_audio_transcription": transcription,
        }
        if self.mode == "caption":
            kwargs["system_instruction"] = self._system_prompt()
        try:  # kill latency-inducing deliberation when the model supports it
            kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        except Exception:
            pass

        last_err: Exception | None = None
        for model in self._candidates():
            try:
                config = types.LiveConnectConfig(**kwargs)
            except Exception:
                kwargs.pop("thinking_config", None)
                config = types.LiveConnectConfig(**kwargs)
            try:
                self._ctx = client.aio.live.connect(model=model, config=config)
                self._session = await self._ctx.__aenter__()
                self._model_used = model
                break
            except Exception as err:  # unknown model / quota / auth
                last_err = err
                log.warning("gemini live connect failed for %s: %s", model, err)
                self._ctx = self._session = None
        if self._session is None:
            raise RuntimeError(f"could not open a Gemini Live session: {last_err}")

        self.name = f"gemini:{self._model_used}"
        self.status(f"gemini live ready ({self._model_used}, {self.mode} mode)")
        self._receiver = asyncio.create_task(self._receive_loop())

    async def feed(self, pcm: bytes, t: float) -> None:
        self.last_t = t + len(pcm) / 2 / 16000
        if self._session is None or not pcm:
            return
        from google.genai import types

        try:
            async with self._send_lock:
                await self._session.send_realtime_input(
                    audio=types.Blob(data=pcm, mime_type="audio/pcm;rate=16000")
                )
        except Exception as err:
            log.warning("gemini send failed: %s", err)
            self._session = None

    async def on_utterance_end(self, t: float) -> None:
        if self._session is None:
            return
        try:
            async with self._send_lock:
                await self._session.send_realtime_input(audio_stream_end=True)
        except Exception as err:
            log.warning("gemini turn-end failed: %s", err)

    async def stop(self) -> None:
        for task in list(self._translate_tasks):
            task.cancel()
        if self._receiver:
            self._receiver.cancel()
            try:
                await self._receiver
            except (asyncio.CancelledError, Exception):
                pass
        if self.mode == "caption":
            self._parser.flush()
        elif self._input_acc:
            await self._emit_transcribed(final=True)
        if self._ctx is not None:
            try:
                await self._ctx.__aexit__(None, None, None)
            except Exception:
                pass
        self._ctx = self._session = None

    # ------------------------------------------------------------------
    # caption mode
    def _on_partial(self, texts: dict[str, str]) -> None:
        if texts:
            self.emit("partial", texts, t0=max(0.0, self.last_t - 2.0))

    def _on_final(self, texts: dict[str, str]) -> None:
        if texts:
            self.emit("final", texts, t0=max(0.0, self.last_t - 2.0))

    # transcribe mode
    async def _emit_transcribed(self, *, final: bool) -> None:
        text = self._input_acc.strip()
        if not text:
            return
        lang = self.cfg.src_lang if self.cfg.src_lang != "auto" else None
        self.emit(
            "final" if final else "partial",
            {lang or "src": text},
            src_lang=lang,
            t0=self._input_t0,
        )
        if final and self.cfg.outputs:
            targets = [o for o in self.cfg.outputs if o and o != lang]
            if targets:
                task = asyncio.create_task(self._translate_and_emit(text, targets))
                self._translate_tasks.add(task)
                task.add_done_callback(self._translate_tasks.discard)
        if final:
            self._input_acc = ""
            self._input_t0 = self.last_t

    async def _translate_and_emit(self, text: str, targets: list[str]) -> None:
        mt = await translate_texts(text, targets, self.cfg.glossary, self.settings)
        if mt:
            self.emit("final", mt, t0=max(0.0, self.last_t - 2.0))

    # ------------------------------------------------------------------
    def _handle_message(self, msg: Any) -> None:
        sc = getattr(msg, "server_content", None)

        # model text output (caption mode)
        text = getattr(msg, "text", None)
        if text is None and sc is not None:
            mt = getattr(sc, "model_turn", None)
            parts = getattr(mt, "parts", None) if mt else None
            if parts:
                joined = "".join(getattr(p, "text", "") or "" for p in parts)
                text = joined or None
        if text and self.mode == "caption":
            self._model_acc, delta = _merge_delta(self._model_acc, text)
            if delta:
                self._parser.feed(delta)

        if sc is not None:
            tr = getattr(sc, "input_transcription", None)
            if tr is not None and self.mode == "transcribe":
                chunk = getattr(tr, "text", "") or ""
                finished = bool(
                    getattr(tr, "finished", False) or getattr(tr, "is_final", False)
                )
                if chunk or finished:
                    if not self._input_acc and chunk:
                        self._input_t0 = max(0.0, self.last_t - 2.0)
                    self._input_acc = _merge_transcript(self._input_acc, chunk)
                    if finished:
                        self._loop_run(self._emit_transcribed(final=True))
                    else:
                        self._loop_run(self._emit_transcribed(final=False))
            if getattr(sc, "turn_complete", False) or getattr(sc, "generation_complete", False):
                if self.mode == "caption":
                    self._model_acc = ""
                    self._parser.flush()

    def _loop_run(self, coro) -> None:
        """Schedule a coroutine from sync context (the receive loop)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(coro)
        self._translate_tasks.add(task)
        task.add_done_callback(self._translate_tasks.discard)

    async def _receive_loop(self) -> None:
        try:
            async for msg in self._session.receive():
                self._handle_message(msg)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            log.warning("gemini receive failed: %s", err)
            self.status(f"gemini stream error: {err}")
            self._session = None
