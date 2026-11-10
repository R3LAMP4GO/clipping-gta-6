# clipper

Finds the best moments in GTA 6 YouTube videos from a creator watchlist, lets you review them, and renders captioned 9:16 shorts: 4 hook variants per clip, title options and a description. Local tools: yt-dlp, whisper.cpp, Demucs (voice separation), WhisperKit (speaker labels), FFmpeg, Pillow. Voiceover uses Fish Audio's free developer model when `FISH_API_KEY` is in the environment or `.env`, otherwise macOS `say`.

Fonts (Montserrat, Bebas Neue, TikTok Sans, Luckiest Guy, bundled in `assets/fonts`), hook and title rules come from `research/viral-gta-shorts.md` (28 GTA Shorts with 500k+ views).

Agent commands (Claude Code: `.claude/commands/`, Codex: copy `.codex/prompts/*.md` to `~/.codex/prompts/` and use `/prompts:<name>`):
- `/clip-setup`: installs the tools, the whisper model and these commands (globally, so they work from any folder)
- `/clip [url | phrase]`: setup questions (voiceover off/all/auto, number of videos, hooks per video), then find → review → render
- `/clip-creators [add @handle | remove name]`: manage the watched creators (`creators.yaml`)
- `/clip-schedule [HH:MM]`: run daily via a Claude Code Desktop local task, a Codex app scheduled task, or launchd (CLI)
- `/clip-daily`: the unattended run a schedule calls; uses `prefs.yaml`

Runs on macOS and Ubuntu/Debian (CPU-only is fine; `clipper bench` sizes it). `clipper setup --install` installs everything for either.

Output: `exports/<profile>/<date>/video N/<hook>.mp4` + `titles and description.md`, with `exports/<profile>/<date>/index.md` listing everything.

**Profiles** (niches) live in `profiles/<name>/`: `profile.yaml` (topic patterns, keywords, hashtags, searches; merged over `watchlist.yaml`), `creators.yaml` and `live.yaml`, plus an optional `prefs.yaml` (else the root one is shared). Pick one with `--profile <name>` before the command (`python3 -m clipper --profile gta-rp watch`) or `CLIPPER_PROFILE`; the default is `gta6`.

```
python3 -m clipper watch                       # new on-topic uploads from the profile's creators + searches
python3 -m clipper run <url>                   # download + transcribe + score -> jobs/<id>/candidates.md
python3 -m clipper frame <id> 100              # gridded frame to locate a facecam (split layout)
python3 -m clipper voice-setup                 # save a Fish Audio key (macOS: key page + TextEdit note; Linux: hidden prompt)
python3 -m clipper creators add @KaiCenat       # or: list / remove
python3 -m clipper prefs set voice=auto videos_per_run=3 hooks_per_video=4
python3 -m clipper daily                       # new GTA 6 uploads -> analyzed jobs
python3 -m clipper schedule install --time 09:00   # CLI-only fallback scheduler
python3 -m clipper render <id> --picks picks.json   # exports/<profile>/<date>/video N/<hook>.mp4
python3 -m clipper simulate picks.json          # rank hook variants with a simulated swipe test
python3 -m clipper live add twitch:xqc kick:xqc youtube:@KaiCenat   # streams to record while they play GTA 6
python3 -m clipper live watch                  # start recorders for live GTA 6 streams (run every few minutes)
python3 -m clipper live jobs | done <job>      # finished 30-min chunks to clip / mark clipped (frees disk)
python3 -m clipper bench                        # how many live creators this machine keeps up with
python3 -m clipper setup [--install]           # check/install dependencies + global /clip commands
python3 -m unittest discover -s tests
```

Creators live in `profiles/<name>/creators.yaml`, saved choices in `prefs.yaml`, topic filters in `profiles/<name>/profile.yaml`, and signal weights and clip length in `watchlist.yaml`.
