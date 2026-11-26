import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from . import analyze as analyze_mod
from . import config, hooks, library, render as render_mod, schedule, simulate, sources, transcribe, voice_setup
from . import bench as bench_mod
from . import cleanup as cleanup_mod
from . import dub as dub_mod
from . import longbank, longform
from . import live as live_mod
from . import setup as setup_mod
from . import stats as stats_mod


def _picks_from_ids(job, ids):
    data = json.loads((job / "candidates.json").read_text(encoding="utf-8"))
    by_id = {c["id"]: c for c in data["candidates"]}
    picks = []
    for i in ids.split(","):
        c = by_id.get(int(i))
        if not c:
            raise SystemExit(f"no candidate #{i}")
        line = c.get("loudest_line") or c.get("hook") or ""  # "hook" in candidates.json written before 2026-11-25
        picks.append({"start": c["start"], "end": c["end"], "hooks": [line], "titles": [line]})
    return picks


def job_words(ref):
    """A job's transcript words (source seconds), or None when it has none."""
    f = config.job_dir(ref) / "transcript.json"
    return transcribe.drop_repeats(json.loads(f.read_text(encoding="utf-8"))["words"]) if f.exists() else None


def reused_footage(picks, job_ref, cfg):
    """{video n: [clips already using its footage]} for picks whose job is known (`--job`, the pick's or every
    segment's `job`)."""
    out = {}
    for n, pick in enumerate(picks, 1):
        ref = pick.get("job") or job_ref
        if not ref and not (pick.get("segments") and all(s.get("job") for s in pick["segments"])):
            continue
        job = config.job_dir(ref or pick["segments"][0]["job"])
        reused = render_mod.footage_reuse(render_mod.footage(pick, job, render_mod.load_meta(job)))
        if reused:
            out[n] = reused + ["pick other moments: the same footage gets no reach the second time"]
    return out


def is_favored(channel, cfg):
    """A source from one of the profile's `favor_creators` (Kai Cenat: 4 of our 5 best Shorts)."""
    ch = str(channel or "").lower()
    return any(str(name).lower() in ch for name in cfg.get("favor_creators") or [] if str(name).strip())


def favored_first(found, cfg):
    """Favored creators first, then the other creators, then searches; newest order kept within each."""
    return sorted(found, key=lambda v: (not is_favored(v.get("channel"), cfg), v["source"].startswith("search:")))


def source_order(found, cfg, demand=None):
    """Sources whose streamers measured best on the 100K+ clip channels first (clear, then lean, by lift), then the
    profile's favored creators, then the rest; searches last within each tier, newest order kept otherwise."""
    from . import demand as demand_mod
    d = demand if demand is not None else demand_mod.load()

    def key(v):
        tier, lift = demand_mod.source_rank(f"{v.get('channel') or ''} {v.get('title') or ''}", d)
        return (tier, -lift if tier < 2 else 0, not is_favored(v.get("channel"), cfg), v["source"].startswith("search:"))
    return sorted(found, key=key)


def cleaned_total(c):
    """Files and GB a cleanup run freed: sources plus the long-form purge."""
    lf = c.get("longform") or {}
    return {"files": c["files"] + lf.get("files", 0), "gb": round(c["gb"] + lf.get("gb", 0), 2)}


def daily(cfg, limit=None):
    """Pick the newest unprocessed uploads on the profile's topic from the creators list and analyze them."""
    prefs = library.load_prefs()
    cleaned = cleanup_mod.run(cfg)  # old downloads go before new ones arrive
    limit = limit or int(prefs.get("sources_per_day", 2))
    found, errors, skipped = sources.watch(cfg, per_channel=6)
    from . import demand as demand_mod
    dem = demand_mod.load()
    fresh = source_order([v for v in found if not v["processed"]], cfg, dem)
    max_s = int(prefs.get("daily_max_minutes", 90)) * 60
    jobs = []
    for v in fresh[:limit]:
        section = f"0:00-{max_s // 3600}:{max_s % 3600 // 60:02d}:00" if v["duration"] > max_s else None
        try:
            job, _ = sources.fetch(v["id"], section)
        except subprocess.CalledProcessError as e:  # age-restricted, private or removed: skip, don't end the run
            errors.append({"source": v["id"], "error": f"download failed: {e}"})
            continue
        try:
            res = analyze_mod.analyze(job, cfg)
        except subprocess.CalledProcessError as e:  # unreadable audio etc.: skip this source, keep the run going
            errors.append({"source": v["id"], "error": f"analysis failed: {e}"})
            continue
        jobs.append({"job": v["id"], "title": v["title"], "channel": v["channel"], "section": section,
                     "favored": is_favored(v["channel"], cfg),
                     "demand": demand_mod.line_for(f"{v['channel']} {v['title']}", dem),
                     "minutes": round(v["duration"] / 60), "candidates_md": str(job / "candidates.md"),
                     "candidates": len(res["candidates"]), "recommended": res["recommended"]})
    want = prefs.get("videos_per_run", "auto")
    total = (min(sum(j["recommended"] for j in jobs), int(prefs.get("max_videos_per_run", 10)))
             if want == "auto" else int(want))
    return {"prefs": prefs, "new_videos": len(fresh), "analyzed": jobs, "videos_to_export": total,
            "cleaned": cleaned_total(cleaned),
            "skipped_off_topic": skipped, "errors": errors}


def tools_on_path():
    """yt-dlp and other pip-installed tools sit next to the interpreter (a .venv's bin/); find them even when that
    folder isn't on PATH, e.g. when an agent runs `.venv/bin/python -m clipper` from its own shell."""
    here = str(Path(sys.executable).parent)
    if here not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = here + os.pathsep + os.environ.get("PATH", "")


def main(argv=None):
    tools_on_path()
    p = argparse.ArgumentParser(prog="clipper", description="Find, review and render short clips.")
    p.add_argument("--config")
    p.add_argument("--profile", help="niche profile in profiles/ (default: $CLIPPER_PROFILE or gta6)")
    sub = p.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("watch", help="list new on-topic videos from the watchlist")
    w.add_argument("--per-channel", type=int, default=8)
    w.add_argument("--search", action="append", help="extra YouTube search (repeatable)")
    w.add_argument("--no-search", action="store_true", help="skip the config's searches")
    for name, hlp in (("fetch", "download a video"), ("run", "fetch + analyze")):
        f = sub.add_parser(name, help=hlp)
        f.add_argument("video", help="YouTube URL or id")
        f.add_argument("--section", help="only download part, e.g. 1:00:00-1:30:00")
        f.add_argument("--fast", action="store_true", help="smaller whisper model")
    a = sub.add_parser("analyze", help="transcribe, score and list candidate clips")
    a.add_argument("job")
    a.add_argument("--fast", action="store_true")
    a.add_argument("--force", action="store_true")
    r = sub.add_parser("render", help="render approved clips to vertical mp4 + metadata")
    r.add_argument("job")
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--picks", help="JSON list of {start,end,title,hook,description,hashtags,voiceover}")
    g.add_argument("--ids", help="candidate ids, e.g. 1,3")
    r.add_argument("--first-hook-only", action="store_true", help="render one variant per clip (quick check)")
    r.add_argument("--top-hooks", type=int, help="render only the N best-ranked hooks per clip (simulate's ranking); "
                                                 "default $CLIPPER_TOP_HOOKS (e.g. in .env), else every hook")
    r.add_argument("--out", help="output folder (default exports/<profile>/<today>; numbering continues)")
    r.add_argument("--allow-say", action="store_true", help="use the system voice (macOS say / espeak-ng) if no Fish Audio key is saved")
    sub.add_parser("voice-setup", help="open Fish Audio + a TextEdit note to paste and save your API key")
    ck = sub.add_parser("check", help="check picks.json hooks/titles against the viral research rules")
    ck.add_argument("picks")
    ck.add_argument("--job", help="the picks' job: also fail picks reusing footage this profile already exported")
    ck.add_argument("--rendered", nargs="*", default=[],
                    help="rendered MP4s (in pick order) to compare with the 100K+ profile too")
    sm = sub.add_parser("simulate", help="Monte Carlo swipe test: rank a picks.json's hook variants")
    sm.add_argument("picks", nargs="?", help="omit to print the fitted effect of every hook feature")
    sm.add_argument("--strategies", action="store_true", help="compare hooks-per-clip strategies at equal uploads")
    sm.add_argument("--uploads", type=int, default=8)
    st = sub.add_parser("setup", help="check/install dependencies and install the /clip commands globally")
    st.add_argument("--install", action="store_true", help="brew/pip install what's missing + download the model")
    st.add_argument("--dry-run", action="store_true", help="show what would change without writing anything")
    lv = sub.add_parser("live", help="record GTA 6 live streams (Twitch/Kick/YouTube) in chunks while they're on")
    lv.add_argument("action", choices=["list", "add", "remove", "status", "watch", "record", "jobs", "pending", "done",
                                       "restart", "analyze", "health"])
    lv.add_argument("refs", nargs="*", help="add: twitch:NAME | kick:NAME | youtube:@NAME | URL; record: NAME URL; "
                                             "done: JOB")
    lv.add_argument("--chunk", type=int, default=30, help="minutes per chunk")
    lv.add_argument("--any-title", action="store_true", help="add: record even if the title isn't on the profile's topic")
    lv.add_argument("--replace", type=int, help="record: the old recorder's pid, stopped once this one is recording")
    db = sub.add_parser("dub", help="re-render a clip in another language in each speaker's cloned voice (Fish Audio)")
    db.add_argument("action", choices=["segments", "render"], help="segments: lines to translate; render: the dub")
    db.add_argument("job")
    db.add_argument("--pick", type=int, required=True, help="which pick in jobs/<id>/picks.json (1 = first)")
    db.add_argument("--lang", help="render: the translation's language code, e.g. ru")
    db.add_argument("--translation", help="render: the translation JSON (see `dub segments` for its template)")
    rp = sub.add_parser("report", help="append a run report to exports/<profile>/<date>/index.md (never rewrites it)")
    rp.add_argument("text", help="the report, in Markdown")
    cl = sub.add_parser("cleanup", help="delete old job video/audio (keep_live_sources_hours, keep_sources_days), "
                                        "then the long-form purge (see `bank purge`); transcripts, picks, long "
                                        "MP4s and long.json stay")
    cl.add_argument("--dry-run", action="store_true", help="list what would be deleted, delete nothing")
    bn = sub.add_parser("bench", help="measure this machine and how many live creators it can keep up with")
    bn.add_argument("--seconds", type=int, default=60)
    bn.add_argument("--moments", action="store_true", help="instead: score the moment finder's signals on 83 "
                                                         "outlier-vs-flop pairs (research/moment-pairs.json)")
    cr = sub.add_parser("creators", help="list / add / remove watched creators")
    cr.add_argument("action", choices=["list", "add", "remove"])
    cr.add_argument("refs", nargs="*", help="@handle, handle, or channel URL")
    pr = sub.add_parser("prefs", help="show or set saved choices (voice, videos_per_run, ...)")
    pr.add_argument("action", choices=["show", "set"])
    pr.add_argument("pairs", nargs="*", help="key=value")
    dl = sub.add_parser("daily", help="find new uploads on the profile's topic and analyze them (step 1 of /clip-daily)")
    dl.add_argument("--limit", type=int, help="override sources_per_day")
    sc = sub.add_parser("schedule", help="launchd/systemd fallback for Claude Code or Codex CLI users, per profile")
    sc.add_argument("action", choices=["install", "live", "remove", "status"])
    sc.add_argument("--time", help="HH:MM (default prefs schedule_time)")
    sc.add_argument("--every", type=int, default=2, help="live: hours between live clip runs")
    sc.add_argument("--watch-only", action="store_true", help="live: only the stream watcher (clip from your app's own "
                                                                 "scheduled task)")
    sc.add_argument("--agent", choices=schedule.AGENTS, help="install/live: run /clip-daily with claude or codex "
                                                              "(default prefs agent, else claude)")
    sc.add_argument("--clip-cmd", help="live: shell command that clips the waiting chunks instead of `claude -p "
                                       "'/clip-daily live'` (e.g. your own agent runner); still only runs when chunks wait")
    fd = sub.add_parser("find", help="search recent jobs' transcripts (all streams) for a line, e.g. one cutscene "
                                     "line to find the same moment in every stream for a multi-streamer edit")
    fd.add_argument("pattern", help="regex, case-insensitive")
    fd.add_argument("--hours", type=float, default=6, help="only jobs recorded or fetched in the last N hours")
    fr = sub.add_parser("frame", help="grab a gridded frame to locate the facecam for split layout")
    fr.add_argument("job")
    fr.add_argument("seconds", type=float)
    vr = sub.add_parser("viral", help="what outliers (3x their channel's median) have in common: collect Shorts, "
                                      "measure with code, optional Gemini scores, compare and validate; raw YouTube "
                                      "data in viral/ is deleted after 30 days")
    vr.add_argument("action", choices=["collect", "import", "measure", "openings", "labels", "actions", "hooks",
                                       "pairs", "score", "report", "purge", "sample"])
    vr.add_argument("--path", help="import: an earlier study's ext.json; labels: a folder of *.jsonl; actions: a JSONL; hooks: a folder of *.jsonl; pairs: JSON [{id, title, stream_date}] of our uploads")
    vr.add_argument("--grouped", help="import: grouped.json with durations/dates for some of those videos")
    vr.add_argument("--own", type=int, default=100, help="collect: our last N uploads (Shorts kept)")
    vr.add_argument("--per-channel", type=int, default=40, help="collect: each clip channel's last N uploads")
    vr.add_argument("--limit", type=int, help="measure/score: at most N videos this run")
    vr.add_argument("--cached-only", action="store_true", help="measure: only videos already downloaded (no scraping)")
    vr.add_argument("--slices", action="store_true",
                    help="measure: only the first ~6 s of each undownloaded settled Short (frames, Apple OCR, speech); "
                         "one at a time, stops at the first bot check")
    vr.add_argument("--pause", type=float, default=6.0, help="measure --slices: seconds between downloads (+ jitter)")
    vr.add_argument("--prompt", default="full", help="score: a prompt name (full, short1-short5) or all")
    vr.add_argument("--model", default=None, help="score: Gemini model (default $GEMINI_MODEL or gemini-2.5-flash)")
    vr.add_argument("--runs", type=int, default=50, help="report: validation runs")
    vr.add_argument("--sample", type=int, default=30, help="report: videos with views hidden per run")
    vr.add_argument("--seed", type=int, default=7)
    sub.add_parser("calibrate", help="review criteria vs our views: rank correlations and suggested weights "
                                     "(prints only; weights come from watchlist.yaml)")
    pk = sub.add_parser("profile100k", help="what 100K+ clips do vs the same channels' flops: build the profile from "
                                            "research/100k-split-2026-11.json (+ labels, measured sample), or show it")
    pk.add_argument("action", choices=["build", "show"])
    dm = sub.add_parser("demand", help="each streamer's and subject's 100K+ rate on the watched clip channels")
    dm.add_argument("action", choices=["build", "show"])
    sa = sub.add_parser("stats", help="our uploads' views, engaged share and retention joined to their upload.json "
                                      "(read-only YouTube OAuth); saves research/own-stats.json + simulate's own data")
    sa.add_argument("--no-save", action="store_true", help="print the report, write nothing")
    rq = sub.add_parser("requeue", help="re-check this profile's rendered-but-unposted clips against the own-channel "
                                        "winners: keep, recut (payoff by ~16 s, end 3 s after it) or hold")
    rq.add_argument("--apply", action="store_true", help="save recut picks to jobs/<id>/picks-requeue.json and render "
                                                         "them into new video N folders (default: dry run, writes nothing)")
    lg = sub.add_parser("long", help="long-form 16:9: a running-bit supercut (8-10 min), a \"what happens\" video "
                        "(kind mid, 30s-3 min), a narrated story (kind story, 4-10 min) or a streamer's funniest "
                        "moments (kind compilation, 8-12 min): check or render a spec, remake a `long N` "
                        "thumbnail, list channels ready for a compilation, or build the thumbnail exemplars")
    lg.add_argument("action", choices=["check", "render", "thumb", "ready", "exemplars"])
    lg.add_argument("spec", nargs="?", help="check/render: JSON spec (see /clip-long); thumb: a `long N` folder; "
                                            "exemplars: build")
    lg.add_argument("--out", help="output folder (default exports/<profile>/<today>; `long N` numbering continues)")
    lg.add_argument("--no-ai-thumb", action="store_true", help="render/thumb: use the raw source frame as the "
                                                               "thumbnail instead of a Codex $imagegen one")
    lg.add_argument("--min-minutes", type=float, default=9.0, help="ready: unused bank footage a channel needs "
                                                                   "(default 9)")
    lg.add_argument("--json", action="store_true", help="ready: print JSON")
    lg.add_argument("--spec", dest="thumb_spec", help="thumb: the spec the folder was rendered from (default: the "
                                                      "jobs/long-*.json with the same spec_sha256)")
    bk = sub.add_parser("bank", help="clip bank for long-form: keep tagged moments as small clips so their sources "
                                     "can be deleted; a moment goes once a long video that used it is posted")
    bks = bk.add_subparsers(dest="bank_cmd", required=True)
    bt = bks.add_parser("tag", help="cut a moment (padded by longbank_pad_s) into jobs/_longbank/")
    bt.add_argument("job", nargs="?", help="job id or folder")
    bt.add_argument("start", nargs="?", type=float, help="source seconds")
    bt.add_argument("end", nargs="?", type=float, help="source seconds")
    bt.add_argument("--note", help="what happens (shown in `bank list`)")
    bt.add_argument("--niche", choices=["irl", "gaming", "rp"])
    bt.add_argument("--short", help="instead of job/start/end: tag the moment of a rendered Short (a `video N` folder)")
    bks.add_parser("list", help="every banked moment, its status and size, and what's due for deletion")
    bd = bks.add_parser("done", help="mark a `long N` folder posted: its bank clips and thumbnail files go after "
                                     "keep_after_post_days")
    bd.add_argument("folder")
    bd.add_argument("--youtube-id")
    bp = bks.add_parser("purge", help="delete used-and-posted bank clips, expired unused ones, posted longs' "
                                      "thumbnails and Codex leftovers (also part of `cleanup`)")
    bp.add_argument("--dry-run", action="store_true", help="list what would be deleted, delete nothing")
    args = p.parse_args(argv)
    config.load_env()
    cfg = config.load(args.config, args.profile)

    if args.cmd == "watch":
        searches = [] if args.no_search else None
        if args.search:
            searches = (searches if searches is not None else cfg.get("search", [])) + args.search
        found, errors, skipped = sources.watch(cfg, args.per_channel, searches)
        json.dump({"videos": found, "skipped_off_topic": skipped, "errors": errors}, sys.stdout, indent=2)
    elif args.cmd in ("fetch", "run"):
        job, meta = sources.fetch(args.video, args.section)
        if args.cmd == "run":
            res = analyze_mod.analyze(job, cfg, fast=args.fast)
            print(analyze_mod.to_markdown(res))
        print(json.dumps({"job": str(job), **meta}, indent=2))
    elif args.cmd == "analyze":
        res = analyze_mod.analyze(config.job_dir(args.job), cfg, args.fast, args.force)
        print(analyze_mod.to_markdown(res))
    elif args.cmd == "render":
        job = config.job_dir(args.job)
        picks = (json.loads(open(args.picks, encoding="utf-8").read()) if args.picks
                 else _picks_from_ids(job, args.ids))
        too_long = [f"video {n}: {hooks.check_length(p)}" for n, p in enumerate(picks, 1) if hooks.check_length(p)]
        if too_long:
            raise SystemExit("[check] clips over the length cap, nothing rendered:\n" + "\n".join(too_long))
        problems = hooks.check_picks(picks, cfg, job_words(job), job_words)
        if hooks.has_fails(problems):
            print("[check] hooks/titles that break the research rules (rendering anyway):\n"
                  + json.dumps(problems, indent=2, ensure_ascii=False), file=sys.stderr)
        if any(p.get("voiceover") for p in picks) and not os.environ.get("FISH_API_KEY") and not args.allow_say:
            if sys.stdin.isatty():
                voice_setup.setup(cfg)
            else:
                print("Voiceover needs a Fish Audio API key. Run `python3 -m clipper voice-setup` "
                      "(opens the key page + a TextEdit note to paste it), or pass --allow-say.", file=sys.stderr)
                sys.exit(3)
        top = args.top_hooks if args.top_hooks is not None else int(os.environ.get("CLIPPER_TOP_HOOKS") or 0)
        print(json.dumps(render_mod.render(job, picks, cfg, args.first_hook_only, args.out, top), indent=2))
    elif args.cmd == "check":
        picks = json.loads(open(args.picks, encoding="utf-8").read())
        from .profile100k import clip_loudness
        jd_ = config.job_dir(args.job) if args.job else None
        report = hooks.check_picks(picks, cfg, job_words(args.job) if args.job else None, job_words,
                                   lambda pk: clip_loudness(pk, config.job_dir(pk["job"]) if pk.get("job") else jd_))
        for n, reused in reused_footage(picks, args.job, cfg).items():
            report.setdefault(f"video {n}", {})["footage"] = reused
        if args.job:
            jd = config.job_dir(args.job)
            cams = hooks.known_facecams(config.JOBS, [(jd, picks)])
            for n, pick in enumerate(picks, 1):
                opening = hooks.check_opening_frames(pick, jd)
                if opening:
                    report.setdefault(f"video {n}", {})["opening"] = opening
                facecam = hooks.check_facecam(pick, jd, cams, bool(cfg.get("require_facecam")))
                if facecam:
                    report.setdefault(f"video {n}", {})["facecam"] = facecam
        from . import profile100k
        mode, prof = profile100k.mode_of(cfg), profile100k.load_profile()
        for n, mp4 in enumerate(args.rendered or [], 1):
            got = profile100k.check_rendered(mp4, prof, mode)
            if got and (got["fails"] or got["notes"]):
                report.setdefault(f"video {n}", {})["rendered"] = got
        failing = hooks.has_fails(report) or any((e.get("rendered") or {}).get("fails") for e in report.values())
        if report:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        print("FIX the 'fails' above" if failing else
              "all hooks and titles pass" + (" (notes are judgment calls)" if report else ""))
        sys.exit(1 if failing else 0)
    elif args.cmd == "simulate":
        if args.strategies:
            print(simulate.strategies_report(args.uploads))
        else:
            print(simulate.report(json.loads(open(args.picks, encoding="utf-8").read()),
                                  keep=library.hooks_per_video(), **simulate.profile_kw(cfg)) if args.picks
                  else simulate.effects_report(simulate.niche_for(cfg)))
    elif args.cmd == "setup":
        print(setup_mod.run(args.install, args.dry_run))
    elif args.cmd == "live":
        a, refs = args.action, args.refs
        if a == "add":
            print(json.dumps([live_mod.add(r, topic_only=not args.any_title) for r in refs], indent=2))
        elif a == "remove":
            print(f"removed {sum(live_mod.remove(r) for r in refs)}")
        elif a == "list":
            print(json.dumps(live_mod.load_streams(), indent=2))
        elif a == "status":
            print(json.dumps(live_mod.status(cfg), indent=2))
        elif a == "watch":
            started = live_mod.watch(cfg, args.chunk)
            cleaned = cleanup_mod.run(cfg)
            print(json.dumps({"started": started, "ready": live_mod.ready_jobs(True),
                              "transcribing": sorted(set(live_mod.ready_jobs()) - set(live_mod.ready_jobs(True))),
                              "cleaned": cleaned_total(cleaned)}, indent=2))
        elif a == "health":  # exit 1 on any issue, so a timer or monitor can alert on it
            issues = live_mod.health(cfg)
            print(json.dumps({"ok": not issues, "issues": issues}, indent=2))
            sys.exit(1 if issues else 0)
        elif a == "record":
            live_mod.record(refs[0], refs[1], args.chunk, cfg=cfg, replace_pid=args.replace)
        elif a == "restart":  # e.g. after a code update: the new recorder starts before the old one stops
            print(json.dumps([live_mod.restart(r, args.chunk) for r in refs], indent=2))
        elif a == "analyze":  # a stranded chunk, waiting for a shared analysis slot like the recorders do
            try:
                live_mod.analyze_queued(refs[0], cfg)
            finally:
                (live_mod.JOBS / refs[0] / "analyzing").unlink(missing_ok=True)
        elif a == "jobs":
            print(json.dumps(live_mod.ready_jobs(), indent=2))
        elif a == "pending":  # exit 1 when nothing is ready, so a scheduled clip run doesn't start Claude for nothing
            ready = live_mod.ready_jobs(True)
            print(json.dumps(ready, indent=2))
            sys.exit(0 if ready else 1)
        else:
            print(json.dumps([live_mod.mark_done(j) for j in refs]))
    elif args.cmd == "dub":
        job = config.job_dir(args.job)
        if args.action == "segments":
            out = dub_mod.segments_report(job, args.pick, cfg)
        else:
            if not (args.lang and args.translation):
                raise SystemExit("[dub] render needs --lang and --translation")
            tr = json.loads(Path(args.translation).read_text(encoding="utf-8"))
            out = dub_mod.render_dub(job, args.pick, args.lang, tr, cfg)
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    elif args.cmd == "report":
        print(f"report added to {render_mod.append_report(cfg, args.text)}")
    elif args.cmd == "cleanup":
        print(json.dumps(cleanup_mod.run(cfg, args.dry_run), indent=2))
    elif args.cmd == "bench":
        if args.moments:
            from . import moments_eval
            print(moments_eval.run(cfg)[1])
        else:
            print(bench_mod.run(cfg, args.seconds))
    elif args.cmd == "creators":
        if args.action == "list":
            for c in library.load_creators():
                print(f"{c['name']}\t{c['url']}")
        elif args.action == "add":
            for ref in args.refs:
                print(library.add_creator(ref)[1])
        else:
            for ref in args.refs:
                print(f"removed {library.remove_creator(ref)} matching '{ref}'")
    elif args.cmd == "prefs":
        if args.action == "set":
            try:
                library.set_prefs(args.pairs)
            except ValueError as e:
                raise SystemExit(str(e))
        print(json.dumps(library.load_prefs(), indent=2))
    elif args.cmd == "daily":
        print(json.dumps(daily(cfg, args.limit), indent=2))
    elif args.cmd == "schedule":
        if args.action == "install":
            print(schedule.install(args.time or str(library.load_prefs().get("schedule_time", "09:00")), args.agent))
        elif args.action == "live":
            if not live_mod.load_streams():
                raise SystemExit("no live streams in this profile's live.yaml (add some with `clipper live add`)")
            print(schedule.install_live(args.every, watch_only=args.watch_only, clip_cmd=args.clip_cmd, agent=args.agent))
        else:
            print(schedule.remove() if args.action == "remove" else schedule.status())
    elif args.cmd == "voice-setup":
        sys.exit(0 if voice_setup.setup(cfg) else 1)
    elif args.cmd == "find":
        hits = live_mod.find(args.pattern, args.hours)
        for h in hits:
            print(f"{h['job']}\t{h['channel']}\t{h['at'] or '-'}\t{h['start']}-{h['end']}s\t"
                  f"{'' if h['footage'] else '(footage deleted) '}{h['text']}")
        if not hits:
            print(f"no line matching '{args.pattern}' in the last {args.hours:g} h")
    elif args.cmd == "frame":
        print(analyze_mod.grid_frame(config.job_dir(args.job), args.seconds))
    elif args.cmd == "viral":
        from . import viral
        args.model = args.model or os.environ.get("GEMINI_MODEL") or viral.GEMINI_MODEL
        out = viral.run(args.action, cfg, args)
        print(out if isinstance(out, str) else json.dumps(out, indent=2))
    elif args.cmd == "calibrate":
        print(stats_mod.run_calibrate(cfg))
    elif args.cmd == "profile100k":
        from . import profile100k
        prof = profile100k.build_files() if args.action == "build" else profile100k.load_json(profile100k.PROFILE, None)
        print(profile100k.show(prof) if prof else f"no profile yet: run `clipper profile100k build`")
    elif args.cmd == "demand":
        from . import demand
        d = demand.build_files() if args.action == "build" else demand.load()
        print(demand.show(d) if d else "no demand file yet: run `clipper demand build`")
    elif args.cmd == "stats":
        print(stats_mod.run(save=not args.no_save))
    elif args.cmd == "requeue":
        from . import requeue
        rows = requeue.verdicts(cfg)
        if not requeue.STATS.exists():
            print("[requeue] no research/own-stats.json (run `clipper stats`): only upload.json `youtube_id` marks a "
                  "clip as posted, so posted clips may be listed", file=sys.stderr)
        print(requeue.report(rows))
        if args.apply:
            print(json.dumps(requeue.apply(cfg, rows), indent=2))
        elif any(r["verdict"] == "recut" for r in rows):
            print("dry run: nothing written (add --apply to render the recuts into new video N folders)")
    elif args.cmd == "bank":
        if args.bank_cmd == "tag":
            if args.short:
                tagged = [longbank.tag(j, s, e, cfg, args.note, args.niche, short=Path(args.short).resolve())
                          for j, s, e in longbank.short_moments(args.short)]
            elif args.job and args.start is not None and args.end is not None:
                tagged = [longbank.tag(args.job, args.start, args.end, cfg, args.note, args.niche)]
            else:
                raise SystemExit("bank tag needs <job> <start> <end>, or --short \"<video N folder>\"")
            print(json.dumps(tagged, indent=2, ensure_ascii=False))
        elif args.bank_cmd == "list":
            plan = cleanup_mod.purge_plan(cfg, exports=render_mod.EXPORTS)
            due = {str(e["owner"].resolve()): e["reason"] for e in plan["delete"] if e["kind"] == "bank"}
            rows = [{"id": x["id"], "job": x["job"], "span": f"{x['start']:g}-{x['end']:g}s", "niche": x.get("niche"),
                     "note": x.get("note"), "status": "deleted" if x.get("deleted_at") else x.get("status"),
                     "mb": round(float(x.get("bytes") or 0) / 1e6, 1),
                     "used_in": [Path(u).name for u in x.get("used_in") or []],
                     "purge_after": x.get("purge_after"), "due": due.get(str(d.resolve())),
                     "expires_next_run": x["id"] in plan["expiring"]} for d, x in longbank.entries()]
            live_mb = sum(r["mb"] for r in rows if r["status"] != "deleted")
            print(json.dumps({"clips": rows, "on_disk_mb": round(live_mb, 1),
                              "due_now": sum(1 for r in rows if r["due"])}, indent=2, ensure_ascii=False))
        elif args.bank_cmd == "done":
            print(json.dumps(longbank.mark_posted(args.folder, cfg, args.youtube_id), indent=2))
        else:
            print(json.dumps(cleanup_mod.purge(cfg, args.dry_run, exports=render_mod.EXPORTS), indent=2,
                             ensure_ascii=False))
    elif args.cmd == "long" and args.action == "exemplars":
        if args.spec != "build":
            raise SystemExit("usage: clipper long exemplars build")
        res = longform.build_exemplars()
        print(json.dumps({n: [f"{e['id']} {e['x_normal']}x {e['channel']} ({e['source']})" for e in v]
                          for n, v in res["niches"].items()}, indent=2, ensure_ascii=False))
    elif args.cmd == "long" and args.action == "ready":
        rows = longbank.ready(args.min_minutes)
        if args.json:
            print(json.dumps({"min_minutes": args.min_minutes, "ready": rows}, indent=2, ensure_ascii=False))
        else:
            for r in rows:
                print(f"{r['channel']}: {r['minutes']} min in {r['clips']} unused bank clips ({r['niche'] or 'no niche'})")
            if not rows:
                print(f"no channel has {args.min_minutes:g} min of unused bank footage yet")
    elif args.cmd == "long" and args.action == "thumb":
        if not args.spec:
            raise SystemExit("usage: clipper long thumb \"<long N folder>\" [--spec jobs/long-x.json]")
        spec = json.loads(open(args.thumb_spec, encoding="utf-8").read()) if args.thumb_spec else None
        print(json.dumps(longform.remake_thumbnail(args.spec, cfg, spec, ai=not args.no_ai_thumb), indent=2,
                         ensure_ascii=False))
    elif args.cmd == "long":
        if not args.spec:
            raise SystemExit(f"clipper long {args.action} needs a spec")
        spec = json.loads(open(args.spec, encoding="utf-8").read())
        if args.action == "check":
            report = longform.check_long(spec, job_words, hooks.known_facecams(config.JOBS))
            reused = longform.reused_footage(spec)
            if reused:
                report["fails"] = report.get("fails", []) + reused
            extra = [] if longform.kind_of(spec) == "compilation" else [  # its check already holds these
                n for n in longform.shared_notes(spec) if n not in report.get("notes", [])]
            if extra:
                report["notes"] = report.get("notes", []) + extra
            print(json.dumps(report, indent=2, ensure_ascii=False) if report else "long-form spec passes")
            sys.exit(1 if report.get("fails") else 0)
        print(json.dumps(longform.render_long(spec, cfg, args.out, words_for=job_words,
                                              ai_thumb=not args.no_ai_thumb), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
