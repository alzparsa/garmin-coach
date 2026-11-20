"""SQLite storage. One file: data/coach.db. Back it up by copying the file."""
import json
import os
import sqlite3
import threading

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, os.environ.get("COACH_DB", "coach.db"))
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT
);

-- Long- and short-term goals. Measurable when possible.
CREATE TABLE IF NOT EXISTS goals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  horizon TEXT NOT NULL CHECK (horizon IN ('long','short')),
  title TEXT NOT NULL,
  metric TEXT,              -- e.g. "Back squat e1RM", "10k time"
  baseline_value REAL,
  target_value REAL,
  unit TEXT,                -- kg, lb, min, km, reps ...
  better TEXT DEFAULT 'higher' CHECK (better IN ('higher','lower')),
  target_date TEXT,         -- YYYY-MM-DD
  parent_id INTEGER REFERENCES goals(id) ON DELETE SET NULL,
  status TEXT DEFAULT 'active' CHECK (status IN ('active','achieved','dropped')),
  notes TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

-- Workouts on the calendar: yours and AI-suggested.
CREATE TABLE IF NOT EXISTS planned_workouts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL,
  title TEXT NOT NULL,
  type TEXT DEFAULT 'other',      -- run, strength, bike, swim, mobility, rest, other
  details TEXT,
  duration_min INTEGER,
  intensity TEXT,                 -- easy, moderate, hard
  source TEXT DEFAULT 'me' CHECK (source IN ('me','ai')),
  status TEXT DEFAULT 'planned' CHECK (status IN ('planned','done','skipped')),
  rpe INTEGER,                    -- how hard it felt, 1-10 (filled after)
  feel_notes TEXT,
  ai_plan_id INTEGER,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pw_date ON planned_workouts(date);

-- Lifts: one row per exercise entry (sets x reps @ weight).
CREATE TABLE IF NOT EXISTS lift_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL,
  exercise TEXT NOT NULL,
  sets INTEGER DEFAULT 1,
  reps INTEGER NOT NULL,
  weight REAL NOT NULL,
  unit TEXT DEFAULT 'kg',
  rpe REAL,
  notes TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_lift_ex ON lift_logs(exercise, date);

-- Any other number you track: 5k time, bodyweight, max pull-ups, plank...
CREATE TABLE IF NOT EXISTS metric_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL,
  metric TEXT NOT NULL,
  value REAL NOT NULL,
  unit TEXT,
  better TEXT DEFAULT 'higher' CHECK (better IN ('higher','lower')),
  notes TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_metric ON metric_logs(metric, date);

-- Garmin data (cached locally; raw JSON kept so mapping can be improved later).
CREATE TABLE IF NOT EXISTS garmin_activities (
  activity_id INTEGER PRIMARY KEY,
  date TEXT,
  start_time TEXT,
  name TEXT,
  type TEXT,
  duration_s REAL,
  distance_m REAL,
  avg_hr REAL,
  max_hr REAL,
  calories REAL,
  training_load REAL,
  aerobic_te REAL,
  anaerobic_te REAL,
  avg_speed REAL,
  elevation_gain REAL,
  raw TEXT
);
CREATE INDEX IF NOT EXISTS idx_ga_date ON garmin_activities(date);

CREATE TABLE IF NOT EXISTS garmin_daily (
  date TEXT PRIMARY KEY,
  resting_hr REAL,
  steps REAL,
  stress_avg REAL,
  sleep_seconds REAL,
  sleep_score REAL,
  hrv_last_night REAL,
  hrv_weekly_avg REAL,
  hrv_status TEXT,
  body_battery_high REAL,
  body_battery_low REAL,
  body_battery_charged REAL,
  raw TEXT
);

CREATE TABLE IF NOT EXISTS ai_plans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  week_start TEXT,
  plan_json TEXT,
  applied INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS coach_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now'))
);
"""


def connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


_conn = None


def conn():
    global _conn
    if _conn is None:
        _conn = connect()
        _conn.executescript(SCHEMA)
        _conn.commit()
    return _conn


def q(sql, params=()):
    with _lock:
        cur = conn().execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def q1(sql, params=()):
    rows = q(sql, params)
    return rows[0] if rows else None


def ex(sql, params=()):
    with _lock:
        cur = conn().execute(sql, params)
        conn().commit()
        return cur.lastrowid


def exmany(sql, seq):
    with _lock:
        conn().executemany(sql, seq)
        conn().commit()


def get_setting(key, default=None):
    row = q1("SELECT value FROM settings WHERE key=?", (key,))
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return row["value"]


def set_setting(key, value):
    ex("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
       (key, json.dumps(value)))


def insert(table, data, allowed):
    cols = [c for c in allowed if c in data]
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})"
    return ex(sql, [data[c] for c in cols])


def update(table, row_id, data, allowed, pk="id"):
    cols = [c for c in allowed if c in data]
    if not cols:
        return
    sql = f"UPDATE {table} SET {','.join(c + '=?' for c in cols)} WHERE {pk}=?"
    ex(sql, [data[c] for c in cols] + [row_id])
