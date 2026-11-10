"""Script-Agent: Hook, Untertitel (an echte Ereignisse der Simulation gekoppelt), CTA, Post-Text.

Weil die Simulation vorab läuft, weiß der Agent genau, WANN etwas passiert
(Führungswechsel, Knockout, Beinahe-Ausbruch) und setzt die Einblendung exakt dorthin.
"""
import random

from .. import db, llm

HEADERS = {"escape": "WHO ESCAPES FIRST?", "clash": "LAST ORB STANDING", "territory": "BIGGEST TERRITORY WINS"}

HOOKS = {
    "challenge": {"escape": ("ONLY 1 ORB ESCAPES", "Pick yours before the gate opens"),
                  "clash": ("ONLY 1 ORB SURVIVES", "Pick your fighter now"),
                  "territory": ("{n} ORBS. 1 MAP.", "Pick a color before it starts")},
    "prediction": {"escape": ("PREDICT THE ESCAPE", "Comment your pick before the end"),
                   "clash": ("PREDICT THE WINNER", "Comment before the first KO"),
                   "territory": ("WHO OWNS THE MAP?", "Lock in your pick in the comments")},
    "rivalry": {"*": ("{a} vs {b}. AGAIN.", "The league's biggest rivalry")},
    "underdog": {"*": ("{u} HAS NEVER WON", "Is today the day?")},
    "champion": {"*": ("{c} IS THE CHAMP", "Can anyone stop them?")},
}
HASHTAGS = {"escape": "#escape", "clash": "#battle", "territory": "#territory"}


def _fill(t, ctx):
    try:
        return t.format(**ctx)
    except Exception:
        return t


def _met_before(a, b):
    rows = db.q("SELECT orbs FROM episodes WHERE status NOT IN ('rejected','qa_failed','failed') AND orbs LIKE ? AND orbs LIKE ?",
                (f'%"{a}"%', f'%"{b}"%'))
    return len(rows) > 0


def hook_for(fmt, style, plan, table):
    st = plan.get("story", {})
    rec = {r["orb"]: r for r in table}
    u = st.get("underdog", plan["orbs"][0])
    if style == "underdog" and (rec.get(u, {}).get("wins", 0) > 0 or rec.get(u, {}).get("losses", 0) < 3):
        style = "challenge"  # Aussage wäre sonst falsch oder leer – Ehrlichkeit vor Clickbait
    rivals = st.get("rivals", plan["orbs"][:2])
    ctx = {"n": len(plan["orbs"]), "a": rivals[0], "b": rivals[-1], "u": u, "c": st.get("champion", plan["orbs"][0])}
    if style == "rivalry" and (not all(r in plan["orbs"] for r in rivals) or not _met_before(rivals[0], rivals[-1])):
        style = "challenge"  # "AGAIN" nur, wenn sie wirklich schon gegeneinander gespielt haben
    if style == "champion" and (ctx["c"] not in plan["orbs"] or rec.get(ctx["c"], {}).get("wins", 0) == 0):
        style = "prediction"
    t = HOOKS[style].get(fmt) or HOOKS[style]["*"]
    hook, sub = _fill(t[0], ctx), _fill(t[1], ctx)
    extra = (plan.get("theme") or {}).get("hook_extra")
    if extra and random.random() < 0.5:
        sub = extra
    return hook, sub, style


def captions_from_events(fmt, events, decided_at, max_t):
    caps = []

    def add(t, text, color=None):
        if t < 2.8 or t > decided_at - 0.3:
            return
        if any(abs(t - c["t"]) < 2.3 for c in caps):
            return
        c = {"t": round(t, 2), "text": text, "dur": 1.8}
        if color:
            c["color"] = color
        caps.append(c)

    if fmt == "escape":
        for e in events:
            if e["type"] == "gate_open":
                add(e["t"], "THE GATE IS OPEN")
        nm = [e for e in events if e["type"] == "bounce" and e.get("near_miss") and e["t"] > 3.5]
        if nm:
            add(nm[0]["t"], f"{nm[0]['orb']} ALMOST!")
        if len(nm) > 3:
            e = nm[len(nm) // 2]
            add(e["t"], "SO CLOSE...")
        if decided_at > 14:
            add(decided_at - 4.5, "ANY SECOND NOW...")
    elif fmt == "clash":
        for e in events:
            if e["type"] == "hit" and e.get("crit"):
                add(e["t"], "CRITICAL HIT!", (255, 90, 90))
                break
        for e in events:
            if e["type"] == "ko":
                add(e["t"], f"{e['orb']} IS OUT!" if e["left"] > 1 else f"{e['by']} FINISHES IT")
                if e["left"] == 2:
                    add(e["t"] + 2.3, "FINAL TWO")
            elif e["type"] == "sudden_death":
                add(e["t"], "SUDDEN DEATH", (255, 90, 90))
            elif e["type"] == "pickup" and e["kind"] == "spike":
                add(e["t"], f"{e['orb']} GOT SPIKES")
    elif fmt == "territory":
        late = [e for e in events if e["type"] == "lead_change" and e["t"] > max_t * 0.45]
        seen = set()
        for e in late[:3]:
            add(e["t"], f"{e['orb']} IS BACK IN FRONT" if e["orb"] in seen else f"{e['orb']} TAKES THE LEAD")
            seen.add(e["orb"])
        add(max_t * 0.3, "WATCH THE BORDERS")
        add(max_t - 9, "IT'S CLOSE...")
    return sorted(caps, key=lambda c: c["t"])


def post_text(fmt, hook, orbs, plan):
    j = llm.ask_json(
        "Du schreibst TikTok-Captions für ORB LEAGUE (Physik-Simulations-Liga, international, Englisch). Keine Lügen, "
        "keine Clickbait-Versprechen, die das Video nicht hält. Keine Erwähnung von Marken.",
        f"Format: {fmt}. Hook im Video: '{hook}'. Teilnehmer: {orbs}. Storyline: {plan.get('story')}. "
        'Schreibe eine Caption (max 120 Zeichen) die zu Kommentaren mit dem eigenen Tipp anregt. JSON: {"caption": "..."}',
        200, "script")
    cap = (j or {}).get("caption") or random.choice([
        "Who did you pick? Be honest 👇",
        f"{' vs '.join(orbs[:2])}... and the rest. Your pick? 👇",
        "Physics decided. Did you call it? 👇",
        "Comment your pick BEFORE the end 👇",
    ])
    tags = " ".join(["#orbleague", HASHTAGS[fmt], "#satisfying", "#physics", "#simulation"])
    return f"{cap} {tags}"[:2000]


def write(plan, sim_meta, table, record):
    fmt = plan["format"]
    hook, sub, style = hook_for(fmt, plan["hook_style"], plan, table)
    caps = captions_from_events(fmt, sim_meta["events"], sim_meta["decided_at"], sim_meta["max_t"])
    w = sim_meta["winner"]
    cta = random.choice([f"Who should fight {w} next?", "Did you call it?", f"Rematch? Pick {w}'s next rival",
                         "Who wins the rematch?"])
    db.log("script", f"Hook '{hook}' ({style}), {len(caps)} Ereignis-Einblendungen")
    return {"hook": hook, "hook_sub": sub, "hook_style": style, "header": HEADERS[fmt], "captions": caps,
            "cta": cta, "post_text": post_text(fmt, hook, plan["orbs"], plan), "record": record}
