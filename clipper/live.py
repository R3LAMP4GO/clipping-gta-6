"""Record live streams (Twitch, Kick, YouTube) while they're on, in gapless chunks that become normal jobs.

A recorder per live stream runs ffmpeg's segment muxer on the stream's HLS URL, so there's no gap between chunks.
Each finished chunk is remuxed into jobs/live-<name>-<time>/ with job.json + source.info.json, ready for
`clipper analyze`."""
import fcntl
import json
import os
import threading
import re
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import yaml

from . import config
from .config import JOBS, ROOT
from .sources import topic_evidence

WORK = JOBS / "_live"  # shared by all profiles: one recorder per stream, one set of analysis slots
HEADER = "# Live streams to record while they're on topic. Managed by `python3 -m clipper live add|remove`.\n"


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def streams_path():
    return config.profile_file("live.yaml")


def profile_env():
    """Child processes (recorders, analysis) run under the same profile."""
    return {**os.environ, "CLIPPER_PROFILE": config.PROFILE}


def load_streams():
    path = streams_path()
    if not path.exists():
        return []
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("streams") or []


def save_streams(streams):
    path = streams_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(HEADER + yaml.safe_dump({"streams": streams}, sort_keys=False), encoding="utf-8")


def stream_url(ref):
    """'twitch:xqc', 'kick:xqc', 'youtube:@KaiCenat' or a full URL -> the live URL yt-dlp understands."""
    if ref.startswith("http"):
        return ref.rstrip("/")
    site, _, name = ref.partition(":")
    return {"twitch": f"https://www.twitch.tv/{name}", "kick": f"https://kick.com/{name}",
            "youtube": f"https://www.youtube.com/@{name.lstrip('@')}/live"}[site]


def stream_name(url):
    """'xqc-twitch', 'xqc-kick', 'KaiCenat-youtube': one recorder per channel per site."""
    m = re.search(r"(twitch\.tv|kick\.com|youtube\.com)/@?([^/?]+)", url)
    return f"{m.group(2)}-{m.group(1).split('.')[0]}" if m else slug(url)


def topic_only(stream):
    return stream.get("topic_only", stream.get("gta_only", True))  # gta_only is the pre-profile name


def add(ref, name=None, topic_only=True):
    streams = [s for s in load_streams() if s["url"] != stream_url(ref)]
    url = stream_url(ref)
    streams.append({"name": name or stream_name(url), "url": url, "topic_only": topic_only})
    save_streams(streams)
    return streams[-1]


def remove(ref):
    keep = [s for s in load_streams() if ref.lower() not in (s["name"].lower(), s["url"].lower())]
    removed = len(load_streams()) - len(keep)
    save_streams(keep)
    return removed


def probe(url):
    """{'live': bool, 'title', 'description', 'tags'} for a channel's live URL."""
    res = subprocess.run(["yt-dlp", "-J", "--no-warnings", "--skip-download", "--no-playlist", url],
                         capture_output=True, text=True, timeout=90)
    if res.returncode != 0 or not res.stdout.strip():
        return {"live": False}
    info = json.loads(res.stdout)
    title = info.get("fulltitle") or info.get("title") or ""
    if re.fullmatch(r".+ \(live\)", title) and info.get("description"):
        title = info["description"]  # Twitch: yt-dlp's title is "<name> (live)"; the stream title is the description
    return {"live": bool(info.get("is_live") or info.get("live_status") == "is_live"),
            "title": title, "description": info.get("description") or "",
            "tags": info.get("tags") or [], "channel": info.get("channel") or info.get("uploader")}


def _alive(pid_file):
    try:
        pid = int(pid_file.read_text())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def status(cfg):
    streams = load_streams()
    with ThreadPoolExecutor(max_workers=8) as pool:
        probes = list(pool.map(lambda s: probe(s["url"]), streams))
    out = []
    for s, p in zip(streams, probes):
        on = bool(p.get("live")) and (not topic_only(s) or
                                      topic_evidence(p.get("title", ""), p.get("description"), p.get("tags"), cfg))
        out.append({**s, "live": p.get("live", False), "title": p.get("title"), "on_topic": bool(on),
                    "recording": bool(_alive(WORK / slug(s["name"]) / "pid"))})
    return out


def watch(cfg, chunk_minutes=30):
    """Start a recorder for every live on-topic stream that isn't being recorded yet."""
    started = []
    for s in status(cfg):
        if s["live"] and s["on_topic"] and not s["recording"]:
            d = WORK / slug(s["name"])
            d.mkdir(parents=True, exist_ok=True)
            log = open(d / "recorder.log", "a")
            proc = subprocess.Popen([sys.executable, "-m", "clipper", "live", "record", s["name"], s["url"],
                                     "--chunk", str(chunk_minutes)], cwd=ROOT, stdout=log, stderr=log,
                                    start_new_session=True, env=profile_env())
            (d / "pid").write_text(str(proc.pid))
            started.append(s["name"])
    return started


def make_job(segment, name, url, title, started_at):
    # seconds too: a stream that reconnects in the same minute must not overwrite an earlier chunk
    jid = f"live-{slug(name)}-{datetime.fromtimestamp(started_at):%Y%m%d-%H%M%S}"
    job = JOBS / jid
    job.mkdir(parents=True, exist_ok=True)
    src = job / "source.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(segment), "-c", "copy", "-movflags", "+faststart",
                    str(src)], check=True)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(src)], capture_output=True, text=True).stdout.strip() or 0)
    meta = {"id": jid, "url": url, "title": title, "channel": name, "duration": round(dur), "offset": 0.0,
            "live": True, "recorded_at": started_at, "profile": config.PROFILE}
    (job / "job.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (job / "source.info.json").write_text(json.dumps({"title": title, "channel": name, "is_live": True}),
                                          encoding="utf-8")
    (job / "live_ready").write_text(datetime.now().isoformat())
    segment.unlink(missing_ok=True)
    print(f"[live] chunk ready: {jid} ({dur / 60:.0f} min)", flush=True)
    return jid


def workers(cfg):
    """(analysis slots, whisper threads each): `live_workers: auto` keeps ~4 cores per transcription."""
    cpus = os.cpu_count() or 4
    n = cfg.get("live_workers", "auto")
    n = max(1, cpus // 4) if n == "auto" else max(1, int(n))
    return n, max(1, cpus // n)


def analyze_queued(jid, cfg):
    """Transcribe + score a chunk as soon as a slot is free. Slots are lock files, so every recorder process
    shares the same limit and the CPU isn't swamped when many creators are live."""
    n, threads = workers(cfg)
    slots = WORK / "slots"
    slots.mkdir(parents=True, exist_ok=True)
    while True:
        for i in range(n):
            f = open(slots / f"{i}.lock", "w")
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                f.close()
                continue
            try:
                cmd = [sys.executable, "-m", "clipper", "analyze", jid] + (["--fast"] if cfg.get("live_fast", True) else [])
                subprocess.run(cmd, cwd=ROOT, env={**profile_env(), "CLIPPER_ASR_THREADS": str(threads)},
                               stdout=subprocess.DEVNULL)
                print(f"[live] analyzed {jid}", flush=True)
            finally:
                f.close()
            return
        time.sleep(15)


def record(name, url, chunk_minutes=30, quality="best[height<=1080]/best", cfg=None):
    """Record until the stream ends; every finished chunk becomes a job."""
    d = WORK / slug(name)
    d.mkdir(parents=True, exist_ok=True)
    (d / "pid").write_text(str(os.getpid()))
    stop = []
    signal.signal(signal.SIGTERM, lambda *_: stop.append(1))
    misses = 0
    pending = []
    while not stop and misses < 3:
        p = probe(url)
        if not p.get("live"):
            misses += 1
            time.sleep(60)
            continue
        misses = 0
        hls = subprocess.run(["yt-dlp", "-g", "-f", quality, "--no-warnings", url], capture_output=True, text=True)
        if hls.returncode != 0:
            time.sleep(60)
            continue
        session = time.time()
        pattern = d / f"{int(session)}-%04d.ts"
        ff = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", hls.stdout.strip().splitlines()[0], "-c", "copy",
                               "-f", "segment", "-segment_time", str(chunk_minutes * 60), "-reset_timestamps", "1",
                               str(pattern)])
        done = set()

        def finish(final=False):
            segs = sorted(d.glob(f"{int(session)}-*.ts"))
            ready = segs if final else segs[:-1]  # the newest segment is still being written
            for i, seg in enumerate(ready):
                if seg.name not in done and seg.stat().st_size > 1_000_000:
                    idx = int(seg.stem.split("-")[1])
                    jid = make_job(seg, name, url, p["title"], session + idx * chunk_minutes * 60)
                    done.add(seg.name)
                    if cfg is not None:
                        t = threading.Thread(target=analyze_queued, args=(jid, cfg))
                        t.start()
                        pending.append(t)
        while ff.poll() is None and not stop:
            time.sleep(20)
            finish()
        if stop:
            ff.terminate()
            ff.wait()
        finish(final=True)  # ffmpeg ended: the stream stopped or the HLS URL expired; re-probe and go on
    for t in pending:
        t.join()
    (d / "pid").unlink(missing_ok=True)


def job_profile(job):
    try:
        return json.loads((job / "job.json").read_text(encoding="utf-8")).get("profile") or config.DEFAULT_PROFILE
    except (OSError, ValueError):
        return config.DEFAULT_PROFILE


def ready_jobs(analyzed_only=False):
    """The active profile's recorded chunks not clipped yet (with analyzed_only, only those already scored)."""
    return sorted(p.parent.name for p in JOBS.glob("live-*/live_ready") if not (p.parent / "live_done").exists()
                  and (not analyzed_only or (p.parent / "candidates.json").exists())
                  and job_profile(p.parent) == config.PROFILE)


def mark_done(jid, drop_source=True):
    job = JOBS / jid
    (job / "live_done").write_text(datetime.now().isoformat())
    if drop_source:  # a live chunk is ~1-3 GB/hour; the clips are rendered, the transcript and picks stay
        for f in ("source.mp4", "audio.wav"):
            (job / f).unlink(missing_ok=True)
    return jid
