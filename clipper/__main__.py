import argparse
import json
import os
import sys
from pathlib import Path

from . import analyze as analyze_mod
from . import config, hooks, library, render as render_mod, schedule, simulate, sources, voice_setup
from . import bench as bench_mod
from . import live as live_mod
from . import setup as setup_mod


def _picks_from_ids(job, ids):
    data = json.loads((job / "candidates.json").read_text(encoding="utf-8"))
    by_id = {c["id"]: c for c in data["candidates"]}
    picks = []
    for i in ids.split(","):
        c = by_id.get(int(i))
        if not c:
            raise SystemExit(f"no candidate #{i}")
        picks.append({"start": c["start"], "end": c["end"], "hooks": [c["hook"]], "titles": [c["hook"]]})
    return picks


def daily(cfg, limit=None):
    """Pick the newest unprocessed GTA 6 uploads from the creators list and analyze them."""
    prefs = library.load_prefs()
    limit = limit or int(prefs.get("sources_per_day", 2))
    found, errors, skipped = sources.watch(cfg, per_channel=6)
    fresh = [v for v in found if not v["processed"]]
    fresh.sort(key=lambda v: v["source"].startswith("search:"))  # creators first, then searches
    max_s = int(prefs.get("daily_max_minutes", 90)) * 60
    jobs = []
    for v in fresh[:limit]:
        section = f"0:00-{max_s // 3600}:{max_s % 3600 // 60:02d}:00" if v["duration"] > max_s else None
        job, _ = sources.fetch(v["id"], section)
        res = analyze_mod.analyze(job, cfg)
        jobs.append({"job": v["id"], "title": v["title"], "channel": v["channel"], "section": section,
                     "minutes": round(v["duration"] / 60), "candidates_md": str(job / "candidates.md"),
                     "candidates": len(res["candidates"]), "recommended": res["recommended"]})
    want = prefs.get("videos_per_run", "auto")
    total = (min(sum(j["recommended"] for j in jobs), int(prefs.get("max_videos_per_run", 10)))
             if want == "auto" else int(want))
    return {"prefs": prefs, "new_videos": len(fresh), "analyzed": jobs, "videos_to_export": total,
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
    r.add_argument("--out", help="output folder (default exports/<profile>/<today>; numbering continues)")
    r.add_argument("--allow-say", action="store_true", help="use the system voice (macOS say / espeak-ng) if no Fish Audio key is saved")
    sub.add_parser("voice-setup", help="open Fish Audio + a TextEdit note to paste and save your API key")
    ck = sub.add_parser("check", help="check picks.json hooks/titles against the viral research rules")
    ck.add_argument("picks")
    sm = sub.add_parser("simulate", help="Monte Carlo swipe test: rank a picks.json's hook variants")
    sm.add_argument("picks", nargs="?", help="omit to print the fitted effect of every hook feature")
    sm.add_argument("--strategies", action="store_true", help="compare hooks-per-clip strategies at equal uploads")
    sm.add_argument("--uploads", type=int, default=8)
    st = sub.add_parser("setup", help="check/install dependencies and install the /clip commands globally")
    st.add_argument("--install", action="store_true", help="brew/pip install what's missing + download the model")
    st.add_argument("--dry-run", action="store_true", help="show what would change without writing anything")
    lv = sub.add_parser("live", help="record GTA 6 live streams (Twitch/Kick/YouTube) in chunks while they're on")
    lv.add_argument("action", choices=["list", "add", "remove", "status", "watch", "record", "jobs", "pending", "done"])
    lv.add_argument("refs", nargs="*", help="add: twitch:NAME | kick:NAME | youtube:@NAME | URL; record: NAME URL; "
                                             "done: JOB")
    lv.add_argument("--chunk", type=int, default=30, help="minutes per chunk")
    lv.add_argument("--any-title", action="store_true", help="add: record even if the title isn't on the profile's topic")
    bn = sub.add_parser("bench", help="measure this machine and how many live creators it can keep up with")
    bn.add_argument("--seconds", type=int, default=60)
    cr = sub.add_parser("creators", help="list / add / remove watched creators")
    cr.add_argument("action", choices=["list", "add", "remove"])
    cr.add_argument("refs", nargs="*", help="@handle, handle, or channel URL")
    pr = sub.add_parser("prefs", help="show or set saved choices (voice, videos_per_run, ...)")
    pr.add_argument("action", choices=["show", "set"])
    pr.add_argument("pairs", nargs="*", help="key=value")
    dl = sub.add_parser("daily", help="find new GTA 6 uploads and analyze them (step 1 of /clip-daily)")
    dl.add_argument("--limit", type=int, help="override sources_per_day")
    sc = sub.add_parser("schedule", help="launchd fallback for Claude Code CLI users")
    sc.add_argument("action", choices=["install", "live", "remove", "status"])
    sc.add_argument("--time", help="HH:MM (default prefs schedule_time)")
    sc.add_argument("--every", type=int, default=2, help="live: hours between live clip runs")
    sc.add_argument("--watch-only", action="store_true", help="live: only the stream watcher (clip from your app's own "
                                                                 "scheduled task)")
    sc.add_argument("--clip-cmd", help="live: shell command that clips the waiting chunks instead of `claude -p "
                                       "'/clip-daily live'` (e.g. your own agent runner); still only runs when chunks wait")
    fr = sub.add_parser("frame", help="grab a gridded frame to locate the facecam for split layout")
    fr.add_argument("job")
    fr.add_argument("seconds", type=float)
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
        problems = hooks.check_picks(picks, cfg)
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
        print(json.dumps(render_mod.render(job, picks, cfg, args.first_hook_only, args.out), indent=2))
    elif args.cmd == "check":
        report = hooks.check_picks(json.loads(open(args.picks, encoding="utf-8").read()), cfg)
        failing = hooks.has_fails(report)
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
            print(json.dumps({"started": live_mod.watch(cfg, args.chunk), "ready": live_mod.ready_jobs(True),
                              "transcribing": sorted(set(live_mod.ready_jobs()) - set(live_mod.ready_jobs(True)))},
                             indent=2))
        elif a == "record":
            live_mod.record(refs[0], refs[1], args.chunk, cfg=cfg)
        elif a == "jobs":
            print(json.dumps(live_mod.ready_jobs(), indent=2))
        elif a == "pending":  # exit 1 when nothing is ready, so a scheduled clip run doesn't start Claude for nothing
            ready = live_mod.ready_jobs(True)
            print(json.dumps(ready, indent=2))
            sys.exit(0 if ready else 1)
        else:
            print(json.dumps([live_mod.mark_done(j) for j in refs]))
    elif args.cmd == "bench":
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
            print(schedule.install(args.time or str(library.load_prefs().get("schedule_time", "09:00"))))
        elif args.action == "live":
            if not live_mod.load_streams():
                raise SystemExit("no live streams in this profile's live.yaml (add some with `clipper live add`)")
            print(schedule.install_live(args.every, watch_only=args.watch_only, clip_cmd=args.clip_cmd))
        else:
            print(schedule.remove() if args.action == "remove" else schedule.status())
    elif args.cmd == "voice-setup":
        sys.exit(0 if voice_setup.setup(cfg) else 1)
    elif args.cmd == "frame":
        print(analyze_mod.grid_frame(config.job_dir(args.job), args.seconds))


if __name__ == "__main__":
    main()
