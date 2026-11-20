"""AI coach on the Claude API: weekly planning, weekly review and free-form questions.

Uses the Messages API directly with urllib (no SDK needed).
Needs an API key from https://console.anthropic.com (billed separately from a claude.ai plan).
"""
import datetime as dt
import json
import re
import urllib.error
import urllib.request

import analytics as an
import db
import secrets_store

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-5-5"

SYSTEM = """You are a pragmatic, evidence-based endurance and strength coach working with ONE athlete through their personal training app.
You see their goals, profile/constraints, planned workouts, logged lifts/numbers and Garmin watch data.

Principles:
- Goals drive every decision: tie each recommendation to a short-term goal, and short-term goals to the long-term goal.
- Respect the athlete's own planned workouts. Keep them unless there's a clear reason (recovery signals, load spike, clash with a goal); if you change one, say why.
- Use recovery data (HRV vs baseline, resting HR, sleep, body battery, acute:chronic load ratio) to set intensity. Rough rules: ratio > 1.3 or two red signals -> reduce intensity/volume.
- Progressive overload in small steps. Hard/easy alternation. Don't stack hard sessions on consecutive days unless the athlete planned it.
- Be specific: sets x reps @ load (kg/lb or %e1RM or RPE), run paces/HR zones/durations.
- Data from Garmin may be missing or incomplete; say so instead of guessing. Never invent numbers that aren't in the data.
- You are not a doctor. If injuries or pain are mentioned, recommend getting them checked and plan around them conservatively.
- Be concise."""


class CoachError(Exception):
    pass


def _call(messages, max_tokens=4000, system=SYSTEM):
    key = secrets_store.get("anthropic_api_key")
    if not key:
        raise CoachError("No Claude API key set. Add it in Settings.")
    model = db.get_setting("ai_model") or DEFAULT_MODEL
    body = json.dumps({"model": model, "max_tokens": max_tokens, "system": system, "messages": messages}).encode()
    req = urllib.request.Request(API_URL, data=body, method="POST", headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise CoachError(f"Claude API error {e.code}: {e.read()[:400].decode('utf-8', 'replace')}") from None
    except urllib.error.URLError as e:
        raise CoachError(f"Network error: {e.reason}") from None
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


# ---------- context ----------

def build_context(week_start=None):
    t = an.today()
    ws = week_start or an.week_start(t)
    profile = db.get_setting("profile") or {}
    goals = [{k: g[k] for k in ("horizon", "title", "metric", "baseline_value", "target_value", "unit", "better", "target_date", "notes")}
             | {"current": (g["progress"] or {}).get("current"), "pct": (g["progress"] or {}).get("pct")}
             for g in an.goals_with_progress() if g["status"] == "active"]
    planned = db.q("SELECT date,title,type,details,duration_min,intensity,source,status,rpe,feel_notes FROM planned_workouts "
                   "WHERE date>=? AND date<=? ORDER BY date", ((ws - dt.timedelta(days=14)).isoformat(), (ws + dt.timedelta(days=13)).isoformat()))
    acts = db.q("SELECT date,name,type,duration_s,distance_m,avg_hr,max_hr,training_load,aerobic_te,anaerobic_te "
                "FROM garmin_activities WHERE date>=? ORDER BY date", ((t - dt.timedelta(days=28)).isoformat(),))
    for a in acts:
        a["min"] = round((a.pop("duration_s") or 0) / 60)
        a["km"] = round((a.pop("distance_m") or 0) / 1000, 2) or None
    daily = [{k: r.get(k) for k in ("date", "resting_hr", "hrv_last_night", "hrv_status", "sleep_hours", "sleep_score", "body_battery_high", "stress_avg", "steps")}
             for r in an.daily_series(14)]
    lifts = db.q("SELECT date,exercise,sets,reps,weight,unit,rpe,notes FROM lift_logs WHERE date>=? ORDER BY date",
                 ((t - dt.timedelta(days=42)).isoformat(),))
    metrics = db.q("SELECT date,metric,value,unit,notes FROM metric_logs WHERE date>=? ORDER BY date",
                   ((t - dt.timedelta(days=90)).isoformat(),))
    p = an.prs()
    pr_lines = [f"{l['exercise']}: e1RM {l['best_e1rm']['value']}{l['unit']} ({l['best_e1rm']['date']})" for l in p["lifts"] if l["best_e1rm"]]
    pr_lines += [f"{m['metric']}: best {m['best']['value']} {m['unit'] or ''} ({m['best']['date']})" for m in p["metrics"]]
    ctx = {
        "today": t.isoformat(), "weekday": t.strftime("%A"),
        "target_week_start": ws.isoformat(),
        "athlete_profile": profile,
        "goals": goals,
        "readiness_today": an.readiness(),
        "load_ratio": an.load_ratio(),
        "weekly_volume_last_8_weeks": an.weekly_volume(8),
        "plan_adherence_last_4_weeks": an.adherence(4),
        "planned_workouts_window": planned,
        "garmin_activities_last_28_days": acts,
        "garmin_daily_last_14_days": daily,
        "lift_logs_last_6_weeks": lifts,
        "other_numbers_last_90_days": metrics,
        "personal_records": pr_lines,
    }
    return json.dumps(ctx, default=str, separators=(",", ":"))


def _extract_json(text):
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    raw = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    return json.loads(raw)


# ---------- features ----------

def plan_week(week_start, request_note=""):
    ws = dt.date.fromisoformat(week_start) if week_start else an.week_start()
    days = [(ws + dt.timedelta(days=i)).isoformat() for i in range(7)]
    prompt = f"""Here is my data (JSON):
{build_context(ws)}

Plan my training week {days[0]} to {days[-1]}.
{('Extra request from me: ' + request_note) if request_note else ''}

Return ONLY a JSON object, no prose outside it:
{{
  "summary": "2-3 sentences: the week's focus and how it moves my short-term goals",
  "readiness_take": "1-2 sentences on what my recovery/load data says",
  "days": [
    {{"date": "YYYY-MM-DD", "title": "short name", "type": "run|strength|bike|swim|mobility|rest|other",
      "duration_min": 45, "intensity": "easy|moderate|hard",
      "details": "specific prescription (sets x reps @ load, paces/HR zones, intervals)",
      "keeps_my_plan": true, "why": "one line tying it to a goal or recovery"}}
  ],
  "changes_to_my_plan": ["what you changed in my planned workouts and why (empty if none)"],
  "watch_outs": ["short warnings, data gaps or things to monitor"]
}}
Include exactly one entry per day (use type "rest" for rest days)."""
    text = _call([{"role": "user", "content": prompt}], max_tokens=5000)
    try:
        plan = _extract_json(text)
    except Exception:
        raise CoachError("The AI reply wasn't valid JSON. Try again.\n\n" + text[:1000])
    plan_id = db.ex("INSERT INTO ai_plans(week_start, plan_json) VALUES(?,?)", (ws.isoformat(), json.dumps(plan)))
    return {"id": plan_id, "week_start": ws.isoformat(), "plan": plan}


def apply_plan(plan_id, replace_mine=False):
    row = db.q1("SELECT * FROM ai_plans WHERE id=?", (plan_id,))
    if not row:
        raise CoachError("Plan not found")
    plan = json.loads(row["plan_json"])
    dates = [d["date"] for d in plan.get("days", [])]
    if dates:
        lo, hi = min(dates), max(dates)
        db.ex("DELETE FROM planned_workouts WHERE source='ai' AND status='planned' AND date BETWEEN ? AND ?", (lo, hi))
        if replace_mine:
            db.ex("DELETE FROM planned_workouts WHERE source='me' AND status='planned' AND date BETWEEN ? AND ?", (lo, hi))
    for d in plan.get("days", []):
        mine = db.q1("SELECT id FROM planned_workouts WHERE date=? AND source='me'", (d["date"],))
        if not replace_mine and d.get("keeps_my_plan") and mine:
            continue  # the user's own workout is already on the calendar
        if not replace_mine and mine and d.get("type") == "rest":
            continue  # don't stack a rest entry on top of the user's session
        details = (d.get("details") or "") + (f"\n\nWhy: {d['why']}" if d.get("why") else "")
        db.insert("planned_workouts", {
            "date": d["date"], "title": d.get("title") or "Workout", "type": d.get("type") or "other",
            "details": details.strip(), "duration_min": d.get("duration_min"), "intensity": d.get("intensity"),
            "source": "ai", "ai_plan_id": plan_id}, ["date", "title", "type", "details", "duration_min", "intensity", "source", "ai_plan_id"])
    db.ex("UPDATE ai_plans SET applied=1 WHERE id=?", (plan_id,))
    return {"ok": True}


def ask(question):
    history = db.q("SELECT role, content FROM coach_messages ORDER BY id DESC LIMIT 10")[::-1]
    msgs = [{"role": "user", "content": f"My current data (JSON), for reference:\n{build_context()}"},
            {"role": "assistant", "content": "Got it. I have your data. What would you like to know?"}]
    msgs += [{"role": h["role"], "content": h["content"]} for h in history]
    msgs.append({"role": "user", "content": question})
    answer = _call(msgs, max_tokens=2000)
    db.ex("INSERT INTO coach_messages(role,content) VALUES('user',?)", (question,))
    db.ex("INSERT INTO coach_messages(role,content) VALUES('assistant',?)", (answer,))
    return {"answer": answer}


WEEKLY_REVIEW = ("Review my last 7 days: what I planned vs. what I did, recovery trends, any PRs, and progress toward each "
                 "short-term goal. Then give the 3 most important adjustments for next week. Use short headings and bullets.")
