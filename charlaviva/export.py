"""Export session transcripts as SRT, WebVTT or plain text."""

from __future__ import annotations

from .audio import format_srt_time, format_vtt_time
from .events import CaptionEvent


def _finals(events: list[CaptionEvent]) -> list[CaptionEvent]:
    finals = [e for e in events if e.kind == "final"]
    finals.sort(key=lambda e: (e.t0, e.seq))
    return finals


def _cues(events: list[CaptionEvent], lang: str | None) -> list[tuple[float, float, str]]:
    cues: list[tuple[float, float, str]] = []
    prev_end: dict[int, float] = {}
    for ev in _finals(events):
        text = ""
        if lang:
            text = (ev.texts.get(lang) or "").strip()
        else:  # bilingual: original on top, translation below
            src = (ev.texts.get(ev.src_lang or "") or next(iter(ev.texts.values()), "")).strip()
            rest = [
                v.strip()
                for k, v in ev.texts.items()
                if k != ev.src_lang and v.strip() and v.strip() != src
            ]
            text = "\n".join([src, *rest])
        if not text:
            continue
        t0 = ev.t0 if ev.t0 > 0 else ev.estimated_t0()
        t1 = ev.t1 if ev.t1 > t0 else t0 + max(1.0, len(text) / 15.0)
        cues.append((t0, t1, text))
    # no overlaps: clamp start to previous end
    fixed: list[tuple[float, float, str]] = []
    last_end = 0.0
    for t0, t1, text in cues:
        t0 = max(t0, last_end)
        t1 = max(t1, t0 + 0.8)
        fixed.append((t0, t1, text))
        last_end = t1
    return fixed


def to_srt(events: list[CaptionEvent], lang: str | None = None) -> str:
    lines: list[str] = []
    for i, (t0, t1, text) in enumerate(_cues(events, lang), start=1):
        lines += [
            str(i),
            f"{format_srt_time(t0)} --> {format_srt_time(t1)}",
            text,
            "",
        ]
    return "\n".join(lines)


def to_vtt(events: list[CaptionEvent], lang: str | None = None) -> str:
    lines = ["WEBVTT", ""]
    for t0, t1, text in _cues(events, lang):
        lines += [
            f"{format_vtt_time(t0)} --> {format_vtt_time(t1)}",
            text,
            "",
        ]
    return "\n".join(lines)


def to_txt(events: list[CaptionEvent], lang: str | None = None) -> str:
    out: list[str] = []
    for ev in _finals(events):
        if lang:
            text = (ev.texts.get(lang) or "").strip()
        else:
            text = "; ".join(f"{k}: {v}" for k, v in ev.texts.items())
        if text:
            out.append(text)
    return "\n".join(out) + ("\n" if out else "")


EXPORTERS = {"srt": to_srt, "vtt": to_vtt, "txt": to_txt}
CONTENT_TYPES = {"srt": "application/x-subrip", "vtt": "text/vtt", "txt": "text/plain"}
