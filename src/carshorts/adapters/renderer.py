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
from pathlib import Path

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
    str(Path(__file__).resolve().parents[3] / "assets" / "fonts" / "Montserrat-Black.ttf"),
    "assets/fonts/Montserrat-Black.ttf",                     # cwd-relative fallback
    r"C:\Windows\Fonts\Montserrat-Black.ttf",               # Windows: if user-installed
    "/System/Library/Fonts/SFCompactRounded.ttf",
    "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    r"C:\Windows\Fonts\ariblk.ttf",                          # Windows: Arial Black (heavy)
    r"C:\Windows\Fonts\seguisb.ttf",                         # Windows: Segoe UI Semibold
] + _FONT_CANDIDATES

# Overlay palette (research-derived): white base + ONE desaturated-cyan accent
# on numbers only. Yellow is banned — it pattern-matches to clip-farm content.
TEXT_WHITE = (255, 255, 255, 255)
ACCENT_CYAN = (126, 229, 227, 255)      # #7EE5E3 — the channel accent
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


def _overlay_png(text: str, font_size: int, fill, out_path: str,
                 pill: bool = False, max_width: int = 780,
                 accent_bar: bool = False, accent_digits: bool = False,
                 fit_one_line: bool = False) -> str:
    """Render text to a transparent PNG. Research-derived treatment: heavy
    face, ~9% black stroke (load-bearing over busy footage), soft blurred
    shadow, and — for number pops — cyan digits with white unit labels so the
    single accent color stays reserved for the payload figure.
    max_width=780 keeps centered text inside the Shorts safe box
    (x∈[60,930] on 1080w, right 150px reserved for the engagement rail)."""
    from PIL import Image, ImageDraw, ImageFilter

    font = _load_heavy_font(font_size)   # one face everywhere = coherent look
    tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    if fit_one_line:
        # shrink until the whole text sits on ONE line inside the safe box
        # (reaction slams scale 1.3x on entry — leave headroom for that too)
        while font_size > 44 and tmp.textlength(text, font=font) > 560:
            font_size -= 6
            font = _load_heavy_font(font_size)
    lines = _wrap(tmp, text, font, max_width)
    ascent, descent = font.getmetrics()
    line_h = ascent + descent + 8
    stroke = max(3, round(font_size * 0.09))
    width = max(int(tmp.textlength(l, font=font)) for l in lines) + 80 + 2 * stroke
    height = line_h * len(lines) + 48 + 2 * stroke
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if pill:
        draw.rounded_rectangle([0, 0, width - 1, height - 1], radius=26,
                               fill=(10, 10, 14, 200))

    def draw_line(target, line, x, y, with_color):
        if with_color and accent_digits:
            # cyan on the figure, white on the unit — sequential segments
            cx = x
            for token in line.split(" "):
                color = ACCENT_CYAN if _numberish(token) else TEXT_WHITE
                target.text((cx, y), token, font=font, fill=color,
                            stroke_width=stroke, stroke_fill=STROKE_BLACK)
                cx += target.textlength(token + " ", font=font)
        else:
            color = fill if with_color else (0, 0, 0, 255)
            target.text((x, y), line, font=font, fill=color,
                        stroke_width=stroke if with_color else 0,
                        stroke_fill=STROKE_BLACK)

    # soft blurred shadow on its own layer (research: offset +3/+5, blur 8)
    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    y = 24 + stroke
    for line in lines:
        x = (width - tmp.textlength(line, font=font)) // 2
        draw_line(sdraw, line, x + 3, y + 5, with_color=False)
        y += line_h
    shadow = shadow.filter(ImageFilter.GaussianBlur(8))
    shadow.putalpha(shadow.getchannel("A").point(lambda a: int(a * 0.55)))
    img.alpha_composite(shadow)

    y = 24 + stroke
    for line in lines:
        x = (width - tmp.textlength(line, font=font)) // 2
        draw_line(draw, line, x, y, with_color=True)
        y += line_h
    if accent_bar:   # cyan signature bar under the figure
        bar_w = min(width - 100, max(140, width // 3))
        bx = (width - bar_w) // 2
        draw.rounded_rectangle([bx, y + 4, bx + bar_w, y + 14], radius=5,
                               fill=ACCENT_CYAN)
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


def _wipe_bar_frames(full_width: int, tdir: str, tag: str) -> list[str]:
    """12 frames of a cyan marker-bar wiping left->right (ease-out, 0.35s)."""
    from PIL import Image, ImageDraw

    frames = []
    for f in range(12):
        progress = 1 - (1 - (f + 1) / 12) ** 2
        w = max(3, int(full_width * progress))
        img = Image.new("RGBA", (full_width, 14), (0, 0, 0, 0))
        ImageDraw.Draw(img).rounded_rectangle([0, 2, w, 12], radius=5,
                                              fill=ACCENT_CYAN)
        path = f"{tdir}/{tag}_f{f}.png"
        img.save(path)
        frames.append(path)
    return frames


def _lss_strip_png(out_path: str, icon_size: int = 116,
                   strip_width: int = 640) -> str:
    """Like/Share/Subscribe strip — three filled white icons with a dilated
    black outline (same visual language as the text stroke) + small labels.
    Drawn procedurally with Pillow; no emoji fonts, no downloads."""
    from PIL import Image, ImageDraw, ImageFilter

    stroke = max(4, round(icon_size * 0.08))
    label_font = _load_heavy_font(30)
    pad = 40
    label_h = 52
    canvas_w = strip_width + 2 * pad
    canvas_h = icon_size + label_h + 2 * pad
    cell = strip_width // 3
    centers = [pad + cell // 2 + i * cell for i in range(3)]
    cy = pad + icon_size // 2

    # white silhouettes first — outline and shadow derive from their alpha
    white = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(white)
    W = (255, 255, 255, 255)

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

    for draw_icon, cx in zip((thumb, share, bell), centers):
        draw_icon(cx)
    for label, cx in zip(("LIKE", "SHARE", "SUBSCRIBE"), centers):
        lw = d.textlength(label, font=label_font)
        d.text((cx - lw / 2, pad + icon_size + 14), label,
               font=label_font, fill=W)

    # outline: dilate the white alpha, fill black, sit it underneath
    alpha = white.getchannel("A")
    outline_mask = alpha.filter(ImageFilter.MaxFilter(stroke * 2 + 1))
    outline = Image.new("RGBA", white.size, (0, 0, 0, 0))
    outline.paste((0, 0, 0, 255), mask=outline_mask)
    # soft shadow from the outline's silhouette
    shadow = Image.new("RGBA", white.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 140), mask=outline_mask)
    shadow = shadow.filter(ImageFilter.GaussianBlur(8))

    img = Image.new("RGBA", white.size, (0, 0, 0, 0))
    img.alpha_composite(shadow, (3, 5))
    img.alpha_composite(outline)
    img.alpha_composite(white)
    img.save(out_path)
    return out_path


def _countup_frames(final_text: str, label: str, tdir: str, tag: str,
                    n_frames: int = 34) -> list[str]:
    """Big-number card count-up: ease-out toward the exact final value, digits
    in accent cyan at ~300px, static white label below. One per short, for THE
    payoff stat only."""
    import re as _re

    from PIL import Image, ImageDraw

    match = _re.search(r"\d[\d,]*(?:\.\d+)?", final_text)
    final_value = float(match.group(0).replace(",", "")) if match else 0.0
    prefix = final_text[:match.start()] if match else ""
    suffix = final_text[match.end():] if match else final_text
    decimals = len(match.group(0).split(".")[1]) if match and "." in match.group(0) else 0
    # autofit: THE number should be huge, but never clipped — shrink until the
    # final text (the widest frame) sits inside the Shorts safe box (<=860px)
    from PIL import Image as _Img, ImageDraw as _Draw
    probe = _Draw.Draw(_Img.new("RGBA", (8, 8)))
    digit_size = 300
    final_probe = f"{prefix}{final_value:,.{decimals}f}{suffix}".upper()
    while digit_size > 90 and probe.textlength(
            final_probe, font=_load_heavy_font(digit_size)) > 860:
        digit_size -= 10
    digit_font = _load_heavy_font(digit_size)
    label_font = _load_heavy_font(64)
    stroke = round(digit_size * 0.09)
    width, height = 1080, digit_size + 320
    frames = []
    for f in range(n_frames):
        progress = 1 - (1 - (f + 1) / n_frames) ** 3     # ease-out, slow landing
        value = final_value * progress if f < n_frames - 1 else final_value
        text = f"{prefix}{value:,.{decimals}f}{suffix}".upper()
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        x = (width - d.textlength(text, font=digit_font)) // 2
        d.text((x, 60), text, font=digit_font, fill=ACCENT_CYAN,
               stroke_width=stroke, stroke_fill=STROKE_BLACK)
        if label:
            lx = (width - d.textlength(label.upper(), font=label_font)) // 2
            d.text((lx, digit_size + 180), label.upper(), font=label_font,
                   fill=TEXT_WHITE, stroke_width=6, stroke_fill=STROKE_BLACK)
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
        width, height = self.size
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
        """A stock clip, cover-cropped to the vertical frame, silenced, and
        looped or trimmed to exactly `dur` (so it matches its section's voice)."""
        width, height = self.size
        clip = VideoFileClip(path).without_audio()
        scale = max(width / clip.w, height / clip.h)
        clip = clip.resized(scale)
        clip = clip.cropped(width=width, height=height,
                            x_center=clip.w / 2, y_center=clip.h / 2)
        if clip.duration >= dur:
            return clip.subclipped(0, dur)
        reps = int(dur / clip.duration) + 1
        return concatenate_videoclips([clip] * reps).subclipped(0, dur)

    def _render_ffmpeg_full(self, sections, out_path, music_path, fps, loop_close):
        """Fully ffmpeg path (increment 2): base scene AND overlays composited by
        ffmpeg, so moviepy never touches the full timeline. Overlays are baked
        from the identical PIL generators, so the look is unchanged. Raises on
        any failure so render_sections can fall back."""
        import subprocess
        import tempfile

        from moviepy import AudioFileClip

        from . import ffoverlay
        from .ffrenderer import global_cuts_from_sections, render_base_from_cuts

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
            gcuts = list(gcuts) + [(total, gcuts[0][1])]
            video_total = total + 0.5

        base_path = f"{tdir}/base.mp4"
        render_base_from_cuts(gcuts, video_total, base_path, fps=fps,
                              size=self.size, no_darken=frozenset(no_darken))

        layers = ffoverlay.build_layers(sections, durations, self.size, fps, tdir)

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
                        loop_close: bool = True) -> str:
        """Multi-scene render: each Section becomes a clip whose length equals its
        own audio — so visuals stay in sync with the spoken script, section by
        section. Still photos get motion (alternating slow zoom-in / zoom-out) so
        they feel like video; captions are optional; optional music is mixed low
        under the voice."""
        from moviepy import (AudioFileClip, CompositeVideoClip, ImageClip,
                             ImageSequenceClip, VideoFileClip,
                             concatenate_audioclips, concatenate_videoclips)

        # --- FAST PATH (hybrid): let ffmpeg assemble the base scene (cuts + Ken
        # Burns) in C — ~20x faster than moviepy's per-frame Python compositing —
        # then run the IDENTICAL overlay/audio/music code below on top of it, so
        # the tuned overlay look is byte-for-byte unchanged. Opt-in, and only
        # when every section is phrase-synced (all have timed_cuts); anything
        # else falls through to the moviepy path untouched. Any failure falls
        # back too, so a render never dies on the fast path.
        import os as _os
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
                                                 fps, loop_close)
            except Exception as exc:  # noqa: BLE001
                print(f"     [fffull] failed ({str(exc)[:140]}); "
                      f"falling back to hybrid/moviepy")
        video = None
        if use_ffbase:
            try:
                from .ffrenderer import (global_cuts_from_sections,
                                         render_base_from_cuts)
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
            except Exception as exc:  # noqa: BLE001 — fall back to moviepy
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
        width, height = self.size
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
                    frames = _countup_frames(pop_text, label, tdir, f"card_{k}_{pi}")
                    countup = (ImageSequenceClip(frames, fps=24)
                               .with_start(start_abs)
                               .with_position(("center", int(height * 0.30))))
                    hold = (ImageClip(frames[-1], transparent=True)
                            .with_start(start_abs + countup.duration)
                            .with_duration(max(0.7, show_dur - countup.duration))
                            .with_position(("center", int(height * 0.30))))
                    overlays.extend([countup, hold])
                elif kind == "reaction":
                    # the editor's dry voice, upper third, slams into the
                    # silence beat right after the punchline lands
                    png = _overlay_png(pop_text.upper(), 110, TEXT_WHITE,
                                       f"{tdir}/rx_{k}_{pi}.png", fit_one_line=True)
                    clip = (ImageClip(png, transparent=True)
                            .with_start(start_abs)
                            .with_duration(show_dur)
                            .resized(_slam_scale)
                            .with_position(("center", int(height * 0.30))))
                    overlays.append(clip)
                elif kind == "lss":
                    # like/share/subscribe icon strip — three procedural PIL
                    # icons (thumbs-up, share arrow, bell). Slams in like a
                    # reaction, own slot at y=0.30, holds through the beat.
                    png = _lss_strip_png(f"{tdir}/lss_{k}_{pi}.png")
                    clip = (ImageClip(png, transparent=True)
                            .with_start(start_abs)
                            .with_duration(show_dur)
                            .resized(_slam_scale)
                            .with_position(("center", int(height * 0.30))))
                    overlays.append(clip)
                else:
                    png = _overlay_png(pop_text.upper(), 96, TEXT_WHITE,
                                       f"{tdir}/pop_{k}_{pi}.png",
                                       accent_digits=(kind == "number"))
                    clip = (ImageClip(png, transparent=True)
                            .with_start(start_abs)
                            .with_duration(show_dur)
                            .resized(_settle_scale)
                            .with_position(("center", int(height * 0.64))))
                    overlays.append(clip)
                    if kind == "number":
                        # cyan marker-wipe under the figure (0.35s ease-out)
                        from PIL import Image as _PILImage
                        png_w = _PILImage.open(png).width
                        bar_w = min(png_w - 90, max(140, png_w // 3))
                        bar_y = int(height * 0.64) + _PILImage.open(png).height - 8
                        frames = _wipe_bar_frames(bar_w, tdir, f"bar_{k}_{pi}")
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
                png = _overlay_png(section.keyword.upper(), 88,
                                   (255, 214, 10, 255) if any(c.isdigit() for c in section.keyword)
                                   else (245, 245, 245, 255),
                                   f"{tdir}/kw_{k}.png", accent_bar=True)
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
                    png = _overlay_png(line, 54, (245, 245, 245, 255),
                                       f"{tdir}/co_{k}_{li}.png", pill=True)
                    st = min(st, dur - 0.6)
                    clip = (ImageClip(png, transparent=True)
                            .with_start(cursor + st).with_duration(max(0.8, min(en, dur) - st))
                            .with_position(("center", int(height * (0.55 + 0.08 * li)))))
                    overlays.append(clip)
            else:
                for li, line in enumerate(section.callout_lines[:5]):
                    png = _overlay_png(line, 58, (245, 245, 245, 255),
                                       f"{tdir}/co_{k}_{li}.png", pill=True)
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
