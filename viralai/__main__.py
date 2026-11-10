"""CLI:  python -m viralai run | web | agent | once | status"""
import sys
import threading

from . import db, orchestrator, web


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "run":  # Dashboard + Agenten in einem Prozess (Standard für den Server)
        threading.Thread(target=web.serve, daemon=True).start()
        orchestrator.loop()
    elif cmd == "web":
        web.serve()
    elif cmd == "agent":
        orchestrator.loop()
    elif cmd == "once":  # ein einzelner Durchlauf (zum Testen)
        orchestrator.recover()
        orchestrator.tick()
    elif cmd == "status":
        for ep in db.episodes(limit=10):
            print(ep["episode_no"], ep["status"], ep["format"], ep["hook"], ep["winner"])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
