"""Delete job video and audio that's no longer needed, so recordings don't fill the disk.

Only a job's source.mp4 and audio.wav go. Transcripts, candidates, picks and every export stay, and a finished
download can be fetched again."""
import time

from . import live
from .config import JOBS

TARGETS = ("source.mp4", "audio.wav")


def stale_sources(cfg, jobs_dir=None, now=None):
    """Source files past their keep time: a clipped live chunk's after keep_live_sources_hours (it's only kept for
    multi-streamer edits), any other job's once nothing in it changed for keep_sources_days. null keeps them."""
    jobs_dir, now = jobs_dir or JOBS, now or time.time()
    live_h, days = cfg.get("keep_live_sources_hours"), cfg.get("keep_sources_days")
    out = []
    if not jobs_dir.is_dir():
        return out
    for job in sorted(jobs_dir.iterdir()):
        if job.name.startswith("_") or not job.is_dir() or live._alive(job / "analyzing"):
            continue
        files = [job / n for n in TARGETS if (job / n).exists()]
        if not files:
            continue
        done = job / "live_done"
        if done.exists() and live_h is not None and now - done.stat().st_mtime > float(live_h) * 3600:
            out += files
            continue
        newest = max(f.stat().st_mtime for f in job.iterdir() if f.is_file())
        if days is not None and now - newest > float(days) * 86400:
            out += files
    return out


def run(cfg, dry_run=False, jobs_dir=None):
    files = stale_sources(cfg, jobs_dir)
    size = sum(f.stat().st_size for f in files)
    if not dry_run:
        for f in files:
            f.unlink(missing_ok=True)
    return {"dry_run": dry_run, "files": len(files), "gb": round(size / 1e9, 2),
            "jobs": sorted({f.parent.name for f in files})}
