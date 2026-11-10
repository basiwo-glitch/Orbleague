"""Quality-Agent: technische und inhaltliche Prüfung jedes Videos vor der Freigabe."""
import json
import re
import subprocess

from .. import db

BANNED = re.compile(r"\b(kill|die|dead|blood|gun|nazi|sex)\b", re.I)


def _probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
                       capture_output=True, text=True)
    return json.loads(r.stdout or "{}")


def _audio_levels(path):
    r = subprocess.run(["ffmpeg", "-i", path, "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    mean = re.search(r"mean_volume: (-?[\d.]+) dB", r.stderr)
    peak = re.search(r"max_volume: (-?[\d.]+) dB", r.stderr)
    return (float(mean.group(1)) if mean else -99, float(peak.group(1)) if peak else -99)


def _black_seconds(path):
    r = subprocess.run(["ffmpeg", "-i", path, "-vf", "blackdetect=d=0.5:pix_th=0.05", "-an", "-f", "null", "-"],
                       capture_output=True, text=True)
    return sum(float(m) for m in re.findall(r"black_duration:([\d.]+)", r.stderr))


def check(ep, meta):
    checks = []

    def c(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    p = _probe(meta["path"])
    v = next((s for s in p.get("streams", []) if s["codec_type"] == "video"), {})
    a = next((s for s in p.get("streams", []) if s["codec_type"] == "audio"), None)
    dur = float(p.get("format", {}).get("duration", 0))
    size = int(p.get("format", {}).get("size", 0))
    c("Auflösung 1080x1920", v.get("width") == 1080 and v.get("height") == 1920, f"{v.get('width')}x{v.get('height')}")
    c("Codec H.264", v.get("codec_name") == "h264", v.get("codec_name", "?"))
    c("Länge 12–60 s", 12 <= dur <= 60, f"{dur:.1f}s")
    c("Tonspur vorhanden", a is not None)
    mean, peak = _audio_levels(meta["path"])
    c("Lautstärke ok", -28 <= mean <= -8 and peak <= 0.1, f"mean {mean} dB, peak {peak} dB")
    blk = _black_seconds(meta["path"])
    c("Keine Schwarzbilder", blk < 0.5, f"{blk:.1f}s schwarz")
    c("Dateigröße < 200 MB", size < 200e6, f"{size / 1e6:.1f} MB")
    c("Sieger entschieden", bool(meta.get("winner")))
    c("Spannung (Drama-Score ≥ 6)", (ep.get("drama") or 0) >= 6, str(ep.get("drama")))
    c("Entscheidung nicht zu früh (≥ 10 s)", meta.get("decided_at", 0) >= 10, f"{meta.get('decided_at')}s")
    texts = " ".join([ep["hook"], ep["hook_sub"] or "", ep["cta"], ep["post_text"]] + [x["text"] for x in ep["captions"]])
    c("Texte unbedenklich", not BANNED.search(texts))
    c("Hook kurz (≤ 6 Wörter)", len(ep["hook"].split()) <= 6, ep["hook"])
    recent = db.q("SELECT format, orbs FROM episodes WHERE status IN ('ready','published','inbox') ORDER BY id DESC LIMIT 6")
    dup = any(r["format"] == ep["format"] and sorted(json.loads(r["orbs"])) == sorted(ep["orbs"]) for r in recent)
    c("Keine Wiederholung der letzten 6 Folgen", not dup)
    ok = all(x["ok"] for x in checks)
    db.log("quality", f"Ep {ep['episode_no']}: {'BESTANDEN' if ok else 'DURCHGEFALLEN'} – " +
           ", ".join(x["check"] for x in checks if not x["ok"]), "INFO" if ok else "WARN")
    return ok, checks
