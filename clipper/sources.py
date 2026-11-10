import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor

from .config import JOBS


def _flat(url, limit):
    cmd = ["yt-dlp", "--flat-playlist", "-I", f"1:{limit}", "-J", "--no-warnings", url]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if res.returncode != 0:
        return None, res.stderr.strip().splitlines()[-1:] or ["yt-dlp failed"]
    return json.loads(res.stdout), None


def _matches(title, keywords):
    t = title.lower()
    return [k for k in keywords if re.search(r"\b" + re.escape(k.lower()) + r"\b", t)]


def _full_meta(vid):
    res = subprocess.run(["yt-dlp", "-j", "--skip-download", "--no-warnings", "--no-playlist",
                          f"https://www.youtube.com/watch?v={vid}"], capture_output=True, text=True, timeout=120)
    return json.loads(res.stdout) if res.returncode == 0 and res.stdout.strip() else None


def topic_patterns(cfg):
    return cfg.get("topic_patterns", cfg.get("gta6_patterns", []))  # gta6_* are the pre-profile names


def require_topic(cfg):
    return cfg.get("require_topic", cfg.get("require_gta6", True))


def topic_evidence(title, description, tags, cfg):
    """Where the video proves it's on the profile's topic ('title'/'description'/'tags'), or None."""
    pats = [re.compile(p, re.I) for p in topic_patterns(cfg)]
    excl = [re.compile(p, re.I) for p in cfg.get("exclude_title_patterns", [])]
    if any(p.search(title) for p in excl):
        return None
    if any(p.search(title) for p in pats):
        return "title"
    if any(p.search((description or "")[:600]) for p in pats):
        return "description"
    if any(p.search(t) for p in pats for t in tags or []):
        return "tags"
    return None


def watch(cfg, per_channel=8, searches=None):
    keywords = cfg.get("keywords", [])
    max_s = cfg.get("max_source_minutes", 240) * 60
    sources = [(c["name"], c["url"], c.get("match", "any")) for c in cfg.get("channels", [])]
    for q in searches if searches is not None else cfg.get("search", []):
        sources.append((f"search: {q}", f"ytsearch{per_channel}:{q}", "keywords"))

    found, errors, seen = [], [], set()
    for name, url, match in sources:
        data, err = _flat(url, per_channel)
        if err:
            errors.append({"source": name, "error": err[0]})
            continue
        for e in data.get("entries") or []:
            vid, title, dur = e.get("id"), e.get("title") or "", e.get("duration")
            if not vid or vid in seen or not dur or dur < 90 or dur > max_s:
                continue
            hits = _matches(title, keywords)
            if match != "any" and not hits:
                continue
            seen.add(vid)
            found.append({
                "id": vid, "title": title, "duration": int(dur),
                "channel": e.get("channel") or e.get("uploader") or name, "source": name,
                "views": e.get("view_count"), "keywords": hits,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "processed": (JOBS / vid / "candidates.json").exists(),
            })
    if not require_topic(cfg):
        return found, errors, 0
    with ThreadPoolExecutor(max_workers=6) as pool:
        metas = list(pool.map(_full_meta, [v["id"] for v in found]))
    kept = []
    for v, m in zip(found, metas):
        ev = topic_evidence(v["title"], (m or {}).get("description"), (m or {}).get("tags"), cfg)
        if ev:
            v["topic_evidence"] = ev
            kept.append(v)
    return kept, errors, len(found) - len(kept)


def _seconds(ts):
    secs = 0.0
    for part in ts.split(":"):
        secs = secs * 60 + float(part)
    return secs


def video_id(video):
    m = re.search(r"(?:v=|youtu\.be/|shorts/|live/)([\w-]{11})", video)
    if m:
        return m.group(1)
    if re.fullmatch(r"[\w-]{11}", video):
        return video
    res = subprocess.run(["yt-dlp", "--print", "id", "--no-playlist", video],
                         capture_output=True, text=True, check=True)
    return res.stdout.strip().splitlines()[0]


def fetch(video, section=None):
    vid = video_id(video)
    url = f"https://www.youtube.com/watch?v={vid}"
    job = JOBS / vid
    job.mkdir(parents=True, exist_ok=True)
    src = job / "source.mp4"
    if not src.exists():
        cmd = ["yt-dlp", "--no-playlist", "--write-info-json", "--merge-output-format", "mp4",
               "-f", "bv*[height<=1080][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b",
               "-o", str(job / "source.%(ext)s"), url]
        if section:
            cmd += ["--download-sections", f"*{section}", "--force-keyframes-at-cuts"]
        subprocess.run(cmd, check=True)
    info = json.loads((job / "source.info.json").read_text(encoding="utf-8"))
    meta = {
        "id": vid, "url": url, "title": info.get("title"),
        "channel": info.get("channel") or info.get("uploader"),
        "duration": info.get("duration"),
        "offset": _seconds(section.split("-")[0]) if section else 0.0,
    }
    (job / "job.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return job, meta
