"""The TTSProvider adapter — turns script text into spoken audio.

Two engines behind one interface:
  - EdgeTTSProvider   : free, neural, decent but limited expression. Per-persona
                        rate/pitch adds some life. Use while iterating.
  - ElevenLabsTTSProvider : genuinely expressive/emotional + multilingual (handles
                        Hinglish well). Free tier, then paid. Use for FINAL cuts.

Swapping engines is a one-line change (make_tts) — the pipeline never knows which.
"""
from __future__ import annotations

import asyncio
import os
import re
import ssl
from abc import ABC, abstractmethod

# Speech normalization — scripts stay clean ("82 PS", "₹5.79 lakh") but TTS
# mispronounces acronym units and the ₹ glyph. Fix at synthesis time so every
# voiceover (edge AND ElevenLabs) sounds right without hand-editing scripts.
_SPEECH_SUBS = [
    (re.compile(r"₹\s?"), ""),                       # drop rupee glyph: "₹5.79 lakh" -> "5.79 lakh"
    (re.compile(r"\bRs\.?\s?"), ""),                 # drop "Rs"
    (re.compile(r"N[⋅·]?m\b", re.I), "N-m"),         # torque Nm / N⋅m / N·m -> spoken "N M"
    (re.compile(r"\bPS\b"), "P-S"),                  # metric horsepower
    (re.compile(r"\bbhp\b", re.I), "B-H-P"),
    (re.compile(r"\bkW\b"), "k-W"),
    # Indian trim codes (ZXi, VXi, LXi, ZXi+ ...) — spell the letters so TTS
    # doesn't mangle them ("ZXi" -> "Z-X-i").
    (re.compile(r"\b([A-Z])(X)(i)(\+?)\b"),
     lambda m: f"{m.group(1)}-{m.group(2)}-{m.group(3)}{' plus' if m.group(4) else ''}"),
]


def normalize_for_speech(text: str) -> str:
    """Make text TTS-friendly (acronym units spelled out, ₹ dropped)."""
    for pattern, repl in _SPEECH_SUBS:
        text = pattern.sub(repl, text)
    return text

try:
    import certifi

    _SSL_CONTEXT: ssl.SSLContext | None = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = None

# Per-persona edge-tts settings — a cheap way to differentiate energy for free.
PERSONA_VOICE = {
    "bhai":    {"voice": "en-IN-PrabhatNeural", "rate": "+8%",  "pitch": "+2Hz"},
    # owner-chosen channel voice (2026-07-22): Indian English, expressive read
    # slowed slightly so the deadpan lands dry. Free (edge) — drafts AND finals.
    "deadpan": {"voice": "en-IN-NeerjaExpressiveNeural", "rate": "+3%", "pitch": "-2Hz"},
    "hype":    {"voice": "en-US-GuyNeural",       "rate": "+18%", "pitch": "+4Hz"},
    "default": {"voice": "en-US-GuyNeural",       "rate": "+0%",  "pitch": "+0Hz"},
}


class TTSProvider(ABC):
    @abstractmethod
    def synthesize(self, text: str, out_path: str) -> str:
        """Write spoken audio for `text` to `out_path`; return the path."""


class EdgeTTSProvider(TTSProvider):
    """Free online TTS via edge-tts. Needs network, no key, no cost.
    rate/pitch give a little expression (edge-tts has no true emotion styles)."""

    def __init__(self, voice: str = "en-US-GuyNeural", rate: str = "+0%", pitch: str = "+0Hz"):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch

    def synthesize(self, text: str, out_path: str, marks_path: str | None = None) -> str:
        """Write audio; optionally also write word-boundary marks (JSON list of
        {"w": word, "t": seconds}) — the raw material for phrase-synced cuts."""
        import json

        import edge_tts

        text = normalize_for_speech(text)

        async def _run() -> None:
            communicate = edge_tts.Communicate(text, self.voice, rate=self.rate,
                                                pitch=self.pitch, boundary="WordBoundary")
            words = []
            with open(out_path, "wb") as fh:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        fh.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        words.append({"w": chunk["text"], "t": chunk["offset"] / 1e7})
            if marks_path:
                with open(marks_path, "w") as fh:
                    json.dump(words, fh)

        asyncio.run(_run())
        return out_path


class ElevenLabsTTSProvider(TTSProvider):
    """Expressive, emotional, multilingual TTS. Needs ELEVENLABS_API_KEY.

    Voice: set ELEVENLABS_VOICE_ID (browse voices at elevenlabs.io/voice-library).
    Default is 'Adam' (a common male voice). Model eleven_multilingual_v2 speaks
    English AND Hinglish with real expression.
    """

    def __init__(self, voice_id: str | None = None, api_key: str | None = None,
                 model: str = "eleven_multilingual_v2"):
        self.voice_id = voice_id or os.environ.get("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")
        self.api_key = api_key or os.environ.get("ELEVENLABS_API_KEY")
        self.model = model

    def synthesize(self, text: str, out_path: str, marks_path: str | None = None) -> str:
        """Synthesize expressive speech; also derive word-boundary marks from the
        character-alignment endpoint so phrase-synced cutting works on finals."""
        import base64
        import json
        import urllib.request

        if not self.api_key:
            raise RuntimeError("ELEVENLABS_API_KEY not set — get a free key at elevenlabs.io")
        text = normalize_for_speech(text)
        endpoint = "with-timestamps" if marks_path else ""
        url = (f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
               + (f"/{endpoint}" if endpoint else ""))
        body = json.dumps({
            "text": text,
            "model_id": self.model,
            # Lower stability + some style = more expressive, less flat delivery.
            "voice_settings": {"stability": 0.4, "similarity_boost": 0.75, "style": 0.5},
        }).encode()
        req = urllib.request.Request(url, data=body, headers={
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
            "User-Agent": "carshorts/0.1",
        })
        with urllib.request.urlopen(req, timeout=120, context=_SSL_CONTEXT) as resp:
            payload = resp.read()
        if marks_path:
            data = json.loads(payload)
            audio = base64.b64decode(data["audio_base64"])
            align = data.get("alignment") or {}
            chars = align.get("characters", [])
            starts = align.get("character_start_times_seconds", [])
            words, word, w_start = [], "", None
            for ch, t in zip(chars, starts):
                if ch.isspace():
                    if word:
                        words.append({"w": word, "t": w_start})
                        word, w_start = "", None
                else:
                    if w_start is None:
                        w_start = t
                    word += ch
            if word:
                words.append({"w": word, "t": w_start})
            with open(marks_path, "w") as fh:
                json.dump(words, fh)
        else:
            audio = payload
        with open(out_path, "wb") as fh:
            fh.write(audio)
        return out_path


class SilentTTSProvider(TTSProvider):
    """Offline mock for tests/plan runs: writes silence sized by word count
    (~2.6 words/sec) plus evenly-spaced word marks. No network, no cost."""

    def synthesize(self, text: str, out_path: str, marks_path: str | None = None) -> str:
        import json
        import wave

        words = normalize_for_speech(text).split()
        duration = max(1.0, len(words) / 2.6)
        sr = 22050
        import math
        n = int(sr * duration)
        # a faint tone (not pure silence) so downstream silence-trimming
        # behaves like it does on real speech
        pcm = bytearray()
        for i in range(n):
            val = int(800 * math.sin(2 * math.pi * 220 * i / sr))
            pcm += val.to_bytes(2, "little", signed=True)
        with wave.open(out_path, "w") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sr)
            wav.writeframes(bytes(pcm))
        if marks_path:
            step = duration / max(1, len(words))
            with open(marks_path, "w") as fh:
                json.dump([{"w": w, "t": round(i * step, 3)} for i, w in enumerate(words)], fh)
        return out_path


def make_tts(engine: str = "edge", persona: str = "", voice: str | None = None) -> TTSProvider:
    """Build a TTS provider. engine='edge' (free) or 'elevenlabs' (expressive)."""
    if engine == "mock":
        return SilentTTSProvider()
    if engine == "elevenlabs":
        return ElevenLabsTTSProvider()
    cfg = PERSONA_VOICE.get(persona, PERSONA_VOICE["default"])
    return EdgeTTSProvider(voice=voice or cfg["voice"], rate=cfg["rate"], pitch=cfg["pitch"])
