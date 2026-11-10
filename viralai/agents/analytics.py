"""Analytics-Agent: holt Kennzahlen über die Display API und bewertet jedes Video.

Verfügbar über die offizielle Display API: Aufrufe, Likes, Kommentare, Shares pro Video
sowie Follower/Likes des Accounts. NICHT verfügbar: Wiedergabedauer/Retention – die zeigt
TikTok nur in der App (bzw. für Business-Accounts über die Business API). Als Ersatz-Signal
für Zuschauerbindung dienen Share- und Kommentarrate.
"""
import math
import time

from .. import db, tiktok
from . import strategy

MATURE_AFTER = 48 * 3600


def collect():
    if not tiktok.connected():
        return
    try:
        u = tiktok.user_stats()
        db.run("INSERT INTO account_metrics VALUES(?,?,?,?)",
               (time.time(), u.get("follower_count", 0), u.get("likes_count", 0), u.get("video_count", 0)))
    except Exception as e:
        db.log("analytics", f"user.info fehlgeschlagen: {e}", "WARN")
    try:
        vids = tiktok.list_videos()
    except Exception as e:
        db.log("analytics", f"video.list fehlgeschlagen: {e}", "WARN")
        return
    by_id = {str(v["id"]): v for v in vids}
    _match_inbox_posts(vids)
    n = 0
    for ep in db.episodes("tiktok_video_id IS NOT NULL", limit=500):
        v = by_id.get(str(ep["tiktok_video_id"]))
        if not v:
            continue
        db.run("INSERT INTO metrics VALUES(?,?,?,?,?,?)", (ep["id"], time.time(), v.get("view_count", 0),
               v.get("like_count", 0), v.get("comment_count", 0), v.get("share_count", 0)))
        if v.get("share_url") and not ep.get("share_url"):
            db.update_episode(ep["id"], share_url=v["share_url"])
        n += 1
    db.log("analytics", f"Kennzahlen für {n} Videos aktualisiert")
    score_matured()


def _match_inbox_posts(vids):
    """Inbox-Modus: du postest den Entwurf in der App -> Video der Episode zuordnen (nach Zeitpunkt)."""
    known = {r["tiktok_video_id"] for r in db.q("SELECT tiktok_video_id FROM episodes WHERE tiktok_video_id IS NOT NULL")}
    free = sorted([v for v in vids if str(v["id"]) not in known], key=lambda v: v.get("create_time", 0))
    for ep in db.episodes("status='inbox' AND tiktok_video_id IS NULL", order="published_at ASC"):
        cand = [v for v in free if v.get("create_time", 0) >= (ep["published_at"] or 0) - 60]
        if cand:
            v = cand[0]
            free.remove(v)
            db.update_episode(ep["id"], tiktok_video_id=str(v["id"]), status="published",
                              published_at=v.get("create_time"), share_url=v.get("share_url"))
            db.log("analytics", f"Ep {ep['episode_no']} dem geposteten TikTok-Video zugeordnet")


def latest(eid):
    return db.one("SELECT * FROM metrics WHERE episode_id=? ORDER BY ts DESC LIMIT 1", (eid,))


def raw_score(m):
    if not m:
        return 0.0
    v = max(m["views"], 1)
    eng = (m["likes"] + 3 * m["comments"] + 5 * m["shares"]) / v
    return math.log10(v + 1) + 4 * min(eng, 0.5)


def score_matured():
    """Vergibt nach 48 h eine Belohnung 0..1 = Perzentil gegenüber den letzten 30 Videos."""
    cutoff = time.time() - MATURE_AFTER
    todo = db.episodes("reward IS NULL AND status='published' AND published_at < ?", (cutoff,), limit=50)
    if not todo:
        return
    hist = [raw_score(latest(e["id"])) for e in db.episodes("status='published' AND published_at < ?", (cutoff,), limit=30)]
    for ep in todo:
        s = raw_score(latest(ep["id"]))
        if len(hist) >= 5:
            reward = sum(1 for h in hist if h < s) / len(hist)
        else:
            reward = min(1.0, s / 6.0)
        reward = round(reward, 3)
        db.update_episode(ep["id"], reward=reward)
        strategy.record_reward(ep["arms"] or [], reward)
        db.log("analytics", f"Ep {ep['episode_no']} bewertet: Belohnung {reward} ({ep['format']}, {ep['hook_style']})")


def overview():
    tot = db.one("""SELECT COALESCE(SUM(v),0) views, COALESCE(SUM(l),0) likes, COALESCE(SUM(c),0) comments, COALESCE(SUM(s),0) shares FROM (
        SELECT m.episode_id, MAX(m.views) v, MAX(m.likes) l, MAX(m.comments) c, MAX(m.shares) s FROM metrics m GROUP BY m.episode_id)""")
    acc = db.one("SELECT * FROM account_metrics ORDER BY ts DESC LIMIT 1") or {}
    first = db.one("SELECT * FROM account_metrics ORDER BY ts ASC LIMIT 1") or {}
    tot["followers"] = acc.get("followers", 0)
    tot["followers_gained"] = acc.get("followers", 0) - first.get("followers", 0) if first else 0
    return tot
