"""Fallback daily schedule for CLI users (no Desktop app): launchd (macOS) or a systemd user timer (Linux) running
/clip-daily per profile with Claude Code (`claude -p`) or Codex (`codex exec`)."""
import os
import plistlib
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from . import config, library
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


AGENTS = ("claude", "codex")
# codex-cli 0.165 (`codex exec --help`): never stop for approval, write only inside the project, network on for
# yt-dlp and Fish Audio (workspace-write blocks it by default).
CODEX_ARGS = ["-s", "workspace-write", "-c", "sandbox_workspace_write.network_access=true", "-c", 'approval_policy="never"']
CODEX_APP = Path("/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex")  # the ChatGPT app's bundled CLI


def pick_agent(agent=None):
    """The agent a scheduled run uses: the --agent flag, else prefs `agent`, else claude."""
    agent = agent or str(library.load_prefs().get("agent") or "claude")
    if agent not in AGENTS:
        raise SystemExit(f"unknown agent '{agent}' (choose from {', '.join(AGENTS)})")
    return agent


def find_agent(agent):
    found = shutil.which(agent)
    if not found and agent == "codex" and CODEX_APP.exists():
        return str(CODEX_APP)
    return found


def _daily_args(extra=""):
    """/clip-daily's arguments: the profile (when not the default; CLIPPER_PROFILE also names it) and e.g. `live`."""
    p = config.PROFILE
    return " ".join(x for x in ("" if p == config.DEFAULT_PROFILE else p, extra) if x)


def _agent_cmd(agent, binary, args=""):
    """argv for one unattended /clip-daily run. `codex exec` can't expand a custom prompt, so it reads the file."""
    if agent == "codex":
        prompt = ("Unattended scheduled run: read .codex/prompts/clip-daily.md and follow it exactly. "
                  f"Its arguments: {args or 'none'}.")
        return [binary, "exec", "-C", str(ROOT), *CODEX_ARGS, prompt]
    return _claude_cmd(binary, f"/clip-daily {args}".strip())


def _live_names():
    """(launchd label suffix / systemd unit suffix) per profile, so each profile's live jobs are separate."""
    p = config.PROFILE
    return "" if p == config.DEFAULT_PROFILE else f"-{p}"


def _daily_names():
    """(launchd label, systemd unit) of this profile's daily run; gta6 keeps the original names."""
    return f"{LABEL}{_live_names()}", f"{UNIT}{_live_names()}"


def live_jobs(claude, every_hours=2, watch_minutes=5, watch_only=False, clip_cmd=None, agent="claude"):
    """{name: (argv, interval seconds, keep children)}: the watcher starts recorders (no AI, so it can run every few
    minutes and catch streams as they go live); the clip run starts the agent only when analyzed chunks are waiting.
    `claude` is the agent's binary (claude or codex)."""
    py, sfx = sys.executable, _live_names()
    jobs = {f"live-watch{sfx}": ([py, "-m", "clipper", "live", "watch"], watch_minutes * 60, True)}
    run = clip_cmd or (claude and shlex.join(_agent_cmd(agent, claude, _daily_args("live"))))
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


def install_live(every_hours=2, watch_minutes=5, watch_only=False, clip_cmd=None, agent=None):
    agent = pick_agent(agent)
    claude = find_agent(agent)
    jobs = live_jobs(claude, every_hours, watch_minutes, watch_only, clip_cmd, agent)
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
        out += (f"; live clip run ({'your --clip-cmd' if clip_cmd else f'/clip-daily live with {agent}'}) every "
                f"{every_hours} h, only when chunks are ready")
    elif not watch_only:
        out += f"; {agent} CLI not found, so chunks are clipped by the daily run (/clip-daily step 0)"
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


def _install_systemd(argv, time_str):
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    UNIT_DIR.mkdir(parents=True, exist_ok=True)
    unit, sfx = _daily_names()[1], _live_names()
    (UNIT_DIR / f"{unit}.service").write_text(f"""[Unit]
Description=Daily {config.PROFILE} clipping run (/clip-daily)

[Service]
Type=oneshot
WorkingDirectory={ROOT}
Environment=PATH={os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")}
Environment=CLIPPER_PROFILE={config.PROFILE}
ExecStart={shlex.join(argv)}
StandardOutput=append:{logs / f"daily{sfx}.log"}
StandardError=append:{logs / f"daily{sfx}.err.log"}
""", encoding="utf-8")
    (UNIT_DIR / f"{unit}.timer").write_text(f"""[Unit]
Description=Run /clip-daily at {time_str}

[Timer]
OnCalendar=*-*-* {time_str}:00
Persistent=true

[Install]
WantedBy=timers.target
""", encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", f"{unit}.timer"], check=True)
    return (f"daily {config.PROFILE} run scheduled at {time_str} via a systemd user timer ({unit}.timer); logs in "
            f"logs/daily{sfx}.log. To run while logged out: sudo loginctl enable-linger {os.environ.get('USER', '$USER')}")


def _plist_path():
    return PLIST.with_name(f"{_daily_names()[0]}.plist")


def install(time_str, agent=None):
    """This profile's daily run (gta6 keeps the original label/unit, others add -<profile>) with Claude or Codex."""
    agent = pick_agent(agent)
    binary = find_agent(agent)
    if not binary:
        raise SystemExit(f"{agent} CLI not found on PATH")
    argv = _agent_cmd(agent, binary, _daily_args())
    if not IS_MAC:
        return _install_systemd(argv, time_str)
    hour, minute = (int(x) for x in time_str.split(":"))
    logs, sfx, plist_path = ROOT / "logs", _live_names(), _plist_path()
    logs.mkdir(exist_ok=True)
    plist = {
        "Label": plist_path.stem,
        "ProgramArguments": argv,
        "WorkingDirectory": str(ROOT),
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "StandardOutPath": str(logs / f"daily{sfx}.log"), "StandardErrorPath": str(logs / f"daily{sfx}.err.log"),
        "EnvironmentVariables": {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:"
                                         + str(Path(binary).parent) + ":" + str(Path(shutil.which("python3")).parent),
                                 "CLIPPER_PROFILE": config.PROFILE},
    }
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
    plist_path.write_bytes(plistlib.dumps(plist))
    subprocess.run(["launchctl", "load", str(plist_path)], check=True)
    return f"daily {config.PROFILE} run ({agent}) scheduled at {time_str} via launchd ({plist_path}); logs in logs/daily{sfx}.log"


def remove():
    live = remove_live()
    note = f" (and {', '.join(live)})" if live else ""
    return _remove_daily() + note


def _remove_daily():
    if not IS_MAC:
        unit = _daily_names()[1]
        subprocess.run(["systemctl", "--user", "disable", "--now", f"{unit}.timer"], capture_output=True)
        for ext in ("service", "timer"):
            (UNIT_DIR / f"{unit}.{ext}").unlink(missing_ok=True)
        return f"systemd {config.PROFILE} schedule removed"
    plist_path = _plist_path()
    if not plist_path.exists():
        return f"no launchd schedule installed for {config.PROFILE}"
    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
    plist_path.unlink()
    return f"launchd {config.PROFILE} schedule removed"


def status():
    live = ([f.stem for f in PLIST.parent.glob(f"{LABEL.rsplit('.', 1)[0]}.live-*.plist")] if IS_MAC else
            [f.stem for f in UNIT_DIR.glob(f"{UNIT.rsplit('-', 1)[0]}-live-*.timer")])
    return _daily_status() + ("\nlive: " + ", ".join(sorted(live)) if live else "\nlive: not scheduled")


def _daily_status():
    unit = _daily_names()[1]
    if not IS_MAC:
        if not (UNIT_DIR / f"{unit}.timer").exists():
            return f"no systemd schedule for {config.PROFILE} (use `clipper --profile {config.PROFILE} schedule install`)"
        res = subprocess.run(["systemctl", "--user", "list-timers", f"{unit}.timer", "--no-pager"],
                             capture_output=True, text=True)
        return res.stdout.strip() or f"{unit}.timer installed"
    plist_path = _plist_path()
    if not plist_path.exists():
        return (f"no launchd schedule for {config.PROFILE} (use the Claude Code Desktop / Codex app scheduler, or "
                f"`clipper --profile {config.PROFILE} schedule install`)")
    p = plistlib.loads(plist_path.read_bytes())
    t, argv = p["StartCalendarInterval"], p["ProgramArguments"]
    run = "codex exec" if argv[1:2] == ["exec"] else f"claude -p {argv[2]}"
    return (f"launchd: daily {config.PROFILE} run at {t['Hour']:02d}:{t['Minute']:02d} -> {run} "
            f"({Path(p['StandardOutPath']).relative_to(ROOT)})")
