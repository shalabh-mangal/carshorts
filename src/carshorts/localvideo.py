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


def generate(prompt: str, out_path: str, width: int = 448, height: int = 640,
             num_frames: int = 33, steps: int = 20, fps: int = 24,
             low_mem: bool = True) -> str:
    import gc

    import torch
    from diffusers import LTXPipeline
    from diffusers.utils import export_to_video

    dtype = torch.bfloat16  # halves memory vs float32; LTX's native dtype
    pipe = LTXPipeline.from_pretrained(MODEL, torch_dtype=dtype)

    if low_mem:
        # Sequential offload streams one submodule at a time, so peak allocation
        # is ~the largest single module, not the sum (T5-XXL never coexists with
        # the transformer). Slow, but the only way to fit ~13GB of weights + the
        # activations into 16GB. Fall back gracefully if MPS rejects a strategy.
        placed = False
        for strategy in ("sequential", "model"):
            try:
                if strategy == "sequential":
                    pipe.enable_sequential_cpu_offload(device="mps")
                else:
                    pipe.enable_model_cpu_offload(device="mps")
                placed = True
                break
            except Exception:  # noqa: BLE001
                continue
        if not placed:
            pipe.to("mps")
    else:
        pipe.to("mps")

    pipe.enable_attention_slicing()
    try:
        pipe.enable_vae_tiling()   # decode the video in tiles -> lower peak memory
    except Exception:  # noqa: BLE001
        pass

    gc.collect()
    if torch.backends.mps.is_available():
        torch.mps.empty_cache()

    result = pipe(
        prompt=prompt,
        negative_prompt="blurry, distorted, watermark, text, logo, brand name",
        width=width, height=height, num_frames=num_frames, num_inference_steps=steps,
    )
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    export_to_video(result.frames[0], out_path, fps=fps)
    return out_path


def main() -> None:
    p = argparse.ArgumentParser(description="Generate one clip locally via LTX-Video.")
    p.add_argument("--prompt", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--frames", type=int, default=33)
    p.add_argument("--steps", type=int, default=20)
    p.add_argument("--no-lowmem", action="store_true", help="Disable offload (needs lots of RAM).")
    args = p.parse_args()
    path = generate(args.prompt, args.out, num_frames=args.frames, steps=args.steps,
                    low_mem=not args.no_lowmem)
    print(f"Done -> {path}")


if __name__ == "__main__":
    main()
