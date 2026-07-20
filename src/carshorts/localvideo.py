"""Local, free AI video via LTX-Video (diffusers) on Apple Silicon MPS.

  python -m carshorts.localvideo --prompt "..." --out assets/ai/<car>/local_seg_0.mp4

Zero cost, no watermark, no license strings — but HEAVY: multi-GB model download
on first run, and generation is slow + memory-tight on a 16GB M4 (may OOM). This
is the "option 2" of the Pika-vs-local comparison. If it's too slow/OOMs, Pika
is the practical free route.

Kept small on purpose: 480x704, few frames — the renderer cover-crops to the
vertical frame anyway, and lower settings are the only way this fits in 16GB.
"""
from __future__ import annotations

import argparse
from pathlib import Path

MODEL = "Lightricks/LTX-Video"


def generate(prompt: str, out_path: str, width: int = 480, height: int = 704,
             num_frames: int = 49, steps: int = 25, fps: int = 24) -> str:
    import torch
    from diffusers import LTXPipeline
    from diffusers.utils import export_to_video

    # bfloat16 is LTX's native dtype; fall back to float16 if MPS rejects it.
    dtype = torch.bfloat16
    pipe = LTXPipeline.from_pretrained(MODEL, torch_dtype=dtype)
    pipe.to("mps")
    pipe.enable_attention_slicing()  # trade speed for lower peak memory (16GB)

    result = pipe(
        prompt=prompt,
        negative_prompt="blurry, distorted, watermark, text, logo, brand",
        width=width, height=height, num_frames=num_frames, num_inference_steps=steps,
    )
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    export_to_video(result.frames[0], out_path, fps=fps)
    return out_path


def main() -> None:
    p = argparse.ArgumentParser(description="Generate one clip locally via LTX-Video.")
    p.add_argument("--prompt", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--frames", type=int, default=49)
    p.add_argument("--steps", type=int, default=25)
    args = p.parse_args()
    path = generate(args.prompt, args.out, num_frames=args.frames, steps=args.steps)
    print(f"Done -> {path}")


if __name__ == "__main__":
    main()
