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

import tempfile
from abc import ABC, abstractmethod

VERTICAL = (1080, 1920)

# Common macOS/Linux font locations, tried in order. Falls back to Pillow's
# built-in bitmap font if none resolve (ugly but never crashes).
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
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
    """One scene of the video: an audio clip and the caption shown while it plays.
    background_image is optional per-section (the footage station fills this later)."""

    def __init__(self, audio_path: str, caption: str, background_image: str | None = None):
        self.audio_path = audio_path
        self.caption = caption
        self.background_image = background_image


class VideoRenderer(ABC):
    @abstractmethod
    def render(self, audio_path: str, out_path: str,
               background_image: str | None = None, title: str | None = None) -> str:
        """Produce a vertical MP4 at out_path from audio (+ optional visuals)."""


class MoviePyRenderer(VideoRenderer):
    def __init__(self, size: tuple[int, int] = VERTICAL, bg_color: tuple[int, int, int] = (18, 18, 24)):
        self.size = size
        self.bg_color = bg_color

    def _prepare_background(self, background_image: str | None, text: str | None) -> str:
        from PIL import Image, ImageDraw

        width, height = self.size
        if background_image:
            img = _cover_crop(Image.open(background_image).convert("RGB"), width, height)
            # Darken so white captions stay readable over any photo.
            overlay = Image.new("RGB", (width, height), (0, 0, 0))
            img = Image.blend(img, overlay, 0.35)
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

    def render_sections(self, sections: list[Section], out_path: str,
                        music_path: str | None = None, ken_burns: bool = True) -> str:
        """Multi-scene render: each Section becomes a clip whose length equals its
        own audio, with its caption on screen — so visuals/captions stay in sync
        with the spoken script, section by section. Still photos get a slow zoom
        (Ken Burns) so they feel like video; optional background music is mixed
        low under the voice."""
        from moviepy import (AudioFileClip, CompositeVideoClip, ImageClip,
                             concatenate_videoclips)

        clips = []
        for section in sections:
            audio = AudioFileClip(section.audio_path)
            dur = audio.duration
            bg_path = self._prepare_background(section.background_image, section.caption)
            base = ImageClip(bg_path).with_duration(dur)
            if ken_burns and section.background_image:
                # Slow 6% zoom-in. Clip starts filling the frame, so zooming in
                # never exposes an edge; CompositeVideoClip crops back to size.
                zoom = base.resized(lambda t, d=dur: 1.0 + 0.06 * (t / d)).with_position("center")
                scene = CompositeVideoClip([zoom], size=self.size).with_duration(dur)
            else:
                scene = base
            clips.append(scene.with_audio(audio))

        video = concatenate_videoclips(clips, method="chain")
        video = self._add_music(video, music_path)
        video.write_videofile(out_path, fps=24, codec="libx264",
                              audio_codec="aac", logger=None)
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
