"""Tests for SRT / VTT / TXT export."""

from charlaviva.events import CaptionEvent
from charlaviva.export import to_srt, to_txt, to_vtt


def events():
    return [
        CaptionEvent(
            utt_id=0, kind="final", texts={"en": "Hello world.", "es": "Hola mundo."},
            src_lang="en", t0=0.5, t1=2.5, seq=1,
        ),
        CaptionEvent(
            utt_id=1, kind="final", texts={"en": "Second line.", "es": "Segunda línea."},
            src_lang="en", t0=3.0, t1=5.0, seq=2,
        ),
        CaptionEvent(utt_id=2, kind="partial", texts={"en": "wip"}, t1=5.5, seq=3),
    ]


def test_srt_single_lang():
    srt = to_srt(events(), lang="es")
    assert "00:00:00,500 --> 00:00:02,500" in srt
    assert "Hola mundo." in srt
    assert "Segunda línea." in srt
    assert "wip" not in srt  # partials are not exported
    assert srt.startswith("1\n")


def test_srt_bilingual_stack():
    srt = to_srt(events(), lang=None)
    assert "Hello world.\nHola mundo." in srt


def test_srt_never_overlaps():
    evs = events()
    evs[1].t0 = 1.0  # overlaps the previous cue
    srt = to_srt(evs, lang="en")
    assert "00:00:02,500 --> " in srt  # clamped to previous end


def test_vtt_format():
    vtt = to_vtt(events(), lang="en")
    assert vtt.startswith("WEBVTT")
    assert "00:00:00.500 --> 00:00:02.500" in vtt


def test_txt():
    txt = to_txt(events(), lang="en")
    assert txt == "Hello world.\nSecond line.\n"


def test_estimated_t0_for_missing_start():
    ev = CaptionEvent(utt_id=0, kind="final", texts={"en": "x" * 30}, t0=0, t1=5.0)
    srt = to_srt([ev], lang="en")
    assert "-->" in srt
