"""Caption-line parser shared by the Gemini Live engines.

The captioner model is instructed to emit one block per utterance:

    [en] Welcome to Nerdearla, let's get started.
    [es] Bienvenidos a Nerdearla, empecemos.
    [pt] Bem-vindos à Nerdearla, vamos começar.

Text streams in as deltas; this parser turns the stream into partial/final
CaptionEvents per utterance block, with minimal latency (a partial is emitted
as soon as the first tagged line is readable).
"""

from __future__ import annotations

import re
from typing import Callable

TAG_RE = re.compile(r"^\[(?P<lang>[a-zA-Z]{2,3}(?:-[A-Za-z]+)?)\]\s?(?P<text>.*)$")

LANG_ALIASES = {
    "sp": "es", "spa": "es", "esp": "es",
    "en": "en", "eng": "en", "us": "en", "gb": "en",
    "pt": "pt", "por": "pt", "br": "pt", "prt": "pt",
    "fr": "fr", "fra": "fr",
}


def norm_lang(tag: str) -> str:
    tag = tag.strip().lower()
    return LANG_ALIASES.get(tag, tag[:2] if len(tag) > 2 else tag)


class CaptionBlockParser:
    """Stateful parser: feed() text deltas, receive block callbacks."""

    def __init__(
        self,
        on_partial: Callable[[dict[str, str]], None],
        on_final: Callable[[dict[str, str]], None],
    ) -> None:
        self.on_partial = on_partial
        self.on_final = on_final
        self._buf = ""  # unprocessed text tail (may contain an incomplete line)
        self._block: dict[str, str] = {}  # committed lines of current utterance
        self._last_lang: str | None = None
        self._saw_tag = False  # did the model follow the format at least once?

    @property
    def saw_tagged_output(self) -> bool:
        return self._saw_tag

    def _current_texts(self) -> dict[str, str]:
        texts = dict(self._block)
        # surface the in-progress line so the UI can show it dimmed
        line = self._buf.strip()
        if line:
            m = TAG_RE.match(line)
            if m:
                self._saw_tag = True
                texts[norm_lang(m.group("lang"))] = m.group("text").strip()
            elif self._last_lang and not line.startswith("["):
                texts[self._last_lang] = (self._block.get(self._last_lang, "") + " " + line).strip()
        return {k: v for k, v in texts.items() if v}

    def _commit_line(self, line: str) -> None:
        line = line.rstrip()
        m = TAG_RE.match(line)
        if m:
            self._saw_tag = True
            lang = norm_lang(m.group("lang"))
            if lang in self._block:  # a repeated tag starts a new utterance
                self._finish_block()
            self._block[lang] = m.group("text").strip()
            self._last_lang = lang
        elif not line.strip():
            if self._block:
                self._finish_block()
        elif self._last_lang:  # wrapped continuation of the previous tagged line
            self._block[self._last_lang] = (
                self._block.get(self._last_lang, "") + " " + line.strip()
            ).strip()

    def _finish_block(self) -> None:
        if self._block:
            self.on_final({k: v for k, v in self._block.items() if v})
        self._block = {}
        self._last_lang = None

    def feed(self, delta: str) -> None:
        if not delta:
            return
        self._buf += delta
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._commit_line(line)
        self.on_partial(self._current_texts())

    def flush(self) -> None:
        """End of model turn/stream: commit everything still open."""
        if self._buf.strip():
            self._commit_line(self._buf)
            self._buf = ""
        self._finish_block()
        self.on_partial({})
