"""Rendert eine komplette Episode (Video + Ton) aus einer Episoden-Spezifikation."""
import json
import math
import os
import tempfile
import time

from PIL import ImageDraw

from .. import brand
from . import engine as E
from .audio import Track, penta_note, midi_hz
from .formats import FORMATS

LAYOUT = {  # y-Positionen pro Format (TikTok-UI-Safe-Zones beachtet)
    "escape": {"hook": 330, "header": 250, "caption": 470},
    "clash": {"hook": 330, "header": 250, "caption": 420},
    "territory": {"hook": 250, "header": 235, "caption": 345, "sub_dy": 100},
}
END_CARD = 3.4
WINNER_PAUSE = 0.9


def _ease_pop(x):
    """0..1 -> Skalierung mit leichtem Überschwingen."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    return 1 + 2.7 * (x - 1) ** 3 + 1.7 * (x - 1) ** 2


def render_episode(spec, out_path, log=print):
    """spec: dict mit format, orbs, seed, mods, hook, header, captions, episode_no, record, cta."""
    t0 = time.time()
    fmt = spec["format"]
    match = FORMATS[fmt](spec["orbs"], spec["seed"], spec.get("mods"))
    lay = LAYOUT[fmt]
    bg = E.background(spec.get("bg_variant", 0))
    captions = spec.get("captions", [])
    total_est = match.max_t + WINNER_PAUSE + END_CARD + 1

    tmpdir = tempfile.mkdtemp(prefix="orb_")
    vtmp = os.path.join(tmpdir, "v.mp4")
    wtmp = os.path.join(tmpdir, "a.wav")
    writer = E.VideoWriter(vtmp)
    track = Track(total_est + 5, spec["seed"])
    done_t = None
    intensity_marks = []

    while True:
        ev = match.step()
        t = match.frame / E.FPS
        if match.done and done_t is None:
            done_t = t
        _sounds(track, ev, match, t)
        if done_t is not None and t > done_t + WINNER_PAUSE + END_CARD:
            break
        # ---- Zeichnen
        img = bg.copy()
        sh = match.shake
        ox = math.sin(t * 91) * 18 * sh
        oy = math.cos(t * 77) * 18 * sh
        match.draw_world(img, ox, oy)
        match.draw_hud(img)
        _intro_labels(img, match, t)
        _hook(img, spec, lay, t)
        _captions(img, captions, lay, t)
        if done_t is not None and t > done_t + WINNER_PAUSE:
            _end_card(img, spec, match, t - done_t - WINNER_PAUSE)
        writer.write(img)
    writer.close()
    length = writer.frames / E.FPS
    # Hintergrund-Groove: Intensität steigt zum Finale
    fin = done_t or length

    def inten(tt):
        return 0.6 + 0.6 * min(1, tt / max(fin, 1)) if tt < fin else 0.35
    track.beat(0.0, fin + WINNER_PAUSE, bpm=spec.get("bpm", 124), intensity=inten, root=spec.get("root", 45))
    track.write(wtmp, length)
    E.mux(vtmp, wtmp, out_path)
    for f in (vtmp, wtmp):
        os.remove(f)
    os.rmdir(tmpdir)
    meta = {
        "path": out_path, "duration": round(length, 2), "winner": match.winner, "decided_at": round(done_t or length, 2),
        "standings": match.standings(), "events": _summarize(match.events), "render_seconds": round(time.time() - t0, 1),
    }
    log(f"rendered {out_path} in {meta['render_seconds']}s, winner {match.winner}")
    return meta


def _summarize(events):
    keep = {"lead_change", "ko", "escape", "win", "timeout", "sudden_death", "gate_open", "pickup"}
    out = [e for e in events if e["type"] in keep]
    out += [e for e in events if e["type"] == "bounce" and e.get("near_miss")][:12]
    out += [e for e in events if e["type"] == "hit" and e.get("crit")][:10]
    return sorted(out, key=lambda e: e["t"])


# ---------------------------------------------------------------- Sound mapping
def _sounds(tr, ev, match, t):
    for e in ev:
        k = e["type"]
        if k == "bounce":
            tr.pluck(e["t"], penta_note(min(e["n"], 22), 60), 0.20 if not e.get("near_miss") else 0.30)
            if e.get("near_miss"):
                tr.tick(e["t"], 2600, 0.15)
        elif k == "clash":
            tr.tick(e["t"], 900, 0.10)
        elif k == "escape":
            tr.boom(e["t"], 0.6)
            tr.fanfare(e["t"] + 0.15)
        elif k == "hit":
            tr.hit(e["t"], 0.55 if e.get("crit") else 0.38, 1.4 if e.get("crit") else 1.0)
            if e.get("crit"):
                tr.bell(e["t"], midi_hz(84), 0.15, 0.6)
        elif k == "wall":
            idx = match.orbs_names.index(e["orb"])
            tr.pluck(e["t"], penta_note(idx * 2 + 5, 60), 0.08, 0.3)
        elif k == "ko":
            tr.boom(e["t"], 0.7)
            tr.whoosh(e["t"] + 0.05, 0.3)
        elif k in ("win", "timeout"):
            tr.fanfare(e["t"] + 0.1)
        elif k == "paint":
            tr.pluck(e["t"], penta_note(e["idx"] * 3 + 4 + (int(e["t"] * 2) % 3), 60), 0.06, 0.18)
        elif k == "countdown":
            tr.bell(e["t"], midi_hz(76 if e["n"] > 1 else 88), 0.22, 0.7)
        elif k == "sudden_death":
            tr.whoosh(e["t"], 0.45, 1.0)
            tr.bell(e["t"], midi_hz(57), 0.3, 1.4)
        elif k == "gate_open":
            tr.whoosh(e["t"], 0.35, 0.8)
        elif k == "pickup":
            tr.bell(e["t"], midi_hz(91 if e["kind"] == "spike" else 79), 0.18, 0.5)
        elif k == "lead_change":
            tr.tick(e["t"], 1500, 0.08)


# ---------------------------------------------------------------- Overlays
def _hook(img, spec, lay, t):
    hook = spec.get("hook", "")
    header = spec.get("header", "")
    if t < 2.6:
        s = _ease_pop(t / 0.35)
        if s > 0.02:
            E.paste(img, E.scaled(E.text_sprite(hook, 88, brand.WHITE), s), 540, lay["hook"])
            sub = spec.get("hook_sub")
            if sub and t > 0.5:
                E.paste(img, E.with_alpha(E.text_sprite(sub, 46, brand.ACCENT, brand.FONT_BOLD), min(1, (t - 0.5) / 0.3)), 540, lay["hook"] + lay.get("sub_dy", 120))
    else:
        a = min(1, (t - 2.6) / 0.3)
        E.paste(img, E.with_alpha(E.text_sprite(header, 52, brand.WHITE), a), 540, lay["header"])
    # Episoden-Badge
    badge = f"S{spec.get('season', 1)} · EP {spec.get('episode_no', 1):02d}"
    E.paste(img, E.with_alpha(E.text_sprite(badge, 30, brand.ACCENT, brand.FONT_BOLD, 3), 0.9), 540, 165)


def _captions(img, captions, lay, t):
    for c in captions:
        st, du = c["t"], c.get("dur", 1.8)
        if st <= t < st + du:
            x = (t - st)
            s = _ease_pop(x / 0.25)
            a = 1 if x < du - 0.25 else max(0, (st + du - t) / 0.25)
            col = tuple(c.get("color", brand.ACCENT))
            E.paste(img, E.with_alpha(E.scaled(E.text_sprite(c["text"], c.get("size", 64), col), s), a), 540, lay["caption"])


def _intro_labels(img, match, t):
    if t > 2.8:
        return
    a = min(1, t / 0.2) * (1 if t < 2.4 else max(0, (2.8 - t) / 0.4))
    for b in match.bodies:
        if b.alive:
            E.paste(img, E.with_alpha(E.text_sprite(b.name, 30, b.color, brand.FONT_BOLD, 3), a), b.x, b.y - b.r - 30)


def _end_card(img, spec, match, te):
    a = min(1, te / 0.35)
    dim = E.with_alpha(_dim_layer(), 0.72 * a)
    img.alpha_composite(dim)
    w = match.winner
    s = _ease_pop(te / 0.45)
    col = brand.orb_color(w)
    E.paste(img, E.glow_sprite(col, 170, 0.9), 540, 860)
    E.paste(img, E.scaled(E.orb_sprite(w, 160, -1, "win"), max(0.01, s)), 540, 860)
    if te > 0.25:
        E.paste(img, E.scaled(E.text_sprite(f"{w} WINS!", 120, col), _ease_pop((te - 0.25) / 0.35)), 540, 540)
    rec = spec.get("record", {}).get(w)
    if rec and te > 0.6:
        E.paste(img, E.with_alpha(E.text_sprite(f"Season record: {rec}", 46, brand.WHITE, brand.FONT_BOLD), min(1, (te - 0.6) / 0.3)), 540, 1100)
    cta = spec.get("cta", f"Who should fight {w} next?")
    if te > 0.9:
        E.paste(img, E.with_alpha(E.text_sprite(cta, 60, brand.ACCENT), min(1, (te - 0.9) / 0.3)), 540, 1260)
    if te > 1.3:
        E.paste(img, E.with_alpha(E.text_sprite(brand.BRAND_NAME, 40, brand.MUTED, brand.FONT_BOLD), min(1, (te - 1.3) / 0.3)), 540, 1420)


_DIM = None


def _dim_layer():
    global _DIM
    if _DIM is None:
        from PIL import Image
        _DIM = Image.new("RGBA", (E.W, E.H), (6, 6, 14, 255))
    return _DIM


if __name__ == "__main__":
    import sys
    spec = json.load(open(sys.argv[1]))
    print(render_episode(spec, sys.argv[2]))
