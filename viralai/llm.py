"""Schlanker Claude-API-Client mit Kostenerfassung und Tagesbudget.

Ist kein Key gesetzt oder das Budget erschöpft, liefert ask_json() None – die Agenten
fallen dann auf ihre eingebauten Regeln/Vorlagen zurück. Das System läuft also auch
komplett ohne laufende KI-Kosten.
"""
import json
import time
import urllib.request

from . import config, db

API = "https://api.anthropic.com/v1/messages"


def available():
    if not config.ANTHROPIC_API_KEY:
        return False
    spent = db.cost_since(time.time() - 86400, "llm")
    return spent < config.LLM_DAILY_BUDGET_USD


def ask(system, prompt, max_tokens=900, agent="llm"):
    if not available():
        return None
    body = json.dumps({
        "model": config.LLM_MODEL, "max_tokens": max_tokens, "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(API, body, {
        "x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read())
    except Exception as e:
        db.log(agent, f"LLM-Aufruf fehlgeschlagen, nutze Fallback: {e}", "WARN")
        return None
    u = data.get("usage", {})
    usd = u.get("input_tokens", 0) / 1e6 * config.LLM_PRICE_IN + u.get("output_tokens", 0) / 1e6 * config.LLM_PRICE_OUT
    db.add_cost("llm", usd, f"{agent} {u.get('input_tokens', 0)}in/{u.get('output_tokens', 0)}out")
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


def ask_json(system, prompt, max_tokens=900, agent="llm"):
    txt = ask(system + "\nAntworte ausschließlich mit gültigem JSON, ohne Erklärtext.", prompt, max_tokens, agent)
    if not txt:
        return None
    s, e = txt.find("{"), txt.rfind("}")
    if s < 0 or e < 0:
        return None
    try:
        return json.loads(txt[s:e + 1])
    except Exception:
        db.log(agent, "LLM lieferte kein gültiges JSON – Fallback", "WARN")
        return None
