"""AI video generation adapter — comedic clips + Living Stills, behind a hard wall.

Two capabilities, one local model (LTX-Video on the RTX 5060, isolated in
.venv-video so its newer diffusers can't break chatterbox):
  - text-to-video  -> COMEDY / reaction / metaphor cutaways (a rocket for "turbo",
    money-rain for "value"). These are editorial jokes, never factual claims.
  - image-to-video -> LIVING STILLS: animate one of our REAL, vetted car photos.

THE WALL (enforced by callers + provenance): the car and every fact are only ever
REAL footage. t2v is NEVER used to depict the subject car; i2v only ever animates
a photo that already passed assetvet. Every generated clip is tagged 'generated'
in data/gen_provenance.json so QA can prove the car is never synthetic and the
description can disclose AI use.

Generation is best-effort: if the video env or model isn't there, callers fall
back to stills/stock — a render never depends on it.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from carshorts.core import paths

VIDEO_PY = paths.ROOT / ".venv-video" / "Scripts" / "python.exe"
WORKER = paths.ROOT / "tools" / "ltx_worker.py"
GEN_DIR = paths.ASSETS / "gen"
PROVENANCE = paths.DATA / "gen_provenance.json"


def available() -> bool:
    """True if the isolated video env + worker exist (so callers can fall back)."""
    return VIDEO_PY.exists() and WORKER.exists()


def is_generated(clip_path: str | Path) -> bool:
    """Whether a clip was AI-generated (per the provenance ledger). Used by the
    QA wall to assert the subject car is never a synthetic clip."""
    if not PROVENANCE.exists():
        return False
    try:
        return str(clip_path) in json.loads(PROVENANCE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return False


def _record(clip_path: str, kind: str, prompt: str, source_image: str | None) -> None:
    PROVENANCE.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if PROVENANCE.exists():
        try:
            data = json.loads(PROVENANCE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            data = {}
    data[str(clip_path)] = {"provenance": "generated", "kind": kind,
                            "prompt": prompt, "source_image": source_image}
    PROVENANCE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def generate(prompt: str, mode: str = "t2v", image: str | Path | None = None,
             out_path: str | None = None, width: int = 384, height: int = 224,
             frames: int = 25, steps: int = 20, fps: int = 24, seed: int = 0,
             timeout: int = 1200) -> str | None:
    """Generate one clip via the isolated LTX worker. Returns the clip path (and
    records provenance), or None on any failure so callers fall back cleanly.
    mode='t2v' for a comedy prompt; mode='i2v' animates `image` (a real photo)."""
    if not available():
        return None
    if out_path is None:
        key = hashlib.md5(f"{mode}|{prompt}|{image}|{seed}".encode()).hexdigest()[:12]
        out_path = str(GEN_DIR / f"{mode}_{key}.mp4")
    if Path(out_path).exists():          # cache: reuse a clip we already made
        return out_path
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    cmd = [str(VIDEO_PY), str(WORKER), "--mode", mode, "--prompt", prompt,
           "--out", out_path, "--width", str(width), "--height", str(height),
           "--frames", str(frames), "--steps", str(steps), "--fps", str(fps),
           "--seed", str(seed)]
    if mode == "i2v":
        if not image:
            return None
        cmd += ["--image", str(image)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:  # noqa: BLE001 — never let generation break a render
        return None
    if result.returncode != 0 or not Path(out_path).exists():
        return None
    _record(out_path, mode, prompt, str(image) if image else None)
    return out_path
