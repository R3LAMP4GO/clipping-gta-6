"""Fallback daily schedule for Claude Code CLI users (no Desktop app): launchd (macOS) or a systemd user timer
(Linux) running /clip-daily."""
import os
import plistlib
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from . import config
from .config import IS_MAC, ROOT

UNIT_DIR = Path("~/.config/systemd/user").expanduser()
UNIT = "clipper-gta6-daily"

LABEL = "com.clipper.gta6.daily"
PLIST = Path("~/Library/LaunchAgents").expanduser() / f"{LABEL}.plist"
# Only what a clipping run needs, so the unattended agent can't wander.
ALLOWED = ["Bash(python3 -m clipper:*)", "Bash(ffmpeg:*)", "Bash(ffprobe:*)", "Bash(open:*)", "Read", "Glob", "Grep",
           "Edit(jobs/**)", "Edit(exports/**)"]  # Edit path rules cover Write too; Write(path) rules are ignored


MODEL = "sonnet"  # good judgment on picks and hooks at a fraction of Opus's usage


def _claude_cmd(claude, prompt="/clip-daily"):
    return [claude, "-p", prompt, "--model", MODEL, "--permission-mode", "dontAsk", "--allowedTools", *ALLOWED]


def _live_names():
    """(launchd label suffix / systemd unit suffix) per profile, so each profile's live jobs are separate."""
    p = config.PROFILE
    return "" if p == config.DEFAULT_PROFILE else f"-{p}"


def live_jobs(claude, every_hours=2, watch_minutes=5, watch_only=False, clip_cmd=None):
    """{name: (argv, interval seconds, keep children)}: the watcher starts recorders (no AI, so it can run every few
    minutes and catch streams as they go live); the clip run starts Claude only when analyzed chunks are waiting."""
    py, sfx = sys.executable, _live_names()
    jobs = {f"live-watch{sfx}": ([py, "-m", "clipper", "live", "watch"], watch_minutes * 60, True)}
    run = clip_cmd or (claude and shlex.join(_claude_cmd(claude, "/clip-daily live")))
    if run and not watch_only:
        gate = shlex.join([py, "-m", "clipper", "live", "pending"])
        jobs[f"live-clip{sfx}"] = (["/bin/sh", "-c", f"if {gate}; then {run}; fi"], every_hours * 3600, False)
    return jobs


def _live_env(claude):
    path = os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")
    if IS_MAC:
        path = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:" + path
    if claude:
        path = str(Path(claude).parent) + ":" + path
    return {"PATH": path, "CLIPPER_PROFILE": config.PROFILE}


def install_live(every_hours=2, watch_minutes=5, watch_only=False, clip_cmd=None):
    claude = shutil.which("claude")
    jobs = live_jobs(claude, every_hours, watch_minutes, watch_only, clip_cmd)
    env = _live_env(claude)
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    for name, (argv, interval, keep_children) in jobs.items():
        log = logs / f"{name}.log"
        if IS_MAC:
            plist_path = PLIST.parent / f"{LABEL.rsplit('.', 1)[0]}.{name}.plist"
            plist = {"Label": plist_path.stem, "ProgramArguments": argv, "WorkingDirectory": str(ROOT),
                     "StartInterval": interval, "RunAtLoad": True, "EnvironmentVariables": env,
                     "StandardOutPath": str(log), "StandardErrorPath": str(log),
                     # recorders outlive the watcher; launchd would otherwise kill them when it exits
                     "AbandonProcessGroup": keep_children}
            plist_path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
            plist_path.write_bytes(plistlib.dumps(plist))
            subprocess.run(["launchctl", "load", str(plist_path)], check=True)
        else:
            unit = f"{UNIT.rsplit('-', 1)[0]}-{name}"
            UNIT_DIR.mkdir(parents=True, exist_ok=True)
            envs = "\n".join(f"Environment={k}={v}" for k, v in env.items())
            # KillMode=process: systemd would otherwise stop the recorders when the watcher exits
            (UNIT_DIR / f"{unit}.service").write_text(f"""[Unit]
Description=Clipper {name}

[Service]
Type=oneshot
WorkingDirectory={ROOT}
{envs}
ExecStart={shlex.join(argv)}
{"KillMode=process" if keep_children else ""}
StandardOutput=append:{log}
StandardError=append:{log}
""", encoding="utf-8")
            (UNIT_DIR / f"{unit}.timer").write_text(f"""[Unit]
Description=Run clipper {name} every {interval // 60} minutes

[Timer]
OnBootSec=1min
OnUnitActiveSec={interval}s

[Install]
WantedBy=timers.target
""", encoding="utf-8")
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            subprocess.run(["systemctl", "--user", "enable", "--now", f"{unit}.timer"], check=True)
    out = f"live watch every {watch_minutes} min"
    if f"live-clip{_live_names()}" in jobs:
        out += (f"; live clip run ({'your --clip-cmd' if clip_cmd else '/clip-daily live'}) every {every_hours} h, "
                "only when chunks are ready")
    elif not watch_only:
        out += "; claude CLI not found, so chunks are clipped by the daily run (/clip-daily step 0)"
    return out + "; logs in logs/live-*.log"


def remove_live():
    removed = []
    if IS_MAC:
        for f in PLIST.parent.glob(f"{LABEL.rsplit('.', 1)[0]}.live-*.plist"):
            subprocess.run(["launchctl", "unload", str(f)], capture_output=True)
            f.unlink()
            removed.append(f.stem)
    else:
        for f in UNIT_DIR.glob(f"{UNIT.rsplit('-', 1)[0]}-live-*.timer"):
            subprocess.run(["systemctl", "--user", "disable", "--now", f.name], capture_output=True)
            f.unlink()
            f.with_suffix(".service").unlink(missing_ok=True)
            removed.append(f.stem)
    return removed


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
    live = remove_live()
    note = f" (and {', '.join(live)})" if live else ""
    return _remove_daily() + note


def _remove_daily():
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
    live = ([f.stem for f in PLIST.parent.glob(f"{LABEL.rsplit('.', 1)[0]}.live-*.plist")] if IS_MAC else
            [f.stem for f in UNIT_DIR.glob(f"{UNIT.rsplit('-', 1)[0]}-live-*.timer")])
    return _daily_status() + ("\nlive: " + ", ".join(sorted(live)) if live else "\nlive: not scheduled")


def _daily_status():
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
