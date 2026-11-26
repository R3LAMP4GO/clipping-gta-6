"""Delete media that's no longer needed, so recordings don't fill the disk.

Sources: only a job's source.mp4 and audio.wav go. Transcripts, candidates, picks and exports stay, and a finished
download can be fetched again.

Long-form (purge): a clip bank cut once every long video that used it is posted and keep_after_post_days passed; an
unused one bank_expire_days after tagging (listed one run first); a posted long's thumbnail files after the same
grace; Codex's leftover session folders; cached exemplar thumbnails (jobs/_thumbstyle/, YouTube data) after 30
days; and, only when keep_posted_short_exports_days is set, posted Shorts' MP4s.
A path is deleted only inside what owns it (a bank clip folder, a posted `long N`, the recorded Codex session, a
posted `video N`, jobs/_thumbstyle/), and every deletion is appended to jobs/_longbank/ledger.jsonl. The finished long MP4 and
long.json are never deleted."""
import json
import time
from pathlib import Path

from . import live, longbank
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


def _json(f):
    try:
        return json.loads(Path(f).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _grace(cfg):
    return float(cfg.get("keep_after_post_days", 2) or 0) * 86400


def _spans(spec):
    th = spec.get("thumbnail") or {}
    items = [*(spec.get("clips") or []), *(spec.get("flash_forward") or [])]
    if th.get("job") and th.get("t") is not None:
        items.append({"job": th["job"], "start": th["t"], "end": th["t"]})
    for r in th.get("refs") or []:
        if isinstance(r, dict) and r.get("job") and r.get("t") is not None:
            items.append({"job": r["job"], "start": r["t"], "end": r["t"]})
    out = []
    for it in items:
        try:
            out.append((Path(str(it["job"])).name, float(it["start"]), float(it["end"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def draft_spans(jobs_dir, posted_hashes):
    """(job, start, end) used by specs on disk (jobs/long-*.json) that aren't a posted long's exact spec: drafts and
    re-edits keep their bank clips."""
    from .longform import spec_sha256
    out = []
    for f in sorted(Path(jobs_dir).glob("long-*.json")):
        spec = _json(f)
        if isinstance(spec, dict) and spec_sha256(spec) not in posted_hashes:
            out += _spans(spec)
    return out


def _longs(exports):
    return {f.parent.resolve(): m for f in sorted(Path(exports).glob("**/long.json"))
            if isinstance(m := _json(f), dict)} if exports and Path(exports).is_dir() else {}


def owned(path, kind, owner, bank, codex_gen):
    """Whether `path` is a file inside `owner`, and `owner` is one of the five things the purge may delete from."""
    path, owner = Path(path), Path(owner)
    try:
        p, o = path.resolve(), owner.resolve()
    except OSError:
        return False
    if not path.is_file() or path.is_symlink() or not p.is_relative_to(o) or p == o:
        return False
    if kind == "bank":
        return o.parent == Path(bank).resolve()
    if kind == "long":
        return bool((_json(o / "long.json") or {}).get("posted_at"))
    if kind == "codex":
        return o.parent == Path(codex_gen).resolve()
    if kind == "thumbstyle":
        return o.name == "_thumbstyle" and p.parent == o
    if kind == "short":
        data = _json(o / "upload.json")
        return isinstance(data, list) and any(isinstance(e, dict) and e.get("youtube_id") for e in data)
    return False


def purge_plan(cfg, jobs_dir=None, exports=None, now=None, codex=None):
    """What the long-form rules delete now: {"delete": [{path, bytes, reason, kind, owner}], "expiring": [ids that go
    next run], "warn": [bank dirs to mark]}."""
    from .longform import STYLE_CACHE_DAYS, THUMB_FILES, codex_home
    jobs_dir, now = Path(jobs_dir or JOBS), now or time.time()
    bank = jobs_dir / "_longbank"
    grace, expire = _grace(cfg), cfg.get("bank_expire_days", 30)
    longs = _longs(exports)
    posted_hashes = {m.get("spec_sha256") for m in longs.values() if m.get("posted_at")}
    drafts = draft_spans(jobs_dir, posted_hashes)
    out = {"delete": [], "expiring": [], "warn": []}

    def add(path, kind, owner, reason):
        out["delete"].append({"path": Path(path), "bytes": Path(path).stat().st_size, "reason": reason,
                              "kind": kind, "owner": Path(owner)})

    for d, x in longbank.entries(bank):
        if not longbank.alive(d, x):
            continue
        if any(j == x["job"] and s <= float(x["to"]) and e >= float(x["from"]) for j, s, e in drafts):
            continue  # a spec on disk still needs it
        if x.get("status") == "used":
            used = [Path(u) for u in x.get("used_in") or []]
            posted = [(_json(u / "long.json") or {}).get("posted_at") for u in used]
            if used and all(posted) and now >= max(map(float, posted)) + grace:
                add(d / "clip.mp4", "bank", d, f"used in {', '.join(u.name for u in used)}, posted, "
                                               f"{grace / 86400:g} days grace over")
        elif expire is not None and now - float(x.get("tagged_at") or now) > float(expire) * 86400:
            if x.get("expire_warned_at"):
                add(d / "clip.mp4", "bank", d, f"unused for {expire:g} days")
            else:
                out["expiring"].append(x["id"])
                out["warn"].append(d)
    gen = Path(codex or codex_home()) / "generated_images"
    for folder, m in longs.items():
        sess = m.get("codex_session_dir")
        if sess and Path(sess).is_dir():
            for f in sorted(Path(sess).iterdir()):
                if f.is_file():
                    add(f, "codex", sess, "Codex's copy of a generated thumbnail")
        if m.get("posted_at") and now >= float(m["posted_at"]) + grace:
            for pat in THUMB_FILES:
                for f in sorted(folder.glob(pat)):
                    add(f, "long", folder, f"thumbnail of posted {folder.name}, {grace / 86400:g} days grace over")
    style = jobs_dir / "_thumbstyle"
    for f in sorted(style.glob("*")) if style.is_dir() else []:
        if f.is_file() and now - f.stat().st_mtime > STYLE_CACHE_DAYS * 86400:
            add(f, "thumbstyle", style, f"cached exemplar thumbnail older than {STYLE_CACHE_DAYS} days (YouTube data)")
    days = cfg.get("keep_posted_short_exports_days")
    if days is not None and exports and Path(exports).is_dir():
        wanted = {str(Path(x["short"]).resolve()) for d, x in longbank.entries(bank)
                  if x.get("short") and x.get("status") == "tagged" and longbank.alive(d, x)}
        for f in sorted(Path(exports).glob("**/video */upload.json")):
            data = _json(f)
            posted = isinstance(data, list) and any(isinstance(e, dict) and e.get("youtube_id") for e in data)
            if not posted or now - f.stat().st_mtime <= float(days) * 86400 or str(f.parent.resolve()) in wanted:
                continue
            for mp4 in sorted(f.parent.glob("*.mp4")):
                add(mp4, "short", f.parent, f"posted Short, older than {days:g} days")
    return out


def purge(cfg, dry_run=False, jobs_dir=None, exports=None, now=None, codex=None):
    """Run purge_plan: delete (or, dry run, only list) its files after the ownership check, log each to the ledger
    and mark the records (clip.json deleted_at, long.json thumbnail_deleted_at)."""
    from .longform import codex_home
    jobs_dir, now = Path(jobs_dir or JOBS), now or time.time()
    bank = jobs_dir / "_longbank"
    gen = Path(codex or codex_home()) / "generated_images"
    plan = purge_plan(cfg, jobs_dir, exports, now, codex)
    done, refused, ledger = [], [], []
    for e in plan["delete"]:
        if not owned(e["path"], e["kind"], e["owner"], bank, gen):
            refused.append(str(e["path"]))
            continue
        done.append(e)
        if dry_run:
            continue
        e["path"].unlink(missing_ok=True)
        ledger.append({"at": now, "path": str(e["path"]), "bytes": e["bytes"], "reason": e["reason"]})
        if e["kind"] == "bank":
            x = longbank.load(e["owner"])
            longbank.save(e["owner"], {**x, "deleted_at": now, "deleted_reason": e["reason"]})
        elif e["kind"] == "long":
            f = e["owner"] / "long.json"
            m = _json(f)
            if m is not None and not m.get("thumbnail_deleted_at"):
                f.write_text(json.dumps({**m, "thumbnail_deleted_at": now}, indent=2, ensure_ascii=False), encoding="utf-8")
        elif e["kind"] == "codex":
            try:
                e["owner"].rmdir()
            except OSError:
                pass  # not empty yet
    if not dry_run:
        if ledger:
            longbank.append_ledger(ledger, bank)
        for d in plan["warn"]:
            longbank.save(d, {**longbank.load(d), "expire_warned_at": now})
    size = sum(e["bytes"] for e in done)
    return {"dry_run": dry_run, "files": len(done), "bytes": size, "gb": round(size / 1e9, 3),
            "deleted": [{"path": str(e["path"]), "mb": round(e["bytes"] / 1e6, 1), "reason": e["reason"]} for e in done],
            "expiring_next_run": plan["expiring"], "refused": refused}


def run(cfg, dry_run=False, jobs_dir=None, exports=None, now=None, codex=None):
    """The source rule, then the long-form purge. Exports default to exports/ only for the real jobs folder."""
    from .render import EXPORTS
    files = stale_sources(cfg, jobs_dir, now)
    size = sum(f.stat().st_size for f in files)
    if not dry_run:
        for f in files:
            f.unlink(missing_ok=True)
    longform = purge(cfg, dry_run, jobs_dir, exports if exports or jobs_dir else EXPORTS, now, codex)
    return {"dry_run": dry_run, "files": len(files), "gb": round(size / 1e9, 2),
            "jobs": sorted({f.parent.name for f in files}), "longform": longform}
