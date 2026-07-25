"""Generate a punchy vertical thumbnail (Short cover) — free, from a real CC photo.

  python -m carshorts.rendering.thumbnail --image assets/images/tata-nexon/2023_Tata_Nexon_XZA_front_view.jpg \
      --headline "TATA NEXON" --price "FROM 7.37L" --features "360 CAM . CRUISE . AUTO AC" \
      --out out/nexon_thumb.png

No AI image generation (that would fake the car). We composite bold text over an
actual licensed photo of the exact car — high-contrast, big fonts, a tilted price
banner. Repeatable per car.
"""
from __future__ import annotations

import argparse

from carshorts.adapters.renderer import _cover_crop, _load_font

SIZE = (1080, 1920)
YELLOW = (255, 214, 10)
RED = (230, 40, 40)
WHITE = (245, 245, 245)
BLACK = (12, 12, 12)


def _gradient(draw, top: bool, height: int, width: int, max_alpha: int):
    """Draw a vertical black fade for text legibility (top or bottom band)."""
    for i in range(height):
        alpha = int(max_alpha * (1 - i / height)) if top else int(max_alpha * (i / height))
        y = i if top else (SIZE[1] - height + i)
        draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))


def _stroked(draw, xy, text, font, fill, stroke=(0, 0, 0), sw=8, anchor=None):
    draw.text(xy, text, font=font, fill=fill, stroke_width=sw, stroke_fill=stroke, anchor=anchor)


def _tilted_banner(text: str, font, bg, fg, angle: float = -8.0):
    """A filled banner with text, rotated for energy. Returns an RGBA image."""
    from PIL import Image, ImageDraw

    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    tw = int(tmp.textlength(text, font=font))
    th = sum(font.getmetrics())
    pad_x, pad_y = 46, 26
    banner = Image.new("RGBA", (tw + pad_x * 2, th + pad_y * 2), (0, 0, 0, 0))
    bd = ImageDraw.Draw(banner)
    bd.rounded_rectangle([0, 0, banner.width - 1, banner.height - 1], radius=24, fill=bg)
    bd.text((pad_x, pad_y - 4), text, font=font, fill=fg)
    return banner.rotate(angle, expand=True, resample=Image.BICUBIC)


def generate_thumbnail(image_path: str, out_path: str, headline: str,
                       price: str = "", features: str = "") -> str:
    from PIL import Image, ImageDraw

    width, height = SIZE
    img = _cover_crop(Image.open(image_path).convert("RGB"), width, height)

    overlay = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    _gradient(od, top=True, height=560, width=width, max_alpha=205)
    _gradient(od, top=False, height=520, width=width, max_alpha=225)
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img)

    # Headline top — big, white, heavy black stroke.
    head_font = _load_font(150)
    _stroked(draw, (54, 70), headline.upper(), head_font, WHITE, sw=10)

    # Accent underline bar.
    draw.rectangle([58, 250, 58 + 420, 268], fill=YELLOW)

    # Tilted price banner — the attention grabber.
    if price:
        banner = _tilted_banner(price.upper(), _load_font(96), YELLOW, BLACK)
        img.paste(banner, (60, 360), banner)

    # A red "!" shout near the price for energy.
    _stroked(draw, (width - 190, 330), "?!", _load_font(180), RED, sw=10)

    # Features across the bottom band.
    if features:
        feat_font = _load_font(58)
        lines = _wrap(draw, features.upper(), feat_font, int(width * 0.9))
        y = height - 120 - (sum(feat_font.getmetrics()) + 10) * len(lines)
        for line in lines:
            _stroked(draw, (54, y), line, feat_font, YELLOW, sw=6)
            y += sum(feat_font.getmetrics()) + 10

    img.save(out_path)
    return out_path


def _wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def main() -> None:
    p = argparse.ArgumentParser(description="Generate a vertical Short thumbnail.")
    p.add_argument("--image", required=True, help="Background car photo (a CC still).")
    p.add_argument("--headline", required=True)
    p.add_argument("--price", default="")
    p.add_argument("--features", default="")
    p.add_argument("--out", default="out/thumb.png")
    args = p.parse_args()
    path = generate_thumbnail(args.image, args.out, args.headline, args.price, args.features)
    print(f"Done -> {path}")


if __name__ == "__main__":
    main()
