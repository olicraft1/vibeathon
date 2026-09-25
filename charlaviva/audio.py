"""Audio plumbing: decode any file/stream to mono PCM16 @ 16 kHz, VAD, conversions.

The whole pipeline runs on mono s16le @ 16 kHz — the exact format the Gemini
Live API accepts — so every engine and source speaks one dialect.
"""

from __future__ import annotations

import math
from typing import Iterator

import numpy as np

SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2  # s16le


def pcm16_to_float(pcm: bytes) -> np.ndarray:
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0


def float_to_pcm16(samples: np.ndarray) -> bytes:
    clipped = np.clip(samples, -1.0, 1.0)
    return (clipped * 32767.0).astype("<i2").tobytes()


def chunk_ms_to_bytes(ms: int) -> int:
    return SAMPLE_RATE * (ms / 1000.0) * BYTES_PER_SAMPLE


def decode_pcm16(source: str) -> Iterator[bytes]:
    """Decode a local file or media URL into mono PCM16 @ 16 kHz chunks.

    Uses PyAV (libav) so mp3/wav/ogg/flac/m4a and network streams (HLS, RTMP,
    HTTP…) all work without a system ffmpeg binary.
    """
    import av

    with av.open(source) as container:
        if not container.streams.audio:
            raise ValueError(f"no audio stream in {source!r}")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
        for frame in container.decode(audio=0):
            for out in resampler.resample(frame):
                data = out.to_ndarray().tobytes()
                if data:
                    yield data
        for out in resampler.resample(None):
            data = out.to_ndarray().tobytes()
            if data:
                yield data


def rechunk(data_iter: Iterator[bytes], chunk_ms: int = 100) -> Iterator[bytes]:
    """Re-pack decoded audio into fixed-size chunks (Gemini likes ~100 ms)."""
    want = int(chunk_ms_to_bytes(chunk_ms))
    buf = bytearray()
    for data in data_iter:
        buf += data
        while len(buf) >= want:
            yield bytes(buf[:want])
            del buf[:want]
    if buf:
        yield bytes(buf)


class EnergyVAD:
    """Tiny RMS-based voice activity detector.

    Good enough to split utterances for whisper windows and to fire hybrid-VAD
    turn ends at the Gemini Live API (`audio_stream_end`) for lower latency.
    """

    def __init__(
        self,
        silence_ms: int = 600,
        min_speech_ms: int = 250,
        frame_ms: int = 30,
        threshold: float = 0.012,
    ) -> None:
        self.silence_ms = silence_ms
        self.min_speech_ms = min_speech_ms
        self.frame_ms = frame_ms
        self.threshold = threshold
        self.in_speech = False
        self._silence_run = 0.0  # ms of trailing silence while in speech
        self._speech_run = 0.0  # ms of speech since utterance start

    def _frames(self, pcm: bytes) -> Iterator[np.ndarray]:
        n = int(chunk_ms_to_bytes(self.frame_ms))
        for i in range(0, len(pcm), n):
            yield pcm[i : i + n]

    def feed(self, pcm: bytes) -> list[str]:
        """Feed PCM16 audio; returns VAD events: 'speech_start' / 'speech_end'."""
        events: list[str] = []
        for frame in self._frames(pcm):
            if len(frame) < 2:
                continue
            samples = pcm16_to_float(frame)
            rms = float(np.sqrt(np.mean(samples**2))) if len(samples) else 0.0
            is_speech = rms >= self.threshold
            if is_speech:
                if not self.in_speech:
                    self.in_speech = True
                    self._silence_run = 0.0
                    self._speech_run = 0.0
                    events.append("speech_start")
                self._speech_run += self.frame_ms
                self._silence_run = 0.0
            elif self.in_speech:
                self._silence_run += self.frame_ms
                if self._silence_run >= self.silence_ms:
                    if self._speech_run >= self.min_speech_ms:
                        events.append("speech_end")
                    self.in_speech = False
                    self._silence_run = 0.0
                    self._speech_run = 0.0
        return events

    def flush(self) -> list[str]:
        """End of stream: close an in-progress utterance if any."""
        if self.in_speech and self._speech_run >= self.min_speech_ms:
            self.in_speech = False
            return ["speech_end"]
        self.in_speech = False
        return []


def format_srt_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_vtt_time(seconds: float) -> str:
    return format_srt_time(seconds).replace(",", ".")
