"""Audio polish — the difference between "slideshow" and "produced".

Takes the rendered video (voice-only audio) and, in ONE ffmpeg pass:
  1. DUCKS the music under speech (sidechain compression keyed by the voice)
     and lets it swell back in the gaps — the signature of pro shorts.
  2. Places self-synthesized SFX: a soft whoosh on each section boundary and a
     quiet riser leading into the value/price reveal.
  3. Normalizes the final mix to YouTube's loudness target (-14 LUFS, -1.5 dBTP)
     so the video is neither quiet nor crushed next to other Shorts.

Video stream is stream-copied (no re-encode, fast, lossless).
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from carshorts.adapters.music import generate_riser, generate_whoosh


def polish(video_in: str, out_path: str, music_path: str | None = None,
           whoosh_times: list[float] | None = None,
           riser_time: float | None = None,
           music_gain: float = 0.55, sfx_gain: float = 0.5) -> str:
    """Mix voice (from video_in) + ducked music + timed SFX -> loudnorm -> out."""
    whoosh_times = [t for t in (whoosh_times or []) if t > 0.05]
    tmp = Path(tempfile.mkdtemp(prefix="polish_"))

    inputs: list[str] = ["-i", video_in]
    idx = 1
    music_idx = riser_idx = None
    whoosh_idx: list[int] = []

    if music_path:
        # -stream_loop -1: a track shorter than the video loops instead of
        # falling silent; amix duration=first still trims to video length.
        inputs += ["-stream_loop", "-1", "-i", str(music_path)]
        music_idx = idx
        idx += 1
    if whoosh_times:
        wpath = generate_whoosh(str(tmp / "whoosh.wav"))
        for _ in whoosh_times:
            inputs += ["-i", wpath]
            whoosh_idx.append(idx)
            idx += 1
    if riser_time and riser_time > 1.2:
        rpath = generate_riser(str(tmp / "riser.wav"))
        inputs += ["-i", rpath]
        riser_idx = idx
        idx += 1

    parts: list[str] = []
    mix_ins = ["[voice]"]
    parts.append("[0:a]aformat=sample_rates=44100:channel_layouts=stereo,asplit=2[voice][key]")

    if music_idx is not None:
        # duck music with the VOICE as sidechain key, then trim to video length
        parts.append(
            f"[{music_idx}:a]aformat=sample_rates=44100:channel_layouts=stereo,"
            f"volume={music_gain}[m0]")
        parts.append(
            "[m0][key]sidechaincompress=threshold=0.02:ratio=12:attack=20:release=400[mduck]")
        mix_ins.append("[mduck]")
    else:
        parts.append("[key]anullsink")

    for j, (w_idx, t) in enumerate(zip(whoosh_idx, whoosh_times)):
        ms = int(t * 1000)
        parts.append(f"[{w_idx}:a]volume={sfx_gain},adelay={ms}|{ms}[w{j}]")
        mix_ins.append(f"[w{j}]")
    if riser_idx is not None:
        ms = int((riser_time - 1.1) * 1000)   # riser ENDS at the reveal
        parts.append(f"[{riser_idx}:a]volume={sfx_gain*0.8},adelay={ms}|{ms}[riser]")
        mix_ins.append("[riser]")

    parts.append(
        "".join(mix_ins) +
        f"amix=inputs={len(mix_ins)}:duration=first:normalize=0,"
        # loudnorm outputs 192 kHz internally; resample back or AAC ships 96 kHz
        "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=44100,"
        # hard ceiling: single-pass loudnorm can overshoot TP on punchy voices
        "alimiter=limit=0.79:level=0[aout]")

    # Unified LIGHT grade: one subtle curve over everything (own clips, stock,
    # stills, press) so mixed sources read as one look. Costs a re-encode.
    cmd = ["ffmpeg", "-y", *inputs,
           "-filter_complex", ";".join(parts),
           "-map", "0:v", "-map", "[aout]",
           "-vf", "eq=contrast=1.03:saturation=1.06,unsharp=3:3:0.3",
           "-c:v", "libx264", "-crf", "19", "-preset", "faster",
           "-c:a", "aac", "-b:a", "192k",
           str(out_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"audio polish failed: {proc.stderr[-400:]}")
    return str(out_path)
