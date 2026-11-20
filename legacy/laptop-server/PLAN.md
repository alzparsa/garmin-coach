# Coach: product plan

## Goal
A personal, phone-first training app that combines Garmin watch data with my own logs (lifts, PRs, numbers) and my long/short-term goals, and uses Claude to plan and adjust each week.

## Architecture (v1, built)
- **Mac** runs `server.py` (Python stdlib + SQLite). Serves the app and the API.
- **iPhone** opens it as a home-screen web app (PWA) over Wi-Fi or Tailscale. No App Store.
- **Garmin Connect Personal API** (official, Oct 2026): API key → 24h token → read-only GET endpoints. Synced into SQLite on demand.
- **Claude API**: weekly planner (structured JSON), weekly review, coach chat. Gets a compact context: goals, profile, planned vs. done, 28 days of activities, 14 days of recovery data, 6 weeks of lifts, PRs, load ratio.

## Screens
| Tab | What it does |
|---|---|
| Today | Readiness (HRV, RHR, sleep, Body Battery, load ratio), today's session with Done/Skip + RPE, week strip, goal progress, new PRs, recent watch activities, Ask coach |
| Plan | Week navigator, your planned workouts, "Plan this week" AI, accept (add) or replace |
| Log | Lifts (sets × reps × weight, RPE), other numbers (5k time, bodyweight…), PR board |
| Trends | Weekly time by sport, load, run km, lifting volume, HRV / RHR / sleep / Body Battery, e1RM per lift, any logged number |
| Goals | Long-term goals → linked short-term goals with auto-progress from logs |

## Gaps in the original idea, and how v1 handles them
1. **Garmin is read-only.** Plans can't be sent to the watch. The plan lives in the app.
2. **Missing Garmin metrics.** No Training Readiness, Training Status, VO2 max, recovery time. Home-made readiness score and acute:chronic load ratio instead.
3. **Strength detail.** Garmin doesn't reliably give sets/reps/weights, so manual lift logging is the source of truth for PRs.
4. **Feedback loop.** A plan is only as good as the "how did it go" data. Done/Skip + RPE + notes after each session.
5. **Constraints.** Days available, session length, equipment, injuries, schedule. Without these the AI plans fantasy weeks. Stored in Settings → About you.
6. **Measurable goals.** Each goal links to a metric with baseline, target and date, so progress is computed rather than guessed.
7. **Key and token lifecycle.** Garmin key expires (max 1 year), tokens every 24h (auto-refreshed). Claude API is billed separately from a Claude.ai plan.
8. **Phone access and security.** Mac must be on. Tailscale for anywhere-access and HTTPS. Passcode. Keys stay on the Mac.
9. **Backups.** `data/` folder or JSON export.
10. **Medical.** The coach flags pain and injury instead of programming through it.

## Roadmap
- **v1.1:** parse the FIT files (`/download-service/files/activity/{id}`) for laps, HR zones, splits. Per-activity detail screen.
- **v1.2:** scheduled daily sync + morning push via an iOS Shortcut that hits `/api/garmin/sync`.
- **v1.3:** workout templates and "copy last week". Plate calculator. Per-set logging with rest timer.
- **v1.4:** periodization: AI builds a 4–8 week block toward a short-term goal; weekly plan follows the block.
- **v2:** always-on host (Raspberry Pi / small VPS) so the Mac can sleep.
