"""Living Stills — animate a car's REAL vetted photos into short i2v motion clips.

Pre-generated ONCE per car (like the joke library) so a render never spawns the
GPU worker mid-render (that OOMs the 8GB card next to the loaded voice model). The
clips land in assets/cars/<slug>/own/ (named living_<stem>.mp4) where produce
already picks them up as the car's own motion footage — and produce then drops the
matching static still, so Living Stills replaces the slideshow. i2v anchors on the
REAL photo, so the car stays factual (never fabricated).

  carshorts liven "Tata Punch"            # animate every vetted still (cached)
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from carshorts.adapters import videogen
from carshorts.core import paths

# The car identity comes from the ANCHOR PHOTO (i2v), so the prompt only needs to
# describe MOTION + a quality bar — generic across cars on purpose.
_PROMPT = ("Cinematic slow dolly push-in on a parked car, smooth steady camera "
           "glide forward, gentle parallax, soft natural daylight, shallow depth "
           "of field, photorealistic, sharp, stable, high detail, no warping, no "
           "melting, no distortion")

# HQ Living-Stills config, validated on the RTX 5060 8GB (2026-07-30): 448×256,
# 73 frames @ 24fps (~3.0s), 40 steps → smooth, stable, no warp. ~2× the lo-fi
# comedy default, but the REAL car is on-screen for seconds so it earns the cost.
# Pre-generated once per car (never mid-render), so the minutes are free overnight.
_HQ = dict(width=448, height=256, frames=73, steps=40)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def liven(car: str, limit: int = 8) -> dict[str, str | None]:
    """Animate up to `limit` of the car's vetted stills into i2v clips (cached)."""
    if not videogen.available():
        print("video env not found (.venv-video) — install the LTX stack first.")
        return {}
    slug = _slug(car)
    car_root = paths.ASSETS / "cars" / slug
    own_dir = car_root / "own"
    own_dir.mkdir(parents=True, exist_ok=True)
    stills = (sorted((car_root / "press").glob("*.[jp][pn]g"))
              + sorted((car_root / "images").glob("*.[jp][pn]g")))[:limit]
    if not stills:
        print(f"no vetted stills for {car} — fetch + vet the pool first.")
        return {}

    out: dict[str, str | None] = {}
    for still in stills:
        dest = own_dir / f"living_{still.stem}.mp4"
        clip = videogen.generate(_PROMPT, mode="i2v", image=str(still),
                                 out_path=str(dest), **_HQ)
        out[still.name] = clip
        print(f"  {still.name[:42]:44} {'-> ' + Path(clip).name if clip else 'FAILED'}")
    done = sum(1 for v in out.values() if v)
    print(f"livened {done}/{len(stills)} stills -> {own_dir}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Animate a car's vetted stills into i2v Living Stills (one-time, cached).")
    ap.add_argument("car", help='Car name, e.g. "Tata Punch".')
    ap.add_argument("--limit", type=int, default=8, help="Max stills to animate.")
    args = ap.parse_args()
    liven(args.car, limit=args.limit)


if __name__ == "__main__":
    main()
