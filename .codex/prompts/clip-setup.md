---
description: Install everything the GTA 6 clipper needs (FFmpeg, yt-dlp, whisper.cpp, WhisperKit, Demucs, the whisper model) and its /clip commands
---

Set up the GTA 6 clipper on this Mac (run from the clipping-gta-6 project root).

1. Run `python3 -m clipper setup --dry-run`. It lists each dependency as ok/MISSING and what it would install. On macOS: Homebrew packages (ffmpeg, yt-dlp, whisper-cpp, whisperkit-cli) and pip packages. On Ubuntu/Debian: apt packages (ffmpeg, espeak-ng, build tools), yt-dlp and Demucs (CPU PyTorch unless there's an NVIDIA card) from pip, and whisper.cpp built from source into ~/.local/bin; WhisperKit is macOS-only, so Linux captions are single-speaker. It also lists the whisper models (plus a fast one for live streams on Linux) and the `/clip*` commands copied to `~/.claude/commands` and `~/.codex/prompts` so they work from any folder.
2. macOS: if Homebrew is missing, tell the user to install it from https://brew.sh and stop. Linux: if setup says the Python is system-managed, run the venv command it prints, then use that venv's python for everything after.
3. Show the user the list and ask whether to install it (multiple choice: "Install everything" recommended / "Only install the commands" / "Cancel"). In Claude Code use the AskUserQuestion tool; in Codex use request_user_input if available, otherwise list numbered options and wait.
4. "Install everything": run `python3 -m clipper setup --install` with a 30-minute timeout (Demucs pulls in PyTorch; on Linux it asks for sudo for apt). "Only install the commands": run `python3 -m clipper setup`, which installs the commands and only reports missing tools.
5. Run `python3 -m clipper setup` again and `python3 -m unittest discover -s tests`, then report what is ready. If the user wants AI voiceovers, offer `python3 -m clipper voice-setup` (Fish Audio key).
6. For live streams (`python3 -m clipper live`), run `python3 -m clipper bench` once: it measures this machine and says how many creators it can keep up with live and what to set `live_workers` to in `watchlist.yaml`.
