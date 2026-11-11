"""Publishing-Agent: Zeitplan + Upload über die offizielle Content Posting API."""
import datetime as dt
import time
from zoneinfo import ZoneInfo

from .. import config, db, tiktok


def _every_hour():
    last = float(db.setting("last_wait_warn") or 0)
    if time.time() - last > 3600:
        db.set_setting("last_wait_warn", time.time())
        return True
    return False


def slot_times(days=2):
    """Nächste Veröffentlichungs-Slots (Unix-Zeit) laut Einstellungen."""
    tz = ZoneInfo(config.TIMEZONE)
    times = [t.strip() for t in db.setting("post_times").split(",") if t.strip()]
    ppd = int(db.setting("posts_per_day"))
    times = times[:ppd] if len(times) >= ppd else times + [f"{(10 + 3 * i) % 24:02d}:20" for i in range(ppd - len(times))]
    now = dt.datetime.now(tz)
    out = []
    for d in range(days + 1):
        day = (now + dt.timedelta(days=d)).date()
        for t in sorted(times):
            h, m = map(int, t.split(":"))
            ts = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=tz).timestamp()
            if ts > time.time() + 600:
                out.append(ts)
    return sorted(out)


def free_slots(days=1):
    taken = {round(r["scheduled_at"]) for r in db.q(
        "SELECT scheduled_at FROM episodes WHERE scheduled_at IS NOT NULL AND status NOT IN ('rejected','failed','qa_failed')")}
    return [s for s in slot_times(days) if round(s) not in taken]


def due_episode():
    return db.episodes("status='ready' AND scheduled_at <= ?", (time.time(),), order="scheduled_at ASC", limit=1)


def reschedule_overdue():
    """Verpasste Slots (TikTok nicht verbunden, Modus aus, Pause) nicht nachholen, sondern in freie Slots schieben.
    Verhindert, dass nach dem Verbinden alle liegengebliebenen Videos auf einmal hochgeladen werden."""
    overdue = db.episodes("status='ready' AND scheduled_at < ?", (time.time() - 3600,), order="scheduled_at ASC")
    if not overdue:
        return
    slots = free_slots(int(db.setting("buffer_days") or 1) + 1)
    for ep, slot in zip(overdue, slots):
        db.update_episode(ep["id"], scheduled_at=slot)
    db.log("publishing", f"{min(len(overdue), len(slots))} verpasste(s) Video(s) auf die nächsten freien Slots verschoben")


def publish_due():
    reschedule_overdue()
    mode = db.setting("publish_mode")
    if mode == "off":
        return
    if not tiktok.connected():
        if db.episodes("status='ready' AND scheduled_at <= ?", (time.time(),), limit=1) and _every_hour():
            db.log("publishing", "Fälliges Video wartet: TikTok ist noch nicht verbunden", "WARN")
        return
    for ep in due_episode():
        auto = db.setting("auto_approve") == "1"
        if mode == "direct" and not (ep["approved"] or auto):
            if not ep.get("error"):
                db.update_episode(ep["id"], error="wartet auf Freigabe im Dashboard")
            continue
        privacy = db.setting("direct_privacy")
        try:
            db.update_episode(ep["id"], status="publishing", attempts=(ep["attempts"] or 0) + 1)
            pid = tiktok.post_video(ep["video_path"], ep["post_text"], mode, privacy,
                                    cover_ms=1000, is_aigc=db.setting("is_aigc") == "1")
            db.update_episode(ep["id"], publish_id=pid, status="publishing", error=None)
            db.log("publishing", f"Ep {ep['episode_no']} hochgeladen ({mode}), publish_id={pid}")
        except tiktok.TikTokError as e:
            retry = e.code in ("rate_limit_exceeded", "internal_error", "http_500", "http_502", "http_503") and ep["attempts"] < 3
            if e.code == "spam_risk_too_many_posts":
                db.log("publishing", "TikTok-Tageslimit erreicht – Post wird auf morgen verschoben", "WARN")
                db.update_episode(ep["id"], status="ready", scheduled_at=ep["scheduled_at"] + 86400, error=str(e))
            elif retry:
                db.update_episode(ep["id"], status="ready", scheduled_at=time.time() + 900, error=str(e))
                db.log("publishing", f"Ep {ep['episode_no']}: {e} – neuer Versuch in 15 min", "WARN")
            else:
                db.update_episode(ep["id"], status="failed", error=str(e))
                db.log("publishing", f"Ep {ep['episode_no']} fehlgeschlagen: {e}", "ERROR")
        except Exception as e:
            db.update_episode(ep["id"], status="ready", scheduled_at=time.time() + 1800, error=str(e))
            db.log_exc("publishing", f"Ep {ep['episode_no']} Upload-Fehler")


def poll_status():
    for ep in db.episodes("status='publishing' AND publish_id IS NOT NULL", limit=20):
        try:
            st = tiktok.post_status(ep["publish_id"])
        except Exception as e:
            db.log("publishing", f"Status-Abfrage Ep {ep['episode_no']}: {e}", "WARN")
            continue
        s = st.get("status")
        if s == "PUBLISH_COMPLETE":
            ids = st.get("publicaly_available_post_id") or []
            db.update_episode(ep["id"], status="published", published_at=time.time(),
                              tiktok_video_id=str(ids[0]) if ids else None)
            db.log("publishing", f"Ep {ep['episode_no']} veröffentlicht")
        elif s == "SEND_TO_USER_INBOX":
            db.update_episode(ep["id"], status="inbox", published_at=time.time())
            db.log("publishing", f"Ep {ep['episode_no']} liegt als Entwurf in deiner TikTok-App bereit")
        elif s == "FAILED":
            db.update_episode(ep["id"], status="failed", error=st.get("fail_reason", "FAILED"))
            db.log("publishing", f"Ep {ep['episode_no']}: TikTok meldet FAILED ({st.get('fail_reason')})", "ERROR")
