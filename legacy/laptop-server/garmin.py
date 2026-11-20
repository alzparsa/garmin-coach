"""Garmin Connect Personal API client + sync into SQLite.

Official docs: https://developer.garmin.com/gc-developer-program/personal/personal-faq/
- Create a key in Garmin Connect Web (Personal API Key page). Keys last 30d..1y.
- Exchange key for a 24h bearer token (no refresh tokens; just mint a new one).
- Read-only GET endpoints on personal.connectapi.garmin.com.

Garmin's exact JSON field names aren't all documented publicly, so the field
extraction below is defensive (tries several names, searches nested objects),
and the raw JSON is stored so mappings can be fixed later without re-syncing.
"""
import base64
import datetime as dt
import json
import time
import urllib.error
import urllib.parse
import urllib.request

import db
import secrets_store

BASE = "https://personal.connectapi.garmin.com"
TOKEN_PATH = "/personalapitoken-service/personal-api/personal-api-key/token"
CHUNK_DAYS = 28  # steps/stress cap at 28, sleep/body battery at 31 -> use 28 for all

_token_cache = {"token": None, "exp": 0}


class GarminError(Exception):
    pass


def _http(method, url, headers=None, timeout=30):
    req = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        body = e.read()[:500].decode("utf-8", "replace")
        raise GarminError(f"HTTP {e.code} on {url.split('?')[0]}: {body}") from None
    except urllib.error.URLError as e:
        raise GarminError(f"Network error: {e.reason}") from None


def _jwt_exp(token):
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get("exp", 0)
    except Exception:
        return 0


def get_token(force=False):
    if not force and _token_cache["token"] and _token_cache["exp"] - time.time() > 3600:
        return _token_cache["token"]
    key = secrets_store.get("garmin_api_key")
    if not key:
        raise GarminError("No Garmin Personal API key set. Add it in Settings.")
    _, body = _http("POST", BASE + TOKEN_PATH, {"Authorization": f"ApiKey {key}", "Accept": "application/json"})
    text = body.decode("utf-8").strip()
    token = None
    # The response may be a raw JWT or JSON wrapping one; handle both.
    if text.startswith("{"):
        data = json.loads(text)
        for k in ("access_token", "accessToken", "token", "bearerToken"):
            if data.get(k):
                token = data[k]
                break
    else:
        token = text.strip('"')
    if not token:
        raise GarminError("Token endpoint returned no token: " + text[:200])
    _token_cache["token"] = token
    _token_cache["exp"] = _jwt_exp(token) or time.time() + 23 * 3600
    return token


def get(path, params=None):
    url = BASE + path
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    token = get_token()
    try:
        _, body = _http("GET", url, {"Authorization": f"Bearer {token}", "Accept": "application/json"})
    except GarminError as e:
        if "HTTP 401" in str(e):
            token = get_token(force=True)
            _, body = _http("GET", url, {"Authorization": f"Bearer {token}", "Accept": "application/json"})
        else:
            raise
    if not body:
        return None
    return json.loads(body)


# ---------- defensive field helpers ----------

def pick(obj, *names, default=None):
    """Find the first matching key anywhere in a nested dict/list (breadth-first)."""
    queue = [obj]
    seen = 0
    while queue and seen < 2000:
        cur = queue.pop(0)
        seen += 1
        if isinstance(cur, dict):
            for n in names:
                if n in cur and cur[n] not in (None, "", []):
                    return cur[n]
            queue.extend(v for v in cur.values() if isinstance(v, (dict, list)))
        elif isinstance(cur, list):
            queue.extend(v for v in cur if isinstance(v, (dict, list)))
    return default


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _as_list(data, *keys):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in keys:
            if isinstance(data.get(k), list):
                return data[k]
        for v in data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
    return []


def _date_of(item):
    d = pick(item, "calendarDate", "date", "summaryDate", "startTimeLocal", "startDate")
    return str(d)[:10] if d else None


def _ranges(start, end, days=CHUNK_DAYS):
    cur = start
    while cur <= end:
        stop = min(cur + dt.timedelta(days=days - 1), end)
        yield cur, stop
        cur = stop + dt.timedelta(days=1)


# ---------- sync ----------

def upsert_daily(date, fields, raw_part, raw_key):
    row = db.q1("SELECT raw FROM garmin_daily WHERE date=?", (date,))
    raw = json.loads(row["raw"]) if row and row["raw"] else {}
    raw[raw_key] = raw_part
    fields = {k: v for k, v in fields.items() if v is not None}
    if row:
        sets = ",".join(f"{k}=?" for k in fields) + ("," if fields else "") + "raw=?"
        db.ex(f"UPDATE garmin_daily SET {sets} WHERE date=?", list(fields.values()) + [json.dumps(raw), date])
    else:
        cols = list(fields) + ["date", "raw"]
        db.ex(f"INSERT INTO garmin_daily ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
              list(fields.values()) + [date, json.dumps(raw)])


def sync_activities(start, end, log):
    n, offset = 0, 0
    while True:
        data = get("/activitylist-service/activities/search/activities",
                   {"start": offset, "limit": 100, "startDate": start.isoformat(), "endDate": end.isoformat()})
        items = _as_list(data, "activityList", "activities")
        for a in items:
            aid = pick(a, "activityId")
            if not aid:
                continue
            st = pick(a, "startTimeLocal", "startTimeGMT") or ""
            atype = a.get("activityType")
            atype = atype.get("typeKey") if isinstance(atype, dict) else (atype or pick(a, "activityTypeKey"))
            row = (
                int(aid), str(st)[:10], str(st), a.get("activityName"), atype,
                _num(pick(a, "duration", "elapsedDuration")), _num(pick(a, "distance")),
                _num(pick(a, "averageHR", "avgHr")), _num(pick(a, "maxHR", "maxHr")),
                _num(pick(a, "calories")), _num(pick(a, "activityTrainingLoad", "trainingLoad")),
                _num(pick(a, "aerobicTrainingEffect")), _num(pick(a, "anaerobicTrainingEffect")),
                _num(pick(a, "averageSpeed")), _num(pick(a, "elevationGain")), json.dumps(a),
            )
            db.ex("""INSERT OR REPLACE INTO garmin_activities
                (activity_id,date,start_time,name,type,duration_s,distance_m,avg_hr,max_hr,calories,
                 training_load,aerobic_te,anaerobic_te,avg_speed,elevation_gain,raw)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", row)
            n += 1
        if len(items) < 100:
            break
        offset += 100
    log.append(f"activities: {n}")


def sync_daily_summaries(start, end, log):
    n = 0
    for s, e in _ranges(start, end):
        data = get("/usersummary-service/v2/dailysummaries", {"startDate": s.isoformat(), "endDate": e.isoformat()})
        for item in _as_list(data, "dailySummaries", "summaries"):
            d = _date_of(item)
            if not d:
                continue
            upsert_daily(d, {
                "resting_hr": _num(pick(item, "restingHeartRate", "restingHeartRateInBeatsPerMinute")),
                "steps": _num(pick(item, "totalSteps", "steps")),
                "stress_avg": _num(pick(item, "averageStressLevel", "avgStressLevel")),
                "body_battery_high": _num(pick(item, "bodyBatteryHighestValue", "highestBodyBattery")),
                "body_battery_low": _num(pick(item, "bodyBatteryLowestValue", "lowestBodyBattery")),
                "body_battery_charged": _num(pick(item, "bodyBatteryChargedValue", "charged")),
            }, item, "summary")
            n += 1
    log.append(f"daily summaries: {n}")


def sync_sleep(start, end, log):
    n = 0
    for s, e in _ranges(start, end):
        data = get("/sleep-service/sleep/dailySleepSummariesByDate",
                   {"startDate": s.isoformat(), "endDate": e.isoformat()})
        for item in _as_list(data, "dailySleepSummaries", "sleepSummaries"):
            d = _date_of(item)
            if not d:
                continue
            score = pick(item, "overallScore", "sleepScore")
            if isinstance(score, dict):
                score = score.get("value")
            upsert_daily(d, {
                "sleep_seconds": _num(pick(item, "sleepTimeSeconds", "totalSleepSeconds", "sleepTimeInSeconds")),
                "sleep_score": _num(score),
            }, item, "sleep")
            n += 1
    log.append(f"sleep nights: {n}")


def sync_hrv(start, end, log):
    n = 0
    for s, e in _ranges(start, end):
        data = get(f"/hrv-service/hrv/daily/{s.isoformat()}/{e.isoformat()}")
        for item in _as_list(data, "hrvSummaries", "summaries"):
            d = _date_of(item)
            if not d:
                continue
            upsert_daily(d, {
                "hrv_last_night": _num(pick(item, "lastNightAvg", "lastNightAverage")),
                "hrv_weekly_avg": _num(pick(item, "weeklyAvg", "weeklyAverage")),
                "hrv_status": pick(item, "status"),
            }, item, "hrv")
            n += 1
    log.append(f"hrv nights: {n}")


def sync(days=None):
    """Pull everything since last sync (or `days` back). Each source fails independently."""
    today = dt.date.today()
    last = db.get_setting("garmin_last_sync")
    if days:
        start = today - dt.timedelta(days=days)
    elif last:
        start = dt.date.fromisoformat(last) - dt.timedelta(days=3)  # re-pull a few days for late syncs
    else:
        start = today - dt.timedelta(days=120)
    log, errors = [], []
    get_token()  # fail fast on bad key
    for fn in (sync_activities, sync_daily_summaries, sync_sleep, sync_hrv):
        try:
            fn(start, today, log)
        except Exception as e:  # keep going; show what failed
            errors.append(f"{fn.__name__}: {e}")
    db.set_setting("garmin_last_sync", today.isoformat())
    db.set_setting("garmin_last_sync_at", dt.datetime.now().isoformat(timespec="minutes"))
    return {"from": start.isoformat(), "to": today.isoformat(), "log": log, "errors": errors}
