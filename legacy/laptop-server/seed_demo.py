"""Fills data/demo.db with ~10 weeks of believable sample data so you can try the app before connecting Garmin."""
import datetime as dt
import json
import math
import random

import db


def seed_if_empty():
    if db.q1("SELECT COUNT(*) n FROM goals")["n"]:
        return
    random.seed(7)
    t = dt.date.today()
    db.set_setting("profile", {"age": 29, "bodyweight": "80 kg", "days_per_week": 5, "session_minutes": 60,
                               "sports": "Hybrid: strength + running", "experience": "4 yrs lifting, 1 yr running",
                               "equipment": "Full gym", "schedule": "Long run on Saturdays", "injuries": None})
    lg = db.insert("goals", {"horizon": "long", "title": "Hybrid athlete: sub-45 10k and 180 kg squat", "target_date": (t + dt.timedelta(days=240)).isoformat(),
                             "notes": "Want to be strong and fit at the same time."}, ["horizon", "title", "target_date", "notes"])
    cols = ["horizon", "title", "metric", "baseline_value", "target_value", "unit", "better", "target_date", "parent_id"]
    db.insert("goals", {"horizon": "short", "title": "Back squat e1RM 170 kg", "metric": "Back squat", "baseline_value": 140, "target_value": 170,
                        "unit": "kg", "better": "higher", "target_date": (t + dt.timedelta(days=45)).isoformat(), "parent_id": lg}, cols)
    db.insert("goals", {"horizon": "short", "title": "5k under 23:00", "metric": "5k time", "baseline_value": 25.0, "target_value": 23.0,
                        "unit": "min", "better": "lower", "target_date": (t + dt.timedelta(days=60)).isoformat(), "parent_id": lg}, cols)
    db.insert("goals", {"horizon": "short", "title": "Bench press e1RM 110 kg", "metric": "Bench press", "baseline_value": 95, "target_value": 110,
                        "unit": "kg", "better": "higher", "target_date": (t + dt.timedelta(days=70)).isoformat(), "parent_id": lg}, cols)

    start = t - dt.timedelta(days=70)
    aid = 10_000_000
    for i in range(71):
        d = start + dt.timedelta(days=i)
        wd = d.weekday()
        prog = i / 70
        # daily wellness
        hrv = 58 + 6 * math.sin(i / 6) + random.gauss(0, 4) + prog * 4
        rhr = 52 - prog * 2 + random.gauss(0, 1.5)
        sleep = random.gauss(7.2, 0.6)
        if i == 70:
            hrv, rhr, sleep = hrv - 2, rhr + 1, 6.6
        db.ex("INSERT OR REPLACE INTO garmin_daily(date,resting_hr,steps,stress_avg,sleep_seconds,sleep_score,hrv_last_night,hrv_weekly_avg,hrv_status,body_battery_high,body_battery_low,raw) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
              (d.isoformat(), round(rhr), random.randint(6000, 14000), random.randint(20, 40), sleep * 3600, round(60 + (sleep - 6) * 15 + random.gauss(0, 5)),
               round(hrv), round(hrv), "BALANCED", random.randint(60, 95), random.randint(10, 30), "{}"))
        if i == 70:
            continue
        sessions = []
        if wd in (0, 3):
            sessions.append(("strength_training", "Strength", 60 + random.randint(-5, 10), 0, 118, 55))
        if wd == 1:
            sessions.append(("running", "Intervals", 45, 8000 + random.randint(0, 800), 158, 110))
        if wd == 2:
            sessions.append(("running", "Easy run", 40, 7000, 138, 50))
        if wd == 4:
            sessions.append(("strength_training", "Upper body", 55, 0, 112, 45))
        if wd == 5:
            sessions.append(("running", "Long run", 70 + int(prog * 25), 12000 + int(prog * 5000), 145, 120))
        if wd == 6 and random.random() < .5:
            sessions.append(("cycling", "Spin", 45, 18000, 128, 40))
        for typ, name, mins, dist, hr, load in sessions:
            aid += 1
            db.ex("INSERT INTO garmin_activities(activity_id,date,start_time,name,type,duration_s,distance_m,avg_hr,max_hr,calories,training_load,aerobic_te,anaerobic_te,raw) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (aid, d.isoformat(), d.isoformat() + " 07:00:00", name, typ, mins * 60, dist or None, hr, hr + 25, mins * 10,
                   load * (1 + random.gauss(0, .1)), 3.2, 1.1, json.dumps({"demo": True})))
        # lifts
        if wd == 0:
            w = 120 + round(prog * 18 / 2.5) * 2.5
            db.insert("lift_logs", {"date": d.isoformat(), "exercise": "Back squat", "sets": 4, "reps": 5, "weight": w, "unit": "kg", "rpe": 8}, ["date", "exercise", "sets", "reps", "weight", "unit", "rpe"])
            db.insert("lift_logs", {"date": d.isoformat(), "exercise": "Romanian deadlift", "sets": 3, "reps": 8, "weight": 100 + round(prog * 15), "unit": "kg"}, ["date", "exercise", "sets", "reps", "weight", "unit"])
        if wd == 3:
            db.insert("lift_logs", {"date": d.isoformat(), "exercise": "Deadlift", "sets": 3, "reps": 3, "weight": 160 + round(prog * 15 / 2.5) * 2.5, "unit": "kg", "rpe": 8.5}, ["date", "exercise", "sets", "reps", "weight", "unit", "rpe"])
        if wd == 4:
            db.insert("lift_logs", {"date": d.isoformat(), "exercise": "Bench press", "sets": 4, "reps": 6, "weight": 80 + round(prog * 8 / 2.5) * 2.5, "unit": "kg", "rpe": 8}, ["date", "exercise", "sets", "reps", "weight", "unit", "rpe"])
            db.insert("lift_logs", {"date": d.isoformat(), "exercise": "Weighted pull-up", "sets": 3, "reps": 6, "weight": 10 + round(prog * 6), "unit": "kg"}, ["date", "exercise", "sets", "reps", "weight", "unit"])
        if wd == 6 and (i // 7) % 2 == 0:
            db.insert("metric_logs", {"date": d.isoformat(), "metric": "5k time", "value": round(25.2 - prog * 1.6 + random.gauss(0, .15), 2), "unit": "min", "better": "lower"}, ["date", "metric", "value", "unit", "better"])
        if wd == 0:
            db.insert("metric_logs", {"date": d.isoformat(), "metric": "Bodyweight", "value": round(81 - prog * 1.5 + random.gauss(0, .3), 1), "unit": "kg", "better": "lower"}, ["date", "metric", "value", "unit", "better"])

    # this week's plan: past days done, today + future planned
    ws = t - dt.timedelta(days=t.weekday())
    plan = [(0, "Lower body A", "strength", "Back squat 4×5 @ 137.5 kg\nRDL 3×8 @ 115 kg", 60, "hard"),
            (1, "Track intervals", "run", "6 × 800 m @ 4:20/km, 2 min jog", 45, "hard"),
            (2, "Easy run", "run", "40 min Z2 (HR < 145)", 40, "easy"),
            (3, "Deadlift + accessories", "strength", "Deadlift 3×3 @ 175 kg", 55, "hard"),
            (4, "Upper body", "strength", "Bench 4×6 @ 87.5 kg\nWeighted pull-ups 3×6 @ 15 kg", 55, "moderate"),
            (5, "Long run", "run", "16 km easy, last 2 km at 10k pace", 95, "moderate"),
            (6, "Rest / mobility", "rest", "", 20, "easy")]
    for off, title, typ, det, mins, inten in plan:
        d = ws + dt.timedelta(days=off)
        status = "done" if d < t else "planned"
        db.insert("planned_workouts", {"date": d.isoformat(), "title": title, "type": typ, "details": det, "duration_min": mins, "intensity": inten,
                                       "source": "me", "status": status, "rpe": 7 if status == "done" else None},
                  ["date", "title", "type", "details", "duration_min", "intensity", "source", "status", "rpe"])
    # previous weeks mostly done
    for w in range(1, 4):
        for off, title, typ, det, mins, inten in plan[:6]:
            d = ws - dt.timedelta(weeks=w) + dt.timedelta(days=off)
            db.insert("planned_workouts", {"date": d.isoformat(), "title": title, "type": typ, "duration_min": mins, "intensity": inten, "source": "me",
                                           "status": "skipped" if (w == 2 and off == 2) else "done"},
                      ["date", "title", "type", "duration_min", "intensity", "source", "status"])
    db.set_setting("garmin_last_sync_at", dt.datetime.now().isoformat(timespec="minutes"))
