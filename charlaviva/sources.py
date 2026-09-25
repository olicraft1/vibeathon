"""Audio sources: files, live streams and microphones → PCM chunks with time.

Every source yields ``(pcm16le_mono_16k, t_seconds)`` at roughly real time so
latency measurements mean what they say.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from typing import AsyncIterator

from .audio import decode_pcm16, rechunk
from .config import CHUNK_MS

CHUNK_SEC = CHUNK_MS / 1000.0


class AudioSource(ABC):
    kind = "abstract"

    @abstractmethod
    async def chunks(self) -> AsyncIterator[tuple[bytes, float]]:
        """Yield (pcm chunk, chunk start time in seconds on the session timeline)."""
        ...

    def describe(self) -> str:
        return self.kind


class FileSource(AudioSource):
    """Local audio file (mp3/wav/ogg/flac/m4a…), played at real-time pace.

    ``speed`` > 1 accelerates (tests); ``loop`` repeats forever (demo stages).
    """

    kind = "file"

    def __init__(
        self,
        path: str,
        speed: float = 1.0,
        loop: bool = False,
        chunk_ms: int = CHUNK_MS,
    ) -> None:
        self.path = path
        self.speed = max(0.1, speed)
        self.loop = loop
        self.chunk_ms = chunk_ms

    def describe(self) -> str:
        tag = f"file:{self.path}"
        if self.loop:
            tag += " (loop)"
        return tag

    async def chunks(self) -> AsyncIterator[tuple[bytes, float]]:
        t = 0.0
        while True:
            produced = 0
            for pcm in rechunk(decode_pcm16(self.path), self.chunk_ms):
                yield pcm, t
                produced += 1
                t += (len(pcm) / 2) / 16000
                if self.speed == 1.0:
                    await asyncio.sleep((len(pcm) / 2) / 16000)
                else:
                    await asyncio.sleep(((len(pcm) / 2) / 16000) / self.speed)
            if not (self.loop and produced > 0):
                break


class StreamSource(AudioSource):
    """Live network stream (HLS/m3u8, HTTP, RTMP…) decoded via PyAV as it arrives."""

    kind = "stream"

    def __init__(self, url: str, chunk_ms: int = CHUNK_MS) -> None:
        self.url = url
        self.chunk_ms = chunk_ms

    def describe(self) -> str:
        return f"stream:{self.url}"

    async def chunks(self) -> AsyncIterator[tuple[bytes, float]]:
        start = time.monotonic()
        iterator = rechunk(decode_pcm16(self.url), self.chunk_ms)
        loop = asyncio.get_running_loop()
        # decode is blocking (network + codecs) — keep the event loop breathing
        sentinel = object()

        def _next():
            try:
                return next(iterator)
            except StopIteration:
                return sentinel

        while True:
            pcm = await loop.run_in_executor(None, _next)
            if pcm is sentinel:
                break
            yield pcm, time.monotonic() - start


class MicSource(AudioSource):
    """Browser microphone: PCM16/16k binary frames arrive over a WebSocket.

    The ingestion WebSocket pushes bytes into :meth:`push`; the session pipeline
    consumes them at the pace they arrive.
    """

    kind = "mic"
    chunk_ms = CHUNK_MS

    def __init__(self, chunk_ms: int = CHUNK_MS) -> None:
        self.chunk_ms = chunk_ms
        self.queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.start_mono: float | None = None

    def describe(self) -> str:
        return "mic (browser)"

    def push(self, pcm: bytes) -> None:
        self.queue.put_nowait(pcm)

    def close(self) -> None:
        self.queue.put_nowait(None)

    async def chunks(self) -> AsyncIterator[tuple[bytes, float]]:
        self.start_mono = time.monotonic()
        # re-chunk whatever sizes the browser sends into ~100ms blocks
        buf = bytearray()
        want = int(16000 * (self.chunk_ms / 1000.0) * 2)
        while True:
            pcm = await self.queue.get()
            if pcm is None:
                if buf:
                    yield bytes(buf), time.monotonic() - self.start_mono
                break
            buf += pcm
            while len(buf) >= want:
                out = bytes(buf[:want])
                del buf[:want]
                yield out, time.monotonic() - self.start_mono


def build_source(spec: dict) -> AudioSource:
    """Create a source from a session spec dict: {type, path|url, speed, loop}."""
    stype = (spec.get("type") or "file").lower()
    if stype == "file":
        return FileSource(
            spec["path"],
            speed=float(spec.get("speed") or 1.0),
            loop=bool(spec.get("loop")),
        )
    if stype == "stream":
        return StreamSource(spec.get("url") or spec.get("path") or "")
    if stype == "mic":
        return MicSource()
    raise ValueError(f"unknown source type {stype!r} (use file|stream|mic)")
