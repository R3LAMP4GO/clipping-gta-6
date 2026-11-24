"""Clip bank: moments tagged for long-form, cut out of their source (padded, re-encoded at source size) into
jobs/_longbank/<id>/clip.mp4 + clip.json, so the multi-GB source can still be deleted on schedule. A banked moment is
single use: once a long video that used it is posted (`clipper bank done`) and keep_after_post_days pass,
cleanup.py deletes it; an unused one ages out after bank_expire_days."""
import json
import re
import subprocess
import time
from pathlib import Path

from . import config, render

LEDGER = "ledger.jsonl"
TOL = 0.05  # seconds of slack when matching a span to a bank clip (frame rounding)


def root():
    return config.JOBS / "_longbank"


def load(d):
    return json.loads((Path(d) / "clip.json").read_text(encoding="utf-8"))


def save(d, data):
    tmp = Path(d) / "clip.json.tmp"
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(Path(d) / "clip.json")


def entries(bank=None):
    """[(dir, clip.json)] for every banked moment, deleted ones included (their clip.json stays as the record)."""
    bank = Path(bank or root())
    out = []
    for f in sorted(bank.glob("*/clip.json")) if bank.is_dir() else []:
        try:
            out.append((f.parent, json.loads(f.read_text(encoding="utf-8"))))
        except (OSError, ValueError):
            continue
    return sorted(out, key=lambda x: x[1].get("tagged_at") or 0)


def alive(d, data):
    return not data.get("deleted_at") and (Path(d) / "clip.mp4").exists()


def clip_id(job_name, start, end):
    base = re.sub(r"[^A-Za-z0-9_-]+", "-", job_name).strip("-")[:60] or "job"
    return f"{base}-{start:.1f}-{end:.1f}".replace(".", "_")


def covering(job_name, start, end, bank=None):
    """(dir, clip.json) of a live bank clip holding [start, end] of that job, the most recent first; else None."""
    hits = [(d, x) for d, x in entries(bank) if x.get("job") == job_name and alive(d, x)
            and float(x["from"]) <= float(start) + TOL and float(end) <= float(x["to"]) + TOL]
    return hits[-1] if hits else None


def deleted_covering(job_name, start, end, bank=None):
    """A bank clip of that span that was already deleted (used in a posted long, or expired), else None."""
    hits = [(d, x) for d, x in entries(bank) if x.get("job") == job_name and x.get("deleted_at")
            and float(x["from"]) <= float(start) + TOL and float(end) <= float(x["to"]) + TOL]
    return hits[-1] if hits else None


def overlapping(job_name, start, end, bank=None):
    """Live bank clips whose tagged moment overlaps [start, end] of that job."""
    return [(d, x) for d, x in entries(bank) if x.get("job") == job_name and alive(d, x)
            and float(x["start"]) < float(end) and float(start) < float(x["end"])]


def _duration(src):
    res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)],
                         capture_output=True, text=True, check=True)
    return float(res.stdout.strip() or 0)


def tag(job, start, end, cfg, note=None, niche=None, short=None, bank=None):
    """Cut [start - pad, end + pad] of the job's source into the bank and record it; returns clip.json. A moment an
    existing bank clip already holds isn't cut again."""
    start, end = float(start), float(end)
    if end <= start:
        raise SystemExit(f"end {end:g}s must be after start {start:g}s")
    jd = config.job_dir(job)
    bank = Path(bank or root())
    hit = covering(jd.name, start, end, bank)
    if hit:
        return {**hit[1], "already_banked": True}
    src = jd / "source.mp4"
    if not src.exists():
        raise SystemExit(f"{jd.name}: source.mp4 is already deleted; a moment can only be tagged while its source is "
                         "on disk (cleanup keeps it keep_sources_days, live chunks keep_live_sources_hours)")
    dur = _duration(src)
    if dur and end > dur + TOL:
        raise SystemExit(f"{jd.name}: {end:g}s is past the end of the source ({dur:.0f}s)")
    pad = float(cfg.get("longbank_pad_s", 3) or 0)
    a, b = max(0.0, start - pad), min(dur, end + pad) if dur else end + pad
    d = bank / clip_id(jd.name, start, end)
    d.mkdir(parents=True, exist_ok=True)
    part = d / "clip.part.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}",
                    "-i", str(src), "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-movflags", "+faststart", str(part)], check=True)
    part.replace(d / "clip.mp4")
    try:
        channel = render.load_meta(jd).get("channel")
    except (OSError, ValueError):
        channel = None
    data = {"id": d.name, "job": jd.name, "start": round(start, 3), "end": round(end, 3), "pad": pad,
            "from": round(a, 3), "to": round(b, 3), "niche": niche, "note": note, "channel": channel,
            "short": str(short) if short else None, "status": "tagged", "bytes": (d / "clip.mp4").stat().st_size,
            "tagged_at": time.time(), "used_in": []}
    save(d, data)
    return data


def short_moments(folder, jobs_dir=None):
    """[(job name, start, end)] in source seconds for a rendered Short (`video N` folder), from its upload.json
    `footage` (wall-clock seconds for live chunks), matched to the job whose source holds it."""
    f = Path(folder) / "upload.json"
    if not f.exists():
        raise SystemExit(f"no upload.json in {folder}")
    data = json.loads(f.read_text(encoding="utf-8"))
    fp = next((e.get("footage") for e in (data if isinstance(data, list) else [data])
               if isinstance(e, dict) and e.get("footage") and not e.get("lang")), None)
    if not fp:
        raise SystemExit(f"{folder}/upload.json lists no footage (rendered before footage was recorded)")
    jobs_dir = Path(jobs_dir or config.JOBS)
    out = []
    for span in fp:
        found = None
        for jd in sorted(jobs_dir.iterdir()) if jobs_dir.is_dir() else []:
            if jd.name.startswith("_") or not (jd / "job.json").exists():
                continue
            try:
                meta = render.load_meta(jd)
            except (OSError, ValueError):
                continue
            if render.footage_key(meta) != span.get("source"):
                continue
            base = (float(meta.get("recorded_at") or 0) if render.wall_clock(meta) else 0.0) + float(meta.get("offset", 0) or 0)
            s, e = float(span["from"]) - base, float(span["to"]) - base
            if s < -TOL:
                continue
            src = jd / "source.mp4"
            if src.exists() and e <= _duration(src) + TOL:
                found = (jd.name, max(0.0, s), e)
                break
            if found is None and not render.wall_clock(meta):
                found = (jd.name, max(0.0, s), e)  # a VOD job: the right one even if its source is gone
        if not found:
            raise SystemExit(f"no job in {jobs_dir} holds {span.get('source')} {span.get('from')}-{span.get('to')}")
        out.append(found)
    return out


def ids_for(items, bank=None):
    """Ids of the live bank clips that the spec items ({job, start, end}) use."""
    out = []
    for it in items:
        try:
            jd = config.job_dir(it["job"])
        except SystemExit:
            continue
        for d, x in overlapping(jd.name, float(it["start"]), float(it["end"]), bank):
            if x["id"] not in out:
                out.append(x["id"])
    return out


def mark_used(ids, folder, bank=None):
    bank = Path(bank or root())
    for i in ids:
        d = bank / i
        x = load(d)
        x["status"] = "used"
        x["used_in"] = sorted(set(x.get("used_in") or []) | {str(Path(folder).resolve())})
        x["used_at"] = time.time()
        save(d, x)


def mark_posted(folder, cfg, youtube_id=None, bank=None, now=None):
    """`clipper bank done`: the long video in `folder` is posted. Records posted_at in long.json and in every bank
    clip it used, which starts their keep_after_post_days grace before cleanup deletes them."""
    folder = Path(folder).resolve()
    f = folder / "long.json"
    if not f.exists():
        raise SystemExit(f"no long.json in {folder}")
    m = json.loads(f.read_text(encoding="utf-8"))
    now = now or time.time()
    m["posted_at"] = m.get("posted_at") or now
    if youtube_id:
        m["youtube_id"] = youtube_id
    tmp = folder / "long.json.tmp"
    tmp.write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(f)
    grace = float(cfg.get("keep_after_post_days", 2) or 0) * 86400
    bank = Path(bank or root())
    marked = []
    for i in m.get("bank_ids") or []:
        d = bank / i
        if not (d / "clip.json").exists():
            continue
        x = load(d)
        x["posted_at"] = max(float(x.get("posted_at") or 0), float(m["posted_at"]))
        x["purge_after"] = x["posted_at"] + grace
        save(d, x)
        marked.append(i)
    return {"folder": str(folder), "posted_at": m["posted_at"], "youtube_id": m.get("youtube_id"), "bank_clips": marked,
            "purge_after_days": grace / 86400}


def append_ledger(rows, bank=None):
    bank = Path(bank or root())
    bank.mkdir(parents=True, exist_ok=True)
    with open(bank / LEDGER, "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
