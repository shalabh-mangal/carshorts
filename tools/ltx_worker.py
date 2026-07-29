# -*- coding: utf-8 -*-
"""LTX-Video generation worker — RUN WITH THE .venv-video PYTHON, not the main venv.

Kept in its own isolated environment so LTX's newer diffusers/torch can never
break chatterbox's pinned diffusers in the main venv. The carshorts.adapters.videogen
adapter shells out to this as a subprocess.

  .venv-video\\Scripts\\python.exe tools/ltx_worker.py --mode t2v \\
      --prompt "a cartoon rocket blasting off" --out out/ai_clips/rocket.mp4
  ... --mode i2v --image assets/cars/x/images/car.jpg --prompt "slow cinematic push-in"

Memory-tuned for 8GB: bf16 + model-cpu-offload + VAE tiling, small res/short clips.
"""
from __future__ import annotations

import argparse
import os

import torch
from diffusers.utils import export_to_video

_MODEL = "Lightricks/LTX-Video"
_NEG = "blurry, distorted, low quality, watermark, text, deformed, ugly, jpeg artifacts"


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate one LTX-Video clip.")
    ap.add_argument("--mode", choices=["t2v", "i2v"], required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--image", help="Reference image (required for i2v).")
    ap.add_argument("--out", required=True)
    ap.add_argument("--width", type=int, default=512)
    ap.add_argument("--height", type=int, default=320)
    ap.add_argument("--frames", type=int, default=65)      # must be N*8+1
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    gen = torch.Generator(device="cpu").manual_seed(args.seed)
    common = dict(prompt=args.prompt, negative_prompt=_NEG, width=args.width,
                  height=args.height, num_frames=args.frames,
                  num_inference_steps=args.steps, generator=gen)

    if args.mode == "t2v":
        from diffusers import LTXPipeline
        pipe = LTXPipeline.from_pretrained(_MODEL, torch_dtype=torch.bfloat16)
        pipe.enable_model_cpu_offload()
        try:
            pipe.vae.enable_tiling()
        except Exception:  # noqa: BLE001
            pass
        frames = pipe(**common).frames[0]
    else:
        from diffusers import LTXImageToVideoPipeline
        from diffusers.utils import load_image
        if not args.image:
            raise SystemExit("i2v needs --image")
        pipe = LTXImageToVideoPipeline.from_pretrained(_MODEL, torch_dtype=torch.bfloat16)
        pipe.enable_model_cpu_offload()
        try:
            pipe.vae.enable_tiling()
        except Exception:  # noqa: BLE001
            pass
        frames = pipe(image=load_image(args.image), **common).frames[0]

    export_to_video(frames, args.out, fps=args.fps)
    print("WORKER_DONE", args.out)


if __name__ == "__main__":
    main()
