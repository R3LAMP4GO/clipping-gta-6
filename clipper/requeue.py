"""Re-check rendered-but-unposted clips against the own-channel winners (2026-11-23): payoff by ~16 s, end within ~5 s
after it, 12-25 s, no stuck-pattern idea. Each unposted `video N` gets one verdict: keep, recut or hold. A dry run
writes nothing; `--apply` saves the recut picks to jobs/<id>/picks-requeue.json and renders them into new `video N`
folders, so the originals stay untouched (each gets a `superseded.json` pointing at its recut)."""
import json
import os
import re
from pathlib import Path

from . import config, hooks, render as render_mod
from .config import JOBS
from .render import EXPORTS
from .stats import STATS, norm_title

RECUT_TAIL_S = 3.0      # end this long after the payoff
RECUT_PAYOFF_S = 16.0   # a late payoff moves the start up so it lands about here
SUPERSEDED = "superseded.json"

# Ideas that stuck at ~1k on our channel: quizzes, sentimental moments, cutscenes and other people talking.
STUCK = re.compile(r"\b(quiz\w*|trivia|guess(es|ing)?|sentimental|heartfelt|emotional|cr(y|ies|ied|ying)|tears?|"
                   r"cutscenes?|story ?line|lore)\b", re.I)


def posted_titles(stats=STATS):
    """Normalized titles of our public uploads (`clipper stats` saves them); empty without the file."""
    try:
        rows = json.loads(Path(stats).read_text(encoding="utf-8")).get("uploads") or []
    except (OSError, ValueError):
        return set()
    return {norm_title(r.get("t")) for r in rows if r.get("t")}


def is_posted(entries, titles):
    return any(e.get("youtube_id") or (e.get("title") and norm_title(e["title"]) in titles) for e in entries)


def job_picks(jobs=JOBS):
    """[(job dir, picks file, index, pick, footage)] for every pick saved in any job's picks*.json."""
    out = []
    for f in sorted(Path(jobs).glob("*/picks*.json")):
        job = f.parent
        try:
            picks, meta = json.loads(f.read_text(encoding="utf-8")), render_mod.load_meta(job)
        except (OSError, ValueError):
            continue
        for i, pick in enumerate(picks if isinstance(picks, list) else []):
            try:
                fp = render_mod.footage(pick, job, meta)
            except (OSError, KeyError, TypeError, ValueError):
                continue
            out.append((job, f, i, pick, fp))
    return out


def match_pick(fp, candidates):
    """The saved pick whose footage is this export's (most shared seconds, at least most of the clip)."""
    want = sum(x["to"] - x["from"] for x in fp or [])
    best = max(candidates, key=lambda c: render_mod.footage_overlap(fp, c[4]), default=None)
    if best is None or want <= 0 or render_mod.footage_overlap(fp, best[4]) < 0.8 * want:
        return None
    return best


def stuck_reasons(pick, entries):
    """Why the idea looks like one of our ~1k-stuck Shorts (empty when it doesn't)."""
    out = []
    if pick.get("streamer_reacts") is False:
        out.append("the streamer isn't talking or reacting through it")
    text = " ".join(str(pick.get(k) or "") for k in ("turn", "cold_premise", "loop", "clip_type"))
    text += " " + " ".join(str(e.get("title") or "") for e in entries)
    m = STUCK.search(text)
    if m:
        out.append(f"stuck-pattern idea ({m.group(0)!r}: quizzes, sentimental moments, cutscenes or storylines)")
    if hooks.check_cold(pick):
        out.append("needs an inside joke or storyline: " + hooks.check_cold(pick)[0].split(":")[0])
    if not str(pick.get("loop") or "").strip():
        out.append("no `loop`: the title may promise something the clip never answers")
    return out


def _sources_gone(pick, job):
    jobs = [render_mod.segment_job_dir(s, job) for s in pick["segments"]] if pick.get("segments") else [job]
    return [j.name for j in dict.fromkeys(jobs) if not (Path(j) / "source.mp4").exists()]


def _words(job):
    f = Path(job) / "transcript.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))["words"]
    except (OSError, ValueError, KeyError):
        return []


def window(lo, hi, at):
    """(new start, new end) in the pick's seconds, or None when the clip already pays off by 20 s and ends within 5 s."""
    late, tail = at - lo > hooks.PAYOFF_BY_S, hi - at > hooks.PAYOFF_TAIL_S
    if not (late or tail):
        return None
    return (max(lo, at - RECUT_PAYOFF_S) if late else lo), (min(hi, at + RECUT_TAIL_S) if tail else hi)


def _snap(new_lo, new_hi, lo, hi, at, words):
    """Never cut a word in half: start on the first word from new_lo, end after the word running at new_hi."""
    ws = sorted((float(w["s"]), float(w["e"])) for w in words if "s" in w and "e" in w)
    if new_lo > lo:
        new_lo = next((s for s, _ in ws if new_lo <= s < at), new_lo)
    if new_hi < hi:
        new_hi = next((min(e, hi, at + hooks.PAYOFF_TAIL_S) for s, e in ws if s < new_hi < e), new_hi)
    return round(new_lo, 2), round(new_hi, 2)


def _in(t, a, b):
    return a <= float(t) <= b


def recut(pick, job):
    """The pick cut to the winners' shape: a copy, or None when it needs no recut."""
    at, (lo, hi) = float(pick["payoff_at"]), hooks.clip_bounds(pick)
    lo, hi = float(lo), float(hi)
    win = window(lo, hi, at)
    if not win:
        return None
    new = {k: v for k, v in pick.items()}
    if not pick.get("segments"):
        a, b = _snap(*win, lo, hi, at, _words(job))
        new.update(start=a, end=b)
        shift = 0.0
    else:  # segment picks: payoff, labels, fx and music are clip seconds
        a, b = win
        segs, t = [], 0.0
        for seg in pick["segments"]:
            d = float(seg["end"]) - float(seg["start"])
            s0, s1 = max(t, a), min(t + d, b)
            if s1 - s0 >= 0.5:
                segs.append({**seg, "start": round(float(seg["start"]) + s0 - t, 2),
                             "end": round(float(seg["start"]) + s1 - t, 2)})
            t += d
        new["segments"], shift = segs, a
        new["payoff_at"] = round(at - a, 2)
    for key, tk in (("labels", "s"), ("fx", "t"), ("music", "s")):
        if isinstance(pick.get(key), list) and pick[key]:
            new[key] = [{**x, tk: round(float(x[tk]) - shift, 2),
                         **({"e": round(min(float(x["e"]), b) - shift, 2)} if "e" in x else {})}
                        for x in pick[key] if _in(x[tk], a, b)]
    return new


def verdicts(cfg, exports=EXPORTS, jobs=JOBS, stats=STATS):
    """[{folder, verdict, reasons, job, pick?}] for every unposted, not yet superseded `video N` of the profile."""
    profile = cfg.get("profile", config.PROFILE)
    titles, candidates, out = posted_titles(stats), job_picks(jobs), []
    found = [f for f in Path(exports, profile).glob("*/video */upload.json") if re.fullmatch(r"video \d+", f.parent.name)]
    for f in sorted(found, key=lambda p: (p.parent.parent.name, int(p.parent.name.split()[-1]))):
        folder = f.parent
        rel = str(folder.relative_to(exports))
        if (folder / SUPERSEDED).exists():
            continue
        try:
            entries = [e for e in json.loads(f.read_text(encoding="utf-8")) if isinstance(e, dict) and not e.get("lang")]
        except (OSError, ValueError):
            out.append({"folder": rel, "verdict": "hold", "reasons": ["upload.json unreadable"]})
            continue
        if is_posted(entries, titles):
            continue
        fp = next((e.get("footage") for e in entries if e.get("footage")), None)
        if not fp:
            out.append({"folder": rel, "verdict": "hold", "reasons": ["no footage recorded (rendered before footage "
                                                                       "tracking): can't find its pick to recut"]})
            continue
        hit = match_pick(fp, candidates)
        if not hit:
            out.append({"folder": rel, "verdict": "hold", "reasons": ["source deleted: no saved pick or job "
                                                                       "uses this footage any more"]})
            continue
        job, pfile, idx, pick = hit[:4]
        row = {"folder": rel, "job": job.name, "picks": f"{pfile.parent.name}/{pfile.name}#{idx + 1}"}
        payoff = pick.get("payoff_at", next((e.get("payoff_at") for e in entries if e.get("payoff_at") is not None),
                                            None))
        reasons = []
        if payoff is None:
            reasons.append("no payoff recorded (`payoff_at`): can't tell where the clip should end")
        reasons += stuck_reasons(pick, entries)
        gone = _sources_gone(pick, job)
        if gone:
            reasons.append(f"source deleted ({', '.join(gone)}): re-fetch it to recut")
        if reasons:
            out.append({**row, "verdict": "hold", "reasons": reasons})
            continue
        pick = {**pick, "payoff_at": float(payoff)}
        lo, hi = (float(x) for x in hooks.clip_bounds(pick))
        if not lo <= pick["payoff_at"] <= hi:
            out.append({**row, "verdict": "hold", "reasons": [f"payoff_at {pick['payoff_at']:g}s is outside the "
                                                               f"clip ({lo:g}-{hi:g}s)"]})
            continue
        new = recut(pick, job)
        if not new:
            out.append({**row, "verdict": "keep", "reasons": [f"pays off {pick['payoff_at'] - lo:.0f}s in and ends "
                                                               f"{hi - pick['payoff_at']:.0f}s after it"]})
            continue
        nlo, nhi = (float(x) for x in hooks.clip_bounds(new))
        why = []
        if pick["payoff_at"] - lo > hooks.PAYOFF_BY_S:
            why.append(f"payoff {pick['payoff_at'] - lo:.0f}s in -> {float(new['payoff_at']) - nlo:.0f}s")
        if hi - pick["payoff_at"] > hooks.PAYOFF_TAIL_S:
            why.append(f"{hi - pick['payoff_at']:.0f}s after the payoff -> {nhi - float(new['payoff_at']):.0f}s")
        why.append(f"{hi - lo:.0f}s -> {nhi - nlo:.0f}s")
        out.append({**row, "verdict": "recut", "reasons": why, "pick": {**new, "requeued_from": rel}})
    return out


def _free_name(job):
    f, n = job / "picks-requeue.json", 2
    while f.exists():  # never overwrite an earlier requeue's picks
        f, n = job / f"picks-requeue-{n}.json", n + 1
    return f


def apply(cfg, rows, exports=EXPORTS, jobs=JOBS, render=None):
    """Save each job's recut picks and render them into new `video N` folders; mark each original superseded."""
    render = render or render_mod.render
    top = int(os.environ.get("CLIPPER_TOP_HOOKS") or 0)
    done = []
    by_job = {}
    for r in rows:
        if r["verdict"] == "recut":
            by_job.setdefault(r["job"], []).append(r)
    for jid, rs in by_job.items():
        job = Path(jobs) / jid
        picks = [r["pick"] for r in rs]
        pf = _free_name(job)
        pf.write_text(json.dumps(picks, indent=2, ensure_ascii=False), encoding="utf-8")
        results = render(job, picks, cfg, top=top)
        for r, res in zip(rs, results):
            new = str(Path(res["folder"]).resolve().relative_to(Path(exports).resolve()))
            (Path(exports) / r["folder"] / SUPERSEDED).write_text(json.dumps(
                {"recut": new, "picks": str(pf.relative_to(jobs)), "reasons": r["reasons"]}, indent=2) + "\n",
                encoding="utf-8")
            done.append({"from": r["folder"], "to": new})
    return done


def report(rows):
    lines = []
    for r in rows:
        lines.append(f"{r['verdict']:5}  {r['folder']}" + (f"  [{r['picks']}]" if r.get("picks") else ""))
        lines += [f"       - {x}" for x in r["reasons"]]
    counts = {v: sum(r["verdict"] == v for r in rows) for v in ("keep", "recut", "hold")}
    lines.append(f"{len(rows)} unposted: " + ", ".join(f"{n} {v}" for v, n in counts.items()))
    return "\n".join(lines)
