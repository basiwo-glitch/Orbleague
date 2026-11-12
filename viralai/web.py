"""Dashboard (nur Python-Standardbibliothek). Optimiert fürs iPhone/iPad.

Geschützt per HTTP-Basic-Auth (DASHBOARD_PASSWORD). /privacy, /terms und /auth/callback
sind öffentlich (TikTok verlangt das für die App-Prüfung bzw. den Login).
"""
import base64
import datetime as dt
import html
import json
import os
import re
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

from . import brand, config, db, tiktok
from .agents import analytics, creative, strategy
from .orchestrator import revert_league

TZ = ZoneInfo(config.TIMEZONE)
PUBLIC = ("/privacy", "/terms", "/auth/callback", "/favicon.ico", "/healthz", "/tiktok")
VERIFY_RE = re.compile(r"^/(tiktok[A-Za-z0-9_-]{4,80}\.txt)$")
STATUS_DE = {"planned": "geplant", "rendering": "wird produziert", "ready": "fertig", "publishing": "wird hochgeladen",
             "inbox": "Entwurf in App", "published": "veröffentlicht", "qa_failed": "Qualität ✗", "failed": "Fehler",
             "rejected": "abgelehnt"}
PHASES = [(1, "30 veröffentlichte Videos", lambda o: o["published"] / 30), (2, "1.000 Follower", lambda o: o["followers"] / 1000),
          (3, "10.000 Follower", lambda o: o["followers"] / 1e4), (4, "100.000 Follower", lambda o: o["followers"] / 1e5),
          (5, "International skalieren", lambda o: o["followers"] / 1e6)]


def e(s):
    return html.escape(str(s if s is not None else ""))


def fmt_ts(ts):
    if not ts:
        return "—"
    return dt.datetime.fromtimestamp(ts, TZ).strftime("%a %d.%m. %H:%M")


def num(n):
    n = n or 0
    return f"{n / 1e6:.1f} Mio" if n >= 1e6 else (f"{n / 1e3:.1f}k" if n >= 1e4 else f"{n:,}".replace(",", "."))


CSS = """
:root{--bg:#0a0c1c;--card:#141830;--line:#262b4d;--fg:#f3f4ff;--mut:#9aa0c6;--acc:#ffd640;--ok:#5ef08f;--bad:#ff6a6a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Inter",sans-serif}
header{position:sticky;top:0;z-index:5;background:rgba(10,12,28,.92);backdrop-filter:blur(10px);border-bottom:1px solid var(--line);padding:12px 16px;display:flex;align-items:center;gap:10px}
header b{font-weight:900;letter-spacing:.5px}nav{display:flex;gap:6px;overflow-x:auto;padding:8px 16px;border-bottom:1px solid var(--line)}
nav a{color:var(--mut);text-decoration:none;padding:6px 10px;border-radius:99px;white-space:nowrap;font-size:14px}nav a.on{background:var(--card);color:var(--fg)}
main{max-width:860px;margin:0 auto;padding:16px}h2{font-size:17px;margin:22px 0 10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px;margin-bottom:12px}
.kpis{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}@media(min-width:640px){.kpis{grid-template-columns:repeat(4,1fr)}}
.kpi .v{font-size:24px;font-weight:800}.kpi .l{color:var(--mut);font-size:13px}
.pill{display:inline-block;padding:2px 9px;border-radius:99px;font-size:12px;background:#22284a;color:var(--mut)}
.pill.ok{background:#173a26;color:var(--ok)}.pill.bad{background:#3d1a1f;color:var(--bad)}.pill.acc{background:#3b3214;color:var(--acc)}
.btn{display:inline-block;border:0;border-radius:12px;padding:10px 14px;font-weight:700;font-size:15px;background:#262d58;color:var(--fg);text-decoration:none;cursor:pointer}
.btn.acc{background:var(--acc);color:#1a1400}.btn.bad{background:#4a1d24;color:#ffb3b3}.btn.sm{padding:6px 10px;font-size:13px}
.ep{display:flex;gap:12px}.ep video{width:110px;height:196px;border-radius:12px;background:#000;object-fit:cover;flex:none}
.ep .meta{flex:1;min-width:0}.mut{color:var(--mut);font-size:13px}.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:7px 6px;border-bottom:1px solid var(--line);text-align:left}th{color:var(--mut);font-weight:600}
.bar{height:8px;background:#22284a;border-radius:9px;overflow:hidden}.bar i{display:block;height:100%;background:var(--acc)}
input,select,textarea{width:100%;background:#0e1126;border:1px solid var(--line);color:var(--fg);border-radius:10px;padding:10px;font-size:16px}
label{display:block;margin:10px 0 4px;color:var(--mut);font-size:13px}.log{font:12px/1.4 ui-monospace,Menlo,monospace;white-space:pre-wrap;word-break:break-word}
.dot{width:12px;height:12px;border-radius:50%;display:inline-block}
"""


def page(title, body, active=""):
    tabs = [("/", "Übersicht"), ("/videos", "Videos"), ("/strategy", "Strategie"), ("/league", "Liga"),
            ("/settings", "Steuerung"), ("/logs", "Logs")]
    nav = "".join(f'<a href="{h}" class="{"on" if h == active else ""}">{t}</a>' for h, t in tabs)
    hb = float(db.setting("heartbeat") or 0)
    alive = time.time() - hb < 300
    paused = db.setting("paused") == "1"
    st = '<span class="pill bad">pausiert</span>' if paused else (
        '<span class="pill ok">läuft</span>' if alive else '<span class="pill bad">Agent offline</span>')
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="apple-mobile-web-app-capable" content="yes"><title>{e(title)} · ORB LEAGUE</title><style>{CSS}</style></head>
<body><header><b>ORB LEAGUE</b>{st}<span style="flex:1"></span>{'<span class="pill ok">TikTok ✓</span>' if tiktok.connected() else '<a class="btn sm acc" href="/auth/tiktok">TikTok verbinden</a>'}</header>
<nav>{nav}</nav><main>{body}</main></body></html>"""


def ep_card(ep, actions=True):
    m = analytics.latest(ep["id"]) if ep["status"] == "published" else None
    vid = f'<video src="/media/{ep["id"]}" controls playsinline preload="none" poster=""></video>' if ep.get("video_path") and os.path.exists(ep["video_path"] or "") else '<div style="width:110px;height:196px;border-radius:12px;background:#0e1126;flex:none"></div>'
    stat = STATUS_DE.get(ep["status"], ep["status"])
    cls = "ok" if ep["status"] in ("published", "ready") else ("bad" if ep["status"] in ("failed", "qa_failed") else "")
    btns = ""
    if actions and ep["status"] in ("ready", "planned"):
        if db.setting("publish_mode") == "direct" and not ep["approved"]:
            btns += f'<button class="btn sm acc" name="a" value="approve:{ep["id"]}">Freigeben</button>'
        btns += f'<button class="btn sm bad" name="a" value="reject:{ep["id"]}">Ablehnen</button>'
    if actions and ep["status"] in ("failed", "qa_failed") and ep.get("video_path"):
        btns += f'<button class="btn sm" name="a" value="retry:{ep["id"]}">Erneut versuchen</button>'
    metrics = f'<div class="row mut">👁 {num(m["views"])} · ♥ {num(m["likes"])} · 💬 {num(m["comments"])} · ↗ {num(m["shares"])}</div>' if m else ""
    qa = ""
    if ep.get("qa") and isinstance(ep["qa"], list):
        bad = [c["check"] + (f' ({c["detail"]})' if c.get("detail") else "") for c in ep["qa"] if not c["ok"]]
        qa = f'<div class="mut" style="color:var(--bad)">✗ {e("; ".join(bad))}</div>' if bad else '<div class="mut">Qualitätsprüfung ✓</div>'
    reward = f' · Score {ep["reward"]:.2f}' if ep.get("reward") is not None else ""
    link = f' · <a href="{e(ep["share_url"])}" style="color:var(--acc)">auf TikTok</a>' if ep.get("share_url") else ""
    return f"""<div class="card ep">{vid}<div class="meta">
<div class="row"><b>EP {ep['episode_no']:02d}</b><span class="pill {cls}">{e(stat)}</span><span class="pill">{e(ep['format'])}</span></div>
<div style="font-weight:800;margin:6px 0 2px">{e(ep['hook'])}</div><div class="mut">{e(ep['hook_sub'])}</div>
<div class="mut">{e(', '.join(ep['orbs']))} · Sieger {e(ep['winner'])} · Spannung {e(ep['drama'])}{reward}</div>
<div class="mut">🕒 {fmt_ts(ep['scheduled_at'])}{link}</div>{metrics}{qa}
{f'<div class="mut" style="color:var(--bad)">{e(ep["error"])}</div>' if ep.get("error") and ep["status"] != "published" else ''}
<details><summary class="mut">Caption</summary><div style="user-select:all;-webkit-user-select:all">{e(ep['post_text'])}</div></details>
<form method="post" action="/action" class="row" style="margin-top:8px">{btns}</form></div></div>"""


def overview_numbers():
    o = analytics.overview()
    o["produced"] = db.one("SELECT COUNT(*) n FROM episodes WHERE video_path IS NOT NULL")["n"]
    o["published"] = db.one("SELECT COUNT(*) n FROM episodes WHERE status='published'")["n"]
    day = time.time() - 86400
    month = time.time() - 30 * 86400
    o["cost_llm_day"] = db.cost_since(day, "llm")
    o["cost_llm_month"] = db.cost_since(month, "llm")
    o["cost_month_total"] = o["cost_llm_month"] + config.SERVER_COST_MONTHLY_USD
    vids_month = db.one("SELECT COUNT(*) n FROM episodes WHERE video_path IS NOT NULL AND created_at > ?", (month,))["n"]
    o["cost_per_video"] = o["cost_month_total"] / vids_month if vids_month else None
    return o


def view_home():
    o = overview_numbers()
    k = lambda v, l: f'<div class="card kpi"><div class="v">{v}</div><div class="l">{l}</div></div>'
    kp = (k(o["produced"], "Videos produziert") + k(o["published"], "veröffentlicht") + k(num(o["views"]), "Aufrufe gesamt")
          + k(num(o["followers"]), f"Follower (+{num(o['followers_gained'])})"))
    cpv = f"${o['cost_per_video']:.2f}" if o["cost_per_video"] is not None else "—"
    cost = f"""<div class="card"><b>Kosten</b><table><tr><td>KI (heute)</td><td>${o['cost_llm_day']:.3f}</td></tr>
<tr><td>KI (30 Tage)</td><td>${o['cost_llm_month']:.2f}</td></tr><tr><td>Server (pauschal/Monat)</td><td>${config.SERVER_COST_MONTHLY_USD:.2f}</td></tr>
<tr><td><b>Gesamt 30 Tage</b></td><td><b>${o['cost_month_total']:.2f}</b></td></tr><tr><td>pro Video</td><td>{cpv}</td></tr></table>
<div class="mut">Rendering läuft auf dem eigenen Server – keine Kosten pro Video. Tagesbudget KI: ${config.LLM_DAILY_BUDGET_USD:.2f}.</div></div>"""
    ph = ""
    for n, label, f in PHASES:
        p = max(0.0, min(1.0, f(o)))
        ph += f'<div style="margin:8px 0"><div class="row"><span>Phase {n}: {label}</span><span class="mut" style="margin-left:auto">{p * 100:.0f}%</span></div><div class="bar"><i style="width:{p * 100:.1f}%"></i></div></div>'
    s = db.jget("strategy", {}) or {}
    nxt = db.episodes("status IN ('planned','rendering','ready')", order="scheduled_at ASC", limit=3)
    paused = db.setting("paused") == "1"
    ctrl = f"""<form method="post" action="/action" class="row">
<button class="btn {'acc' if paused else 'bad'}" name="a" value="{'resume' if paused else 'pause'}">{'▶︎ Automatik fortsetzen' if paused else '■ Automatik stoppen'}</button>
{'<button class="btn" name="a" value="approve_all">Alle fertigen freigeben</button>' if db.setting('publish_mode') == 'direct' else ''}</form>"""
    warn = ""
    if not tiktok.connected():
        warn = '<div class="card" style="border-color:#5a4a14"><b>Einmalige Einrichtung offen:</b> TikTok ist noch nicht verbunden. Videos werden produziert, aber nicht hochgeladen. <a href="/auth/tiktok" style="color:var(--acc)">Jetzt verbinden</a></div>'
    elif db.setting("publish_mode") == "inbox":
        warn = '<div class="card mut">Modus „Entwurf“: Fertige Videos landen zur geplanten Zeit in deinem TikTok-Posteingang. In der App nur noch Caption einfügen und posten.</div>'
    body = f"""{warn}{ctrl}<h2>Kennzahlen</h2><div class="kpis">{kp}</div>
<h2>Aktuelle Strategie</h2><div class="card">{e(s.get('note', 'Wird nach dem ersten Tagesreview erstellt.'))}<div class="mut" style="margin-top:6px">{e('; '.join(s.get('changes', [])))}</div></div>
<h2>Als Nächstes</h2>{''.join(ep_card(x) for x in nxt) or '<div class="card mut">Noch nichts geplant.</div>'}
<h2>Wachstumsziele</h2><div class="card">{ph}<div class="mut">Ziele, keine Garantien.</div></div>{cost}"""
    return page("Übersicht", body, "/")


def view_videos():
    eps = db.episodes(limit=80)
    return page("Videos", "".join(ep_card(x) for x in eps) or '<div class="card mut">Noch keine Videos.</div>', "/videos")


def view_strategy():
    s = db.jget("strategy", {}) or {}
    rows = "".join(f"<tr><td>{e(r['arm'])}{'' if r['active'] else ' <span class=pill>pausiert</span>'}</td><td>{r['pulls']}</td><td>{'' if r['mean'] is None else r['mean']}</td></tr>" for r in strategy.arm_table())
    t = db.jget("trend_brief", {}) or {}
    body = f"""<h2>Strategie-Notiz</h2><div class="card">{e(s.get('note', '—'))}<div class="mut">Stand: {fmt_ts(s.get('ts'))}</div></div>
<h2>Trend-Briefing</h2><div class="card"><div>Thema: {e((t.get('theme') or {}).get('name', '—'))}</div><div class="mut">Twist: {e((t.get('llm_twist') or {}).get('twist', '—'))}</div><div class="mut">Fan-Wünsche offen: {len(t.get('fan_requests', []))}</div></div>
<h2>Was funktioniert (Bandit-Statistik)</h2><div class="card"><table><tr><th>Baustein</th><th>Tests</th><th>Ø Score</th></tr>{rows}</table>
<div class="mut">Score 0–1 = Perzentil eines Videos 48 h nach Veröffentlichung (Aufrufe + Likes + 3×Kommentare + 5×Shares). Bessere Bausteine werden häufiger gewählt.</div></div>"""
    return page("Strategie", body, "/strategy")


def view_league():
    rows = ""
    for i, r in enumerate(creative.league_table(), 1):
        c = "#%02x%02x%02x" % brand.orb_color(r["orb"])
        rows += f'<tr><td>{i}</td><td><span class="dot" style="background:{c}"></span> <b>{r["orb"]}</b></td><td>{r["wins"]}-{r["losses"]}</td><td>{r["elo"]:.0f}</td></tr>'
    chars = "".join(f'<tr><td><span class="dot" style="background:#%02x%02x%02x"></span> {n}</td><td class="mut">{e(v["personality"])}</td></tr>' % v["color"] for n, v in brand.ORBS.items())
    body = f'<h2>Saison 1 – Tabelle</h2><div class="card"><table><tr><th>#</th><th>Orb</th><th>W-L</th><th>Elo</th></tr>{rows}</table></div><h2>Charaktere</h2><div class="card"><table>{chars}</table></div>'
    return page("Liga", body, "/league")


def view_settings(msg=""):
    s = {k: db.setting(k) for k in config.DEFAULTS}
    sel = lambda name, opts: "".join(f'<option value="{v}" {"selected" if s[name] == v else ""}>{l}</option>' for v, l in opts)
    body = f"""{f'<div class="card pill ok">{e(msg)}</div>' if msg else ''}
<h2>Automatik</h2><form method="post" action="/action" class="card"><input type="hidden" name="a" value="settings">
<label>Videos pro Tag (Start 2–3)</label><select name="posts_per_day">{sel('posts_per_day', [(str(i), str(i)) for i in range(1, 7)])}</select>
<label>Uhrzeiten ({e(config.TIMEZONE)}), kommagetrennt</label><input name="post_times" value="{e(s['post_times'])}">
<label>Veröffentlichung</label><select name="publish_mode">{sel('publish_mode', [('inbox', 'Entwurf in TikTok-App (empfohlen bis Audit)'), ('direct', 'Direkt veröffentlichen (nach Audit)'), ('off', 'Nur produzieren')])}</select>
<label>Sichtbarkeit bei Direktpost</label><select name="direct_privacy">{sel('direct_privacy', [('SELF_ONLY', 'Nur ich (vor Audit Pflicht)'), ('PUBLIC_TO_EVERYONE', 'Öffentlich'), ('FOLLOWER_OF_CREATOR', 'Follower')])}</select>
<label>Freigabe bei Direktpost</label><select name="auto_approve">{sel('auto_approve', [('0', 'Jedes Video im Dashboard freigeben'), ('1', 'Automatisch (eigene Verantwortung, s. Hinweis)')])}</select>
<label>KI-Label (is_aigc) setzen</label><select name="is_aigc">{sel('is_aigc', [('0', 'Nein – reine Code-Animation'), ('1', 'Ja')])}</select>
<div style="margin-top:12px"><button class="btn acc">Speichern</button></div>
<p class="mut">Hinweis: TikTok verlangt für die API-Freigabe, dass Creator jeden Post vor der Veröffentlichung sehen und bestätigen können. Vollautomatisches Posten kann gegen die Entwicklerrichtlinien verstoßen.</p></form>
<h2>Fan-Wünsche</h2><form method="post" action="/action" class="card"><input type="hidden" name="a" value="fan">
<label>Häufige Kommentare einfügen (z. B. „VOLT vs FROST rematch“)</label><textarea name="text" rows="3"></textarea>
<div style="margin-top:8px"><button class="btn">Hinzufügen</button></div><p class="mut">Die offizielle API liefert keine Kommentartexte – Wünsche hier einzutragen ist optional, Orb-Namen werden erkannt.</p></form>
<h2>Sofort</h2><form method="post" action="/action" class="card row"><button class="btn" name="a" value="run_analytics">Kennzahlen jetzt abrufen</button><button class="btn" name="a" value="run_strategy">Strategie-Review jetzt</button></form>"""
    return page("Steuerung", body, "/settings")


def view_logs():
    rows = db.q("SELECT * FROM logs ORDER BY ts DESC LIMIT 150")
    col = {"ERROR": "var(--bad)", "WARN": "var(--acc)"}
    txt = "".join(f'<div style="color:{col.get(r["level"], "inherit")}">{fmt_ts(r["ts"])} [{e(r["agent"])}] {e(r["msg"])}</div>' for r in rows)
    return page("Logs", f'<div class="card log">{txt or "—"}</div>', "/logs")


LEGAL = """<h2>{t}</h2><div class="card"><p>ORB LEAGUE ist ein privat betriebenes Tool, das ausschließlich Videos für den eigenen TikTok-Account
des Betreibers erstellt und über die offizielle TikTok Content Posting API hochlädt.</p>
<p>Verarbeitete Daten: OAuth-Token des eigenen Accounts sowie öffentliche Kennzahlen der eigenen Videos (Aufrufe, Likes, Kommentare,
Shares, Follower) über die TikTok Display API. Es werden keine Daten Dritter erhoben, verkauft oder weitergegeben.
Tokens werden verschlüsselt übertragen und lokal auf dem Server gespeichert; die Verbindung kann jederzeit in den TikTok-Einstellungen
widerrufen werden.</p><p>Alle Videoinhalte (Grafik, Animation, Ton) werden vom Tool selbst per Code erzeugt.</p></div>"""


class H(BaseHTTPRequestHandler):
    server_version = "OrbLeague/1"

    def log_message(self, *a):
        pass

    def _authed(self):
        if not config.DASHBOARD_PASSWORD:
            return True
        h = self.headers.get("Authorization", "")
        if h.startswith("Basic "):
            try:
                u, p = base64.b64decode(h[6:]).decode().split(":", 1)
                return u == config.DASHBOARD_USER and p == config.DASHBOARD_PASSWORD
            except Exception:
                return False
        return False

    def _send(self, code, body, ctype="text/html; charset=utf-8", headers=None):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(b)

    def _redirect(self, to):
        self.send_response(303)
        self.send_header("Location", to)
        self.end_headers()

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        path, qs = u.path, urllib.parse.parse_qs(u.query)
        if not path.startswith(PUBLIC) and not self._authed():
            return self._send(401, "Login erforderlich", headers={"WWW-Authenticate": 'Basic realm="ORB LEAGUE"'})
        try:
            if path == "/":
                return self._send(200, view_home())
            if path == "/videos":
                return self._send(200, view_videos())
            if path == "/strategy":
                return self._send(200, view_strategy())
            if path == "/league":
                return self._send(200, view_league())
            if path == "/settings":
                return self._send(200, view_settings(qs.get("msg", [""])[0]))
            if path == "/logs":
                return self._send(200, view_logs())
            m = VERIFY_RE.match(path)
            if m:  # TikTok-Domainverifizierung: Datei liegt in DATA_DIR (siehe README)
                f = config.DATA_DIR / m.group(1)
                if f.exists():
                    return self._send(200, f.read_text(), "text/plain; charset=utf-8")
                return self._send(404, "not found", "text/plain")
            if path == "/healthz":
                return self._send(200, "ok", "text/plain")
            if path == "/api/status":
                o = overview_numbers()
                o["paused"] = db.setting("paused") == "1"
                o["heartbeat"] = float(db.setting("heartbeat") or 0)
                return self._send(200, json.dumps(o), "application/json")
            if path.startswith("/media/"):
                return self._media(int(path.rsplit("/", 1)[1]))
            if path == "/auth/tiktok":
                if not config.TIKTOK_CLIENT_KEY and not config.TIKTOK_MOCK:
                    return self._send(200, page("TikTok", '<div class="card">Bitte zuerst TIKTOK_CLIENT_KEY und TIKTOK_CLIENT_SECRET in der .env eintragen (siehe README).</div>'))
                if config.TIKTOK_MOCK:
                    tiktok.auth_url()
                    tiktok.exchange_code("mock", db.setting("oauth_state"))
                    return self._redirect("/?mock=1")
                return self._redirect(tiktok.auth_url())
            if path == "/auth/callback":
                if "error" in qs:
                    return self._send(400, page("TikTok", f'<div class="card">Abgebrochen: {e(qs.get("error_description", qs["error"])[0])}</div>'))
                tiktok.exchange_code(qs.get("code", [""])[0], qs.get("state", [""])[0])
                return self._redirect("/")
            if path == "/privacy":
                return self._send(200, page("Datenschutz", LEGAL.format(t="Datenschutzerklärung")))
            if path == "/terms":
                return self._send(200, page("Nutzungsbedingungen", LEGAL.format(t="Nutzungsbedingungen")))
            return self._send(404, page("404", '<div class="card">Nicht gefunden</div>'))
        except Exception as ex:
            db.log_exc("web", f"GET {path}")
            return self._send(500, page("Fehler", f'<div class="card">Fehler: {e(ex)}</div>'))

    def _media(self, eid):
        ep = db.episode(eid)
        if not ep or not ep.get("video_path") or not os.path.exists(ep["video_path"]):
            return self._send(404, "not found", "text/plain")
        size = os.path.getsize(ep["video_path"])
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if m:
                if m.group(1):
                    start = int(m.group(1))
                    end = int(m.group(2)) if m.group(2) else size - 1
                else:
                    start = size - int(m.group(2))
        end = min(end, size - 1)
        length = end - start + 1
        self.send_response(206 if rng else 200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if rng:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(ep["video_path"], "rb") as f:
            f.seek(start)
            left = length
            while left > 0:
                chunk = f.read(min(1 << 16, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                left -= len(chunk)

    def do_POST(self):
        if not self._authed():
            return self._send(401, "Login erforderlich", headers={"WWW-Authenticate": 'Basic realm="ORB LEAGUE"'})
        n = int(self.headers.get("Content-Length", 0))
        form = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(n).decode()).items()}
        a = form.get("a", "")
        back = self.headers.get("Referer") or "/"
        try:
            if a == "pause":
                db.set_setting("paused", "1"); db.log("web", "Automatik gestoppt")
            elif a == "resume":
                db.set_setting("paused", "0"); db.log("web", "Automatik fortgesetzt")
            elif a.startswith("approve:"):
                db.update_episode(int(a.split(":")[1]), approved=1, error=None)
            elif a == "approve_all":
                for x in db.episodes("status IN ('ready','planned') AND approved=0"):
                    db.update_episode(x["id"], approved=1, error=None)
            elif a.startswith("reject:"):
                ep = db.episode(int(a.split(":")[1]))
                db.update_episode(ep["id"], status="rejected")
                revert_league(ep)
                db.log("web", f"Ep {ep['episode_no']} abgelehnt – Slot wird neu befüllt")
            elif a.startswith("retry:"):
                db.update_episode(int(a.split(":")[1]), status="ready", error=None, attempts=0, scheduled_at=time.time() + 120)
            elif a == "settings":
                for k in ("posts_per_day", "post_times", "publish_mode", "direct_privacy", "auto_approve", "is_aigc"):
                    if k in form:
                        v = form[k].strip()
                        if k == "post_times" and not re.fullmatch(r"\s*\d{1,2}:\d{2}(\s*,\s*\d{1,2}:\d{2})*\s*", v):
                            continue
                        db.set_setting(k, v)
                db.log("web", "Einstellungen geändert")
                return self._redirect("/settings?msg=Gespeichert")
            elif a == "fan" and form.get("text", "").strip():
                db.run("INSERT INTO fan_requests(ts, text) VALUES(?,?)", (time.time(), form["text"].strip()[:500]))
                return self._redirect("/settings?msg=Fan-Wunsch+gespeichert")
            elif a == "run_analytics":
                db.set_setting("last_analytics", 0)
            elif a == "run_strategy":
                db.set_setting("last_strategy", 0)
        except Exception:
            db.log_exc("web", f"Aktion {a}")
        return self._redirect(back)


def serve():
    srv = ThreadingHTTPServer((config.WEB_HOST, config.WEB_PORT), H)
    db.log("web", f"Dashboard auf Port {config.WEB_PORT}")
    srv.serve_forever()
