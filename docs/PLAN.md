# Coach: product plan

## Goal
A personal, phone-first training app that combines Garmin watch data with my own logs (lifts, PRs, numbers) and my long/short-term goals, and uses Claude to plan and adjust each week.

## Decision (Nov 15, 2026): hosted in my Claude account
I'm on Windows and want a phone-first app that is always available and easy to update. The app is a private page in my Claude account, replacing the earlier laptop version (see `legacy/`).
- **Keep it private** (not public link): Claude can only publish updates to a private (or named-people/org-shared) page.
- **Data:** Claude page storage, owner-only read/write. Collections: goals, planned, lifts, metrics, aiplans, chat, days (recovery, doc id = date), acts (watch activities, doc id = "g"+Garmin id), settings/profile, settings/garmin (last sync, problems). Survives updates.
- **AI coach:** Claude through my plan (no separate API key). Weekly plan (structured JSON, keeps my sessions, plans only remaining days), coach chat, weekly review.
- **Update loop:** give feedback in the Garmin project → Claude republishes → refresh the page.

## Garmin data (decided Nov 15): free laptop helper — working
- Hosted pages can't call outside servers, so the page can't reach Garmin directly.
- athletedata connector was tried and dropped: it's paid after a 7-day trial.
- **Chosen:** `helper/garmin_coach_mcp.py` (helper_version 3), a Python stdlib local MCP server run by the Claude desktop app on my Windows laptop, using Garmin's free official Personal API (key in `garmin_key.txt`; must be created on the Garmin account the watch syncs to). Config in Claude desktop: `"garmin-coach": {"command": "python", "args": ["C:\\CoachHelper\\garmin_coach_mcp.py"]}`. Changing the key file doesn't need a restart; changing the helper code does.
- Tools: `garmin_sync(start_date, end_date)`, `garmin_status`, `garmin_get(path, params)` (raw read-only inspection for debugging).
- Page declares `host:garmin-coach` / `garmin_sync`; **Sync Garmin** on Today, **Sync now / Sync last year** in Settings. Works only when the page is opened in the Claude desktop app on the laptop; the phone shows synced data anywhere.
- **Verified with real data (Nov 15):** activities (name, type, duration, HR, calories, training load, training effect), sleep hours, overnight HRV, resting HR (`heartRate.restingValue`), steps (`movement.steps.value`), stress (`stress.avgLevel`), Body Battery daily peak/low (`bodyBattery.maxValue/minValue`), intensity minutes. Sleep score comes from `/sleep-service/sleep/dailySleep` (`sleepScores.overall.value`), fetched for the most recent 14 nights of each sync.
- Garmin activity types seen: yoga, strength_training, "other" (CrossFit). Activities include `summarizedExerciseSets` / totalSets / totalReps.
- Sync keeps manual soreness and auto-marks a planned session done when a watch activity matches on the same day and sport. Between syncs: Morning check-in (manual) on Today.

## Gaps in the original idea, and how the app handles them
1. **Garmin's Personal API is read-only.** Plans can't be sent to the watch. The plan lives in the app.
2. **Missing Garmin metrics.** No Training Readiness, Training Status, VO2 max, recovery time. Home-made readiness score and acute:chronic load ratio instead.
3. **Strength detail.** Lift logging in the app is the source of truth for PRs (Garmin set summaries could be imported later).
4. **Feedback loop.** Done/Skip + RPE + notes after each session.
5. **Constraints.** Days available, session length, equipment, injuries, schedule in Settings → About you.
6. **Measurable goals.** Each goal links to a metric with baseline, target and date, so progress is computed.
7. **Backups.** Settings → Copy all my data (JSON).
8. **Medical.** The coach flags pain and injury instead of programming through it.

## Roadmap
- Import Garmin strength sets (summarizedExerciseSets) into the lift log
- Map Garmin "other" activities by name (e.g. CrossFit) to a better sport type
- Workout templates, "copy last week", per-set logging with rest timer, plate calculator
- 4–8 week training blocks toward a short-term goal; weekly plan follows the block
