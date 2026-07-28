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
from pathlib import Path

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


# ---------------------------------------------------------------------------
# Chatterbox: open (MIT), voice-CLONING, 23-language TTS — the channel voice.
# Free; GPU-fast, CPU-capable. Clones from a short reference clip so the voice is
# the owner's own, and speaks English / Hindi / Hinglish from ONE model, which is
# what unlocks the eventual move to Hinglish videos.
# ---------------------------------------------------------------------------

# script language -> Chatterbox language_id. Hinglish rides the Hindi model
# (Devanagari Hindi + inline English words is how the scripts are written).
_LANG_ID = {"english": "en", "en": "en", "hindi": "hi", "hi": "hi",
            "hinglish": "hi"}

# persona -> (exaggeration, cfg_weight). Higher exaggeration = more energy;
# lower cfg_weight lets the reference's own cadence come through.
_CHATTERBOX_PERSONA = {
    "deadpan": (0.4, 0.5),
    "hype":    (0.85, 0.35),
    "bhai":    (0.7, 0.4),
    "default": (0.5, 0.5),
}

_CHATTERBOX_MODEL = None   # loaded once per process (heavy: ~few GB)
_WHISPER_MODEL = None      # faster-whisper aligner, loaded once, optional


def _load_chatterbox(device: str):
    global _CHATTERBOX_MODEL
    if _CHATTERBOX_MODEL is None:
        import perth

        # Perth's neural watermarker occasionally fails to initialise its model
        # and comes back as None. Keep the real one when present (responsible-AI
        # marking of synthetic speech); otherwise a no-op so synthesis still runs.
        if getattr(perth, "PerthImplicitWatermarker", None) is None:
            class _NoWatermark:
                def apply_watermark(self, wav, sample_rate=None):
                    return wav
            perth.PerthImplicitWatermarker = _NoWatermark
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        _CHATTERBOX_MODEL = ChatterboxMultilingualTTS.from_pretrained(device=device)
    return _CHATTERBOX_MODEL


def _proportional_marks(text: str, duration: float) -> list[dict]:
    """Word-boundary marks distributed across the clip by word length. Always
    available (no deps, any language), and good enough to anchor phrase cuts when
    the whisper aligner isn't installed."""
    words = text.split()
    if not words:
        return []
    weights = [max(1, len(w)) for w in words]
    total = sum(weights) or 1
    marks, acc = [], 0.0
    for w, wt in zip(words, weights):
        marks.append({"w": w.strip(".,?!—:;\"'"), "t": round(acc, 3)})
        acc += duration * wt / total
    return marks


def _whisper_marks(audio_path: str, language_id: str) -> list[dict] | None:
    """Exact word timings via faster-whisper (optional). Returns None when the
    package isn't installed so callers fall back to proportional marks."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        try:
            _WHISPER_MODEL = WhisperModel("base", device="auto", compute_type="int8")
        except Exception:  # noqa: BLE001 — alignment is best-effort
            return None
    try:
        segments, _ = _WHISPER_MODEL.transcribe(audio_path, language=language_id,
                                                 word_timestamps=True)
        marks = [{"w": w.word.strip(), "t": round(w.start, 3)}
                 for seg in segments for w in (seg.words or [])]
        return marks or None
    except Exception:  # noqa: BLE001
        return None


class ChatterboxTTSProvider(TTSProvider):
    """Open, MIT-licensed cloning TTS. Speaks in the OWNER's voice (cloned from a
    reference clip) across 23 languages incl. Hindi/Hinglish. Reference clip:
    CARSHORTS_VOICE_REF, else data/voice/owner_reference.wav."""

    def __init__(self, persona: str = "", language: str = "english",
                 ref_path: str | None = None):
        import torch  # heavy — kept here so importing tts.py stays light
        self.language_id = _LANG_ID.get((language or "english").lower(), "en")
        self.ref_path = ref_path or os.environ.get(
            "CARSHORTS_VOICE_REF", "data/voice/owner_reference.wav")
        self.exaggeration, self.cfg_weight = _CHATTERBOX_PERSONA.get(
            persona, _CHATTERBOX_PERSONA["default"])
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        # cache identity: a voice change (ref/lang/energy) must not reuse audio
        self.voice = (f"chatterbox:{Path(self.ref_path).stem}:{self.language_id}"
                      f":{self.exaggeration}")

    def synthesize(self, text: str, out_path: str, marks_path: str | None = None) -> str:
        import json
        import subprocess
        import tempfile
        import wave

        from carshorts.core import paths

        text_n = normalize_for_speech(text)
        ref = paths.resolve(self.ref_path)
        if not ref.exists():
            raise RuntimeError(
                f"voice reference clip not found: {ref} — record ~20s and save it "
                f"there, or set CARSHORTS_VOICE_REF")
        model = _load_chatterbox(self._device)
        wav = model.generate(text_n, language_id=self.language_id,
                             audio_prompt_path=str(ref),
                             exaggeration=self.exaggeration, cfg_weight=self.cfg_weight)
        arr = wav.squeeze(0).detach().cpu().numpy()
        sr = int(model.sr)
        # int16 PCM -> temp wav -> ffmpeg to whatever out_path implies (usually mp3)
        pcm = (arr.clip(-1.0, 1.0) * 32767.0).astype("<i2").tobytes()
        tmp = tempfile.mktemp(suffix=".wav")
        with wave.open(tmp, "w") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(pcm)
        subprocess.run(["ffmpeg", "-y", "-i", tmp, "-codec:a", "libmp3lame",
                        "-q:a", "2", out_path], capture_output=True)
        os.unlink(tmp)
        if marks_path:
            marks = (_whisper_marks(out_path, self.language_id)
                     or _proportional_marks(text_n, len(arr) / sr))
            with open(marks_path, "w", encoding="utf-8") as fh:
                json.dump(marks, fh, ensure_ascii=False)
        return out_path


def make_tts(engine: str = "edge", persona: str = "", voice: str | None = None,
             language: str = "english") -> TTSProvider:
    """Build a TTS provider. engine='edge' (free), 'chatterbox' (free, cloned
    channel voice, multilingual), or 'elevenlabs' (paid). Unavailable open
    engines fall back to the free edge voice so a render never breaks."""
    if engine == "mock":
        return SilentTTSProvider()
    if engine == "elevenlabs":
        return ElevenLabsTTSProvider()
    if engine == "chatterbox":
        try:
            return ChatterboxTTSProvider(persona=persona, language=language)
        except Exception as exc:  # noqa: BLE001 — never let voice setup break a render
            print(f"     chatterbox unavailable ({exc}); using the free edge voice")
    cfg = PERSONA_VOICE.get(persona, PERSONA_VOICE["default"])
    return EdgeTTSProvider(voice=voice or cfg["voice"], rate=cfg["rate"], pitch=cfg["pitch"])
