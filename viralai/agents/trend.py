"""Trend-Agent: Saison-/Event-Kalender + Signale aus den eigenen Daten.

Hinweis zur Ehrlichkeit: TikTok bietet normalen Entwicklern keine offizielle API für
globale Trend-Daten (die Research API ist Forschungseinrichtungen vorbehalten), und
Scraping verstößt gegen die Nutzungsbedingungen. Deshalb nutzt dieser Agent
(1) einen Kalender wiederkehrender Anlässe, (2) die Performance der eigenen Videos und
(3) optional Fan-Wünsche, die du im Dashboard einträgst (z. B. häufige Kommentare).
"""
import datetime as dt
import time

from .. import db, llm

CALENDAR = [  # (Monat, Tag-von, Tag-bis, Thema, Hook-Zusatz, Hintergrund-Variante)
    (1, 1, 7, "new_year", "NEW YEAR, NEW CHAMP?", 0),
    (2, 10, 14, "valentine", "RIVALS OR LOVERS?", 2),
    (3, 25, 31, "spring", "SEASON FINALE", 1),
    (6, 1, 30, "summer", "SUMMER SHOWDOWN", 1),
    (10, 25, 31, "halloween", "HALLOWEEN SPECIAL", 2),
    (11, 24, 30, "black_friday", "EVERYTHING MUST GO", 2),
    (12, 1, 26, "christmas", "CHRISTMAS SPECIAL", 1),
    (12, 27, 31, "year_end", "GRAND FINAL", 0),
]


def run():
    today = dt.date.today()
    theme = None
    for m, a, b, name, hook, bg in CALENDAR:
        if today.month == m and a <= today.day <= b:
            theme = {"name": name, "hook_extra": hook, "bg_variant": bg}
    fans = [r["text"] for r in db.q("SELECT text FROM fan_requests WHERE used=0 ORDER BY ts DESC LIMIT 10")]
    perf = db.q("""SELECT format, COUNT(*) n, AVG(reward) r FROM episodes
                   WHERE reward IS NOT NULL AND published_at > ? GROUP BY format""", (time.time() - 14 * 86400,))
    brief = {"date": str(today), "theme": theme, "fan_requests": fans,
             "format_performance": perf, "weekday": today.strftime("%A")}
    idea = llm.ask_json(
        "Du bist Trend-Analyst für einen TikTok-Account mit Physik-Simulations-Wettkämpfen (ORB LEAGUE, 8 Kugel-Charaktere).",
        f"Kontext: {brief}. Schlage EINEN thematischen Twist für heute vor, der ohne Fremdmaterial (keine Marken, keine Musik "
        'Dritter) umsetzbar ist. JSON: {"twist": "kurz", "hook_extra": "max 4 Wörter, CAPS, Englisch"}', 250, "trend")
    if idea:
        brief["llm_twist"] = idea
    db.jset("trend_brief", brief)
    db.log("trend", f"Trend-Briefing: Thema={theme['name'] if theme else '—'}, Fan-Wünsche={len(fans)}")
    return brief
