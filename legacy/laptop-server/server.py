#!/usr/bin/env python3
"""Garmin Coach: personal training app. Run:  python3 server.py   then open the printed URL on your iPhone.

No third-party packages: Python 3.10+ standard library only.
"""
import argparse
import datetime as dt
import hmac
import json
import mimetypes
import os
import re
import socket
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import analytics as an
import coach
import db
import garmin
import secrets_store

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

GOAL_COLS = ["horizon", "title", "metric", "baseline_value", "target_value", "unit", "better", "target_date", "parent_id", "status", "notes"]
PLAN_COLS = ["date", "title", "type", "details", "duration_min", "intensity", "source", "status", "rpe", "feel_notes"]
LIFT_COLS = ["date", "exercise", "sets", "reps", "weight", "unit", "rpe", "notes"]
METRIC_COLS = ["date", "metric", "value", "unit", "better", "notes"]

ROUTES = []


def route(method, pattern):
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), fn))
        return fn
    return deco


class ApiError(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.code = code


def require(body, *fields):
    missing = [f for f in fields if body.get(f) in (None, "")]
    if missing:
        raise ApiError("Missing: " + ", ".join(missing))


# ---------------- settings & status ----------------

@route("GET", "/api/status")
def status(q, b):
    return {
        "keys": secrets_store.status(),
        "last_sync": db.get_setting("garmin_last_sync_at"),
        "profile": db.get_setting("profile") or {},
        "units": db.get_setting("units") or "kg",
        "ai_model": db.get_setting("ai_model") or coach.DEFAULT_MODEL,
        "counts": {t: db.q1(f"SELECT COUNT(*) n FROM {t}")["n"] for t in
                   ("goals", "planned_workouts", "lift_logs", "metric_logs", "garmin_activities", "garmin_daily")},
    }


@route("POST", "/api/settings")
def save_settings(q, b):
    secrets_store.set_many({k: b.get(k) for k in secrets_store.KEYS if k in b})
    for k in ("profile", "units", "ai_model"):
        if k in b:
            db.set_setting(k, b[k])
    return status(q, b)


@route("POST", "/api/garmin/sync")
def garmin_sync(q, b):
    try:
        return garmin.sync(days=int(b["days"]) if b.get("days") else None)
    except garmin.GarminError as e:
        raise ApiError(str(e), 502)


@route("GET", "/api/garmin/raw-sample")
def garmin_raw(q, b):
    """Debug helper: shows raw Garmin JSON for the latest day/activity so field mappings can be checked."""
    a = db.q1("SELECT raw FROM garmin_activities ORDER BY date DESC LIMIT 1")
    d = db.q1("SELECT raw FROM garmin_daily ORDER BY date DESC LIMIT 1")
    return {"activity": json.loads(a["raw"]) if a else None, "daily": json.loads(d["raw"]) if d else None}


# ---------------- today ----------------

@route("GET", "/api/today")
def today(q, b):
    t = an.today()
    ws = an.week_start(t)
    week = db.q("SELECT * FROM planned_workouts WHERE date BETWEEN ? AND ? ORDER BY date, id",
                (ws.isoformat(), (ws + dt.timedelta(days=6)).isoformat()))
    acts = db.q("SELECT activity_id,date,name,type,duration_s,distance_m,avg_hr,training_load FROM garmin_activities "
                "ORDER BY start_time DESC LIMIT 5")
    goals = [g for g in an.goals_with_progress() if g["status"] == "active"]
    for g in goals:
        if g["progress"]:
            g["progress"].pop("series", None)
    return {"date": t.isoformat(), "readiness": an.readiness(), "week": week, "recent_activities": acts,
            "recent_prs": an.recent_prs(), "goals": goals, "adherence": an.adherence(4),
            "last_sync": db.get_setting("garmin_last_sync_at")}


# ---------------- goals ----------------

@route("GET", "/api/goals")
def goals_list(q, b):
    return {"goals": an.goals_with_progress(), "names": an.known_names()}


@route("POST", "/api/goals")
def goals_add(q, b):
    require(b, "horizon", "title")
    return {"id": db.insert("goals", b, GOAL_COLS)}


@route("PUT", r"/api/goals/(\d+)")
def goals_upd(q, b, gid):
    db.update("goals", int(gid), b, GOAL_COLS)
    return {"ok": True}


@route("DELETE", r"/api/goals/(\d+)")
def goals_del(q, b, gid):
    db.ex("DELETE FROM goals WHERE id=?", (int(gid),))
    return {"ok": True}


# ---------------- planned workouts ----------------

@route("GET", "/api/planned")
def planned_list(q, b):
    ws = an.week_start()
    lo = q.get("from") or ws.isoformat()
    hi = q.get("to") or (ws + dt.timedelta(days=6)).isoformat()
    return {"items": db.q("SELECT * FROM planned_workouts WHERE date BETWEEN ? AND ? ORDER BY date, id", (lo, hi))}


@route("POST", "/api/planned")
def planned_add(q, b):
    require(b, "date", "title")
    return {"id": db.insert("planned_workouts", b, PLAN_COLS)}


@route("PUT", r"/api/planned/(\d+)")
def planned_upd(q, b, pid):
    db.update("planned_workouts", int(pid), b, PLAN_COLS)
    return {"ok": True}


@route("DELETE", r"/api/planned/(\d+)")
def planned_del(q, b, pid):
    db.ex("DELETE FROM planned_workouts WHERE id=?", (int(pid),))
    return {"ok": True}


# ---------------- history: lifts & other numbers ----------------

@route("GET", "/api/lifts")
def lifts_list(q, b):
    return {"items": db.q("SELECT * FROM lift_logs ORDER BY date DESC, id DESC LIMIT ?", (int(q.get("limit", 200)),))}


@route("POST", "/api/lifts")
def lifts_add(q, b):
    entries = b.get("entries") or [b]
    ids = []
    for e in entries:
        require(e, "date", "exercise", "reps", "weight")
        e.setdefault("unit", db.get_setting("units") or "kg")
        ids.append(db.insert("lift_logs", e, LIFT_COLS))
    return {"ids": ids}


@route("DELETE", r"/api/lifts/(\d+)")
def lifts_del(q, b, lid):
    db.ex("DELETE FROM lift_logs WHERE id=?", (int(lid),))
    return {"ok": True}


@route("GET", "/api/metrics")
def metrics_list(q, b):
    return {"items": db.q("SELECT * FROM metric_logs ORDER BY date DESC, id DESC LIMIT ?", (int(q.get("limit", 200)),))}


@route("POST", "/api/metrics")
def metrics_add(q, b):
    require(b, "date", "metric", "value")
    return {"id": db.insert("metric_logs", b, METRIC_COLS)}


@route("DELETE", r"/api/metrics/(\d+)")
def metrics_del(q, b, mid):
    db.ex("DELETE FROM metric_logs WHERE id=?", (int(mid),))
    return {"ok": True}


@route("GET", "/api/prs")
def prs(q, b):
    return an.prs()


# ---------------- trends ----------------

@route("GET", "/api/trends")
def trends(q, b):
    return {"weekly": an.weekly_volume(int(q.get("weeks", 12))), "daily": an.daily_series(int(q.get("days", 90))),
            "load_ratio": an.load_ratio(), "adherence": an.adherence(8), "names": an.known_names()}


@route("GET", "/api/series")
def series(q, b):
    name = q.get("name", "")
    return {"name": name, "points": an.lift_series(name) if q.get("kind") == "lift" else an.metric_series(name)}


@route("GET", "/api/activities")
def activities(q, b):
    rows = db.q("SELECT activity_id,date,start_time,name,type,duration_s,distance_m,avg_hr,max_hr,calories,training_load,"
                "aerobic_te,anaerobic_te FROM garmin_activities ORDER BY start_time DESC LIMIT ?", (int(q.get("limit", 50)),))
    return {"items": rows}


# ---------------- AI coach ----------------

def _coach(fn, *a):
    try:
        return fn(*a)
    except coach.CoachError as e:
        raise ApiError(str(e), 502)


@route("POST", "/api/coach/plan")
def coach_plan(q, b):
    return _coach(coach.plan_week, b.get("week_start"), b.get("note", ""))


@route("POST", "/api/coach/apply")
def coach_apply(q, b):
    require(b, "plan_id")
    return _coach(coach.apply_plan, int(b["plan_id"]), bool(b.get("replace_mine")))


@route("GET", "/api/coach/latest-plan")
def coach_latest(q, b):
    r = db.q1("SELECT * FROM ai_plans ORDER BY id DESC LIMIT 1")
    if not r:
        return {"plan": None}
    return {"id": r["id"], "week_start": r["week_start"], "applied": r["applied"], "plan": json.loads(r["plan_json"])}


@route("POST", "/api/coach/ask")
def coach_ask(q, b):
    question = coach.WEEKLY_REVIEW if b.get("preset") == "weekly_review" else b.get("question")
    if not question:
        raise ApiError("Ask something")
    return _coach(coach.ask, question)


@route("GET", "/api/coach/messages")
def coach_msgs(q, b):
    return {"items": db.q("SELECT * FROM coach_messages ORDER BY id DESC LIMIT 30")[::-1]}


@route("DELETE", "/api/coach/messages")
def coach_clear(q, b):
    db.ex("DELETE FROM coach_messages")
    return {"ok": True}


# ---------------- export ----------------

@route("GET", "/api/export")
def export(q, b):
    tables = ["goals", "planned_workouts", "lift_logs", "metric_logs", "ai_plans", "coach_messages"]
    return {"exported_at": dt.datetime.now().isoformat(), **{t: db.q(f"SELECT * FROM {t}") for t in tables},
            "profile": db.get_setting("profile")}


# ---------------- HTTP plumbing ----------------

class Handler(BaseHTTPRequestHandler):
    server_version = "GarminCoach/1.0"

    def log_message(self, fmt, *args):
        if "/api/" in (args[0] if args else ""):
            sys.stderr.write("%s %s\n" % (self.log_date_time_string(), fmt % args))

    def _send(self, code, payload, ctype="application/json", extra=None):
        data = payload if isinstance(payload, bytes) else json.dumps(payload, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store" if ctype == "application/json" else "no-cache")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self):
        pc = secrets_store.get("passcode")
        return not pc or hmac.compare_digest(self.headers.get("X-Passcode", ""), pc)

    def _handle(self, method):
        url = urlparse(self.path)
        if not url.path.startswith("/api/"):
            return self._static(url.path)
        if url.path == "/api/auth-check":
            return self._send(200 if self._authorized() else 401, {"ok": self._authorized()})
        if not self._authorized():
            return self._send(401, {"error": "Passcode required"})
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        body = {}
        if method in ("POST", "PUT"):
            n = int(self.headers.get("Content-Length") or 0)
            if n:
                try:
                    body = json.loads(self.rfile.read(n))
                except json.JSONDecodeError:
                    return self._send(400, {"error": "Invalid JSON"})
        for m, rx, fn in ROUTES:
            mt = rx.match(url.path)
            if m == method and mt:
                try:
                    return self._send(200, fn(q, body, *mt.groups()))
                except ApiError as e:
                    return self._send(e.code, {"error": str(e)})
                except Exception as e:
                    traceback.print_exc()
                    return self._send(500, {"error": f"{type(e).__name__}: {e}"})
        self._send(404, {"error": "Not found"})

    def _static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        full = os.path.normpath(os.path.join(STATIC, path.lstrip("/")))
        if not full.startswith(STATIC) or not os.path.isfile(full):
            full = os.path.join(STATIC, "index.html")  # SPA fallback
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if full.endswith(".webmanifest"):
            ctype = "application/manifest+json"
        with open(full, "rb") as f:
            self._send(200, f.read(), ctype)

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    def do_DELETE(self):
        self._handle("DELETE")


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8787)))
    ap.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"),
                    help="0.0.0.0 = reachable from your phone on the same Wi-Fi; 127.0.0.1 = this computer only")
    ap.add_argument("--demo", action="store_true", help="use a separate demo database filled with sample data")
    args = ap.parse_args()
    if args.demo:
        db.DB_PATH = os.path.join(db.DATA_DIR, "demo.db")
        import seed_demo
        seed_demo.seed_if_empty()
        print("  DEMO MODE: sample data in data/demo.db (your real data is untouched)")
    db.conn()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"\n  Garmin Coach is running\n  On this computer:  http://localhost:{args.port}")
    if args.host == "0.0.0.0":
        print(f"  On your iPhone:    http://{lan_ip()}:{args.port}   (same Wi-Fi)")
    if not secrets_store.get("passcode"):
        print("  Tip: set a passcode in Settings so others on your Wi-Fi can't open it.")
    print("  Ctrl+C to stop.\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
