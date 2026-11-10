"""Strategy-Agent: entscheidet datengetrieben, welche Formate/Hooks/Varianten weiterlaufen.

Methode: Multi-Armed-Bandit (Thompson Sampling). Jede Entscheidungsdimension (Format,
Variante, Hook-Stil) ist ein "Arm". Belohnung = Performance-Perzentil eines Videos nach 48 h
(siehe Analytics-Agent). Gute Arme werden häufiger gezogen, schlechte seltener, neue
werden bewusst getestet (Exploration). Ergebnis: echte Daten statt Raten.
"""
import json
import random
import time

from .. import db, llm

FORMAT_MODS = {
    "escape": {"classic": {}, "hyper_spin": {"spin": 1.6}, "moon_gravity": {"gravity": 0.6},
               "tiny_gate": {"gap": 0.7}, "heavy": {"gravity": 1.35}},
    "clash": {"classic": {}, "glass_cannon": {"damage": 1.5}, "early_sudden_death": {"sudden_death_at": 18.0},
              "tanks": {"damage": 0.75}, "duel": {"orbs": 2}},
    "territory": {"classic": {}, "duel": {"orbs": 2}, "turbo": {"speed": 1.35}, "blitz": {"duration": 28.0}},
}
HOOK_STYLES = ["challenge", "prediction", "rivalry", "underdog", "champion"]
PARAM_RANGES = {"spin": (0.5, 2.0), "gravity": (0.5, 1.5), "gap": (0.6, 1.4), "damage": (0.6, 1.8),
                "sudden_death_at": (14.0, 40.0), "speed": (0.8, 1.5), "duration": (24.0, 42.0), "orbs": (2, 6)}


def ensure_arms():
    for f, mods in FORMAT_MODS.items():
        _ensure(f"fmt:{f}")
        for m in mods:
            _ensure(f"mod:{f}:{m}")
    for h in HOOK_STYLES:
        _ensure(f"hook:{h}")
    for a in db.q("SELECT arm, note FROM arms WHERE arm LIKE 'mod:%' AND note LIKE '{%'"):
        _, f, m = a["arm"].split(":", 2)
        FORMAT_MODS.setdefault(f, {})[m] = json.loads(a["note"])


def _ensure(arm, note=None):
    db.run("INSERT OR IGNORE INTO arms(arm, note) VALUES(?, ?)", (arm, note))


def _sample(arm_rows):
    best, best_v = None, -1
    for a in arm_rows:
        s, n = a["reward_sum"], a["pulls"]
        v = random.betavariate(1 + s, 1 + max(0.0, n - s))
        if v > best_v:
            best, best_v = a, v
    return best["arm"]


def choose(prefix):
    rows = db.q("SELECT * FROM arms WHERE arm LIKE ? AND active=1", (prefix + "%",))
    if not rows:
        rows = db.q("SELECT * FROM arms WHERE arm LIKE ?", (prefix + "%",))
    return _sample(rows)


def pick_plan():
    """Wählt Format, Variante und Hook-Stil für die nächste Episode."""
    ensure_arms()
    fmt = choose("fmt:").split(":")[1]
    mod_arm = choose(f"mod:{fmt}:")
    mod = mod_arm.split(":", 2)[2]
    hook = choose("hook:").split(":")[1]
    return {"format": fmt, "variant": mod, "mods": dict(FORMAT_MODS[fmt].get(mod, {})), "hook_style": hook,
            "arms": [f"fmt:{fmt}", mod_arm, f"hook:{hook}"]}


def record_reward(arms, reward):
    for a in arms:
        db.run("UPDATE arms SET pulls=pulls+1, reward_sum=reward_sum+? WHERE arm=?", (float(reward), a))


def arm_table():
    rows = db.q("SELECT * FROM arms ORDER BY arm")
    for r in rows:
        r["mean"] = round(r["reward_sum"] / r["pulls"], 3) if r["pulls"] else None
    return rows


def daily_review():
    """Einmal täglich: Arme ausmustern/neue Varianten erfinden, Post-Frequenz anpassen, Notiz schreiben."""
    ensure_arms()
    rows = arm_table()
    changes = []
    # 1) schwache Varianten pausieren (genug Daten + deutlich schlechter als der Schnitt)
    matured = [r for r in rows if r["pulls"] >= 6]
    if matured:
        avg = sum(r["mean"] for r in matured) / len(matured)
        for r in matured:
            kind = r["arm"].rsplit(":", 1)[0]
            siblings = [x for x in rows if x["arm"].rsplit(":", 1)[0] == kind and x["active"]]
            if r["active"] and r["mean"] < min(0.25, avg * 0.6) and len(siblings) > 1:
                db.run("UPDATE arms SET active=0 WHERE arm=?", (r["arm"],))
                changes.append(f"pausiert: {r['arm']} (Ø {r['mean']})")
    # 2) neue Variante eines starken Formats erfinden (max. 1 pro Woche)
    last = float(db.setting("last_invention") or 0)
    if time.time() - last > 6 * 86400 and matured:
        top = max((r for r in matured if r["arm"].startswith("mod:")), key=lambda r: r["mean"], default=None)
        if top:
            new = invent_variant(top["arm"])
            if new:
                changes.append(f"neue Variante: {new}")
                db.set_setting("last_invention", time.time())
    # 3) Post-Frequenz: mehr posten, wenn die letzten 7 Tage besser liefen als die 7 davor
    ppd = int(db.setting("posts_per_day"))
    now = time.time()
    recent = db.q("SELECT reward FROM episodes WHERE reward IS NOT NULL AND published_at > ?", (now - 7 * 86400,))
    before = db.q("SELECT reward FROM episodes WHERE reward IS NOT NULL AND published_at BETWEEN ? AND ?", (now - 14 * 86400, now - 7 * 86400))
    if len(recent) >= 8 and len(before) >= 8:
        r_now = sum(x["reward"] for x in recent) / len(recent)
        r_bef = sum(x["reward"] for x in before) / len(before)
        if r_now > r_bef * 1.1 and ppd < 4:
            ppd += 1
            changes.append(f"Frequenz erhöht auf {ppd}/Tag")
        elif r_now < r_bef * 0.75 and ppd > 2:
            ppd -= 1
            changes.append(f"Frequenz gesenkt auf {ppd}/Tag (Qualität vor Menge)")
        db.set_setting("posts_per_day", ppd)
    note = write_note(rows, changes)
    db.jset("strategy", {"ts": time.time(), "note": note, "changes": changes})
    db.log("strategy", "Tagesreview: " + ("; ".join(changes) or "keine Änderungen"))


def invent_variant(top_arm):
    _, fmt, mod = top_arm.split(":", 2)
    base = dict(FORMAT_MODS[fmt].get(mod, {}))
    keys = [k for k in PARAM_RANGES if k in {"escape": ("spin", "gravity", "gap"), "clash": ("damage", "sudden_death_at", "orbs"),
                                               "territory": ("speed", "duration", "orbs")}[fmt]]
    j = llm.ask_json(
        "Du bist Game-Designer der ORB LEAGUE, einer TikTok-Serie mit Physik-Simulationen.",
        f"Format '{fmt}', erfolgreichste Variante '{mod}' mit Parametern {base}. Erlaubte Parameter und Bereiche: "
        f"{ {k: PARAM_RANGES[k] for k in keys} }. Erfinde EINE neue, spannendere Variante als JSON "
        '{"name": "snake_case_name", "params": {...}}.', 300, "strategy")
    if j and j.get("name") and isinstance(j.get("params"), dict):
        name, params = j["name"][:30], j["params"]
    else:  # Fallback: zufällige Mutation der besten Variante
        name = f"{mod}_mut{random.randint(10, 99)}"
        params = dict(base)
        k = random.choice(keys)
        params[k] = params.get(k, sum(PARAM_RANGES[k]) / 2) * random.uniform(0.8, 1.25)
    clean = {}
    for k, v in params.items():
        if k in PARAM_RANGES:
            lo, hi = PARAM_RANGES[k]
            clean[k] = int(min(hi, max(lo, v))) if k == "orbs" else round(min(hi, max(lo, float(v))), 2)
    arm = f"mod:{fmt}:{name}"
    _ensure(arm, json.dumps(clean))
    FORMAT_MODS[fmt][name] = clean
    return arm


def write_note(rows, changes):
    best = sorted([r for r in rows if r["pulls"] >= 3], key=lambda r: -(r["mean"] or 0))[:4]
    j = llm.ask_json(
        "Du bist Strategy-Agent eines TikTok-Accounts (ORB LEAGUE, Physik-Simulationen). Schreibe knapp auf Deutsch.",
        f"Bandit-Statistik (arm, pulls, mean reward 0-1): {[(r['arm'], r['pulls'], r['mean']) for r in rows]}. "
        f"Heutige Änderungen: {changes}. Gib JSON {{\"note\": \"3-4 Sätze: was funktioniert, was als Nächstes getestet wird\"}}.",
        350, "strategy")
    if j and j.get("note"):
        return j["note"]
    if not best:
        return ("Explorationsphase: Noch zu wenige ausgewertete Videos. Alle drei Formate (Escape, Clash, Territory) "
                "und alle Hook-Stile werden gleichmäßig getestet, bis je Variante mindestens 3 Ergebnisse vorliegen.")
    txt = "Stärkste Bausteine bisher: " + ", ".join(f"{r['arm']} (Ø {r['mean']})" for r in best) + ". "
    txt += "Diese werden häufiger eingesetzt; schwächere Varianten laufen seltener weiter, damit neue Ideen getestet werden."
    return txt
