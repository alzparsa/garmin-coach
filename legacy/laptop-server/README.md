# Coach: your personal Garmin + AI training app

Runs on your Mac and opens on your iPhone like an app. No App Store, no cloud server, no packages to install.

```
garmin-coach/
  server.py        web server + API (Python standard library only)
  garmin.py        Garmin Connect Personal API client + sync
  coach.py         AI coach on the Claude API (weekly plan, review, chat)
  analytics.py     PRs, e1RM, trends, readiness, load ratio, goal progress
  db.py            SQLite schema (data/coach.db)
  seed_demo.py     sample data for --demo mode
  static/          the phone app (HTML/CSS/JS, no build step)
  data/            your database + keys (created on first run; back this up)
```

## 1. Try it with sample data (2 minutes)

```bash
cd garmin-coach
python3 server.py --demo
```
Open http://localhost:8787. Demo mode uses `data/demo.db`, so your real data is never touched.
You need Python 3.10 or newer (`python3 --version`). If you don't have it: `brew install python`.

## 2. Run it for real

```bash
python3 server.py
```

### Connect Garmin (free, official, read-only)
1. Sign in to **Garmin Connect on the web** (connect.garmin.com), open the **Personal API Key** page, and choose **Create Key**.
2. Pick the longest expiry (1 year). The key is shown **only once**, so copy it.
3. In the app: ⚙️ Settings → paste it → **Sync now** (pulls ~4 months the first time). Use **Re-sync 1 year** if you want more history.

The app swaps the key for a 24-hour token automatically. Garmin emails you about a week before the key expires; when it does, create a new key and paste it in.

### Connect the AI coach
1. Create an API key at https://console.anthropic.com. It's billed per use and separate from a Claude.ai subscription. A weekly plan costs a few cents.
2. ⚙️ Settings → paste the Claude API key.
3. Fill in **About you**: days per week, equipment, injuries, schedule. The coach plans around these.

Keys are saved in `data/secrets.json` (readable only by your user). They never reach the phone.

## 3. Put it on your iPhone

**Option A: same Wi-Fi (simplest).** When the server starts it prints `On your iPhone: http://192.168.x.x:8787`.
Open that address in **Safari**, tap **Share → Add to Home Screen**. It opens full-screen like a native app.
Set a **passcode** in Settings, since anyone on your Wi-Fi could otherwise open it.
macOS may ask to allow incoming connections for Python. Click Allow.

**Option B: from anywhere (recommended).** Install [Tailscale](https://tailscale.com) (free) on the Mac and the iPhone, signed in to the same account. Then on the Mac:
```bash
tailscale serve --bg 8787
```
It prints an `https://your-mac.your-tailnet.ts.net` address. Open that on the iPhone (at the gym, on cellular) and Add to Home Screen.
You get HTTPS (so offline caching works) and nothing is exposed to the public internet.

**Keep it running.** The Mac must be awake with the server running. To start it automatically when you log in, see `launchd` below. Settings → Battery → Options → "Prevent automatic sleeping when the display is off" (on power adapter) keeps it reachable.

<details><summary>Auto-start on login (launchd)</summary>

Save as `~/Library/LaunchAgents/com.me.coach.plist` (fix the two paths), then run `launchctl load ~/Library/LaunchAgents/com.me.coach.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.me.coach</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/python3</string><string>/Users/YOU/garmin-coach/server.py</string>
  </array>
  <key>WorkingDirectory</key><string>/Users/YOU/garmin-coach</string>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>StandardErrorPath</key><string>/tmp/coach.log</string>
</dict></plist>
```
</details>

## How to use it each week
1. **Goals tab**: one long-term goal and 2–4 measurable short-term goals. Set "Track with" to an exercise name (uses your best e1RM) or a number you log (e.g. `5k time`), and progress fills in automatically.
2. **Plan tab**: add the workouts you already have planned. Then tap **Plan this week**. The coach keeps your sessions, fills the gaps, explains any changes, and you choose **Add to my week** or **Replace my plan**.
3. **Today tab**: readiness check, today's session, then **Mark done** with an RPE. This feedback is what makes next week's plan better.
4. **Log tab**: log lifts (sets × reps × weight) and other numbers (5k time, bodyweight, max pull-ups). PRs and e1RM are calculated automatically.
5. **Trends tab**: training time and load, running km, lifting volume, HRV / resting HR / sleep, e1RM per lift, your numbers.
6. **Ask coach** (on Today): weekly review, "hard or easy today?", or any question.

## Good to know
- **Garmin's Personal API is read-only.** The app can't push workouts to your watch. Use the plan as your guide, or build the key sessions in Garmin Connect.
- **Not everything is available.** Training Readiness, Training Status, VO2 max and recovery time aren't in the Personal API. The app builds its own readiness signal from HRV, resting HR, sleep, Body Battery and load ratio.
- **Strength sets** aren't reliably available from Garmin, so log lifts in the app. They're the core of your PR history.
- **Field mapping:** Garmin hasn't published every JSON field name. After your first sync, if a number shows "–" that should exist, open `http://localhost:8787/api/garmin/raw-sample` to see the raw data and adjust the field names in `garmin.py`, then use **Re-sync 1 year**.
- **Backup:** copy the `data/` folder, or use Settings → Export.
- **Change the AI model** in Settings (default `claude-sonnet-5-5`).
