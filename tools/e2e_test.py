"""End-to-End-Test mit simulierter TikTok-API: plant, produziert, prüft, veröffentlicht, wertet aus."""
import os, sys, time
os.environ.setdefault("TIKTOK_MOCK", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from viralai import db, tiktok, orchestrator
from viralai.agents import strategy, analytics, publishing

order = iter(["escape", "clash", "territory"])
orig = strategy.pick_plan
def forced():
    p = orig()
    try:
        f = next(order)
    except StopIteration:
        return p
    mod = "classic"
    return {"format": f, "variant": mod, "mods": dict(strategy.FORMAT_MODS[f][mod]), "hook_style": ["challenge", "prediction", "challenge"][["escape","clash","territory"].index(f)],
            "arms": [f"fmt:{f}", f"mod:{f}:{mod}", "hook:x"]}
strategy.pick_plan = forced

orchestrator.recover()
strategy.ensure_arms()
for i in range(3):
    t = time.time(); orchestrator.tick(); print(f"tick {i+1}: {time.time()-t:.0f}s")
eps = db.episodes(order="id ASC")
for e in eps:
    print(e["episode_no"], e["format"], e["status"], e["hook"], "|", e["winner"], e["drama"], e["video_path"])
# TikTok (simuliert) verbinden und erstes Video fällig machen
tiktok.auth_url(); tiktok.exchange_code("x", db.setting("oauth_state"))
ready = db.episodes("status='ready'", order="id ASC")
db.update_episode(ready[0]["id"], scheduled_at=time.time() - 5)
db.set_setting("publish_mode", "direct"); db.set_setting("direct_privacy", "SELF_ONLY")
publishing.publish_due(); print("ohne Freigabe:", db.episode(ready[0]["id"])["status"], db.episode(ready[0]["id"])["error"])
db.update_episode(ready[0]["id"], approved=1)
publishing.publish_due(); publishing.poll_status()
print("nach Freigabe:", db.episode(ready[0]["id"])["status"])
# Analytics: 48h später simulieren
db.update_episode(ready[0]["id"], published_at=time.time() - 50 * 3600)
analytics.collect(); analytics.collect()
print("reward:", db.episode(ready[0]["id"])["reward"], analytics.overview())
strategy.daily_review(); print(db.jget("strategy")["note"])
