"""Creative-Agent: plant Episoden (Format, Besetzung, Variante, Storyline).

Die Liga hat eine fortlaufende Geschichte: Champion, Underdog, Rivalitäten, Rematches.
Das erzeugt Serien-Effekt -> Gründe zu folgen statt nur einmal zu schauen.
"""
import random

from .. import brand, db
from . import strategy


def league_table():
    db.conn()
    for n in brand.ORBS:
        db.run("INSERT OR IGNORE INTO league(orb) VALUES(?)", (n,))
    return db.q("SELECT * FROM league ORDER BY elo DESC")


def storyline(table):
    champ = table[0]
    under = min(table, key=lambda r: (r["wins"] - r["losses"], r["elo"]))
    rivals = table[:2]
    return {"champion": champ["orb"], "underdog": under["orb"], "rivals": [r["orb"] for r in rivals]}


def _fan_orbs():
    out = []
    for r in db.q("SELECT rowid, text FROM fan_requests WHERE used=0 ORDER BY ts DESC LIMIT 5"):
        found = [n for n in brand.ORBS if n.lower() in r["text"].lower()]
        if found:
            out.append((r["rowid"], found))
    return out


def _hue_gap(a, b):
    import colorsys
    ha = colorsys.rgb_to_hsv(*[c / 255 for c in brand.orb_color(a)])[0] * 360
    hb = colorsys.rgb_to_hsv(*[c / 255 for c in brand.orb_color(b)])[0] * 360
    d = abs(ha - hb)
    return min(d, 360 - d)


def plan_episode(rng=None):
    rng = rng or random.Random()
    plan = strategy.pick_plan()
    fmt, mods, style = plan["format"], dict(plan["mods"]), plan["hook_style"]
    n = mods.pop("orbs", None) or {"escape": rng.choice([4, 5, 5, 6]), "clash": rng.choice([3, 4, 4]),
                                   "territory": 4}[fmt]
    if fmt == "territory":
        n = 2 if n <= 3 else 4
    table = league_table()
    story = storyline(table)
    cast = []
    fan = _fan_orbs()
    if fan and rng.random() < 0.6:
        rowid, names = fan[0]
        cast += names[:n]
        db.run("UPDATE fan_requests SET used=1 WHERE rowid=?", (rowid,))
        style_reason = "fan_request"
    else:
        style_reason = style
    if style == "rivalry":
        cast += story["rivals"]
    elif style == "underdog":
        cast.append(story["underdog"])
    elif style == "champion":
        cast.append(story["champion"])
    pool = [o for o in brand.ORBS if o not in cast]
    rng.shuffle(pool)
    if fmt == "territory":  # Gebiete müssen farblich klar unterscheidbar sein
        import itertools
        must = list(dict.fromkeys(cast))[:n]
        best = []
        for combo in itertools.combinations(pool, n - len(must)):
            team = must + list(combo)
            gap = min((_hue_gap(a, b) for a, b in itertools.combinations(team, 2)), default=360)
            best.append((gap, rng.random(), team))
        best.sort(reverse=True)
        good = [b for b in best if b[0] >= 40] or best[:1]
        cast = rng.choice(good[:6])[2]
    else:
        cast = list(dict.fromkeys(cast + pool))
    cast = cast[:n]
    rng.shuffle(cast)
    trend = db.jget("trend_brief", {}) or {}
    return {"format": fmt, "variant": plan["variant"], "mods": mods, "orbs": cast, "hook_style": style,
            "arms": plan["arms"], "story": story, "reason": style_reason,
            "theme": (trend.get("theme") or {}), "twist": (trend.get("llm_twist") or {})}
