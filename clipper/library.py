"""Creators list and saved preferences (plain YAML files the CLI owns), per profile."""
import json
import re
import subprocess

import yaml

from . import config

CREATORS_HEADER = "# Managed by `python3 -m clipper creators`. Every upload is still checked against the profile's topic.\n"
PREF_RULES = {
    "voice": ("off", "all", "auto"),
    "videos_per_run": ("auto", *range(1, 21)), "max_videos_per_run": range(1, 31), "hooks_per_video": ("auto", *range(1, 9)), "sources_per_day": range(1, 11),
    "daily_max_minutes": range(10, 601), "schedule_time": re.compile(r"^([01]\d|2[0-3]):[0-5]\d$"),
}


def creators_path():
    return config.profile_file("creators.yaml")


def prefs_path():
    return config.prefs_file()


def load_creators():
    path = creators_path()
    if not path.exists():
        return []
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("creators") or []


def save_creators(creators):
    path = creators_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(CREATORS_HEADER + yaml.safe_dump({"creators": creators}, sort_keys=False, allow_unicode=True),
                        encoding="utf-8")


def channel_url(ref):
    """'@KaiCenat', 'KaiCenat', or any channel URL -> the channel's /videos URL."""
    ref = ref.strip()
    if ref.startswith("http"):
        base = re.sub(r"/(videos|shorts|streams|featured|live)/?$", "", ref.rstrip("/"))
        return base + "/videos"
    return f"https://www.youtube.com/@{ref.lstrip('@')}/videos"


def lookup_channel(url):
    res = subprocess.run(["yt-dlp", "--flat-playlist", "-I", "1:1", "-J", "--no-warnings", url],
                         capture_output=True, text=True, timeout=120)
    if res.returncode != 0:
        return None
    data = json.loads(res.stdout)
    return data.get("channel") or data.get("uploader") or data.get("title")


def add_creator(ref, name=None):
    url = channel_url(ref)
    creators = load_creators()
    if any(c["url"].lower() == url.lower() for c in creators):
        return None, f"already watching {url}"
    found = lookup_channel(url)
    if not found:
        return None, f"no YouTube channel at {url}"
    entry = {"name": name or found, "url": url}
    save_creators(creators + [entry])
    return entry, f"added {entry['name']} ({url})"


def remove_creator(ref):
    creators = load_creators()
    key = ref.lower().lstrip("@")
    keep = [c for c in creators if key not in (c["name"].lower(), c["url"].lower())
            and f"/@{key}/" not in c["url"].lower()]
    save_creators(keep)
    return len(creators) - len(keep)


def load_prefs():
    path = prefs_path()
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}


def hooks_per_video():
    """The saved number, or with `auto` the count the strategy simulation recommends."""
    val = load_prefs().get("hooks_per_video", "auto")
    if str(val).isdigit():
        return int(val)
    from .simulate import recommended_hooks
    return recommended_hooks()


def set_prefs(pairs):
    """['voice=auto', 'videos_per_run=3'] -> updated prefs; raises ValueError on bad input."""
    prefs = load_prefs()
    for pair in pairs:
        key, _, raw = pair.partition("=")
        key, raw = key.strip(), raw.strip()
        rule = PREF_RULES.get(key)
        if rule is None:
            raise ValueError(f"unknown pref '{key}' (choose from {', '.join(PREF_RULES)})")
        val = int(raw) if raw.isdigit() and not hasattr(rule, "match") else raw
        ok = rule.match(val) if hasattr(rule, "match") else val in rule
        if not ok:
            raise ValueError(f"bad value for {key}: {raw}")
        prefs[key] = val
    path = prefs_path()
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    for key, val in prefs.items():
        line = f'{key}: "{val}"' if key == "schedule_time" else f"{key}: {val}"
        if re.search(rf"^{key}:.*$", text, re.M):
            text = re.sub(rf"^{key}:[^#\n]*?(\s*#.*)?$", lambda m: line + (m.group(1) or ""), text, flags=re.M)
        else:
            text += line + "\n"
    path.write_text(text, encoding="utf-8")
    return prefs
