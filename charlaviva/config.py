"""Runtime settings, loaded from environment / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent
WEB_ROOT = REPO_ROOT / "web"
SAMPLES_DIR = REPO_ROOT / "samples"

# Internal pipeline format: mono PCM16 little-endian @ 16 kHz (what Gemini Live wants).
SAMPLE_RATE = 16000
CHUNK_MS = 100  # granularity of audio feeding

LANG_NAMES = {"es": "Español", "en": "English", "pt": "Português", "fr": "Français"}
DEFAULT_OUTPUTS = ("es", "en")


def _env(name: str, default: str | None = None) -> str | None:
    val = os.environ.get(name)
    if val is None or val == "":
        return default
    return val


@dataclass
class Settings:
    host: str = "0.0.0.0"
    port: int = 8000

    # Engine: auto | gemini | whisper | canned
    engine: str = "auto"

    # Gemini Live
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.8-live"
    gemini_transcribe_model: str = "gemini-3.5-transcribe-live"
    gemini_mode: str = "caption"  # caption | transcribe
    translate_model: str = "gemini-flash-latest"

    # Local whisper
    whisper_model: str = "small"
    whisper_device: str = "auto"
    whisper_compute: str = "int8"

    # Captioning
    default_outputs: tuple[str, ...] = DEFAULT_OUTPUTS
    vad_silence_ms: int = 600

    @classmethod
    def from_env(cls) -> "Settings":
        outputs = tuple(
            o.strip()
            for o in (_env("DEFAULT_OUTPUTS", "es,en") or "es,en").split(",")
            if o.strip()
        )
        return cls(
            host=_env("HOST", "0.0.0.0") or "0.0.0.0",
            port=int(_env("PORT", "8000") or "8000"),
            engine=(_env("CHARLAVIVA_ENGINE", "auto") or "auto").lower(),
            gemini_api_key=_env("GEMINI_API_KEY"),
            gemini_model=_env("GEMINI_MODEL", "gemini-3.8-live") or "gemini-3.8-live",
            gemini_transcribe_model=_env(
                "GEMINI_TRANSCRIBE_MODEL", "gemini-3.5-transcribe-live"
            )
            or "gemini-3.5-transcribe-live",
            gemini_mode=(_env("GEMINI_MODE", "caption") or "caption").lower(),
            translate_model=_env("TRANSLATE_MODEL", "gemini-flash-latest")
            or "gemini-flash-latest",
            whisper_model=_env("WHISPER_MODEL", "small") or "small",
            whisper_device=_env("WHISPER_DEVICE", "auto") or "auto",
            whisper_compute=_env("WHISPER_COMPUTE", "int8") or "int8",
            default_outputs=outputs or DEFAULT_OUTPUTS,
            vad_silence_ms=int(_env("VAD_SILENCE_MS", "600") or "600"),
        )


def resolve_engine(settings: Settings) -> str:
    """Pick the concrete engine for 'auto' mode."""
    if settings.engine != "auto":
        return settings.engine
    if settings.gemini_api_key:
        return "gemini"
    try:
        import faster_whisper  # noqa: F401

        return "whisper"
    except ImportError:
        return "canned"
