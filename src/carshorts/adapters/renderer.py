"""The VideoRenderer adapter — assembles audio + visuals into one MP4.

Free stack: MoviePy (over FFmpeg) for muxing, Pillow for drawing text/cards.
This first implementation is deliberately minimal — a background (a supplied
image, or a dark card with the title drawn on it) plus the voice track, at
vertical 1080x1920 for Shorts. Captions, motion (Ken Burns), and multi-clip
sequencing are the next layers, added behind this same interface. A future
avatar/generative renderer would be another implementation, A/B tested.

Text is drawn with Pillow rather than MoviePy's TextClip because Pillow gives
reliable control over fonts and wrapping without MoviePy 2.x's font-resolution
quirks.
"""
from __future__ import annotations

import os
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass

from carshorts.core import paths

VERTICAL = (1080, 1920)

# Common macOS/Linux/Windows font locations, tried in order. Falls back to
# Pillow's built-in bitmap font if none resolve (ugly but never crashes).
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",       # Windows: Arial Bold
    r"C:\Windows\Fonts\arial.ttf",         # Windows: Arial
    r"C:\Windows\Fonts\segoeui.ttf",       # Windows: Segoe UI
]


def _load_font(size: int):
    from PIL import ImageFont

    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _cover_crop(img, width: int, height: int):
    """Resize `img` to fully cover width x height, then center-crop."""
    from PIL import Image

    src_w, src_h = img.size
    scale = max(width / src_w, height / src_h)
    resized = img.resize((int(src_w * scale) + 1, int(src_h * scale) + 1), Image.LANCZOS)
    rw, rh = resized.size
    left, top = (rw - width) // 2, (rh - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _fit_font_size(text: str) -> int:
    """Pick a caption font size that keeps a spoken line readable but on-screen.
    Longer lines (a full spec sentence) shrink; short punchy lines stay big."""
    n = len(text)
    if n > 140:
        return 46
    if n > 80:
        return 56
    return 68


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_caption(draw, text: str, font, width: int, height: int):
    """Word-wrap `text` and draw it centered, with a soft shadow for legibility."""
    lines = _wrap(draw, text, font, int(width * 0.84))
    ascent, descent = font.getmetrics()
    line_h = ascent + descent + 14
    total_h = line_h * len(lines)
    y = (height - total_h) // 2
    for line in lines:
        w = draw.textlength(line, font=font)
        x = (width - w) // 2
        draw.text((x + 3, y + 3), line, font=font, fill=(0, 0, 0))       # shadow
        draw.text((x, y), line, font=font, fill=(245, 245, 245))          # text
        y += line_h


class Section:
    """One scene: an audio clip plus its visual(s).

    background_pool (preferred): a LIST of visuals (video paths or image paths)
    — the section is cut into fast sub-scenes (~2-3s each), one per visual, so
    pacing stays energetic and no asset lingers. Falls back to the single
    background_video / background_image when no pool is given."""

    def __init__(self, audio_path: str, caption: str, background_image: str | None = None,
                 background_video: str | None = None,
                 background_pool: list[str] | None = None,
                 word_pops: list | None = None,
                 keyword: str = "", callout_lines: list[str] | None = None,
                 timed_cuts: list | None = None,
                 keyword_span: tuple | None = None,
                 timed_callouts: list | None = None):
        self.audio_path = audio_path
        self.caption = caption
        self.background_image = background_image
        self.background_video = background_video
        self.background_pool = background_pool or []
        self.word_pops = word_pops or []           # [(start_off, dur, text)] voice-synced
        self.keyword = keyword                     # short on-screen punch text
        self.callout_lines = callout_lines or []   # staggered feature card lines
        self.timed_cuts = timed_cuts or []         # [(offset_s, path)] phrase-synced
        self.keyword_span = keyword_span           # (start_off, dur) or None
        self.timed_callouts = timed_callouts or [] # [(start_off, end_off, text)]



_HEAVY_FONTS = [
    str(paths.FONTS / "Montserrat-Black.ttf"),
    "assets/fonts/Montserrat-Black.ttf",                     # cwd-relative fallback
    r"C:\Windows\Fonts\Montserrat-Black.ttf",               # Windows: if user-installed
    "/System/Library/Fonts/SFCompactRounded.ttf",
    "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    r"C:\Windows\Fonts\ariblk.ttf",                          # Windows: Arial Black (heavy)
    r"C:\Windows\Fonts\seguisb.ttf",                         # Windows: Segoe UI Semibold
] + _FONT_CANDIDATES

# Overlay palette. White base + ONE restrained metallic accent (champagne) —
# replaces the old tech-cyan, which read gaming/clip-farm and clashed on bright
# cars. Yellow stays banned. (ACCENT_CYAN kept for back-compat; no longer used.)
TEXT_WHITE = (255, 255, 255, 255)
OFFWHITE = (245, 242, 236, 255)
ACCENT_CYAN = (126, 229, 227, 255)      # legacy — retired 2026-08-03
ACCENT_CHAMPAGNE = (201, 162, 75, 255)      # #C9A24B — deep metallic
ACCENT_CHAMPAGNE_LT = (222, 197, 140, 255)  # #DEC58C — legible on dark footage
STROKE_BLACK = (0, 0, 0, 255)

# Stills are darkened so white overlay text stays readable over any photo.
DEFAULT_DARKEN = 0.35
# ...but the OPENING cut is exempt. On a Short frame 1 IS the thumbnail and gets
# about one blink to stop a scroll, and it carries no text yet — pops are
# voice-synced and start later — so it was paying the legibility tax for a
# benefit it never received. Measured against 127 real rival Shorts thumbnails
# (2026-07-23) our openers ran 0.70x brightness, 0.71x contrast and 0.59x
# colourfulness of the feed norm; undoing a 0.65x multiply lands them at it.
# Pops that fire during the opening cut keep their own ~9% black stroke and
# blurred shadow, which is what actually carries legibility over busy footage.
OPENING_DARKEN = 0.0


# --- Premium overlay themes (owner picks A/B; we A/B-test which performs) -------
# Weight -> candidate font files. Prefers bundled Montserrat (repo-portable, added
# for cross-machine/CI consistency), then the Segoe UI weights present on Windows
# (the exact faces the owner approved in the style samples), then DejaVu/Arial. So
# a theme asks for a WEIGHT and gets the best available face with no hard download
# dependency — if Montserrat isn't bundled yet, local renders still look right.
_WEIGHT_CANDIDATES = {
    "light":    [paths.FONTS / "Montserrat-Light.ttf",    r"C:\Windows\Fonts\segoeuil.ttf",
                 r"C:\Windows\Fonts\arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    "regular":  [paths.FONTS / "Montserrat-Regular.ttf",  r"C:\Windows\Fonts\segoeui.ttf",
                 r"C:\Windows\Fonts\arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    "medium":   [paths.FONTS / "Montserrat-Medium.ttf",   r"C:\Windows\Fonts\segoeui.ttf",
                 r"C:\Windows\Fonts\arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    "semibold": [paths.FONTS / "Montserrat-SemiBold.ttf", r"C:\Windows\Fonts\seguisb.ttf",
                 r"C:\Windows\Fonts\arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "black":    [paths.FONTS / "Montserrat-Black.ttf",    r"C:\Windows\Fonts\ariblk.ttf",
                 r"C:\Windows\Fonts\arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
}


def _weight_font(weight: str, size: int):
    from PIL import ImageFont
    for p in _WEIGHT_CANDIDATES.get(weight, []):
        try:
            f = ImageFont.truetype(str(p), size)
            if "Montserrat" in str(p):
                try:
                    f.set_variation_by_name(weight.capitalize())
                except (OSError, AttributeError):
                    pass
            return f
        except OSError:
            continue
    return _load_heavy_font(size)


@dataclass(frozen=True)
class OverlayTheme:
    """One overlay look. Drives every pop generator so a whole render is coherent."""
    name: str
    accent: tuple           # metallic accent
    base: tuple             # main text colour
    value_w: str            # weight key for the big count-up number
    label_w: str            # weight key for the small kicker label
    chip_w: str             # weight key for rail word/number chips
    reaction_w: str         # weight key for reaction slams
    tracking: float         # letter-spacing as a fraction of font size (the premium tell)
    container: str          # "none" (A, boxless) | "panel" (B, smoked glass)
    panel_fill: tuple
    panel_border: tuple
    stroke_frac: float      # heavy stroke retired; kept configurable, 0 for both
    shadow_blur: int        # soft shadow (carries legibility for the boxless theme)
    shadow_alpha: float
    rule: str               # accent rule under the value: "underline" | "tick" | ""
    card_value_accent: bool  # True: value=accent,label=base (A); False: value=base,label=accent (B)


# A — EDITORIAL LUXE: thin, wide-tracked, boxless, champagne number. Owner's pick.
THEME_LUXE = OverlayTheme(
    name="luxe", accent=ACCENT_CHAMPAGNE_LT, base=OFFWHITE,
    value_w="light", label_w="regular", chip_w="light", reaction_w="regular",
    tracking=0.16, container="none", panel_fill=(0, 0, 0, 0), panel_border=(0, 0, 0, 0),
    stroke_frac=0.0, shadow_blur=16, shadow_alpha=0.72, rule="underline",
    card_value_accent=True)

# B — FROSTED BROADCAST: semibold, smoked-glass panel, white value + champagne rule.
THEME_FROST = OverlayTheme(
    name="frost", accent=ACCENT_CHAMPAGNE_LT, base=TEXT_WHITE,
    value_w="semibold", label_w="semibold", chip_w="semibold", reaction_w="semibold",
    tracking=0.10, container="panel", panel_fill=(12, 14, 18, 180), panel_border=(255, 255, 255, 60),
    stroke_frac=0.0, shadow_blur=10, shadow_alpha=0.0, rule="tick",
    card_value_accent=False)

THEMES = {"luxe": THEME_LUXE, "frost": THEME_FROST}


def get_theme(name: str | None) -> OverlayTheme:
    return THEMES.get((name or "luxe").lower(), THEME_LUXE)


def _tracked_len(draw, text: str, font, track: float) -> float:
    if not text:
        return 0.0
    return sum(draw.textlength(c, font=font) + track for c in text) - track


def _draw_tracked(draw, x: float, y: float, text: str, font, fill, track: float,
                  stroke: int = 0, stroke_fill=STROKE_BLACK) -> None:
    for c in text:
        draw.text((x, y), c, font=font, fill=fill,
                  stroke_width=stroke, stroke_fill=stroke_fill)
        x += draw.textlength(c, font=font) + track


def _load_heavy_font(size: int):
    from PIL import ImageFont

    for path in _HEAVY_FONTS:
        try:
            font = ImageFont.truetype(path, size)
            if "Montserrat" in path:
                try:
                    font.set_variation_by_name("Black")
                except OSError:
                    pass
            return font
        except OSError:
            continue
    return _load_font(size)


def _numberish(token: str) -> bool:
    return any(c.isdigit() for c in token) or "₹" in token


def _overlay_png(text: str, font_size: int, out_path: str, *,
                 theme: OverlayTheme = THEME_LUXE, kind: str = "word",
                 fit_one_line: bool = False, max_width: int = 820) -> str:
    """Render a rail/reaction pop to a transparent PNG in the given THEME.

    Premium treatment (both themes): the requested WEIGHT, generous letter-spacing
    (the amateur->pro tell), no heavy stroke. Number pops accent the figure. Theme
    "luxe" is boxless with a soft shadow for legibility; "frost" wraps a smoked-
    glass panel with a hairline border so it reads on any footage."""
    from PIL import Image, ImageDraw, ImageFilter

    weight = theme.reaction_w if kind == "reaction" else theme.chip_w
    font = _weight_font(weight, font_size)
    tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    track = theme.tracking * font_size
    if fit_one_line:
        while font_size > 44 and _tracked_len(tmp, text, font, track) > 620:
            font_size -= 6
            font = _weight_font(weight, font_size)
            track = theme.tracking * font_size
    lines = _wrap(tmp, text, font, max_width)
    ascent, descent = font.getmetrics()
    line_h = ascent + descent + 8
    stroke = max(0, round(font_size * theme.stroke_frac))
    panel = theme.container == "panel"
    pad_x, pad_y = (56, 30) if panel else (34, 20)
    text_w = max(_tracked_len(tmp, ln, font, track) for ln in lines)
    width = int(text_w) + 2 * pad_x + 2 * stroke
    height = line_h * len(lines) + 2 * pad_y + 2 * stroke
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if panel:
        r = min(28, height // 3)
        draw.rounded_rectangle([0, 0, width - 1, height - 1], radius=r, fill=theme.panel_fill)
        draw.rounded_rectangle([0, 0, width - 1, height - 1], radius=r,
                               outline=theme.panel_border, width=2)

    def render_line(target, line, y):
        x = (width - _tracked_len(target, line, font, track)) / 2
        if kind == "number":
            for tok in line.split(" "):
                col = theme.accent if _numberish(tok) else theme.base
                _draw_tracked(target, x, y, tok, font, col, track, stroke)
                x += _tracked_len(target, tok, font, track) + target.textlength(" ", font=font) + track
        else:
            _draw_tracked(target, x, y, line, font, theme.base, track, stroke)

    if not panel and theme.shadow_alpha > 0:
        shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(shadow)
        y = pad_y + stroke
        for line in lines:
            sx = (width - _tracked_len(sdraw, line, font, track)) / 2
            _draw_tracked(sdraw, sx + 3, y + 5, line, font, (0, 0, 0, 255), track)
            y += line_h
        shadow = shadow.filter(ImageFilter.GaussianBlur(theme.shadow_blur))
        shadow.putalpha(shadow.getchannel("A").point(lambda a: int(a * theme.shadow_alpha)))
        img.alpha_composite(shadow)

    y = pad_y + stroke
    for line in lines:
        render_line(draw, line, y)
        y += line_h
    img.save(out_path)
    return out_path


def _settle_scale(t: float) -> float:
    """Grow-overshoot-settle: 0.92 -> 1.05 -> 1.00 over 0.22s (research: the
    canonical premium arrival; overshoot capped well under 1.15)."""
    if t >= 0.22:
        return 1.0
    if t < 0.12:
        progress = t / 0.12
        return 0.92 + 0.13 * (1 - (1 - progress) ** 2)
    return 1.05 - 0.05 * ((t - 0.12) / 0.10)


def _slam_scale(t: float) -> float:
    """Reaction-text entrance: 1.3 -> 1.0 in 150ms, hard and loud on purpose —
    a different voice from the pop rail (the editor reacting, not captions)."""
    return 1.3 - 0.3 * min(t, 0.15) / 0.15 if t < 0.15 else 1.0


def _wipe_bar_frames(full_width: int, tdir: str, tag: str,
                     color: tuple = ACCENT_CHAMPAGNE_LT) -> list[str]:
    """12 frames of an accent marker-bar wiping left->right (ease-out, 0.35s)."""
    from PIL import Image, ImageDraw

    frames = []
    for f in range(12):
        progress = 1 - (1 - (f + 1) / 12) ** 2
        w = max(3, int(full_width * progress))
        img = Image.new("RGBA", (full_width, 14), (0, 0, 0, 0))
        ImageDraw.Draw(img).rounded_rectangle([0, 2, w, 12], radius=5,
                                              fill=color)
        path = f"{tdir}/{tag}_f{f}.png"
        img.save(path)
        frames.append(path)
    return frames


def _lss_strip_png(out_path: str, icon_size: int = 116,
                   strip_width: int = 640, active: int = 3, *,
                   theme: OverlayTheme = THEME_LUXE) -> str:
    """Like/Share/Subscribe strip, PREMIUM treatment in the given THEME: clean
    icons in the theme's base colour, a HAIRLINE edge + soft shadow for legibility
    (not the old thick meme outline), and small letter-spaced labels — matching the
    overlay type. `active` draws only the first N icons (1 = thumb, 2 = +share,
    3 = +bell) at FIXED positions, so the three word-synced pops form one cumulative
    reveal. Drawn procedurally with Pillow; no emoji fonts, no downloads."""
    from PIL import Image, ImageDraw, ImageFilter

    label_font = _weight_font(theme.label_w, 30)
    track = theme.tracking * 30
    pad = 44
    label_h = 56
    canvas_w = strip_width + 2 * pad
    canvas_h = icon_size + label_h + 2 * pad
    cell = strip_width // 3
    centers = [pad + cell // 2 + i * cell for i in range(3)]
    cy = pad + icon_size // 2

    # icons in the theme base colour; edge + shadow derive from their alpha
    white = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(white)
    W = theme.base

    def thumb(cx):
        s_ = icon_size
        # palm block
        d.rounded_rectangle([cx - s_ * 0.30, cy - s_ * 0.10,
                             cx + s_ * 0.30, cy + s_ * 0.42],
                            radius=s_ * 0.10, fill=W)
        # thumb sweeping up-left
        d.rounded_rectangle([cx - s_ * 0.30, cy - s_ * 0.42,
                             cx - s_ * 0.02, cy + s_ * 0.05],
                            radius=s_ * 0.13, fill=W)
        d.pieslice([cx - s_ * 0.34, cy - s_ * 0.50,
                    cx + s_ * 0.10, cy - s_ * 0.10], 150, 340, fill=W)

    def share(cx):
        s_ = icon_size
        # tray: thick open-top U
        t = s_ * 0.11
        d.rounded_rectangle([cx - s_ * 0.34, cy + s_ * 0.30,
                             cx + s_ * 0.34, cy + s_ * 0.44],
                            radius=t / 2, fill=W)          # base
        d.rounded_rectangle([cx - s_ * 0.34, cy - s_ * 0.02,
                             cx - s_ * 0.34 + t, cy + s_ * 0.44],
                            radius=t / 2, fill=W)          # left wall
        d.rounded_rectangle([cx + s_ * 0.34 - t, cy - s_ * 0.02,
                             cx + s_ * 0.34, cy + s_ * 0.44],
                            radius=t / 2, fill=W)          # right wall
        # arrow: shaft + head rising from the tray
        d.rounded_rectangle([cx - t / 2, cy - s_ * 0.30,
                             cx + t / 2, cy + s_ * 0.18],
                            radius=t / 2, fill=W)
        d.polygon([(cx - s_ * 0.22, cy - s_ * 0.20), (cx, cy - s_ * 0.50),
                   (cx + s_ * 0.22, cy - s_ * 0.20)], fill=W)

    def bell(cx):
        s_ = icon_size
        # dome
        d.pieslice([cx - s_ * 0.30, cy - s_ * 0.44,
                    cx + s_ * 0.30, cy + s_ * 0.36], 180, 360, fill=W)
        d.rectangle([cx - s_ * 0.30, cy - s_ * 0.04,
                     cx + s_ * 0.30, cy + s_ * 0.22], fill=W)
        # flared skirt
        d.rounded_rectangle([cx - s_ * 0.38, cy + s_ * 0.18,
                             cx + s_ * 0.38, cy + s_ * 0.30],
                            radius=s_ * 0.06, fill=W)
        # clapper + top nub
        d.ellipse([cx - s_ * 0.08, cy + s_ * 0.32,
                   cx + s_ * 0.08, cy + s_ * 0.48], fill=W)
        d.ellipse([cx - s_ * 0.06, cy - s_ * 0.52,
                   cx + s_ * 0.06, cy - s_ * 0.40], fill=W)

    for draw_icon, cx in zip((thumb, share, bell)[:active], centers[:active]):
        draw_icon(cx)
    for label, cx in zip(("LIKE", "SHARE", "SUBSCRIBE")[:active], centers[:active]):
        lw = _tracked_len(d, label, label_font, track)
        _draw_tracked(d, cx - lw / 2, pad + icon_size + 16, label, label_font, W, track)

    # HAIRLINE edge (a crisp ~2px rim, not the old thick meme outline) so the
    # light icons stay legible over bright skies, plus a soft blurred shadow for
    # depth — the same restrained legibility language as the premium text pops.
    alpha = white.getchannel("A")
    edge_mask = alpha.filter(ImageFilter.MaxFilter(5))       # ~2px each side
    edge = Image.new("RGBA", white.size, (0, 0, 0, 0))
    edge.paste((0, 0, 0, 150), mask=edge_mask)
    shadow = Image.new("RGBA", white.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 255), mask=edge_mask)
    shadow = shadow.filter(ImageFilter.GaussianBlur(10))
    shadow.putalpha(shadow.getchannel("A").point(lambda a: int(a * 0.55)))

    img = Image.new("RGBA", white.size, (0, 0, 0, 0))
    img.alpha_composite(shadow, (2, 5))
    img.alpha_composite(edge)
    img.alpha_composite(white)
    img.save(out_path)
    return out_path


def _ease_out(x: float) -> float:
    return 1 - (1 - max(0.0, min(1.0, x))) ** 3


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _draw_bell(d, cx, cy, s, col):
    d.pieslice([cx - s * .30, cy - s * .44, cx + s * .30, cy + s * .36], 180, 360, fill=col)
    d.rectangle([cx - s * .30, cy - s * .04, cx + s * .30, cy + s * .22], fill=col)
    d.rounded_rectangle([cx - s * .38, cy + s * .18, cx + s * .38, cy + s * .30], radius=s * .06, fill=col)
    d.ellipse([cx - s * .08, cy + s * .32, cx + s * .08, cy + s * .48], fill=col)
    d.ellipse([cx - s * .06, cy - s * .52, cx + s * .06, cy - s * .40], fill=col)


def _draw_cursor(d, x, y, sc=1.0):
    p = [(x, y), (x, y + 46), (x + 12, y + 34), (x + 22, y + 54),
         (x + 31, y + 50), (x + 21, y + 30), (x + 37, y + 30)]
    p = [(x + (px - x) * sc, y + (py - y) * sc) for px, py in p]
    d.polygon(p, fill=(255, 255, 255, 255), outline=(0, 0, 0, 170))


def _subscribe_frames(tdir: str, tag: str, n_frames: int = 46, *,
                      theme: OverlayTheme = THEME_LUXE) -> list[str]:
    """PREMIUM single-ask SUBSCRIBE micro-interaction (no like/share — the owner
    already asks those in the voiceover). A champagne pill slams in, a cursor taps
    it (ripple + press), it flips to SUBSCRIBED ✓ with a bell ring, then holds.
    Research: one clear ask + a satisfying state-change converts and re-watches
    well on the Shorts loop. Returns a full-frame-width sequence of PNG paths."""
    import math

    from PIL import Image, ImageDraw, ImageFilter

    cw, ch = 1080, 460
    cx, cy = cw // 2, ch // 2
    accent = theme.accent
    ink = (16, 14, 10, 255)
    label_f = _weight_font("semibold", 52)
    tr = 0.10 * 52
    frames: list[str] = []
    for f in range(n_frames):
        t = f / (n_frames - 1)
        tapped = t >= 0.44
        img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        # appear overshoot, then a quick press dip on tap
        if t < 0.14:
            sc = 0.85 + 0.20 * _ease_out(t / 0.14)
        elif 0.36 <= t < 0.46:
            sc = 0.965
        else:
            sc = 1.0

        text = "SUBSCRIBED" if tapped else "SUBSCRIBE"
        tw = _tracked_len(d, text, label_f, tr)
        bell_w, check_w, pad_x = 78, (60 if tapped else 0), 58
        pw = (tw + bell_w + check_w + 2 * pad_x) * sc
        ph = 112 * sc
        x0, y0 = cx - pw / 2, cy - ph / 2

        shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle([x0, y0, x0 + pw, y0 + ph],
                                                 radius=ph / 2, fill=(0, 0, 0, 255))
        shadow = shadow.filter(ImageFilter.GaussianBlur(16))
        shadow.putalpha(shadow.getchannel("A").point(lambda a: int(a * 0.45)))
        img.alpha_composite(shadow, (2, 8))

        if tapped:
            d.rounded_rectangle([x0, y0, x0 + pw, y0 + ph], radius=ph / 2, fill=accent)
            txt_col = ink
            bell_col = ink
        else:
            d.rounded_rectangle([x0, y0, x0 + pw, y0 + ph], radius=ph / 2, fill=(10, 12, 16, 110))
            d.rounded_rectangle([x0, y0, x0 + pw, y0 + ph], radius=ph / 2,
                                outline=accent, width=max(3, int(4 * sc)))
            txt_col = accent
            bell_col = accent

        inner = x0 + pad_x * sc
        _draw_bell(d, inner + 26 * sc, cy, 42 * sc, bell_col)
        if tapped and t < 0.66:                      # ring lines burst
            for a in (28, 4, -22):
                rx = inner + 26 * sc + math.cos(math.radians(a)) * 60 * sc
                ry = cy - 6 * sc - math.sin(math.radians(a)) * 60 * sc
                d.ellipse([rx - 4, ry - 4, rx + 4, ry + 4], fill=accent)
        tx = inner + bell_w * sc
        if tapped:
            ccx = tx + 24 * sc
            d.ellipse([ccx - 24 * sc, cy - 24 * sc, ccx + 24 * sc, cy + 24 * sc], fill=ink)
            d.line([(ccx - 10 * sc, cy), (ccx - 2 * sc, cy + 10 * sc), (ccx + 12 * sc, cy - 11 * sc)],
                   fill=accent, width=max(3, int(5 * sc)))
            tx += check_w * sc
        asc, desc = label_f.getmetrics()
        _draw_tracked(d, tx, cy - (asc + desc) / 2 * sc, text, label_f, txt_col, tr)

        # tap ripple + cursor
        if 0.36 <= t <= 0.74:
            rp = (t - 0.36) / 0.38
            for base_r in (34, 74):
                rr = base_r + rp * 140
                al = int(150 * (1 - rp))
                if al > 0:
                    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                              outline=(255, 255, 255, al), width=3)
        if 0.14 <= t <= 0.54:
            cp = _clamp01((t - 0.14) / 0.26)
            curx = cx + 190 - cp * 165
            cury = cy + 165 - cp * 130
            _draw_cursor(d, curx, cury)

        path = f"{tdir}/{tag}_f{f:03d}.png"
        img.save(path)
        frames.append(path)
    return frames


def _countup_frames(final_text: str, label: str, tdir: str, tag: str,
                    n_frames: int = 34, *, theme: OverlayTheme = THEME_LUXE) -> list[str]:
    """Big-number payoff card, count-up to the exact figure, in the given THEME.

    BUGFIX: a unit label ('₹11.49L · EX-SHOWROOM') used to be crammed INTO the
    count-up number line, so it couldn't autofit and clipped off both frame edges.
    We now split it out into the small kicker slot and hard-clamp the value width
    to the safe box, so it can never clip. One per short, for THE payoff stat."""
    import re as _re

    from PIL import Image, ImageDraw, ImageFilter

    if not label and "·" in final_text:
        head, _, tail = final_text.partition("·")
        final_text, label = head.strip(), tail.strip()

    match = _re.search(r"\d[\d,]*(?:\.\d+)?", final_text)
    final_value = float(match.group(0).replace(",", "")) if match else 0.0
    prefix = final_text[:match.start()] if match else ""
    suffix = final_text[match.end():] if match else final_text
    decimals = len(match.group(0).split(".")[1]) if match and "." in match.group(0) else 0

    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    vweight, vtrack_frac = theme.value_w, theme.tracking * 0.5   # digits already wide
    digit_size = 300
    final_probe = f"{prefix}{final_value:,.{decimals}f}{suffix}".upper()
    # hard clamp: shrink until the widest frame fits the safe box — never clip
    while digit_size > 60 and _tracked_len(
            probe, final_probe, _weight_font(vweight, digit_size),
            vtrack_frac * digit_size) > 900:
        digit_size -= 10
    digit_font = _weight_font(vweight, digit_size)
    dtrack = vtrack_frac * digit_size
    label_font = _weight_font(theme.label_w, 54)
    ltrack = theme.tracking * 54
    value_color = theme.accent if theme.card_value_accent else theme.base
    label_color = theme.base if theme.card_value_accent else theme.accent
    stroke = max(0, round(digit_size * theme.stroke_frac))

    panel = theme.container == "panel"
    label_h = 84 if label else 0
    value_h = digit_size + 70
    pad = 48 if panel else 22
    width, height = 1080, label_h + value_h + 70 + 2 * pad
    frames = []
    for f in range(n_frames):
        progress = 1 - (1 - (f + 1) / n_frames) ** 3     # ease-out, slow landing
        value = final_value * progress if f < n_frames - 1 else final_value
        text = f"{prefix}{value:,.{decimals}f}{suffix}".upper()
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        if panel:
            vw = _tracked_len(d, text, digit_font, dtrack)
            lw = _tracked_len(d, label.upper(), label_font, ltrack) if label else 0
            pw = int(max(vw, lw)) + 2 * pad + 48
            px0 = (width - pw) // 2
            d.rounded_rectangle([px0, 0, px0 + pw, height - 1], radius=34, fill=theme.panel_fill)
            d.rounded_rectangle([px0, 0, px0 + pw, height - 1], radius=34,
                                outline=theme.panel_border, width=2)
        y = pad
        if label:
            lx = (width - _tracked_len(d, label.upper(), label_font, ltrack)) / 2
            _draw_tracked(d, lx, y, label.upper(), label_font, label_color, ltrack)
            y += label_h
        vx = (width - _tracked_len(d, text, digit_font, dtrack)) / 2
        if not panel and theme.shadow_alpha > 0:
            sh = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            _draw_tracked(ImageDraw.Draw(sh), vx + 3, y + 6, text, digit_font,
                          (0, 0, 0, 255), dtrack)
            sh = sh.filter(ImageFilter.GaussianBlur(theme.shadow_blur))
            sh.putalpha(sh.getchannel("A").point(lambda a: int(a * theme.shadow_alpha)))
            img.alpha_composite(sh)
        _draw_tracked(d, vx, y, text, digit_font, value_color, dtrack, stroke)
        y += value_h
        if theme.rule == "underline":
            d.rounded_rectangle([width / 2 - 150, y, width / 2 + 150, y + 6],
                                radius=3, fill=theme.accent)
        elif theme.rule == "tick":
            d.rounded_rectangle([width / 2 - 60, y, width / 2 + 60, y + 8],
                                radius=4, fill=theme.accent)
        path = f"{tdir}/{tag}_f{f}.png"
        img.save(path)
        frames.append(path)
    return frames


class VideoRenderer(ABC):
    @abstractmethod
    def render(self, audio_path: str, out_path: str,
               background_image: str | None = None, title: str | None = None) -> str:
        """Produce a vertical MP4 at out_path from audio (+ optional visuals)."""


class MoviePyRenderer(VideoRenderer):
    def __init__(self, size: tuple[int, int] = VERTICAL, bg_color: tuple[int, int, int] = (18, 18, 24)):
        self.size = size
        self.bg_color = bg_color

    def _prepare_background(self, background_image: str | None, text: str | None,
                            darken: float = DEFAULT_DARKEN) -> str:
        from PIL import Image, ImageDraw

        width, height = self.size
        if background_image:
            img = _cover_crop(Image.open(background_image).convert("RGB"), width, height)
            # Darken so white captions stay readable over any photo.
            if darken > 0:
                overlay = Image.new("RGB", (width, height), (0, 0, 0))
                img = Image.blend(img, overlay, darken)
        else:
            img = Image.new("RGB", (width, height), self.bg_color)

        if text:
            draw = ImageDraw.Draw(img)
            _draw_caption(draw, text, _load_font(_fit_font_size(text)), width, height)

        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        img.save(tmp.name)
        return tmp.name

    def render(self, audio_path: str, out_path: str,
               background_image: str | None = None, title: str | None = None) -> str:
        """Single-scene render (audio + one card). Kept for simple cases."""
        from moviepy import AudioFileClip, ImageClip

        bg_path = self._prepare_background(background_image, title)
        audio = AudioFileClip(audio_path)
        clip = ImageClip(bg_path).with_duration(audio.duration).with_audio(audio)
        clip.write_videofile(out_path, fps=24, codec="libx264",
                             audio_codec="aac", logger=None)
        return out_path

    _VIDEO_EXT = (".mp4", ".mov", ".m4v", ".webm")

    def _pooled_scene(self, visuals: list[str], dur: float,
                      VideoFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips,
                      opening: bool = False):
        """Fast-paced scene: split `dur` across the given visuals, cut
        back-to-back. Motion varies per cut so nothing feels like a slideshow:
        stills rotate zoom-in / zoom-out / pan-left / pan-right; video chunks
        get a micro punch-in, and every third one a subtle speed ramp."""
        _width, _height = self.size
        chunk = dur / len(visuals)
        subs = []
        for j, path in enumerate(visuals):
            subs.append(self._sub_visual(path, chunk, j, VideoFileClip, ImageClip,
                                         CompositeVideoClip, concatenate_videoclips,
                                         darken=(OPENING_DARKEN if (opening and j == 0)
                                                 else DEFAULT_DARKEN)))
        return concatenate_videoclips(subs, method="chain")

    def _timed_scene(self, cuts: list, dur: float,
                     VideoFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips,
                     opening: bool = False):
        """Phrase-synced scene: cuts = [(offset_seconds, visual_path)] with
        offsets aligned to the narration's phrase starts, so the picture changes
        exactly when the words change subject."""
        subs = []
        for j, (start, path) in enumerate(cuts):
            end = cuts[j + 1][0] if j + 1 < len(cuts) else dur
            chunk = max(0.4, end - start)
            subs.append(self._sub_visual(path, chunk, j, VideoFileClip, ImageClip,
                                         CompositeVideoClip, concatenate_videoclips,
                                         darken=(OPENING_DARKEN if (opening and j == 0)
                                                 else DEFAULT_DARKEN)))
        return concatenate_videoclips(subs, method="chain")

    def _sub_visual(self, path: str, chunk: float, j: int,
                    VideoFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips,
                    darken: float = DEFAULT_DARKEN):
        width, height = self.size
        if True:
            if path.lower().endswith(self._VIDEO_EXT):
                if j % 3 == 2:   # speed-ramped cut: 1.15x, same on-screen time
                    from moviepy import vfx
                    raw = self._video_scene(path, chunk * 1.15,
                                            VideoFileClip, concatenate_videoclips)
                    clip = raw.with_effects([vfx.MultiplySpeed(1.15)]).with_duration(chunk)
                else:            # micro punch-in keeps even real video alive
                    raw = self._video_scene(path, chunk, VideoFileClip, concatenate_videoclips)
                    punched = raw.resized(lambda t, d=chunk: 1.0 + 0.05 * (t / d)).with_position("center")
                    clip = CompositeVideoClip([punched], size=self.size).with_duration(chunk)
                return clip
            else:
                bg_path = self._prepare_background(path, None, darken=darken)
                base = ImageClip(bg_path).with_duration(chunk)
                mode = j % 4
                if mode == 0:    # zoom in
                    moving = base.resized(lambda t, d=chunk: 1.0 + 0.10 * (t / d)).with_position("center")
                elif mode == 1:  # zoom out
                    moving = base.resized(lambda t, d=chunk: 1.10 - 0.10 * (t / d)).with_position("center")
                else:            # pan left / right at a fixed 1.12 scale
                    moving = base.resized(1.12)
                    over_x = int(width * 0.12)
                    over_y = int(height * 0.12) // 2
                    if mode == 2:
                        moving = moving.with_position(
                            lambda t, d=chunk, ox=over_x, oy=over_y: (-ox * (t / d), -oy))
                    else:
                        moving = moving.with_position(
                            lambda t, d=chunk, ox=over_x, oy=over_y: (-ox * (1 - t / d), -oy))
                return CompositeVideoClip([moving], size=self.size).with_duration(chunk)

    def _video_scene(self, path: str, dur: float, VideoFileClip, concatenate_videoclips):
        """A stock/own clip, silenced, and looped or trimmed to exactly `dur`
        (so it matches its section's voice). Portrait/vertical clips are
        cover-cropped to the frame; LANDSCAPE clips (16:9 phone footage) are
        blur-padded — blurred cover-fill behind the full clip centered — so the
        whole shot is visible instead of one huge middle band."""
        width, height = self.size
        clip = VideoFileClip(path).without_audio()
        if clip.w / clip.h > width / height:          # landscape source
            bg = clip.resized(max(width / clip.w, height / clip.h))
            bg = bg.cropped(width=width, height=height,
                            x_center=bg.w / 2, y_center=bg.h / 2)
            # cheap gaussian-ish blur: heavy downscale + upscale (moviepy has
            # no blur fx) — hides detail so the full clip pops on top
            bg = bg.resized(1 / 24).resized((width, height))
            fg = clip.resized(min(width / clip.w, height / clip.h))
            from moviepy import CompositeVideoClip
            clip = CompositeVideoClip(
                [bg, fg.with_position("center")], size=self.size)
        else:
            scale = max(width / clip.w, height / clip.h)
            clip = clip.resized(scale)
            clip = clip.cropped(width=width, height=height,
                                x_center=clip.w / 2, y_center=clip.h / 2)
        if clip.duration >= dur:
            return clip.subclipped(0, dur)
        reps = int(dur / clip.duration) + 1
        return concatenate_videoclips([clip] * reps).subclipped(0, dur)

    def _render_ffmpeg_full(self, sections, out_path, music_path, fps, loop_close,
                            theme=THEME_LUXE):
        """Fully ffmpeg path (increment 2): base scene AND overlays composited by
        ffmpeg, so moviepy never touches the full timeline. Overlays are baked
        from the identical PIL generators, so the look is unchanged. Raises on
        any failure so render_sections can fall back."""
        import subprocess
        import tempfile

        from moviepy import AudioFileClip

        from carshorts.adapters import ffoverlay
        from carshorts.adapters.ffrenderer import global_cuts_from_sections, render_base_from_cuts

        durations = [AudioFileClip(s.audio_path).duration for s in sections]
        gcuts, total = global_cuts_from_sections(sections, durations)
        if not gcuts:
            raise RuntimeError("no cuts to render")
        tdir = tempfile.mkdtemp(prefix="fffull_")

        # loop-close: append a 0.5s flash of the opener, kept undarkened so the
        # seam back to frame 1 is clean
        no_darken = {0}
        video_total = total
        if loop_close:
            no_darken.add(len(gcuts))
            gcuts = [*list(gcuts), (total, gcuts[0][1])]
            video_total = total + 0.5

        base_path = f"{tdir}/base.mp4"
        render_base_from_cuts(gcuts, video_total, base_path, fps=fps,
                              size=self.size, no_darken=frozenset(no_darken))

        layers = ffoverlay.build_layers(sections, durations, self.size, fps, tdir, theme)

        # voice is concatenated by ffmpeg from the section audio files (moviepy's
        # audio writer was throwing broken-pipe on Windows)
        cmd = ffoverlay.build_overlay_command(
            base_path, layers, [s.audio_path for s in sections], out_path,
            music_path=music_path, total=video_total, fps=fps)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError("ffmpeg overlay composite failed:\n"
                               + proc.stderr[-1500:])
        # section-boundary times, for the downstream audiopolish whooshes
        self.last_boundaries = [sum(durations[:i]) for i in range(1, len(durations))]
        print(f"     [fffull] ffmpeg base + {len(layers)} overlay layers "
              f"-> {out_path}")
        return out_path

    def render_sections(self, sections: list[Section], out_path: str,
                        music_path: str | None = None, ken_burns: bool = True,
                        draw_captions: bool = True, fps: int = 24,
                        loop_close: bool = True, overlay_theme: str = "luxe") -> str:
        """Multi-scene render: each Section becomes a clip whose length equals its
        own audio — so visuals stay in sync with the spoken script, section by
        section. Still photos get motion (alternating slow zoom-in / zoom-out) so
        they feel like video; captions are optional; optional music is mixed low
        under the voice."""
        # --- FAST PATH (hybrid): let ffmpeg assemble the base scene (cuts + Ken
        # Burns) in C — ~20x faster than moviepy's per-frame Python compositing —
        # then run the IDENTICAL overlay/audio/music code below on top of it, so
        # the tuned overlay look is byte-for-byte unchanged. Opt-in, and only
        # when every section is phrase-synced (all have timed_cuts); anything
        # else falls through to the moviepy path untouched. Any failure falls
        # back too, so a render never dies on the fast path.
        import os as _os

        from moviepy import (
            AudioFileClip,
            CompositeVideoClip,
            ImageClip,
            ImageSequenceClip,
            VideoFileClip,
            concatenate_audioclips,
            concatenate_videoclips,
        )
        theme = get_theme(overlay_theme)
        # Fast path ON by default; set CARSHORTS_FFBASE=0 to force pure moviepy.
        # Requires ffmpeg on PATH (as QA/audiopolish already do); any failure
        # falls back through hybrid to moviepy, so default-on is safe.
        use_ffbase = (_os.environ.get("CARSHORTS_FFBASE", "1") != "0"
                      and bool(sections) and all(s.timed_cuts for s in sections))
        # Increment 2: try the FULLY-ffmpeg path (base + overlays in ffmpeg).
        # On any failure fall through to the hybrid (ffmpeg base + moviepy
        # overlays), and from there to pure moviepy — three tiers, each with
        # identical overlays, fastest first.
        if use_ffbase and _os.environ.get("CARSHORTS_FFOVERLAY", "1") == "1":
            try:
                return self._render_ffmpeg_full(sections, out_path, music_path,
                                                 fps, loop_close, theme)
            except Exception as exc:  # noqa: BLE001 — any fast-path failure falls back
                print(f"     [fffull] failed ({str(exc)[:140]}); "
                      f"falling back to hybrid/moviepy")
        video = None
        if use_ffbase:
            try:
                from carshorts.adapters.ffrenderer import (
                    global_cuts_from_sections,
                    render_base_from_cuts,
                )
                durations = [AudioFileClip(s.audio_path).duration for s in sections]
                gcuts, total = global_cuts_from_sections(sections, durations)
                base_path = tempfile.mktemp(suffix="_ffbase.mp4")
                render_base_from_cuts(gcuts, total, base_path,
                                      fps=fps, size=self.size)
                voice = concatenate_audioclips(
                    [AudioFileClip(s.audio_path) for s in sections])
                video = VideoFileClip(base_path).with_audio(voice)
                print(f"     [ffbase] base scene via ffmpeg ({len(gcuts)} cuts, "
                      f"{total:.1f}s)")
            except Exception as exc:  # noqa: BLE001 — fall back to the moviepy base
                print(f"     [ffbase] failed ({str(exc)[:110]}); moviepy base")
                video = None

        clips = []
        for idx, section in enumerate(sections if video is None else []):
            audio = AudioFileClip(section.audio_path)
            dur = audio.duration
            if section.timed_cuts:
                scene = self._timed_scene(section.timed_cuts, dur,
                                          VideoFileClip, ImageClip,
                                          CompositeVideoClip, concatenate_videoclips,
                                          opening=(idx == 0))
            elif section.background_pool:
                scene = self._pooled_scene(section.background_pool, dur,
                                           VideoFileClip, ImageClip,
                                           CompositeVideoClip, concatenate_videoclips,
                                           opening=(idx == 0))
            elif section.background_video:
                scene = self._video_scene(section.background_video, dur,
                                          VideoFileClip, concatenate_videoclips)
            else:
                caption = section.caption if draw_captions else None
                bg_path = self._prepare_background(section.background_image, caption)
                base = ImageClip(bg_path).with_duration(dur)
                if ken_burns and section.background_image:
                    # Alternate zoom-in / zoom-out per scene for variety. Clip
                    # always fills the frame (scale >= 1), so motion never shows
                    # an edge; CompositeVideoClip crops back to size.
                    if idx % 2 == 0:
                        motion = lambda t, d=dur: 1.0 + 0.09 * (t / d)
                    else:
                        motion = lambda t, d=dur: 1.09 - 0.09 * (t / d)
                    zoom = base.resized(motion).with_position("center")
                    scene = CompositeVideoClip([zoom], size=self.size).with_duration(dur)
                else:
                    scene = base
            clips.append(scene.with_audio(audio))

        if video is None:                       # moviepy base path
            video = concatenate_videoclips(clips, method="chain")

        # --- On-screen overlays: keyword pop-ins + staggered callout lines.
        overlays = []
        _width, height = self.size
        tdir = tempfile.mkdtemp(prefix="ovl_")
        cursor = 0.0
        boundaries: list[float] = []
        for k, section in enumerate(sections):
            dur = AudioFileClip(section.audio_path).duration
            if k:
                boundaries.append(cursor)
            for pi, pop in enumerate(section.word_pops):
                pop_start, pop_dur, pop_text = pop[0], pop[1], pop[2]
                kind = pop[3] if len(pop) > 3 else (
                    "number" if any(c.isdigit() for c in pop_text) else "word")
                label = pop[4] if len(pop) > 4 else ""
                start_abs = cursor + pop_start
                # reactions straddle the section cut on purpose (silence beat)
                show_dur = (pop_dur if kind == "reaction"
                            else min(pop_dur, dur - pop_start))
                if kind == "card":
                    # big-number payoff card: count-up to the exact figure
                    frames = _countup_frames(pop_text, label, tdir, f"card_{k}_{pi}", theme=theme)
                    countup = (ImageSequenceClip(frames, fps=24)
                               .with_start(start_abs)
                               .with_position(("center", int(height * 0.30))))
                    hold = (ImageClip(frames[-1], transparent=True)
                            .with_start(start_abs + countup.duration)
                            .with_duration(max(0.7, show_dur - countup.duration))
                            .with_position(("center", int(height * 0.30))))
                    overlays.extend([countup, hold])
                elif kind == "subscribe":
                    # premium subscribe micro-interaction (pill -> tap -> SUBSCRIBED),
                    # lower-centre CTA zone; animated sequence then holds.
                    frames = _subscribe_frames(tdir, f"sub_{k}_{pi}", theme=theme)
                    y_sub = int(height * 0.54)
                    seq = (ImageSequenceClip(frames, fps=24)
                           .with_start(start_abs)
                           .with_position(("center", y_sub)))
                    hold = (ImageClip(frames[-1], transparent=True)
                            .with_start(start_abs + seq.duration)
                            .with_duration(max(0.1, show_dur - seq.duration))
                            .with_position(("center", y_sub)))
                    overlays.extend([seq, hold])
                elif kind == "reaction":
                    # the editor's dry voice, upper third, slams into the
                    # silence beat right after the punchline lands
                    png = _overlay_png(pop_text.upper(), 110, f"{tdir}/rx_{k}_{pi}.png",
                                       theme=theme, kind="reaction", fit_one_line=True)
                    clip = (ImageClip(png, transparent=True)
                            .with_start(start_abs)
                            .with_duration(show_dur)
                            .resized(_slam_scale)
                            .with_position(("center", int(height * 0.30))))
                    overlays.append(clip)
                elif kind == "lss":
                    # like/share/subscribe icon strip — procedural PIL icons
                    # (thumbs-up, share arrow, bell), drawn progressively per
                    # pop (label = how many are active). Slams in like a
                    # reaction, own slot at y=0.30, holds through the beat.
                    png = _lss_strip_png(f"{tdir}/lss_{k}_{pi}.png",
                                         active=int(label) if label.isdigit() else 3,
                                         theme=theme)
                    clip = (ImageClip(png, transparent=True)
                            .with_start(start_abs)
                            .with_duration(show_dur)
                            .resized(_slam_scale)
                            .with_position(("center", int(height * 0.30))))
                    overlays.append(clip)
                else:
                    png = _overlay_png(pop_text.upper(), 96, f"{tdir}/pop_{k}_{pi}.png",
                                       theme=theme, kind=kind)
                    clip = (ImageClip(png, transparent=True)
                            .with_start(start_abs)
                            .with_duration(show_dur)
                            .resized(_settle_scale)
                            .with_position(("center", int(height * 0.64))))
                    overlays.append(clip)
                    if kind == "number":
                        # accent marker-wipe under the figure (0.35s ease-out)
                        from PIL import Image as _PILImage
                        png_w = _PILImage.open(png).width
                        bar_w = min(png_w - 90, max(140, png_w // 3))
                        bar_y = int(height * 0.64) + _PILImage.open(png).height - 8
                        frames = _wipe_bar_frames(bar_w, tdir, f"bar_{k}_{pi}", color=theme.accent)
                        wipe = (ImageSequenceClip(frames, fps=34)
                                .with_start(start_abs)
                                .with_position(("center", bar_y)))
                        bar_hold = (ImageClip(frames[-1], transparent=True)
                                    .with_start(start_abs + wipe.duration)
                                    .with_duration(max(0.1, show_dur - wipe.duration))
                                    .with_position(("center", bar_y)))
                        overlays.extend([wipe, bar_hold])
            if section.word_pops:
                cursor += dur
                continue                 # pops replace all legacy text below
            if section.keyword and not section.timed_callouts:
                # a keyword AND a callout card together crowd the frame — the
                # card wins (owner feedback: on-screen text felt mismatched)
                png = _overlay_png(section.keyword.upper(), 88, f"{tdir}/kw_{k}.png",
                                   theme=theme,
                                   kind=("number" if any(c.isdigit() for c in section.keyword)
                                         else "word"))
                if section.keyword_span:   # speech-timed: exactly while its phrase runs
                    kw_start, kw_dur = section.keyword_span
                else:
                    kw_start, kw_dur = 0.12, min(2.4, dur * 0.85)
                clip = (ImageClip(png, transparent=True)
                        .with_start(cursor + kw_start).with_duration(min(kw_dur, dur - kw_start))
                        .resized(lambda t: 1.12 - 0.12 * min(t, 0.18) / 0.18)
                        .with_position(("center", int(height * 0.66))))
                overlays.append(clip)
            if section.timed_callouts:     # speech-timed lines: appear with their words
                for li, (st, en, line) in enumerate(section.timed_callouts[:4]):
                    png = _overlay_png(line, 54, f"{tdir}/co_{k}_{li}.png",
                                       theme=theme, kind="word")
                    st = min(st, dur - 0.6)
                    clip = (ImageClip(png, transparent=True)
                            .with_start(cursor + st).with_duration(max(0.8, min(en, dur) - st))
                            .with_position(("center", int(height * (0.55 + 0.08 * li)))))
                    overlays.append(clip)
            else:
                for li, line in enumerate(section.callout_lines[:5]):
                    png = _overlay_png(line, 58, f"{tdir}/co_{k}_{li}.png",
                                       theme=theme, kind="word")
                    start = cursor + 0.9 + li * min(1.1, max(0.6, (dur - 1.8) / max(1, len(section.callout_lines))))
                    if start >= cursor + dur - 0.6:
                        break
                    clip = (ImageClip(png, transparent=True)
                            .with_start(start).with_duration(max(0.8, cursor + dur - start))
                            .with_position(("center", int(height * (0.52 + 0.085 * li)))))
                    overlays.append(clip)
            cursor += dur
        # Loop-close: flash the opening visual for half a second at the very end
        # so the short loops seamlessly back into its own first frame (rewatches).
        first_pool = ([c[1] for c in sections[0].timed_cuts] or sections[0].background_pool) if sections else []
        if loop_close and first_pool:
            flash = first_pool[0]
            if flash.lower().endswith(self._VIDEO_EXT):
                tail = self._video_scene(flash, 0.5, VideoFileClip, concatenate_videoclips)
            else:
                # same treatment as the opener it loops back to, or the seam shows
                tail = ImageClip(self._prepare_background(
                    flash, None, darken=OPENING_DARKEN)).with_duration(0.5)
            video = concatenate_videoclips([video, tail], method="chain")
        if overlays:
            video = CompositeVideoClip([video, *overlays], size=self.size).with_duration(video.duration)

        video = self._add_music(video, music_path)
        # ultrafast + all cores: for the polished path this is a throwaway pass
        # that audiopolish re-encodes at crf19, so quality is preserved; for the
        # --no-polish path it keeps drafts fast. moviepy is the bottleneck on
        # CPU-only boxes, so hand x264 every core and the cheapest preset.
        video.write_videofile(out_path, fps=fps, codec="libx264",
                              audio_codec="aac", bitrate="10M", logger=None,
                              preset="ultrafast", threads=os.cpu_count() or 4)
        self.last_boundaries = boundaries
        return out_path

    def _add_music(self, video, music_path: str | None):
        """Mix a background track low under the voice. Trims music to video length."""
        if not music_path:
            return video
        from moviepy import AudioFileClip, CompositeAudioClip

        music = AudioFileClip(music_path)
        if music.duration > video.duration:
            music = music.subclipped(0, video.duration)
        music = music.with_volume_scaled(0.12)  # quiet bed under the voice
        return video.with_audio(CompositeAudioClip([video.audio, music]))
