"""Konfiguration aus Umgebungsvariablen bzw. .env-Datei (keine externen Pakete nötig)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()


def get(key, default=None, cast=str):
    v = os.environ.get(key)
    if v is None or v == "":
        return default
    if cast is bool:
        return v.lower() in ("1", "true", "yes", "on")
    return cast(v)


DATA_DIR = Path(get("DATA_DIR", str(ROOT / "data")))
VIDEO_DIR = DATA_DIR / "videos"
DB_PATH = DATA_DIR / "orbleague.db"
LOG_PATH = DATA_DIR / "orbleague.log"
for p in (DATA_DIR, VIDEO_DIR):
    p.mkdir(parents=True, exist_ok=True)

TIMEZONE = get("TIMEZONE", "Europe/Berlin")
PUBLIC_URL = get("PUBLIC_URL", "http://localhost:8080").rstrip("/")
WEB_HOST = get("WEB_HOST", "0.0.0.0")
WEB_PORT = get("WEB_PORT", 8080, int)
DASHBOARD_USER = get("DASHBOARD_USER", "admin")
DASHBOARD_PASSWORD = get("DASHBOARD_PASSWORD", "")

# LLM (optional – ohne Key arbeitet das System mit eingebauten Vorlagen weiter)
ANTHROPIC_API_KEY = get("ANTHROPIC_API_KEY", "")
LLM_MODEL = get("LLM_MODEL", "claude-haiku-5-5")
# USD pro 1 Mio. Tokens – bitte mit der aktuellen Preisliste abgleichen
LLM_PRICE_IN = get("LLM_PRICE_IN_PER_MTOK", 1.0, float)
LLM_PRICE_OUT = get("LLM_PRICE_OUT_PER_MTOK", 5.0, float)
LLM_DAILY_BUDGET_USD = get("LLM_DAILY_BUDGET_USD", 0.50, float)
SERVER_COST_MONTHLY_USD = get("SERVER_COST_MONTHLY_USD", 6.0, float)

# TikTok
TIKTOK_CLIENT_KEY = get("TIKTOK_CLIENT_KEY", "")
TIKTOK_CLIENT_SECRET = get("TIKTOK_CLIENT_SECRET", "")
TIKTOK_REDIRECT_URI = get("TIKTOK_REDIRECT_URI", PUBLIC_URL + "/auth/callback")
TIKTOK_MOCK = get("TIKTOK_MOCK", False, bool)  # simuliert die API für Tests

# Standardwerte für Laufzeit-Einstellungen (im Dashboard änderbar)
DEFAULTS = {
    "paused": "0",
    "posts_per_day": get("POSTS_PER_DAY", "3"),
    "post_times": get("POST_TIMES", "13:05,18:35,21:10"),
    # inbox  = Video landet als Entwurf in der TikTok-App (1 Tipp zum Posten, ohne Audit möglich)
    # direct = Direktveröffentlichung (vor dem TikTok-Audit nur privat sichtbar)
    # off    = nur produzieren, nicht hochladen
    "publish_mode": get("PUBLISH_MODE", "inbox"),
    "direct_privacy": get("DIRECT_PRIVACY", "SELF_ONLY"),
    "auto_approve": get("AUTO_APPROVE", "0"),
    "is_aigc": get("IS_AIGC", "0"),
    "buffer_days": "1",
}
