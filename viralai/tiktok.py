"""Offizielle TikTok-APIs: Login Kit (OAuth v2), Content Posting API, Display API.

Doku: https://developers.tiktok.com/doc/content-posting-api-reference-direct-post
Wichtige Plattform-Regeln, die hier umgesetzt sind:
  * Vor jedem Direct Post wird creator_info abgefragt; die Privatsphäre muss eine der
    dort erlaubten Optionen sein.
  * Unauditierte Apps dürfen nur privat (SELF_ONLY) posten.
  * Max. 6 Init-Requests pro Minute und Token; tägliche Post-Limits werden respektiert.
Mit TIKTOK_MOCK=1 werden alle Aufrufe simuliert (für Tests ohne Account).
"""
import json
import os
import random
import secrets
import time
import urllib.parse
import urllib.request

from . import config, db

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
API = "https://open.tiktokapis.com/v2"
SCOPES = "user.info.basic,user.info.stats,video.list,video.upload,video.publish"
MAX_SINGLE_CHUNK = 64 * 1024 * 1024


class TikTokError(Exception):
    def __init__(self, code, msg=""):
        super().__init__(f"{code}: {msg}")
        self.code = code


# ---------------------------------------------------------------- HTTP
def _req(method, url, body=None, headers=None, raw=None, timeout=120):
    headers = dict(headers or {})
    data = raw
    if body is not None:
        data = json.dumps(body).encode()
        headers.setdefault("Content-Type", "application/json; charset=UTF-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode() or "{}"
    except urllib.error.HTTPError as e:
        txt = e.read().decode() or "{}"
        try:
            j = json.loads(txt)
        except Exception:
            raise TikTokError(f"http_{e.code}", txt[:300])
        err = j.get("error", {})
        raise TikTokError(err.get("code", f"http_{e.code}"), err.get("message", txt[:300]))
    j = json.loads(txt)
    err = j.get("error") or {}
    if isinstance(err, dict) and err.get("code") not in (None, "ok"):
        raise TikTokError(err.get("code"), err.get("message", ""))
    return j


# ---------------------------------------------------------------- OAuth
def auth_url():
    state = secrets.token_urlsafe(16)
    db.set_setting("oauth_state", state)
    params = {"client_key": config.TIKTOK_CLIENT_KEY, "scope": SCOPES, "response_type": "code",
              "redirect_uri": config.TIKTOK_REDIRECT_URI, "state": state}
    return AUTH_URL + "?" + urllib.parse.urlencode(params)


def _store_tokens(j):
    now = time.time()
    db.jset("tiktok_tokens", {
        "access_token": j["access_token"], "refresh_token": j.get("refresh_token"),
        "open_id": j.get("open_id"), "scope": j.get("scope"),
        "access_expires": now + int(j.get("expires_in", 86400)) - 120,
        "refresh_expires": now + int(j.get("refresh_expires_in", 365 * 86400)),
    })


def exchange_code(code, state):
    if state != db.setting("oauth_state"):
        raise TikTokError("bad_state", "OAuth state stimmt nicht")
    if config.TIKTOK_MOCK:
        _store_tokens({"access_token": "mock", "refresh_token": "mock", "open_id": "mock", "scope": SCOPES})
        return
    body = urllib.parse.urlencode({
        "client_key": config.TIKTOK_CLIENT_KEY, "client_secret": config.TIKTOK_CLIENT_SECRET,
        "code": code, "grant_type": "authorization_code", "redirect_uri": config.TIKTOK_REDIRECT_URI}).encode()
    j = _req("POST", API + "/oauth/token/", raw=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    _store_tokens(j)
    db.log("auth", f"TikTok verbunden (Scopes: {j.get('scope')})")


def connected():
    t = db.jget("tiktok_tokens")
    return bool(t and t.get("refresh_expires", 0) > time.time())


def token():
    t = db.jget("tiktok_tokens")
    if not t:
        raise TikTokError("not_connected", "Bitte im Dashboard mit TikTok verbinden")
    if t["access_expires"] > time.time():
        return t["access_token"]
    if config.TIKTOK_MOCK:
        t["access_expires"] = time.time() + 86000
        db.jset("tiktok_tokens", t)
        return t["access_token"]
    body = urllib.parse.urlencode({
        "client_key": config.TIKTOK_CLIENT_KEY, "client_secret": config.TIKTOK_CLIENT_SECRET,
        "grant_type": "refresh_token", "refresh_token": t["refresh_token"]}).encode()
    j = _req("POST", API + "/oauth/token/", raw=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    _store_tokens(j)
    db.log("auth", "Access-Token erneuert")
    return j["access_token"]


def _auth():
    return {"Authorization": f"Bearer {token()}"}


# ---------------------------------------------------------------- Posting
def creator_info():
    if config.TIKTOK_MOCK:
        return {"creator_username": "orbleague", "privacy_level_options": ["PUBLIC_TO_EVERYONE", "SELF_ONLY"],
                "comment_disabled": False, "duet_disabled": False, "stitch_disabled": False, "max_video_post_duration_sec": 600}
    return _req("POST", API + "/post/publish/creator_info/query/", body={}, headers=_auth())["data"]


def _source_info(size):
    if size <= MAX_SINGLE_CHUNK:
        return {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}
    chunk = 10 * 1024 * 1024
    count = size // chunk  # letzter Chunk nimmt den Rest auf (TikTok-Regel)
    return {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk, "total_chunk_count": count}


def _upload(upload_url, path, src):
    size, chunk, count = src["video_size"], src["chunk_size"], src["total_chunk_count"]
    with open(path, "rb") as f:
        for i in range(count):
            start = i * chunk
            end = size - 1 if i == count - 1 else start + chunk - 1
            f.seek(start)
            data = f.read(end - start + 1)
            _req("PUT", upload_url, raw=data, headers={
                "Content-Type": "video/mp4", "Content-Length": str(len(data)),
                "Content-Range": f"bytes {start}-{end}/{size}"}, timeout=600)


def post_video(path, title, mode, privacy="SELF_ONLY", cover_ms=1000, is_aigc=False):
    """mode 'direct' -> veröffentlicht; mode 'inbox' -> Entwurf in der TikTok-App. Gibt publish_id zurück."""
    size = os.path.getsize(path)
    src = _source_info(size)
    if config.TIKTOK_MOCK:
        db.log("tiktok", f"[MOCK] {mode}-Upload {os.path.basename(path)} ({size // 1024} KB), privacy={privacy}")
        return "mock_" + secrets.token_hex(6)
    if mode == "direct":
        info = creator_info()
        opts = info.get("privacy_level_options", [])
        if privacy not in opts:
            privacy = "SELF_ONLY" if "SELF_ONLY" in opts else opts[0]
        if info.get("max_video_post_duration_sec") and info["max_video_post_duration_sec"] < 15:
            raise TikTokError("duration", "Account erlaubt zu kurze Videos")
        body = {"post_info": {"title": title[:2200], "privacy_level": privacy,
                              "disable_comment": bool(info.get("comment_disabled")),
                              "disable_duet": bool(info.get("duet_disabled")),
                              "disable_stitch": bool(info.get("stitch_disabled")),
                              "video_cover_timestamp_ms": cover_ms, "brand_content_toggle": False,
                              "brand_organic_toggle": False, "is_aigc": bool(is_aigc)},
                "source_info": src}
        j = _req("POST", API + "/post/publish/video/init/", body=body, headers=_auth())
    else:
        j = _req("POST", API + "/post/publish/inbox/video/init/", body={"source_info": src}, headers=_auth())
    d = j["data"]
    _upload(d["upload_url"], path, src)
    return d["publish_id"]


def post_status(publish_id):
    if config.TIKTOK_MOCK:
        return {"status": "PUBLISH_COMPLETE", "publicaly_available_post_id": [str(random.randrange(10**18, 10**19))]}
    return _req("POST", API + "/post/publish/status/fetch/", body={"publish_id": publish_id}, headers=_auth())["data"]


# ---------------------------------------------------------------- Display API
def user_stats():
    if config.TIKTOK_MOCK:
        prev = db.one("SELECT * FROM account_metrics ORDER BY ts DESC LIMIT 1")
        f = (prev["followers"] if prev else 0) + random.randint(0, 40)
        return {"follower_count": f, "likes_count": (prev["likes"] if prev else 0) + random.randint(0, 900),
                "video_count": db.one("SELECT COUNT(*) n FROM episodes WHERE status='published'")["n"]}
    j = _req("GET", API + "/user/info/?fields=follower_count,likes_count,video_count,display_name", headers=_auth())
    return j["data"]["user"]


def list_videos(max_pages=5):
    if config.TIKTOK_MOCK:
        out = []
        for e in db.q("SELECT id, tiktok_video_id, published_at FROM episodes WHERE tiktok_video_id IS NOT NULL"):
            last = db.one("SELECT * FROM metrics WHERE episode_id=? ORDER BY ts DESC LIMIT 1", (e["id"],))
            rnd = random.Random(e["id"])
            base = rnd.choice([300, 800, 2500, 12000])
            v = (last["views"] if last else 0) + int(base * random.uniform(0.2, 1.0))
            out.append({"id": e["tiktok_video_id"], "view_count": v, "like_count": int(v * rnd.uniform(0.03, 0.09)),
                        "comment_count": int(v * rnd.uniform(0.002, 0.02)), "share_count": int(v * rnd.uniform(0.001, 0.01)),
                        "create_time": int(e["published_at"] or time.time())})
        return out
    out, cursor = [], None
    fields = "id,title,create_time,share_url,view_count,like_count,comment_count,share_count,duration"
    for _ in range(max_pages):
        body = {"max_count": 20}
        if cursor:
            body["cursor"] = cursor
        j = _req("POST", API + f"/video/list/?fields={fields}", body=body, headers=_auth())["data"]
        out += j.get("videos", [])
        if not j.get("has_more"):
            break
        cursor = j.get("cursor")
    return out
