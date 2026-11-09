# AGENTS.md

Python clipper for GTA 6 shorts (`clipper/`); see README.md for the commands and what each one does.

## Commands
- Install: `uv sync` (Python deps from `pyproject.toml` / `uv.lock`); system tools (ffmpeg, yt-dlp, whisper.cpp, demucs): `uv run python -m clipper setup --install`
- Test: `uv run python -m unittest discover -s tests`
- Build/lint: none configured

## Rules
- CI lives in `.github/workflows/ci.yml` and must stay green.
- Never commit with `--no-verify`.
- Never commit `.env`, `jobs/`, `exports/` or `logs/` (secrets and large media; already in `.gitignore`).
