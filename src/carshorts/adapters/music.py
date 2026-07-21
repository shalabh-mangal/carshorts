"""Procedurally generated background music — zero licensing risk.

Instead of downloading a track (which raises license/attribution/ToS questions),
we synthesize a mild lo-fi beat ourselves: a soft kick, a quiet hi-hat, and a
gentle chord pad. It is deliberately understated — it sits UNDER the voice as a
bed, it is not the star. Because we author it, it is free to use anywhere with
no attribution. Swappable later for a licensed track via the same file path.
"""
from __future__ import annotations

import wave

import numpy as np

_SR = 44100
# A gentle A-minor-ish pad (A3, C4, E4) — unobtrusive under speech.
_PAD_FREQS = (220.0, 261.63, 329.63)


def _kick(sr: int) -> np.ndarray:
    """A short, soft kick: pitch sweeps down, amplitude decays fast."""
    dur = 0.18
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    freq = 110 * np.exp(-t * 22) + 45          # 110Hz -> ~45Hz sweep
    env = np.exp(-t * 18)
    return 0.7 * np.sin(2 * np.pi * freq * t) * env


def _hat(sr: int) -> np.ndarray:
    """A quiet hi-hat: short burst of noise, fast decay."""
    dur = 0.05
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    # Deterministic noise (no RNG dependency): high-freq sines summed.
    noise = sum(np.sin(2 * np.pi * f * t) for f in (5000, 7000, 9000, 11000))
    return 0.06 * noise * np.exp(-t * 60)


def generate_beat(out_path: str, duration: float, bpm: int = 84, sr: int = _SR) -> str:
    """Write a `duration`-second lo-fi beat to out_path (16-bit mono WAV)."""
    total = int(duration * sr) + sr
    audio = np.zeros(total, dtype=np.float32)

    kick, hat = _kick(sr), _hat(sr)
    beat = 60.0 / bpm

    def place(sample: np.ndarray, at: float) -> None:
        i = int(at * sr)
        end = min(i + len(sample), total)
        audio[i:end] += sample[: end - i]

    step = 0
    t = 0.0
    while t < duration:
        # Kick on beats 1 & 3 of each 4/4 bar, hats on every off-eighth.
        if step % 2 == 0:
            place(kick, t)
        else:
            place(hat, t)
        t += beat / 2
        step += 1

    # Soft chord pad, slow tremolo, low in the mix.
    t_axis = np.linspace(0, duration, int(duration * sr), endpoint=False)
    pad = sum(np.sin(2 * np.pi * f * t_axis) for f in _PAD_FREQS)
    tremolo = 0.5 + 0.5 * np.sin(2 * np.pi * 0.15 * t_axis)
    pad = 0.05 * pad * tremolo
    audio[: len(pad)] += pad.astype(np.float32)

    peak = float(np.max(np.abs(audio))) or 1.0
    audio = (audio / peak) * 0.6                 # headroom; it's a background bed
    pcm = (audio * 32767).astype(np.int16)

    with wave.open(out_path, "w") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        wav.writeframes(pcm.tobytes())
    return out_path


def _write_wav(path: str, audio, sr: int = _SR) -> str:
    peak = float(np.max(np.abs(audio))) or 1.0
    pcm = (audio / peak * 0.85 * 32767).astype(np.int16)
    with wave.open(path, "w") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        wav.writeframes(pcm.tobytes())
    return path


def generate_whoosh(out_path: str, duration: float = 0.35, sr: int = _SR) -> str:
    """A soft transition whoosh: filtered noise with a rising-then-falling sweep.
    Self-synthesized -> no license, no attribution, consistent channel sound."""
    n = int(duration * sr)
    t = np.linspace(0, duration, n, endpoint=False)
    noise = np.cumsum(np.sin(2 * np.pi * (900 + 2600 * t / duration) * t))
    noise = noise / (np.max(np.abs(noise)) or 1.0)
    env = np.sin(np.pi * t / duration) ** 2          # swell in, fade out
    return _write_wav(out_path, 0.5 * noise * env, sr)


def generate_riser(out_path: str, duration: float = 1.1, sr: int = _SR) -> str:
    """A subtle riser into a reveal: sine sweep + tremolo, quiet by design."""
    n = int(duration * sr)
    t = np.linspace(0, duration, n, endpoint=False)
    freq = 180 + 520 * (t / duration) ** 2
    sweep = np.sin(2 * np.pi * np.cumsum(freq) / sr)
    tremolo = 0.6 + 0.4 * np.sin(2 * np.pi * 9 * t)
    env = (t / duration) ** 1.6                      # grows toward the hit
    return _write_wav(out_path, 0.4 * sweep * tremolo * env, sr)
