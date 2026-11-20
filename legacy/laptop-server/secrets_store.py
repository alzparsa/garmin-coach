"""API keys live in data/secrets.json (owner-only permissions), never in the DB or the browser."""
import json
import os

import db

PATH = os.path.join(db.DATA_DIR, "secrets.json")
KEYS = ("garmin_api_key", "anthropic_api_key", "passcode")


def _load():
    try:
        with open(PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get(key):
    return os.environ.get(key.upper()) or _load().get(key)


def set_many(values):
    data = _load()
    for k, v in values.items():
        if k in KEYS and v is not None:
            if v == "":
                data.pop(k, None)
            else:
                data[k] = v.strip()
    os.makedirs(db.DATA_DIR, exist_ok=True)
    with open(PATH, "w") as f:
        json.dump(data, f, indent=2)
    os.chmod(PATH, 0o600)


def status():
    """What the UI may see: whether each key is set, plus a masked hint."""
    out = {}
    for k in KEYS:
        v = get(k)
        out[k] = {"set": bool(v), "hint": (v[:4] + "…" + v[-4:]) if v and len(v) > 12 and k != "passcode" else ("set" if v else "")}
    return out
