"""The TTSProvider adapter — turns script text into spoken audio.

Free tier now: edge-tts (Microsoft Edge's online voices, no API key, no cost).
Paid natural voices (ElevenLabs, PlayHT) would be a second implementation of
this same interface — a one-line swap in the composition root, never a change
in the pipeline. Voice quality is the easiest thing to upgrade once the channel
earns, so we deliberately start free and keep the seam clean.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod


class TTSProvider(ABC):
    @abstractmethod
    def synthesize(self, text: str, out_path: str) -> str:
        """Write spoken audio for `text` to `out_path`; return the path."""


class EdgeTTSProvider(TTSProvider):
    """Free online TTS via edge-tts. Needs network, no key, no cost.

    Voices: run `edge-tts --list-voices` for the full list. A few good English
    ones: en-US-GuyNeural (default here), en-US-JennyNeural, en-IN-PrabhatNeural
    / en-IN-NeerjaNeural for an Indian-English feel that fits a car channel.
    """

    def __init__(self, voice: str = "en-US-GuyNeural", rate: str = "+0%"):
        self.voice = voice
        self.rate = rate

    def synthesize(self, text: str, out_path: str) -> str:
        import edge_tts  # imported lazily so tests/core don't need it

        async def _run() -> None:
            communicate = edge_tts.Communicate(text, self.voice, rate=self.rate)
            await communicate.save(out_path)

        asyncio.run(_run())
        return out_path
