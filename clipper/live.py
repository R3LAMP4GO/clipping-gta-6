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
    url = stream_url(ref)
    old = next((s for s in load_streams() if s["url"] == url), {})
    streams = [s for s in load_streams() if s["url"] != url]
    streams.append({"name": name or stream_name(url), "url": url, "topic_only": topic_only,
                    **({"priority": old["priority"]} if "priority" in old else {})})
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


def alive_recorders():
    """Recorders running now, across every profile (they share jobs/_live)."""
    return sum(1 for f in WORK.glob("*/pid") if _alive(f))


ANALYZE_TRIES = 3


def stranded_jobs():
    """This profile's recorded chunks whose analysis died with its recorder (a restart, a crash): never scored, so
    never clipped. A running analysis keeps an `analyzing` file with its process id."""
    out = []
    for jid in ready_jobs():
        job = JOBS / jid
        if (job / "candidates.json").exists() or not (job / "source.mp4").exists():
            continue
        if _alive(job / "analyzing"):
            continue
        tries = job / "analyze_tries"
        if int(tries.read_text() or 0 if tries.exists() else 0) >= ANALYZE_TRIES:
            continue
        out.append(jid)
    return out


def reanalyze_stranded():
    """Start a detached analysis (sharing the recorders' slots) for every stranded chunk."""
    started = []
    WORK.mkdir(parents=True, exist_ok=True)
    for jid in stranded_jobs():
        job = JOBS / jid
        tries = job / "analyze_tries"
        tries.write_text(str(int(tries.read_text() or 0 if tries.exists() else 0) + 1))
        log = open(WORK / "reanalyze.log", "a")
        proc = subprocess.Popen([sys.executable, "-m", "clipper", "live", "analyze", jid], cwd=ROOT, stdout=log,
                                stderr=log, start_new_session=True, env=profile_env())
        (job / "analyzing").write_text(str(proc.pid))
        started.append(jid)
    return started


def watch(cfg, chunk_minutes=30):
    """Start a recorder for every live on-topic stream that isn't being recorded yet, lowest `priority` first
    (default 100), until `max_recorders` are running. Also re-run the analysis of any chunk whose analysis died."""
    reanalyze_stranded()
    started = []
    cap = cfg.get("max_recorders")
    running = alive_recorders()
    for s in sorted(status(cfg), key=lambda s: float(s.get("priority", 100))):
        if cap is not None and running + len(started) >= int(cap):
            break
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


def make_job(segment, name, url, title, started_at, channel=None, analyzer_pid=None):
    # seconds too: a stream that reconnects in the same minute must not overwrite an earlier chunk
    jid = base = f"live-{slug(name)}-{datetime.fromtimestamp(started_at):%Y%m%d-%H%M%S}"
    n = 2
    while (JOBS / jid / "source.mp4").exists():  # a replacement recorder overlapping the old one, same second
        jid, n = f"{base}-{n}", n + 1
    job = JOBS / jid
    job.mkdir(parents=True, exist_ok=True)
    src = job / "source.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(segment), "-c", "copy", "-movflags", "+faststart",
                    str(src)], check=True)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(src)], capture_output=True, text=True).stdout.strip() or 0)
    channel = channel or name  # the streamer's display name for the credit line, not the recorder slug
    meta = {"id": jid, "url": url, "title": title, "channel": channel, "duration": round(dur), "offset": 0.0,
            "live": True, "recorded_at": started_at, "profile": config.PROFILE}
    (job / "job.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (job / "source.info.json").write_text(json.dumps({"title": title, "channel": channel, "is_live": True}),
                                          encoding="utf-8")
    if analyzer_pid:  # written before live_ready, so `watch` never mistakes a fresh chunk for a stranded one
        (job / "analyzing").write_text(str(analyzer_pid))
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
                (JOBS / jid / "analyzing").unlink(missing_ok=True)
            return
        time.sleep(15)


def _recording_started(d, session, timeout=120):
    """True once this session's first segment is growing on disk."""
    end = time.time() + timeout
    while time.time() < end:
        if any(f.stat().st_size > 256_000 for f in d.glob(f"{int(session)}-*.ts")):
            return True
        time.sleep(2)
    return False


def record(name, url, chunk_minutes=30, quality="best[height<=1080]/best", cfg=None, replace_pid=None):
    """Record until the stream ends; every finished chunk becomes a job. With `replace_pid`, the old recorder of
    this stream is stopped only once this one is writing, so a restart overlaps instead of leaving a gap."""
    d = WORK / slug(name)
    d.mkdir(parents=True, exist_ok=True)
    (d / "pid").write_text(str(os.getpid()))
    stop = []
    signal.signal(signal.SIGTERM, lambda *_: stop.append(1))
    misses = 0
    pending = []
    p, reconnect = {}, False
    while not stop and misses < 3:
        if not reconnect:  # after a session drops, go straight for a fresh HLS URL: no re-probe gap in the recording
            p = probe(url)
            if not p.get("live"):
                misses += 1
                time.sleep(60)
                continue
        reconnect = False
        misses = 0
        hls = subprocess.run(["yt-dlp", "-g", "-f", quality, "--no-warnings", url], capture_output=True, text=True)
        if hls.returncode != 0:
            time.sleep(5)
            continue
        session = time.time()
        pattern = d / f"{int(session)}-%04d.ts"
        ff = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", hls.stdout.strip().splitlines()[0], "-c", "copy",
                               "-f", "segment", "-segment_time", str(chunk_minutes * 60), "-reset_timestamps", "1",
                               str(pattern)])
        done = set()
        if replace_pid and _recording_started(d, session):
            try:
                os.kill(replace_pid, signal.SIGTERM)  # it saves its last partial chunk and exits
                print(f"[live] took over from recorder {replace_pid}", flush=True)
            except OSError:
                pass
            replace_pid = None

        def finish(final=False):
            segs = sorted(d.glob(f"{int(session)}-*.ts"))
            ready = segs if final else segs[:-1]  # the newest segment is still being written
            for i, seg in enumerate(ready):
                if seg.name not in done and seg.stat().st_size > 1_000_000:
                    idx = int(seg.stem.split("-")[1])
                    jid = make_job(seg, name, url, p["title"], session + idx * chunk_minutes * 60,
                                   p.get("channel"), os.getpid() if cfg is not None else None)
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
        finish(final=True)  # ffmpeg ended: the HLS URL expired or the stream stopped
        reconnect = not stop
    for t in pending:
        t.join()
    if _alive(d / "pid") == os.getpid():  # a replacement recorder owns the pid file now
        (d / "pid").unlink(missing_ok=True)


def restart(name, chunk_minutes=30):
    """Replace a stream's recorder (e.g. to load new code) without a gap: the new one starts recording first."""
    s = next((x for x in load_streams() if x["name"] == name or slug(x["name"]) == slug(name)), None)
    if not s:
        raise SystemExit(f"no stream '{name}' in this profile's live.yaml")
    d = WORK / slug(s["name"])
    d.mkdir(parents=True, exist_ok=True)
    old = _alive(d / "pid")
    if old:
        try:  # keep the old recorder's chunk length
            argv = Path(f"/proc/{old}/cmdline").read_bytes().split(b"\0")
            chunk_minutes = int(argv[argv.index(b"--chunk") + 1])
        except (OSError, ValueError, IndexError):
            pass
    log = open(d / "recorder.log", "a")
    cmd = [sys.executable, "-m", "clipper", "live", "record", s["name"], s["url"], "--chunk", str(chunk_minutes)]
    proc = subprocess.Popen(cmd + (["--replace", str(old)] if old else []), cwd=ROOT, stdout=log, stderr=log,
                            start_new_session=True, env=profile_env())
    return {"stream": s["name"], "new_pid": proc.pid, "replacing": old, "chunk": chunk_minutes}


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


def mark_done(jid, drop_source=False):
    """Clipped. source.mp4 stays for a few hours (`keep_live_sources_hours`) so multi-streamer edits can still cut
    this stream's side of a moment; the autopilot cleanup deletes it after that."""
    job = JOBS / jid
    (job / "live_done").write_text(datetime.now().isoformat())
    (job / "audio.wav").unlink(missing_ok=True)  # only analysis reads it
    if drop_source:
        (job / "source.mp4").unlink(missing_ok=True)
    return jid


def job_time(job, meta):
    """When the job's footage was recorded (live) or fetched."""
    return float(meta.get("recorded_at") or (job / "job.json").stat().st_mtime)


def find(pattern, hours=6, jobs_dir=None):
    """Lines matching `pattern` in every job of the last `hours` (all profiles): the same cutscene line is the same
    moment in every stream that played it, which is how a multi-streamer edit finds its other angles."""
    rx = re.compile(pattern, re.I)
    since = time.time() - hours * 3600
    hits = []
    for tf in sorted(Path(jobs_dir or JOBS).glob("*/transcript.json")):
        job = tf.parent
        try:
            meta = json.loads((job / "job.json").read_text(encoding="utf-8"))
            words = json.loads(tf.read_text(encoding="utf-8"))["words"]
        except (OSError, ValueError, KeyError):
            continue
        t0 = job_time(job, meta)
        if t0 + float(meta.get("duration") or 0) < since:
            continue
        from .transcribe import drop_repeats, group_sentences
        for sent in group_sentences(drop_repeats(words)):
            if rx.search(sent["text"]):
                at = (datetime.fromtimestamp(t0 + float(meta.get("offset", 0) or 0) + sent["s"]).strftime("%H:%M:%S")
                      if meta.get("live") else None)
                hits.append({"job": job.name, "channel": meta.get("channel"), "at": at, "start": round(sent["s"], 2),
                             "end": round(sent["e"], 2), "text": sent["text"].strip(),
                             "footage": (job / "source.mp4").exists(), "profile": meta.get("profile")})
    return sorted(hits, key=lambda h: (h["at"] or "", h["job"], h["start"]))
