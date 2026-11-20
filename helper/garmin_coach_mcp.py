#!/usr/bin/env python3
"""Garmin helper for the Coach app.

A tiny local MCP server that the Claude desktop app runs on your laptop. It reads your
data from Garmin's free, official, read-only Personal API and hands it to the Coach page
when you tap "Sync Garmin". Python 3.10+ standard library only; nothing to install.

Your Garmin key stays on this laptop: it is read from the GARMIN_PERSONAL_API_KEY
environment variable (set in Claude's config) or from garmin_key.txt next to this file.
"""
import base64
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("GARMIN_BASE", "https://personal.connectapi.garmin.com")
TOKEN_PATH = "/personalapitoken-service/personal-api/personal-api-key/token"
CHUNK = 28            # Garmin caps several range calls at 28-31 days
MAX_RANGE_DAYS = 400
HERE = os.path.dirname(os.path.abspath(__file__))
_token = {"value": None, "exp": 0, "key": None}


def log(*a):
    print(*a, file=sys.stderr, flush=True)   # stdout is reserved for the protocol


class GarminError(Exception):
    pass


# ---------------- Garmin Personal API ----------------

def api_key():
    k = os.environ.get("GARMIN_PERSONAL_API_KEY", "").strip()
    if not k:
        try:
            with open(os.path.join(HERE, "garmin_key.txt"), encoding="utf-8-sig") as f:
                k = f.read().strip()
        except FileNotFoundError:
            pass
    if not k:
        raise GarminError("No Garmin key found. Put your Personal API key in garmin_key.txt next to garmin_coach_mcp.py, then restart Claude.")
    return k


def http(method, url, headers, timeout=40):
    req = urllib.request.Request(url, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        body = e.read()[:300].decode("utf-8", "replace")
        if e.code in (401, 403) and TOKEN_PATH in url:
            raise GarminError("Garmin rejected the API key. It may have expired or been deleted. Create a new one in Garmin Connect (Personal API Key) and update garmin_key.txt.") from None
        raise GarminError(f"Garmin returned HTTP {e.code} for {url.split('?')[0].replace(BASE, '')}: {body}") from None
    except urllib.error.URLError as e:
        raise GarminError(f"Couldn't reach Garmin ({e.reason}). Check the laptop's internet connection.") from None


def jwt_exp(tok):
    try:
        p = tok.split(".")[1]
        p += "=" * (-len(p) % 4)
        return json.loads(base64.urlsafe_b64decode(p)).get("exp", 0)
    except Exception:
        return 0


def token(force=False):
    key = api_key()
    if not force and _token["value"] and _token["key"] == key and _token["exp"] - time.time() > 600:
        return _token["value"]   # re-mint automatically when garmin_key.txt changes
    # The token service rejects "Accept: application/json" with HTTP 406, so ask for any format,
    # falling back to plain text if it is picky about that too.
    text, last_err = None, None
    for accept in ("*/*", "text/plain", "application/json"):
        try:
            text = http("POST", BASE + TOKEN_PATH, {"Authorization": f"ApiKey {key}", "Accept": accept}).decode().strip()
            break
        except GarminError as e:
            last_err = e
            if "HTTP 406" not in str(e):
                raise
    if text is None:
        raise last_err
    tok = None
    if text.startswith("{"):
        d = json.loads(text)
        tok = next((d[k] for k in ("access_token", "accessToken", "token", "bearerToken") if d.get(k)), None)
    else:
        tok = text.strip('"')
    if not tok:
        raise GarminError("Garmin's token endpoint returned no token.")
    _token.update(value=tok, exp=jwt_exp(tok) or time.time() + 23 * 3600, key=key)
    return tok


def get(path, params=None):
    url = BASE + path + (("?" + urllib.parse.urlencode(params)) if params else "")
    hdr = lambda: {"Authorization": f"Bearer {token()}", "Accept": "application/json"}
    try:
        body = http("GET", url, hdr())
    except GarminError as e:
        if "HTTP 401" not in str(e):
            raise
        token(force=True)
        body = http("GET", url, hdr())
    return json.loads(body) if body else None


# ---------------- defensive field helpers ----------------

def pick(obj, *names):
    q, n = [obj], 0
    while q and n < 3000:
        cur = q.pop(0); n += 1
        if isinstance(cur, dict):
            for k in names:
                if k in cur and cur[k] not in (None, "", []):
                    return cur[k]
            q.extend(v for v in cur.values() if isinstance(v, (dict, list)))
        elif isinstance(cur, list):
            q.extend(v for v in cur if isinstance(v, (dict, list)))
    return None


def dig(obj, *path):
    for k in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(k)
    return obj


def num(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def as_list(data, *keys):
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


def date_of(item):
    d = pick(item, "calendarDate", "date", "summaryDate", "startTimeLocal", "startDate")
    return str(d)[:10] if d else None


def ranges(start, end):
    cur = start
    while cur <= end:
        stop = min(cur + dt.timedelta(days=CHUNK - 1), end)
        yield cur, stop
        cur = stop + dt.timedelta(days=1)


# ---------------- sync ----------------

def fetch_activities(start, end, samples):
    out, offset = [], 0
    while True:
        data = get("/activitylist-service/activities/search/activities",
                   {"start": offset, "limit": 100, "startDate": start.isoformat(), "endDate": end.isoformat()})
        items = as_list(data, "activityList", "activities")
        if items and "activities" not in samples:
            samples["activities"] = sorted(items[0].keys())[:80]
        for a in items:
            aid = pick(a, "activityId")
            if not aid:
                continue
            st = str(pick(a, "startTimeLocal", "startTimeGMT") or "")
            t = a.get("activityType")
            t = t.get("typeKey") if isinstance(t, dict) else (t or pick(a, "activityTypeKey"))
            out.append({
                "id": int(aid), "date": st[:10], "start_time": st, "name": a.get("activityName"), "type": t,
                "duration_s": num(pick(a, "duration", "elapsedDuration")), "distance_m": num(pick(a, "distance")),
                "avg_hr": num(pick(a, "averageHR", "avgHr")), "max_hr": num(pick(a, "maxHR", "maxHr")),
                "calories": num(pick(a, "calories")), "training_load": num(pick(a, "activityTrainingLoad", "trainingLoad")),
                "aerobic_te": num(pick(a, "aerobicTrainingEffect")), "anaerobic_te": num(pick(a, "anaerobicTrainingEffect")),
                "elevation_gain": num(pick(a, "elevationGain")),
            })
        if len(items) < 100:
            return out
        offset += 100


def fetch_days(start, end, samples, errors):
    days = {}

    def day(d):
        return days.setdefault(d, {"date": d})

    def run(label, fn):
        try:
            fn()
        except GarminError as e:
            errors.append(f"{label}: {e}")

    def summaries():
        for s, e in ranges(start, end):
            items = as_list(get("/usersummary-service/v2/dailysummaries", {"startDate": s.isoformat(), "endDate": e.isoformat()}), "dailySummaries", "summaries")
            if items and "daily_summaries" not in samples:
                samples["daily_summaries"] = sorted(items[0].keys())[:80]
            for it in items:
                d = date_of(it)
                if not d:
                    continue
                x = day(d)
                g = lambda *path: dig(it, *path)
                # v2 layout (confirmed Nov 2026): heartRate.restingValue, movement.steps.value, stress.avgLevel, bodyBattery.maxValue
                x["rhr"] = num(g("heartRate", "restingValue") or it.get("restingHeartRate"))
                x["steps"] = num(g("movement", "steps", "value") or it.get("totalSteps"))
                x["stress_avg"] = num(g("stress", "avgLevel") or it.get("averageStressLevel"))
                x["body_battery"] = num(g("bodyBattery", "maxValue") or it.get("bodyBatteryHighestValue"))
                x["body_battery_low"] = num(g("bodyBattery", "minValue") or it.get("bodyBatteryLowestValue"))
                x["intensity_min"] = num((g("intensityMinutes", "moderate") or 0) + 2 * (g("intensityMinutes", "vigorous") or 0)) or None

    def sleep():
        for s, e in ranges(start, end):
            items = as_list(get("/sleep-service/sleep/dailySleepSummariesByDate", {"startDate": s.isoformat(), "endDate": e.isoformat()}), "dailySleepSummaries", "sleepSummaries")
            if items and "sleep" not in samples:
                samples["sleep"] = sorted(items[0].keys())[:80]
            for it in items:
                d = date_of(it)
                if not d:
                    continue
                secs = num(pick(it, "sleepTimeSeconds", "totalSleepSeconds", "sleepTimeInSeconds", "durationInSeconds"))
                score = pick(it, "overallScore", "sleepScore")
                if isinstance(score, dict):
                    score = score.get("value")
                x = day(d)
                x["sleep_hours"] = round(secs / 3600, 2) if secs else x.get("sleep_hours")
                if score is not None and not isinstance(score, dict):
                    x["sleep_score"] = num(score)

    def hrv():
        for s, e in ranges(start, end):
            items = as_list(get(f"/hrv-service/hrv/daily/{s.isoformat()}/{e.isoformat()}"), "hrvSummaries", "summaries")
            if items and "hrv" not in samples:
                samples["hrv"] = sorted(items[0].keys())[:80]
            for it in items:
                d = date_of(it)
                if d:
                    day(d)["hrv"] = num(pick(it, "lastNightAvg", "lastNightAverage"))

    def sleep_scores():
        first = max(start, end - dt.timedelta(days=13))
        d = first
        while d <= end:
            it = get("/sleep-service/sleep/dailySleep", {"date": d.isoformat()}) or {}
            score = dig(it, "sleepScores", "overall", "value")
            if score is not None:
                x = day(d.isoformat())
                x["sleep_score"] = num(score)
                if it.get("sleepTimeSeconds"):
                    x["sleep_hours"] = round(it["sleepTimeSeconds"] / 3600, 2)
            d += dt.timedelta(days=1)

    run("daily summaries", summaries)
    run("sleep scores", sleep_scores)
    run("sleep", sleep)
    run("hrv", hrv)
    clean = []
    for d in sorted(days):
        row = {k: v for k, v in days[d].items() if v is not None}
        if len(row) > 1:
            clean.append(row)
    return clean


def parse_date(s, name):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except Exception:
        raise GarminError(f"{name} must be a date like 2026-11-01")


def garmin_sync(args):
    end = parse_date(args.get("end_date") or dt.date.today().isoformat(), "end_date")
    start = parse_date(args.get("start_date") or (end - dt.timedelta(days=29)).isoformat(), "start_date")
    if start > end:
        raise GarminError("start_date is after end_date")
    if (end - start).days > MAX_RANGE_DAYS:
        raise GarminError(f"Ask for at most {MAX_RANGE_DAYS} days at a time")
    token()  # fail fast on a bad key
    errors, samples = [], {}
    try:
        acts = fetch_activities(start, end, samples)
    except GarminError as e:
        acts = []
        errors.append(f"activities: {e}")
    days = fetch_days(start, end, samples, errors)
    return {"start_date": start.isoformat(), "end_date": end.isoformat(), "synced_at": dt.datetime.now().isoformat(timespec="seconds"),
            "activities": acts, "days": days, "errors": errors, "field_samples": samples, "helper_version": 3}


def garmin_get(args):
    """Debug/inspection: one raw read-only GET on the Personal API host, response truncated."""
    path = str(args.get("path") or "")
    if not path.startswith("/") or "://" in path or ".." in path:
        raise GarminError("path must be an API path like /hrv-service/hrv/2026-11-14")
    params = args.get("params") or None
    url = BASE + path + (("?" + urllib.parse.urlencode(params)) if params else "")
    req = urllib.request.Request(url, method="GET", headers={"Authorization": f"Bearer {token()}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            status, body = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, body = e.code, e.read()
    text = body.decode("utf-8", "replace")
    return {"status": status, "bytes": len(body), "body": text[:15000], "truncated": len(text) > 15000}


def garmin_status(_args):
    token(force=True)
    return {"ok": True, "message": "Garmin key works.", "helper_version": 3}


TOOLS = {
    "garmin_sync": {
        "fn": garmin_sync,
        "description": "Read the athlete's Garmin activities and daily recovery data (sleep, overnight HRV, resting HR, Body Battery, steps, stress) for a date range, normalized for the Coach app. Read-only.",
        "inputSchema": {"type": "object", "properties": {
            "start_date": {"type": "string", "description": "YYYY-MM-DD (default: 30 days before end_date)"},
            "end_date": {"type": "string", "description": "YYYY-MM-DD (default: today)"}}, "additionalProperties": False},
    },
    "garmin_get": {
        "fn": garmin_get,
        "description": "Inspection tool: make one raw read-only GET request to the Garmin Personal API (personal.connectapi.garmin.com) and return the status and response body (truncated). Used to check field names and troubleshoot sync.",
        "inputSchema": {"type": "object", "properties": {
            "path": {"type": "string", "description": "API path, e.g. /activitylist-service/activities/search/activities"},
            "params": {"type": "object", "description": "Query parameters", "additionalProperties": {"type": ["string", "number"]}}},
            "required": ["path"], "additionalProperties": False},
    },
    "garmin_status": {
        "fn": garmin_status,
        "description": "Check that the Garmin Personal API key works. Read-only.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
}


# ---------------- MCP over stdio (JSON-RPC 2.0, one message per line) ----------------

def reply(msg_id, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": msg_id}
    if error:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def handle(req):
    method, mid, params = req.get("method"), req.get("id"), req.get("params") or {}
    if mid is None:      # notification (e.g. notifications/initialized): no reply
        return
    if method == "initialize":
        return reply(mid, {"protocolVersion": params.get("protocolVersion") or "2025-06-18",
                           "capabilities": {"tools": {}},
                           "serverInfo": {"name": "garmin-coach", "version": "1.0.0"}})
    if method == "ping":
        return reply(mid, {})
    if method == "tools/list":
        return reply(mid, {"tools": [{"name": n, "description": t["description"], "inputSchema": t["inputSchema"],
                                      "annotations": {"readOnlyHint": True, "openWorldHint": True}} for n, t in TOOLS.items()]})
    if method == "tools/call":
        name = params.get("name")
        if name not in TOOLS:
            return reply(mid, error={"code": -32602, "message": f"Unknown tool {name}"})
        try:
            data = TOOLS[name]["fn"](params.get("arguments") or {})
            return reply(mid, {"content": [{"type": "text", "text": json.dumps(data, separators=(",", ":"))}], "structuredContent": data})
        except GarminError as e:
            return reply(mid, {"content": [{"type": "text", "text": str(e)}], "isError": True})
        except Exception as e:
            log("Unexpected error:", repr(e))
            return reply(mid, {"content": [{"type": "text", "text": f"Helper error: {type(e).__name__}: {e}"}], "isError": True})
    return reply(mid, error={"code": -32601, "message": f"Method not found: {method}"})


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        # Manual check from a terminal: python garmin_coach_mcp.py --test
        try:
            print(json.dumps(garmin_status({}), indent=1))
            r = garmin_sync({"start_date": (dt.date.today() - dt.timedelta(days=6)).isoformat()})
            print(f"Last 7 days: {len(r['activities'])} activities, {len(r['days'])} days of recovery data")
            for e in r["errors"]:
                print("  problem:", e)
            print("Sample day:", json.dumps(r["days"][-1] if r["days"] else None))
        except GarminError as e:
            print("PROBLEM:", e)
        return
    log("garmin-coach helper running")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        for r in (req if isinstance(req, list) else [req]):
            handle(r)


if __name__ == "__main__":
    main()
