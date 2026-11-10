"""Low-level Rendering: Sprites, Text, Hintergrund, FFmpeg-Writer.

Alles wird per Code gezeichnet -> keine fremden Assets, volle Nutzungsrechte,
keine Kosten pro Video.
"""
import math
import subprocess
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .. import brand

W, H, FPS = 1080, 1920, 30


# ---------------------------------------------------------------- Fonts/Text
@lru_cache(maxsize=64)
def font(path, size):
    return ImageFont.truetype(path, size)


@lru_cache(maxsize=512)
def text_sprite(text, size, color=brand.WHITE, path=None, stroke=None, max_width=980):
    """Rendert Text (mehrzeilig, zentriert) mit Kontur + Schatten als RGBA-Sprite."""
    path = path or brand.FONT_BLACK
    f = font(path, size)
    stroke = max(2, size // 12) if stroke is None else stroke
    # Zeilenumbruch
    words, lines, cur = text.split(), [], ""
    for w_ in words:
        test = (cur + " " + w_).strip()
        if f.getlength(test) + 2 * stroke <= max_width or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    asc, desc = f.getmetrics()
    lh = int((asc + desc) * 1.02)
    tw = int(max(f.getlength(l) for l in lines)) + 4 * stroke + 12
    th = lh * len(lines) + 4 * stroke + 12
    img = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    ds, d = ImageDraw.Draw(shadow), ImageDraw.Draw(img)
    for i, l in enumerate(lines):
        x = (tw - f.getlength(l)) / 2
        y = 2 * stroke + 6 + i * lh
        ds.text((x, y + size * 0.06), l, font=f, fill=(0, 0, 0, 170), stroke_width=stroke, stroke_fill=(0, 0, 0, 170))
        d.text((x, y), l, font=f, fill=tuple(color) + (255,) if len(color) == 3 else color,
               stroke_width=stroke, stroke_fill=(8, 8, 18, 255))
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(2, size // 20)))
    shadow.alpha_composite(img)
    return shadow


def paste(dst, src, x, y, anchor="center"):
    """Alpha-Composite mit Clipping (erlaubt Positionen außerhalb des Bildes)."""
    if anchor == "center":
        x, y = int(round(x - src.width / 2)), int(round(y - src.height / 2))
    else:
        x, y = int(round(x)), int(round(y))
    sx0, sy0 = max(0, -x), max(0, -y)
    sx1, sy1 = min(src.width, dst.width - x), min(src.height, dst.height - y)
    if sx1 <= sx0 or sy1 <= sy0:
        return
    dst.alpha_composite(src, dest=(x + sx0, y + sy0), source=(sx0, sy0, sx1, sy1))


def scaled(sprite, s):
    if abs(s - 1) < 0.01:
        return sprite
    w, h = max(1, int(sprite.width * s)), max(1, int(sprite.height * s))
    return sprite.resize((w, h), Image.BILINEAR)


def with_alpha(sprite, a):
    if a >= 0.999:
        return sprite
    s = sprite.copy()
    al = s.getchannel("A").point(lambda v: int(v * max(0.0, a)))
    s.putalpha(al)
    return s


# ---------------------------------------------------------------- Background
@lru_cache(maxsize=8)
def background(variant=0):
    y = np.linspace(0, 1, H)[:, None, None]
    top, bot = np.array(brand.BG_TOP, float), np.array(brand.BG_BOTTOM, float)
    if variant % 3 == 1:
        bot = np.array((8, 26, 40), float)
    elif variant % 3 == 2:
        bot = np.array((34, 12, 16), float)
    grad = top * (1 - y) + bot * y
    arr = np.broadcast_to(grad, (H, W, 3)).copy()
    # Vignette
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H / 2) / (H * 0.7)) ** 2)
    arr *= np.clip(1.15 - 0.45 * d, 0.55, 1.1)[..., None]
    rng = np.random.default_rng(7 + variant)
    arr += rng.normal(0, 2.0, arr.shape)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
    grid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g = ImageDraw.Draw(grid)
    for gx in range(0, W, 60):
        g.line([(gx, 0), (gx, H)], fill=brand.GRID, width=1)
    for gy in range(0, H, 60):
        g.line([(0, gy), (W, gy)], fill=brand.GRID, width=1)
    img.alpha_composite(grid)
    return img


# ---------------------------------------------------------------- Orb sprites
def _shade(color, r, ss):
    R = r * ss
    n = 2 * R + 4 * ss
    c = n / 2
    yy, xx = np.mgrid[0:n, 0:n].astype(float)
    dx, dy = (xx - c) / R, (yy - c) / R
    d = np.sqrt(dx * dx + dy * dy)
    alpha = np.clip((1 - d) * R + 0.5, 0, 1)
    z = np.sqrt(np.clip(1 - d * d, 0, 1))
    L = np.array([-0.45, -0.6, 0.66])
    L /= np.linalg.norm(L)
    lam = np.clip(dx * L[0] + dy * L[1] + z * L[2], 0, 1)
    base = np.array(color, float)
    col = base[None, None, :] * (0.42 + 0.7 * lam[..., None])
    spec = np.clip(lam, 0, 1) ** 28
    col += 255 * 0.65 * spec[..., None]
    rim = np.clip((d - 0.82) / 0.18, 0, 1) * (d <= 1)
    col = col * (1 - 0.35 * rim[..., None])
    rgba = np.dstack([np.clip(col, 0, 255), alpha * 255]).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def _eyes(img, r, ss, style, look, mood, base=(200, 200, 200)):
    d = ImageDraw.Draw(img)
    c = img.width / 2
    R = r * ss
    ex, ey, er = 0.36 * R, -0.12 * R, 0.25 * R
    if style == "wide":
        er *= 1.2
    lx, ly = look
    for side in (-1, 1):
        cx, cy = c + side * ex, c + ey
        if mood == "ko":
            k = er * 0.8
            d.line([(cx - k, cy - k), (cx + k, cy + k)], fill=(15, 15, 25, 255), width=int(0.09 * R))
            d.line([(cx - k, cy + k), (cx + k, cy - k)], fill=(15, 15, 25, 255), width=int(0.09 * R))
            continue
        if mood == "win":
            d.arc([cx - er, cy - er * 0.6, cx + er, cy + er * 1.2], 200, 340, fill=(15, 15, 25, 255), width=int(0.09 * R))
            continue
        d.ellipse([cx - er, cy - er * 1.1, cx + er, cy + er * 1.1], fill=(255, 255, 255, 255))
        pr = er * 0.52
        px, py = cx + lx * er * 0.42, cy + ly * er * 0.5
        d.ellipse([px - pr, py - pr, px + pr, py + pr], fill=(14, 14, 24, 255))
        d.ellipse([px - pr * 0.35 - pr * 0.2, py - pr * 0.55, px - pr * 0.2 + pr * 0.15, py - pr * 0.05], fill=(255, 255, 255, 230))
        bw = int(0.085 * R)
        top = cy - er * 1.35
        if style == "angry":
            d.line([(cx - side * er * 1.1, top - er * 0.35), (cx + side * er * 0.9, top + er * 0.25)], fill=(15, 15, 25, 255), width=bw)
        elif style == "sad":
            d.line([(cx - side * er * 1.0, top + er * 0.2), (cx + side * er * 0.9, top - er * 0.3)], fill=(15, 15, 25, 255), width=bw)
        elif style == "sly":
            lid = tuple(int(v * 0.85) for v in base) + (255,)
            d.chord([cx - er * 1.08, cy - er * 1.18, cx + er * 1.08, cy + er * 1.02], 180, 360, fill=lid)
            d.line([(cx - er * 1.05, cy - er * 0.08), (cx + er * 1.05, cy - er * 0.08)], fill=(15, 15, 25, 255), width=bw)
        elif style == "smug" and side == 1:
            d.line([(cx - er, top - er * 0.1), (cx + er, top - er * 0.45)], fill=(15, 15, 25, 255), width=bw)
    if mood == "win":
        d.chord([c - R * 0.3, c + R * 0.05, c + R * 0.3, c + R * 0.5], 0, 180, fill=(20, 15, 25, 255))


@lru_cache(maxsize=4096)
def orb_sprite(name, r, look_idx=-1, mood="normal"):
    """Kugel-Charakter mit Schattierung + Augen. look_idx: 0..7 Richtung, -1 = Mitte."""
    ss = 3
    info = brand.ORBS[name]
    img = _shade(info["color"], r, ss)
    look = (0.0, 0.0) if look_idx < 0 else (math.cos(look_idx * math.pi / 4), math.sin(look_idx * math.pi / 4))
    if r >= 14:
        _eyes(img, r, ss, info["eyes"], look, mood, info["color"])
    return img.resize((img.width // ss, img.height // ss), Image.LANCZOS)


def look_index(vx, vy):
    if vx * vx + vy * vy < 400:
        return -1
    return int(round(math.atan2(vy, vx) / (math.pi / 4))) % 8


@lru_cache(maxsize=512)
def glow_sprite(color, r, strength=0.55):
    R = int(r * 2.4)
    n = 2 * R
    yy, xx = np.mgrid[0:n, 0:n].astype(float)
    d = np.sqrt((xx - R) ** 2 + (yy - R) ** 2) / R
    a = np.clip(1 - d, 0, 1) ** 2.2 * 255 * strength
    rgba = np.dstack([np.full((n, n), color[0]), np.full((n, n), color[1]), np.full((n, n), color[2]), a]).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


@lru_cache(maxsize=1024)
def dot_sprite(color, r, alpha):
    ss = 3
    n = (2 * r + 2) * ss
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse([ss, ss, n - ss, n - ss], fill=tuple(color) + (int(alpha),))
    return img.resize((n // ss, n // ss), Image.LANCZOS)


@lru_cache(maxsize=16)
def ring_sprite(radius, thickness, gap, color=(240, 242, 255)):
    """Ring mit Lücke (gap in Radiant, zentriert bei Winkel 0 = rechts)."""
    ss = 2
    R = radius + thickness + 30
    n = 2 * R * ss
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    g2 = math.degrees(gap / 2)
    box = [(R - radius - thickness / 2) * ss, (R - radius - thickness / 2) * ss,
           (R + radius + thickness / 2) * ss, (R + radius + thickness / 2) * ss]
    d.arc(box, g2, 360 - g2, fill=tuple(color) + (255,), width=int(thickness * ss))
    img = img.resize((n // ss, n // ss), Image.LANCZOS)
    glow = img.filter(ImageFilter.GaussianBlur(14))
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    a = glow.getchannel("A").point(lambda v: int(v * 0.9))
    glow.putalpha(a)
    tint = Image.new("RGBA", img.size, brand.ACCENT + (0,))
    tint.putalpha(a)
    out.alpha_composite(tint)
    out.alpha_composite(img)
    return out


# ---------------------------------------------------------------- Writer
class VideoWriter:
    def __init__(self, path, fps=FPS, crf=20):
        self.path = path
        self.proc = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", str(crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart", path],
            stdin=subprocess.PIPE)
        self.frames = 0

    def write(self, img):
        self.proc.stdin.write(img.convert("RGB").tobytes())
        self.frames += 1

    def close(self):
        self.proc.stdin.close()
        if self.proc.wait() != 0:
            raise RuntimeError("ffmpeg encode failed")


def mux(video, audio, out):
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-i", audio,
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest",
                        "-movflags", "+faststart", out], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg mux failed: " + r.stderr[-500:])
