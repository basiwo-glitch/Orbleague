"""SQLite-Speicher: gemeinsames "Blackboard" aller Agenten. Neustart-sicher."""
import json
import sqlite3
import threading
import time
import traceback

from . import config

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS episodes(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at REAL, status TEXT, format TEXT, orbs TEXT, mods TEXT, seed INTEGER, drama REAL,
  hook TEXT, hook_style TEXT, hook_sub TEXT, header TEXT, captions TEXT, cta TEXT,
  post_text TEXT, episode_no INTEGER, season INTEGER DEFAULT 1, arms TEXT, idea TEXT,
  scheduled_at REAL, video_path TEXT, duration REAL, winner TEXT, result TEXT, qa TEXT,
  approved INTEGER DEFAULT 0, publish_id TEXT, tiktok_video_id TEXT, share_url TEXT,
  published_at REAL, reward REAL, attempts INTEGER DEFAULT 0, error TEXT);
CREATE INDEX IF NOT EXISTS ep_status ON episodes(status);
CREATE TABLE IF NOT EXISTS metrics(episode_id INTEGER, ts REAL, views INTEGER, likes INTEGER, comments INTEGER, shares INTEGER);
CREATE TABLE IF NOT EXISTS account_metrics(ts REAL, followers INTEGER, likes INTEGER, videos INTEGER);
CREATE TABLE IF NOT EXISTS league(orb TEXT PRIMARY KEY, wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0, elo REAL DEFAULT 1000);
CREATE TABLE IF NOT EXISTS arms(arm TEXT PRIMARY KEY, pulls INTEGER DEFAULT 0, reward_sum REAL DEFAULT 0, active INTEGER DEFAULT 1, note TEXT);
CREATE TABLE IF NOT EXISTS costs(ts REAL, category TEXT, usd REAL, note TEXT);
CREATE TABLE IF NOT EXISTS logs(ts REAL, level TEXT, agent TEXT, msg TEXT);
CREATE TABLE IF NOT EXISTS fan_requests(ts REAL, text TEXT, used INTEGER DEFAULT 0);
"""


def conn():
    c = getattr(_local, "c", None)
    if c is None:
        c = sqlite3.connect(config.DB_PATH, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        _local.c = c
    return c


def q(sql, args=()):
    return [dict(r) for r in conn().execute(sql, args).fetchall()]


def one(sql, args=()):
    r = conn().execute(sql, args).fetchone()
    return dict(r) if r else None


def run(sql, args=()):
    c = conn()
    cur = c.execute(sql, args)
    c.commit()
    return cur.lastrowid


# ---------------------------------------------------------------- Settings
def setting(key):
    r = one("SELECT value FROM settings WHERE key=?", (key,))
    if r:
        return r["value"]
    return config.DEFAULTS.get(key)


def set_setting(key, value):
    run("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))


def jget(key, default=None):
    v = setting(key)
    if v is None:
        return default
    try:
        return json.loads(v)
    except Exception:
        return default


def jset(key, obj):
    set_setting(key, json.dumps(obj))


# ---------------------------------------------------------------- Logging
def log(agent, msg, level="INFO"):
    ts = time.time()
    try:
        run("INSERT INTO logs VALUES(?,?,?,?)", (ts, level, agent, str(msg)[:4000]))
        run("DELETE FROM logs WHERE ts < ?", (ts - 30 * 86400,))
    except Exception:
        pass
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{level}] {agent}: {msg}"
    print(line, flush=True)
    try:
        with open(config.LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def log_exc(agent, msg):
    log(agent, f"{msg}: {traceback.format_exc()[-1500:]}", "ERROR")


def add_cost(category, usd, note=""):
    run("INSERT INTO costs VALUES(?,?,?,?)", (time.time(), category, float(usd), note))


def cost_since(ts, category=None):
    if category:
        r = one("SELECT COALESCE(SUM(usd),0) s FROM costs WHERE ts>=? AND category=?", (ts, category))
    else:
        r = one("SELECT COALESCE(SUM(usd),0) s FROM costs WHERE ts>=?", (ts,))
    return r["s"]


# ---------------------------------------------------------------- Episodes
JSON_FIELDS = ("orbs", "mods", "captions", "arms", "idea", "result", "qa")


def episode(eid):
    e = one("SELECT * FROM episodes WHERE id=?", (eid,))
    return _decode(e) if e else None


def episodes(where="1=1", args=(), order="id DESC", limit=200):
    return [_decode(e) for e in q(f"SELECT * FROM episodes WHERE {where} ORDER BY {order} LIMIT {int(limit)}", args)]


def _decode(e):
    for f in JSON_FIELDS:
        if e.get(f):
            try:
                e[f] = json.loads(e[f])
            except Exception:
                pass
    return e


def update_episode(eid, **kw):
    sets, vals = [], []
    for k, v in kw.items():
        if k in JSON_FIELDS and not isinstance(v, str) and v is not None:
            v = json.dumps(v)
        sets.append(f"{k}=?")
        vals.append(v)
    vals.append(eid)
    run(f"UPDATE episodes SET {', '.join(sets)} WHERE id=?", vals)


def create_episode(**kw):
    kw.setdefault("created_at", time.time())
    cols, vals = [], []
    for k, v in kw.items():
        if k in JSON_FIELDS and not isinstance(v, str) and v is not None:
            v = json.dumps(v)
        cols.append(k)
        vals.append(v)
    return run(f"INSERT INTO episodes({','.join(cols)}) VALUES({','.join('?' * len(cols))})", vals)
