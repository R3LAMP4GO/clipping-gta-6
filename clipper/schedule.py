"""Fallback daily schedule for Claude Code CLI users (no Desktop app): launchd (macOS) or a systemd user timer
(Linux) running /clip-daily."""
import os
import plistlib
import shutil
import subprocess
from pathlib import Path

from .config import IS_MAC, ROOT

UNIT_DIR = Path("~/.config/systemd/user").expanduser()
UNIT = "clipper-gta6-daily"

LABEL = "com.clipper.gta6.daily"
PLIST = Path("~/Library/LaunchAgents").expanduser() / f"{LABEL}.plist"
# Only what a clipping run needs, so the unattended agent can't wander.
ALLOWED = ["Bash(python3 -m clipper:*)", "Bash(ffmpeg:*)", "Bash(ffprobe:*)", "Bash(open:*)", "Read", "Glob", "Grep",
           "Write(jobs/**)", "Edit(jobs/**)", "Write(exports/**)", "Edit(exports/**)"]


def _claude_cmd(claude):
    return [claude, "-p", "/clip-daily", "--permission-mode", "dontAsk", "--allowedTools", *ALLOWED]


def _install_systemd(claude, time_str):
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    UNIT_DIR.mkdir(parents=True, exist_ok=True)
    cmd = " ".join(f"'{a}'" if any(c in a for c in " ()*") else a for a in _claude_cmd(claude))
    (UNIT_DIR / f"{UNIT}.service").write_text(f"""[Unit]
Description=Daily GTA 6 clipping run (/clip-daily)

[Service]
Type=oneshot
WorkingDirectory={ROOT}
Environment=PATH={os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")}
ExecStart={cmd}
StandardOutput=append:{logs / "daily.log"}
StandardError=append:{logs / "daily.err.log"}
""", encoding="utf-8")
    (UNIT_DIR / f"{UNIT}.timer").write_text(f"""[Unit]
Description=Run /clip-daily at {time_str}

[Timer]
OnCalendar=*-*-* {time_str}:00
Persistent=true

[Install]
WantedBy=timers.target
""", encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", f"{UNIT}.timer"], check=True)
    return (f"daily run scheduled at {time_str} via a systemd user timer ({UNIT}.timer); logs in logs/daily.log. "
            f"To run while logged out: sudo loginctl enable-linger {os.environ.get('USER', '$USER')}")


def install(time_str):
    claude = shutil.which("claude")
    if not claude:
        raise SystemExit("claude CLI not found on PATH")
    if not IS_MAC:
        return _install_systemd(claude, time_str)
    hour, minute = (int(x) for x in time_str.split(":"))
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    plist = {
        "Label": LABEL,
        "ProgramArguments": _claude_cmd(claude),
        "WorkingDirectory": str(ROOT),
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "StandardOutPath": str(logs / "daily.log"), "StandardErrorPath": str(logs / "daily.err.log"),
        "EnvironmentVariables": {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:"
                                         + str(Path(claude).parent) + ":" + str(Path(shutil.which("python3")).parent)},
    }
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
    PLIST.write_bytes(plistlib.dumps(plist))
    subprocess.run(["launchctl", "load", str(PLIST)], check=True)
    return f"daily run scheduled at {time_str} via launchd ({PLIST}); logs in logs/daily.log"


def remove():
    if not IS_MAC:
        subprocess.run(["systemctl", "--user", "disable", "--now", f"{UNIT}.timer"], capture_output=True)
        for ext in ("service", "timer"):
            (UNIT_DIR / f"{UNIT}.{ext}").unlink(missing_ok=True)
        return "systemd schedule removed"
    if not PLIST.exists():
        return "no launchd schedule installed"
    subprocess.run(["launchctl", "unload", str(PLIST)], capture_output=True)
    PLIST.unlink()
    return "launchd schedule removed"


def status():
    if not IS_MAC:
        if not (UNIT_DIR / f"{UNIT}.timer").exists():
            return "no systemd schedule (use `clipper schedule install`)"
        res = subprocess.run(["systemctl", "--user", "list-timers", f"{UNIT}.timer", "--no-pager"],
                             capture_output=True, text=True)
        return res.stdout.strip() or f"{UNIT}.timer installed"
    if not PLIST.exists():
        return "no launchd schedule (use the Claude Code Desktop / Codex app scheduler, or `clipper schedule install`)"
    p = plistlib.loads(PLIST.read_bytes())
    t = p["StartCalendarInterval"]
    return f"launchd: daily at {t['Hour']:02d}:{t['Minute']:02d} -> claude -p /clip-daily (logs/daily.log)"
