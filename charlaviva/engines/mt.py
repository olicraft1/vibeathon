"""Optional text-machine-translation helper (used by whisper/transcribe modes).

One model call translates a finished utterance into every requested target
language at once. Requires GEMINI_API_KEY; without it, engines simply emit the
original-language transcript and mark translations unavailable.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import Settings

LANG_NAMES = {"es": "Spanish", "en": "English", "pt": "Portuguese", "fr": "French"}

_client = None


def get_client(settings: "Settings"):
    global _client
    if not settings.gemini_api_key:
        return None
    if _client is None:
        from google import genai

        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


async def translate_texts(
    text: str,
    targets: list[str],
    glossary: list[str],
    settings: "Settings",
) -> dict[str, str]:
    """Translate `text` into each of `targets`. Returns {lang: translation}."""
    client = get_client(settings)
    if not client or not text.strip() or not targets:
        return {}
    names = ", ".join(f"{LANG_NAMES.get(t, t)} ({t})" for t in targets)
    gloss = "; ".join(glossary[:40])
    prompt = (
        "You are a professional simultaneous interpreter at a tech conference.\n"
        f"Translate the live caption below into: {names}.\n"
        "Keep technical terms and proper nouns precise"
        + (f", respecting this glossary: {gloss}" if gloss else "")
        + ".\n"
        "Preserve the speaker's register; be concise (live captions).\n"
        'Reply with ONLY a JSON object mapping each language code to its translation, '
        'for example {"es": "...", "pt": "..."}.\n'
        f"Caption:\n{text}"
    )
    try:
        resp = await client.aio.models.generate_content(
            model=settings.translate_model,
            contents=prompt,
        )
        raw = (getattr(resp, "text", None) or "").strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return {}
        data = json.loads(m.group(0))
        return {
            norm: str(data[key]).strip()
            for key in list(data.keys())
            if (norm := key.strip().lower()[:2]) in targets and str(data[key]).strip()
        }
    except Exception:
        return {}
