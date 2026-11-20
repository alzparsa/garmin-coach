"""Trends, PRs, readiness and goal progress, computed from your logs + Garmin data."""
import datetime as dt
import statistics

import db


def today():
    return dt.date.today()


def week_start(d=None):
    d = d or today()
    return d - dt.timedelta(days=d.weekday())  # Monday


def e1rm(weight, reps):
    """Epley estimate. Unreliable past ~12 reps, so those don't count toward e1RM."""
    if not weight or not reps or reps > 12:
        return None
    return round(weight if reps == 1 else weight * (1 + reps / 30.0), 1)


# ---------- PRs ----------

def prs():
    lifts = {}
    for r in db.q("SELECT * FROM lift_logs ORDER BY date"):
        ex = r["exercise"].strip()
        k = ex.lower()
        est = e1rm(r["weight"], r["reps"])
        cur = lifts.setdefault(k, {"exercise": ex, "unit": r["unit"], "best_e1rm": None, "best_weight": None, "last_date": None})
        cur["last_date"] = r["date"]
        if est and (not cur["best_e1rm"] or est > cur["best_e1rm"]["value"]):
            cur["best_e1rm"] = {"value": est, "date": r["date"], "weight": r["weight"], "reps": r["reps"]}
        if not cur["best_weight"] or r["weight"] > cur["best_weight"]["value"]:
            cur["best_weight"] = {"value": r["weight"], "date": r["date"], "reps": r["reps"]}
    metrics = {}
    for r in db.q("SELECT * FROM metric_logs ORDER BY date"):
        k = r["metric"].strip().lower()
        cur = metrics.setdefault(k, {"metric": r["metric"].strip(), "unit": r["unit"], "better": r["better"], "best": None, "latest": None})
        cur["latest"] = {"value": r["value"], "date": r["date"]}
        b = cur["best"]
        if not b or (r["value"] > b["value"] if r["better"] == "higher" else r["value"] < b["value"]):
            cur["best"] = {"value": r["value"], "date": r["date"]}
    return {"lifts": sorted(lifts.values(), key=lambda x: x["exercise"]),
            "metrics": sorted(metrics.values(), key=lambda x: x["metric"])}


def recent_prs(days=14):
    """PRs set in the last N days (for the Today screen)."""
    since = (today() - dt.timedelta(days=days)).isoformat()
    out = []
    p = prs()
    for l in p["lifts"]:
        b = l["best_e1rm"]
        if b and b["date"] >= since:
            out.append(f"{l['exercise']}: {b['weight']}{l['unit']} x {b['reps']} (e1RM {b['value']})")
    for m in p["metrics"]:
        b = m["best"]
        if b and b["date"] >= since:
            out.append(f"{m['metric']}: {b['value']} {m['unit'] or ''}".strip())
    return out


# ---------- series ----------

def lift_series(exercise):
    rows = db.q("SELECT date, weight, reps FROM lift_logs WHERE lower(exercise)=lower(?) ORDER BY date", (exercise,))
    by_day = {}
    for r in rows:
        est = e1rm(r["weight"], r["reps"])
        if est:
            by_day[r["date"]] = max(by_day.get(r["date"], 0), est)
    return [{"date": d, "value": v} for d, v in sorted(by_day.items())]


def metric_series(metric):
    return db.q("SELECT date, value FROM metric_logs WHERE lower(metric)=lower(?) ORDER BY date", (metric,))


def daily_series(days=90):
    since = (today() - dt.timedelta(days=days)).isoformat()
    rows = db.q("SELECT * FROM garmin_daily WHERE date>=? ORDER BY date", (since,))
    for r in rows:
        r.pop("raw", None)
        r["sleep_hours"] = round(r["sleep_seconds"] / 3600, 2) if r.get("sleep_seconds") else None
    return rows


def _load_of(a):
    """Garmin training load if present, otherwise minutes as a rough proxy."""
    if a.get("training_load"):
        return a["training_load"]
    return (a.get("duration_s") or 0) / 60.0


def weekly_volume(weeks=12):
    start = week_start() - dt.timedelta(weeks=weeks - 1)
    acts = db.q("SELECT * FROM garmin_activities WHERE date>=?", (start.isoformat(),))
    lifts = db.q("SELECT * FROM lift_logs WHERE date>=?", (start.isoformat(),))
    out = []
    for i in range(weeks):
        ws = start + dt.timedelta(weeks=i)
        we = ws + dt.timedelta(days=6)
        wa = [a for a in acts if ws.isoformat() <= (a["date"] or "") <= we.isoformat()]
        wl = [l for l in lifts if ws.isoformat() <= l["date"] <= we.isoformat()]
        by_type = {}
        for a in wa:
            t = simplify_type(a["type"])
            by_type[t] = round(by_type.get(t, 0) + (a["duration_s"] or 0) / 60.0)
        out.append({
            "week": ws.isoformat(),
            "minutes": round(sum((a["duration_s"] or 0) for a in wa) / 60.0),
            "minutes_by_type": by_type,
            "km": round(sum((a["distance_m"] or 0) for a in wa) / 1000.0, 1),
            "run_km": round(sum((a["distance_m"] or 0) for a in wa if simplify_type(a["type"]) == "run") / 1000.0, 1),
            "load": round(sum(_load_of(a) for a in wa)),
            "sessions": len(wa),
            "tonnage": round(sum((l["sets"] or 1) * l["reps"] * l["weight"] for l in wl)),
        })
    return out


def simplify_type(t):
    t = (t or "other").lower()
    if "run" in t:
        return "run"
    if "strength" in t or "weight" in t:
        return "strength"
    if "cycl" in t or "bik" in t or "ride" in t:
        return "bike"
    if "swim" in t:
        return "swim"
    if "walk" in t or "hik" in t:
        return "walk"
    if "yoga" in t or "pilates" in t or "mobility" in t or "breath" in t:
        return "mobility"
    return "other"


def load_ratio():
    """Acute:chronic workload ratio (7-day vs 28-day weekly average). ~0.8-1.3 is the usual 'safe' band."""
    t = today()
    acts = db.q("SELECT * FROM garmin_activities WHERE date>?", ((t - dt.timedelta(days=28)).isoformat(),))
    acute = sum(_load_of(a) for a in acts if a["date"] > (t - dt.timedelta(days=7)).isoformat())
    chronic = sum(_load_of(a) for a in acts) / 4.0
    if chronic < 1:
        return {"acute": round(acute), "chronic": round(chronic), "ratio": None}
    return {"acute": round(acute), "chronic": round(chronic), "ratio": round(acute / chronic, 2)}


# ---------- readiness (home-made; Garmin's Training Readiness isn't in the Personal API) ----------

def readiness():
    rows = daily_series(30)
    if not rows:
        return {"level": "unknown", "signals": [], "summary": "No Garmin data yet. Sync in Settings."}
    latest = rows[-1]
    signals = []

    def baseline(field, n):
        vals = [r[field] for r in rows[:-1][-n:] if r.get(field)]
        return statistics.mean(vals) if len(vals) >= 3 else None

    hrv, hb = latest.get("hrv_last_night"), baseline("hrv_last_night", 7)
    if hrv and hb:
        d = (hrv - hb) / hb * 100
        signals.append({"name": "HRV", "value": f"{hrv:.0f} ms", "vs": f"{d:+.0f}% vs 7-day",
                        "state": "good" if d > -5 else "ok" if d > -12 else "low"})
    rhr, rb = latest.get("resting_hr"), baseline("resting_hr", 14)
    if rhr and rb:
        d = rhr - rb
        signals.append({"name": "Resting HR", "value": f"{rhr:.0f} bpm", "vs": f"{d:+.0f} vs 14-day",
                        "state": "good" if d <= 2 else "ok" if d <= 5 else "low"})
    sh = latest.get("sleep_hours")
    if sh:
        signals.append({"name": "Sleep", "value": f"{sh:.1f} h" + (f" · score {latest['sleep_score']:.0f}" if latest.get("sleep_score") else ""),
                        "vs": "", "state": "good" if sh >= 7 else "ok" if sh >= 6 else "low"})
    bb = latest.get("body_battery_high")
    if bb:
        signals.append({"name": "Body Battery", "value": f"{bb:.0f}", "vs": "peak",
                        "state": "good" if bb >= 70 else "ok" if bb >= 45 else "low"})
    lr = load_ratio()
    if lr["ratio"]:
        r = lr["ratio"]
        signals.append({"name": "Load ratio", "value": f"{r}", "vs": "7d vs 28d",
                        "state": "good" if 0.8 <= r <= 1.3 else "ok" if r <= 1.5 else "low"})
    lows = sum(s["state"] == "low" for s in signals)
    oks = sum(s["state"] == "ok" for s in signals)
    level = "low" if lows >= 2 else "ok" if lows == 1 or oks >= 2 else "good"
    summary = {"good": "Green light. Good day for quality work.",
               "ok": "Mixed signals. Train, but keep intensity in check.",
               "low": "Recovery looks compromised. Consider easy work or rest."}[level]
    return {"level": level, "date": latest["date"], "signals": signals, "summary": summary}


# ---------- plan adherence & goals ----------

def adherence(weeks=4):
    since = (week_start() - dt.timedelta(weeks=weeks - 1)).isoformat()
    rows = db.q("SELECT status, type FROM planned_workouts WHERE date>=? AND date<? AND type!='rest'",
                (since, today().isoformat()))
    done = sum(r["status"] == "done" for r in rows)
    total = len(rows)
    return {"done": done, "planned": total, "pct": round(done / total * 100) if total else None}


def goal_progress(goal):
    metric = (goal.get("metric") or "").strip()
    if not metric:
        return None
    s = lift_series(metric)
    if s:
        cur = max(x["value"] for x in s)
        source = "e1RM"
    else:
        s = metric_series(metric)
        if not s:
            return None
        vals = [x["value"] for x in s]
        cur = max(vals) if goal.get("better", "higher") == "higher" else min(vals)
        source = "log"
    out = {"current": cur, "source": source, "series": s[-30:]}
    b, t = goal.get("baseline_value"), goal.get("target_value")
    if b is not None and t is not None and t != b:
        out["pct"] = max(0, min(100, round((cur - b) / (t - b) * 100)))
    if goal.get("target_date"):
        out["days_left"] = (dt.date.fromisoformat(goal["target_date"]) - today()).days
    return out


def goals_with_progress():
    goals = db.q("SELECT * FROM goals ORDER BY status='active' DESC, horizon, target_date")
    for g in goals:
        g["progress"] = goal_progress(g)
    return goals


def known_names():
    ex = [r["exercise"] for r in db.q("SELECT DISTINCT exercise FROM lift_logs ORDER BY exercise")]
    me = [r["metric"] for r in db.q("SELECT DISTINCT metric FROM metric_logs ORDER BY metric")]
    return {"exercises": ex, "metrics": me}
