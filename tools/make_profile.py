"""Erzeugt Profilbild (1080x1080, rund zuschneidbar) für ORB LEAGUE."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from PIL import Image, ImageDraw
from viralai import brand
from viralai.render import engine as E

N = 1080
yy, xx = np.mgrid[0:N, 0:N]
d = np.sqrt((xx - N / 2) ** 2 + (yy - N / 2) ** 2) / (N / 2)
top, bot = np.array(brand.BG_TOP, float), np.array((40, 14, 60), float)
arr = top * (1 - d[..., None]) * 0 + (top * (1 - yy[..., None] / N) + bot * (yy[..., None] / N))
arr *= np.clip(1.25 - 0.55 * d, 0.5, 1.2)[..., None]
img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
# goldener Liga-Ring
ring = E.ring_sprite(400, 26, 0.0, (255, 214, 64))
E.paste(img, ring, N / 2, N / 2)
# drei Charaktere: Champion vorne, zwei Rivalen dahinter
for name, x, y, r, look in (("BLAZE", 330, 470, 150, 1), ("NOVA", 750, 470, 150, 3), ("FROST", 540, 640, 210, -1)):
    E.paste(img, E.glow_sprite(brand.orb_color(name), r, 0.55), x, y)
    E.paste(img, E.orb_sprite(name, r, look, "normal"), x, y)
out = sys.argv[1] if len(sys.argv) > 1 else "assets/profile.png"
img.convert("RGB").save(out)
# Vorschau mit runder Maske, wie TikTok es zeigt
m = Image.new("L", (N, N), 0); ImageDraw.Draw(m).ellipse([0, 0, N, N], fill=255)
prev = Image.new("RGBA", (N, N), (255, 255, 255, 0)); prev.paste(img, (0, 0), m)
prev.resize((300, 300), Image.LANCZOS).save(out.replace(".png", "_round_preview.png"))
print(out)
