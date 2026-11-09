---
description: Run the GTA 6 clipper automatically every day (Claude Code Desktop, Codex app, or launchd)
argument-hint: [HH:MM]
---

Set up a daily automatic clipping run (run from the clipping-gta-6 project root). The scheduled run executes `/clip-daily` (in Codex: `.codex/prompts/clip-daily.md`), which uses saved preferences and never asks questions.

1. Run `python3 -m clipper prefs show` and `python3 -m clipper schedule status`. Ask for any missing choices in one go: time of day (default `schedule_time`), voiceover off/all/agent decides, videos per run, hooks per video, and new uploads per day. Ask with multiple-choice questions: in Claude Code use the AskUserQuestion tool; in Codex use request_user_input if available (Plan mode), otherwise list numbered options and wait for the reply. Save them with `python3 -m clipper prefs set …`. If voiceover isn't off, run `python3 -m clipper voice-setup` so the unattended run has a Fish Audio key.
2. Create the schedule natively in whichever app you are running in:
   - **Claude Code Desktop:** create a *local* scheduled task (Scheduled → New task → Only on this computer, or simply create it yourself if you can schedule from this session). Name `gta6-daily-clips`, folder = this project, daily at the chosen time, instructions `/clip-daily`. Project permissions in `.claude/settings.json` already allow the clipper commands so it won't stall. The app must be open and the Mac awake; suggest turning on "Keep computer awake".
   - **Codex / ChatGPT desktop app:** create a scheduled task for this project (local, not worktree, since `jobs/` and `exports/` live here), daily at the chosen time, prompt: "Follow .codex/prompts/clip-daily.md exactly." It needs network access (YouTube, Fish Audio) and to run `python3`, `ffmpeg` and `open`.
   - **Claude Code CLI only (no Desktop app):** run `python3 -m clipper schedule install --time HH:MM`. It installs a launchd agent that runs `claude -p /clip-daily` with only the clipper commands allowed, logging to `logs/daily.log`. Remove it with `python3 -m clipper schedule remove`.
3. Offer a test run now (run the `/clip-daily` steps once) so they can see what tomorrow's output will look like in `exports/<date>/`.
