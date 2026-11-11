"""Produziert einen Vorrat an Folgen zum manuellen Posten (solange der Server noch nicht läuft).

Nutzt exakt die echte Pipeline (Creative -> Simulation -> Script -> Render -> Quality) und
einen ausgewogenen Testplan, damit jede Format-/Hook-Kombination echte Daten sammelt.
Die Metadaten werden an samples/samples.json angehängt -> der Server übernimmt sie beim
ersten Start als bereits gepostete Folgen und zählt die Liga korrekt weiter.

    python3 tools/batch.py <ausgabeordner>
"""
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from viralai import config, db, orchestrator  # noqa: E402
from viralai.agents import strategy  # noqa: E402

PLAN = [  # (Format, Variante, Hook-Stil)
    ("escape", "classic", "prediction"),
    ("clash", "duel", "rivalry"),
    ("territory", "blitz", "challenge"),
    ("escape", "hyper_spin", "champion"),
    ("clash", "glass_cannon", "prediction"),
    ("territory", "duel", "rivalry"),
    ("escape", "tiny_gate", "underdog"),
    ("clash", "early_sudden_death", "champion"),
    ("territory", "turbo", "prediction"),
]


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    orchestrator.recover()  # importiert EP 01-03 aus samples.json
    strategy.ensure_arms()
    current = {}

    def forced():
        f, m, h = current["item"]
        return {"format": f, "variant": m, "mods": dict(strategy.FORMAT_MODS[f][m]), "hook_style": h,
                "arms": [f"fmt:{f}", f"mod:{f}:{m}", f"hook:{h}"]}
    strategy.pick_plan = forced
    made = []
    for item in PLAN:
        current["item"] = item
        for attempt in range(3):
            eid = orchestrator.plan_one(time.time() + 86400 * (len(made) + 1) + attempt)
            orchestrator.produce(db.episode(eid))
            ep = db.episode(eid)
            if ep["status"] == "ready":
                made.append(ep)
                break
            db.update_episode(eid, status="rejected")
            orchestrator.revert_league(db.episode(eid))
            db.run("DELETE FROM episodes WHERE id=?", (eid,))
    samples_path = os.path.join(config.ROOT, "samples", "samples.json")
    samples = json.load(open(samples_path))
    have = {s["episode_no"] for s in samples}
    for ep in made:
        name = f"orbleague_ep{ep['episode_no']:02d}_{ep['format']}.mp4"
        shutil.copy(ep["video_path"], os.path.join(out_dir, name))
        if ep["episode_no"] not in have:
            samples.append({k: ep[k] for k in ("episode_no", "format", "orbs", "mods", "seed", "drama", "hook", "hook_style",
                                               "hook_sub", "header", "captions", "cta", "post_text", "arms", "winner",
                                               "duration", "result", "idea")} | {"video": f"samples/{name}"})
        print(json.dumps({"ep": ep["episode_no"], "file": name, "format": ep["format"], "variant": ep["idea"]["variant"],
                          "orbs": ep["orbs"], "winner": ep["winner"], "hook": ep["hook"], "sub": ep["hook_sub"],
                          "style": ep["hook_style"], "dur": ep["duration"], "drama": ep["drama"],
                          "record": ep["result"]["record"], "caps": [c["text"] for c in ep["captions"]]}, ensure_ascii=False))
    json.dump(samples, open(samples_path, "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1])
