"""Video-Agent: wählt per Vorab-Simulation den spannendsten Seed und rendert das Video."""
import os

from .. import config, db
from ..render import formats as F
from ..render.episode import render_episode


def direct(plan, tries=24):
    seed, match, score = F.direct(plan["format"], plan["orbs"], plan["mods"], tries=tries)
    from ..render.episode import _summarize
    meta = {"seed": seed, "drama": score, "winner": match.winner, "decided_at": round(match.t, 2),
            "max_t": match.max_t, "events": _summarize(match.events), "standings": match.standings()}
    db.log("video", f"{plan['format']}: {tries} Seeds simuliert, bester Spannungswert {score} (Sieger {match.winner})")
    return meta


def render(ep):
    out = os.path.join(config.VIDEO_DIR, f"ep{ep['episode_no']:04d}_{ep['format']}.mp4")
    spec = {"format": ep["format"], "orbs": ep["orbs"], "seed": ep["seed"], "mods": ep["mods"],
            "hook": ep["hook"], "hook_sub": ep["hook_sub"], "header": ep["header"], "captions": ep["captions"],
            "episode_no": ep["episode_no"], "season": ep.get("season") or 1, "cta": ep["cta"],
            "record": (ep.get("result") or {}).get("record", {}),
            "bg_variant": (ep.get("idea") or {}).get("theme", {}).get("bg_variant", ep["episode_no"] % 3)}
    meta = render_episode(spec, out, log=lambda m: db.log("video", m))
    db.add_cost("render", 0.0, f"ep{ep['episode_no']} {meta['render_seconds']}s CPU")
    return meta
