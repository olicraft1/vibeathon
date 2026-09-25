"""End-to-end smoke tests: two concurrent sessions through the canned engine."""

import asyncio

from charlaviva.audio import decode_pcm16, rechunk
from charlaviva.config import SAMPLES_DIR, Settings
from charlaviva.session import SessionManager, demo_session_specs


def test_decode_and_rechunk_sample():
    chunks = list(rechunk(decode_pcm16(str(SAMPLES_DIR / "talk_en2.mp3")), 100))
    assert len(chunks) > 100
    assert all(len(c) == 3200 for c in chunks[:-1])  # 100ms of s16 @ 16kHz


def test_two_sessions_concurrently_canned():
    async def run_all():
        settings = Settings(engine="canned")
        manager = SessionManager(settings)
        sessions = []
        for spec in demo_session_specs(2):
            spec["source"] = {**spec["source"], "speed": 40.0, "loop": False}
            sessions.append(manager.create(spec))
        for s in sessions:
            s.start()
        for s in sessions:
            # state is 'created' until the task gets its first slice of CPU
            while s.state in ("created", "running"):
                await asyncio.sleep(0.02)
            assert s.state == "stopped", f"{s.id} ended as {s.state}: {s.error}"

        # both stages must have produced finalized captions in 2 languages
        for s in sessions:
            finals = [e for e in s.history if e.kind == "final"]
            assert len(finals) >= 3, f"{s.id} produced {len(finals)} finals"
            bilingual = [e for e in finals if len(e.texts) >= 2]
            assert bilingual, f"{s.id} captions lack translations"
            assert s.metrics.finals == len(finals)
        # and the sequences really interleaved (concurrency, not serialization)
        all_seqs = sorted(
            (e.seq, s.id) for s in sessions for e in s.history if e.kind == "final"
        )
        switches = sum(1 for a, b in zip(all_seqs, all_seqs[1:]) if a[1] != b[1])
        assert switches >= 2, "sessions did not interleave their captions"

    asyncio.run(run_all())


def test_manager_delete():
    async def run():
        settings = Settings(engine="canned")
        manager = SessionManager(settings)
        spec = demo_session_specs(1)[0]
        spec["source"] = {**spec["source"], "speed": 50.0}
        s = manager.create(spec, autostart=False)
        assert manager.get(s.id) is s
        assert await manager.delete(s.id) is True
        assert manager.get(s.id) is None

    asyncio.run(run())
