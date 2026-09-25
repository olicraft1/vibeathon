"""Tests for the caption-line parser (Gemini caption mode)."""

from charlaviva.engines.parser import CaptionBlockParser


def make():
    partials, finals = [], []
    p = CaptionBlockParser(on_partial=partials.append, on_final=finals.append)
    return p, partials, finals


def test_tagged_blocks_streaming():
    p, partials, finals = make()
    # deltas split mid-token, as a live model streams them
    for delta in ["[en] Hel", "lo wor", "ld.\n[es] Hol", "a mundo.\n\n"]:
        p.feed(delta)
    assert finals and finals[0] == {"en": "Hello world.", "es": "Hola mundo."}
    # a partial should have surfaced the in-progress lines at some point
    assert any("Hel" in str(partials) or "Hello" in str(d for d in part.values()) for part in partials)


def test_repeated_tag_starts_new_utterance():
    p, _, finals = make()
    p.feed("[en] One.\n[es] Uno.\n[en] Two.\n[es] Dos.\n")
    # the first block closes when the second starts; the last needs a flush
    assert finals == [{"en": "One.", "es": "Uno."}]
    p.flush()
    assert finals == [
        {"en": "One.", "es": "Uno."},
        {"en": "Two.", "es": "Dos."},
    ]


def test_flush_commits_open_block():
    p, _, finals = make()
    p.feed("[en] No newline yet")
    p.flush()
    assert finals == [{"en": "No newline yet"}]


def test_wrapped_continuation_lines():
    p, _, finals = make()
    p.feed("[en] first part\nsecond part\n[es] parte uno\n")
    p.flush()
    assert finals[0]["en"] == "first part second part"
    assert finals[0]["es"] == "parte uno"


def test_lang_alias_normalisation():
    p, _, finals = make()
    p.feed("[ENG] Hi.\n[SP] Hola.\n\n")
    assert finals == [{"en": "Hi.", "es": "Hola."}]


def test_untagged_text_is_ignored():
    p, partials, finals = make()
    p.feed("Sure! I would love to help you with that.\n")
    p.flush()
    assert finals == []
