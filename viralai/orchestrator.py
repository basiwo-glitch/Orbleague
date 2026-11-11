"""Orchestrator: koordiniert alle Agenten über die gemeinsame Datenbank.

Ablauf pro Episode:
  Trend -> Creative (Plan) -> Video (Vorab-Simulation, bester Seed) -> Script (Hook/Captions
  an echte Ereignisse gekoppelt) -> Video (Rendern) -> Quality (Prüfung) -> Publishing
  (zur geplanten Zeit) -> Analytics (Kennzahlen, Bewertung nach 48 h) -> Strategy (lernt daraus)

Jeder Schritt speichert seinen Zustand in SQLite. Nach einem Neustart macht das System
genau dort weiter, wo es aufgehört hat.
"""
import time

from . import db
from .agents import analytics, creative, publishing, quality, script, strategy, trend, video

LOOP_SECONDS = 60


def _every(key, seconds):
    last = float(db.setting(key) or 0)
    if time.time() - last >= seconds:
        db.set_setting(key, time.time())
        return True
    return False


# ---------------------------------------------------------------- Liga
def _elo(winner, losers, sign=1):
    rows = {r["orb"]: r for r in creative.league_table()}
    for lo in losers:
        rw, rl = rows[winner]["elo"], rows[lo]["elo"]
        exp = 1 / (1 + 10 ** ((rl - rw) / 400))
        d = 24 * (1 - exp) * sign
        rows[winner]["elo"] += d
        rows[lo]["elo"] -= d
    for n, r in rows.items():
        db.run("UPDATE league SET elo=? WHERE orb=?", (r["elo"], n))
    db.run("UPDATE league SET wins=wins+? WHERE orb=?", (sign, winner))
    for lo in losers:
        db.run("UPDATE league SET losses=losses+? WHERE orb=?", (sign, lo))


def revert_league(ep):
    if ep.get("winner") and (ep.get("result") or {}).get("applied"):
        _elo(ep["winner"], [o for o in ep["orbs"] if o != ep["winner"]], sign=-1)
        res = ep["result"]
        res["applied"] = False
        db.update_episode(ep["id"], result=res)


# ---------------------------------------------------------------- Schritte
def plan_one(slot):
    plan = creative.plan_episode()
    sim = video.direct(plan)
    winner = sim["winner"]
    losers = [o for o in plan["orbs"] if o != winner]
    _elo(winner, losers)
    table = creative.league_table()
    record = {r["orb"]: f"{r['wins']}-{r['losses']}" for r in table}
    sc = script.write(plan, sim, table, record)
    arms = [a for a in plan["arms"] if not a.startswith("hook:")] + [f"hook:{sc['hook_style']}"]
    no = (db.one("SELECT MAX(episode_no) n FROM episodes")["n"] or 0) + 1
    eid = db.create_episode(
        status="planned", format=plan["format"], orbs=plan["orbs"], mods=plan["mods"], seed=sim["seed"],
        drama=sim["drama"], hook=sc["hook"], hook_style=sc["hook_style"], hook_sub=sc["hook_sub"], header=sc["header"],
        captions=sc["captions"], cta=sc["cta"], post_text=sc["post_text"], episode_no=no, arms=arms,
        idea={"variant": plan["variant"], "story": plan["story"], "reason": plan["reason"], "theme": plan["theme"],
              "twist": plan["twist"]},
        scheduled_at=slot, winner=winner,
        result={"record": {o: record[o] for o in plan["orbs"]}, "applied": True, "standings": sim["standings"]})
    db.log("creative", f"Ep {no} geplant: {plan['format']}/{plan['variant']} mit {', '.join(plan['orbs'])} – Hook „{sc['hook']}“")
    return eid


def produce(ep):
    db.update_episode(ep["id"], status="rendering")
    try:
        meta = video.render(ep)
    except Exception:
        db.log_exc("video", f"Rendern von Ep {ep['episode_no']} fehlgeschlagen")
        db.update_episode(ep["id"], status="planned", attempts=(ep["attempts"] or 0) + 1)
        if (ep["attempts"] or 0) >= 2:
            db.update_episode(ep["id"], status="failed", error="Rendern 3x fehlgeschlagen")
            revert_league(db.episode(ep["id"]))
        return
    if meta["winner"] != ep["winner"]:  # Determinismus-Sicherung
        db.log("video", f"Ep {ep['episode_no']}: Sieger weicht von Vorab-Simulation ab", "ERROR")
    ep = db.episode(ep["id"])
    ok, checks = quality.check(ep, meta)
    db.update_episode(ep["id"], video_path=meta["path"], duration=meta["duration"], qa=checks,
                      status="ready" if ok else "qa_failed")
    if not ok:
        revert_league(db.episode(ep["id"]))


def recover():
    """Nach Neustart: halbfertige Zustände aufräumen."""
    for ep in db.episodes("status='rendering'"):
        db.update_episode(ep["id"], status="planned")
    for ep in db.episodes("status='publishing' AND publish_id IS NULL"):
        db.update_episode(ep["id"], status="ready")
    db.log("orchestrator", "Start/Neustart – Zustand wiederhergestellt")
    import_samples()


def import_samples():
    """Beim allerersten Start: die 3 Testvideos (samples/) als EP 01–03 übernehmen.

    Status 'inbox' = "wird von Hand gepostet". Sobald sie auf TikTok online sind, ordnet der
    Analytics-Agent sie in Posting-Reihenfolge zu. Neue Folgen starten dann bei EP 04.
    """
    import json
    import os
    from . import config
    path = os.path.join(config.ROOT, "samples", "samples.json")
    if db.setting("samples_imported") or db.one("SELECT COUNT(*) n FROM episodes")["n"] or not os.path.exists(path):
        return
    creative.league_table()
    for i, s in enumerate(json.load(open(path))):
        _elo(s["winner"], [o for o in s["orbs"] if o != s["winner"]])
        db.create_episode(
            status="inbox", format=s["format"], orbs=s["orbs"], mods=s["mods"], seed=s["seed"], drama=s["drama"],
            hook=s["hook"], hook_style=s["hook_style"], hook_sub=s["hook_sub"], header=s["header"], captions=s["captions"],
            cta=s["cta"], post_text=s["post_text"], episode_no=s["episode_no"], arms=s["arms"], idea=s.get("idea"),
            winner=s["winner"], result=s["result"], duration=s["duration"], approved=1,
            video_path=(os.path.join(config.ROOT, s["video"]) if s.get("video") and os.path.exists(os.path.join(config.ROOT, s["video"])) else None),
            scheduled_at=i + 1, published_at=i + 1)
    db.set_setting("samples_imported", "1")
    db.log("orchestrator", "Testvideos als EP 01–03 übernommen (werden nach dem Posten automatisch zugeordnet)")


def tick():
    paused = db.setting("paused") == "1"
    if not paused:
        if _every("last_trend", 12 * 3600):
            _safe("trend", trend.run)
        if _every("last_strategy", 24 * 3600):
            _safe("strategy", strategy.daily_review)
        slots = publishing.free_slots(int(db.setting("buffer_days") or 1))
        fails = db.one("SELECT COUNT(*) n FROM episodes WHERE status IN ('qa_failed','failed') AND created_at > ?",
                       (time.time() - 7200,))["n"]
        if fails >= 4:
            if _every("last_fail_warn", 3600):
                db.log("orchestrator", "Viele Fehlschläge in 2 h – Planung pausiert kurz (Details im Log)", "ERROR")
        elif slots:
            _safe("creative", plan_one, slots[0])
        planned = db.episodes("status='planned'", order="scheduled_at ASC", limit=1)
        if planned:
            _safe("video", produce, planned[0])
        _safe("publishing", publishing.publish_due)
    _safe("publishing", publishing.poll_status)
    if _every("last_analytics", 3 * 3600):
        _safe("analytics", analytics.collect)


def _safe(agent, fn, *a):
    try:
        return fn(*a)
    except Exception:
        db.log_exc(agent, "Unerwarteter Fehler")


def loop(stop_event=None):
    recover()
    strategy.ensure_arms()
    creative.league_table()
    while not (stop_event and stop_event.is_set()):
        t0 = time.time()
        tick()
        db.set_setting("heartbeat", time.time())
        wait = 2 if db.episodes("status='planned'", limit=1) else (15 if publishing.free_slots(1) else LOOP_SECONDS)
        while time.time() - t0 < wait and not (stop_event and stop_event.is_set()):
            time.sleep(1)
