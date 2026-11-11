import json
import re
import subprocess
import tempfile
import time
from datetime import date
from pathlib import Path

from . import captions, signals, speakers, transcribe, tts
from .analyze import fmt
from . import config
from .config import ROOT

EXPORTS = ROOT / "exports"

def hook_filename(hook, taken):
    """The hook itself as a readable file name: 'Kai waited 12 years for this.mp4'."""
    name = re.sub(r'[*/\\:<>"|?\x00-\x1f]', "", hook or "").strip(" .")
    name = re.sub(r"\s+", " ", name)[:90].strip() or "no hook"
    base, n = name, 2
    while name.lower() in taken:
        name, n = f"{base} ({n})", n + 1
    taken.add(name.lower())
    return f"{name}.mp4"


def _even(x):
    return max(2, int(x) - int(x) % 2)


def source_size(src):
    res = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "csv=p=0", str(src)],
                         capture_output=True, text=True, check=True)
    w, h = res.stdout.strip().split(",")[:2]
    return int(w), int(h)


def caption_layout(layout):
    """Where hooks and captions sit: a pre-cut vertical source keeps the positions of the layout it was cut with."""
    return layout.get("as", "fit") if layout.get("type") == "vertical" else layout.get("type", "fit")


def video_filter(layout, size):
    if layout.get("type") == "vertical":  # already 1080x1920 (a joined story cut)
        return "[0:v]scale=1080:1920,setsar=1[v1]"
    if layout.get("type") == "split":
        sw, sh = size
        fx, fy, fw, fh = layout["face"]
        gx = layout.get("game_x", 0.5)
        return (f"[0:v]split[a][b];[a]crop={_even(fw * sw)}:{_even(fh * sh)}:{int(fx * sw)}:{int(fy * sh)},"
                "scale=1080:768:force_original_aspect_ratio=increase,crop=1080:768[top];"
                f"[b]scale=-2:1152,crop=1080:1152:(iw-1080)*{gx}:0[bot];[top][bot]vstack[v1]")
    return ("[0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            "gblur=sigma=40,eq=brightness=-0.18[bg];[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[v1]")


def action_labels(pick, words):
    """The pick's `labels` ({s, e, text} in source seconds) as caption words relative to the clip, each shown on its
    own; speech wins where they overlap, so labels only fill the quiet stretches."""
    s, e = float(pick["start"]), float(pick["end"])
    out = []
    for lab in pick.get("labels") or []:
        a, b = max(float(lab["s"]), s) - s, min(float(lab["e"]), e) - s
        if b - a >= 0.2 and str(lab.get("text") or "").strip() and not any(
                w["s"] < b and w["e"] > a for w in words):
            out.append({"w": str(lab["text"]).strip().upper(), "s": round(a, 3), "e": round(b, 3), "spk": 0,
                        "label": True})
    return sorted(words + out, key=lambda w: w["s"])


def prepare_clip(job, pick, fallback_words, cfg, tmp):
    """Per-clip work shared by every hook variant: voice separation, diarized captions, audio bed, voiceover."""
    s, e = float(pick["start"]), float(pick["end"])
    dur = e - s
    clip_wav = tmp / "clip.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{s:.3f}", "-t", f"{dur:.3f}",
                    "-i", str(job / "source.mp4"), "-vn", "-ac", "2", "-ar", "44100", str(clip_wav)], check=True)
    stems = speakers.separate(clip_wav, tmp, cfg) if cfg.get("separate_voices", True) else None
    silent = bool(stems) and (signals.integrated_loudness(stems[0]) or -99) < cfg.get("speech_floor_lufs", -40)
    words = [] if silent else (speakers.diarized_words(stems[0] if stems else clip_wav, tmp / "wk", cfg) or [])
    source = "no speech (captions off)" if silent else "whisperkit+diarization"
    heard = [dict(w, s=w["s"] - s, e=w["e"] - s, spk=0) for w in fallback_words if s <= w["s"] < e]
    # WhisperKit on separated vocals sometimes drops most of the speech (4 of 54 words, one held for 8s)
    if not silent and len(words) < len(heard) / 2:
        words = heard
        source = "source transcript"
    bed = clip_wav
    if stems:
        bed = tmp / "bed.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(stems[0]), "-i", str(stems[1]),
                        "-filter_complex", f"[1:a]volume={cfg.get('game_volume', 0.7)}[g];"
                        "[0:a][g]amix=inputs=2:duration=first:normalize=0", str(bed)], check=True)
    if pick.get("labels"):
        words = action_labels(pick, words)
        source += " + action captions"
    layout = pick.get("layout") or {"type": "fit"}
    caps = captions.write_overlay(words, 0.0, dur, tmp / "caps", caption_layout(layout),
                                  pick.get("caption_style") or cfg.get("caption_style", "bold"))
    vo = None
    if pick.get("voiceover"):
        vo_path = tmp / "vo.wav"
        vo_dur, provider = tts.synth(pick["voiceover"], cfg, vo_path)
        vo = {"path": vo_path, "duration": vo_dur, "provider": provider}
    speakers_found = len({w.get("spk", 0) for w in words if not w.get("label")})
    return {"captions": caps, "bed": bed, "vo": vo, "layout": layout, "speakers": speakers_found,
            "transcript": source, "voices_separated": bool(stems), "words": words}


def encode_variant(job, pick, prep, hook, cfg, out_path, tmp):
    s, e = float(pick["start"]), float(pick["end"])
    dur = e - s
    layout = prep["layout"]
    hook_png = tmp / f"hook_{out_path.stem}.png"
    captions.render_hook(hook, hook_png, pick.get("hook_style", "box"), caption_layout(layout))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{s:.3f}", "-t", f"{dur:.3f}",
           "-i", str(job / "source.mp4"), "-f", "concat", "-safe", "0", "-i", str(prep["captions"]),
           "-loop", "1", "-framerate", "30", "-t", f"{dur:.3f}", "-i", str(hook_png), "-i", str(prep["bed"])]
    vf = (video_filter(layout, source_size(job / "source.mp4")) + ";"
          "[1:v]fps=30,format=rgba[cap];[v1][cap]overlay=0:0:eof_action=pass[v2];"
          "[2:v]format=rgba[hk];[v2][hk]overlay=0:0[v]")
    loud = "loudnorm=I=-14:TP=-1.5:LRA=11"
    if prep["vo"]:
        cmd += ["-i", str(prep["vo"]["path"])]
        af = (f"[3:a]volume=0.25:enable='lt(t,{prep['vo']['duration'] + 0.2:.2f})'[g];[4:a]volume=1.8[vo];"
              f"[g][vo]amix=inputs=2:duration=first:normalize=0,{loud}[aout]")
    else:
        af = f"[3:a]{loud}[aout]"
    cmd += ["-filter_complex", f"{vf};{af}", "-map", "[v]", "-map", "[aout]", "-r", "30",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-t", f"{dur:.3f}", "-movflags", "+faststart",
            str(out_path)]
    subprocess.run(cmd, check=True)


def probe(path):
    res = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True)
    d = json.loads(res.stdout)
    st = d["streams"][0]
    return {"width": st["width"], "height": st["height"],
            "duration": round(float(d["format"]["duration"]), 2), "lufs": signals.integrated_loudness(path)}


def post_description(desc, credits, hashtags):
    """`credits`: (channel, link) per source; a story cut or multi-streamer edit credits every one."""
    # hashtags already written into the description aren't repeated after the credit line
    have = {w.lower() for w in re.findall(r"#\w+", desc)}
    extra = " ".join(t for t in hashtags if t.lower() not in have)
    credits = list({link: (ch, link) for ch, link in reversed(list(credits))}.values())[::-1]  # one line per link
    if len(credits) == 1:
        credit = f"Clip from {credits[0][0]}: {credits[0][1]}"
    else:
        credit = "Clips from:\n" + "\n".join(f"{ch}: {link}" for ch, link in credits)
    return f"{desc}\n\n{credit}" + (f"\n\n{extra}" if extra else "")


def segment_job_dir(seg, job):
    return config.job_dir(seg["job"]) if seg.get("job") else job


def load_meta(job):
    return json.loads((job / "job.json").read_text(encoding="utf-8"))


def pick_sources(pick, job, meta):
    """[{job, meta, start, end}] in source seconds: one per segment, or the pick itself."""
    if not pick.get("segments") or job is None:
        return [{"job": job, "meta": meta, "start": float(pick["start"]), "end": float(pick["end"])}]
    out = []
    for seg in pick["segments"]:
        sj = segment_job_dir(seg, job)
        out.append({"job": sj, "meta": meta if sj == job else load_meta(sj),
                    "start": float(seg["start"]), "end": float(seg["end"])})
    return out


def credits(pick, job, meta):
    return [(src["meta"]["channel"],
             config.timestamp_link(src["meta"]["url"], int(src["start"] + src["meta"].get("offset", 0))))
            for src in pick_sources(pick, job, meta)]


REUSE_TOLERANCE_S = 3.0  # recorder clocks drift a little; a few seconds of shared footage isn't a repost


def footage_key(meta):
    """What footage is the same: a live channel (every chunk shares its wall clock) or a video id."""
    if meta.get("live"):
        m = re.search(r"(twitch|kick|youtube)\.(?:tv|com)/@?([^/?]+)", meta.get("url", ""))
        return f"{m.group(1)}:{m.group(2).lower()}" if m else f"live:{str(meta.get('channel', '')).lower()}"
    return str(meta.get("id") or meta.get("url"))


def footage(pick, job, meta):
    """Per source span: {source, from, to}; wall-clock seconds for live chunks, video seconds otherwise."""
    out = []
    for src in pick_sources(pick, job, meta):
        m = src["meta"]
        base = float(m.get("recorded_at") or 0) if m.get("live") else 0.0
        base += float(m.get("offset", 0) or 0)
        out.append({"source": footage_key(m), "from": round(base + src["start"], 2), "to": round(base + src["end"], 2)})
    return out


def moment_at(pick, job, meta):
    """When the moment happened (wall clock): the newest live segment, else now (a VOD's air time is unknown)."""
    live = [float(src["meta"]["recorded_at"]) + float(src["meta"].get("offset", 0) or 0) + src["start"]
            for src in pick_sources(pick, job, meta) if src["meta"].get("live") and src["meta"].get("recorded_at")]
    return round(max(live) if live else time.time())


def footage_overlap(a, b):
    """Seconds of footage two clips share."""
    return sum(max(0.0, min(x["to"], y["to"]) - max(x["from"], y["from"]))
               for x in a or [] for y in b or [] if x.get("source") == y.get("source"))


def footage_reuse(fp, exports=None, tol=REUSE_TOLERANCE_S):
    """Exported clips that already use more than `tol` seconds of this footage (profiles can share an account, so
    all of them count; a dub's entries don't, as it posts the same clip in another language on its own channel)."""
    hits = []
    for f in sorted(Path(exports or EXPORTS).glob("**/upload.json")):
        try:
            entries = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        used = next((e.get("footage") for e in entries if isinstance(e, dict) and e.get("footage")
                     and not e.get("lang")), None)
        shared = footage_overlap(fp, used)
        if shared > tol:
            hits.append(f"{f.parent.parent.parent.name}/{f.parent.parent.name}/{f.parent.name} already uses {shared:.0f}s of this footage")
    return hits


def predicted(pick, cfg):
    """Each hook's simulated views multiplier (the same ranking `clipper simulate` prints)."""
    try:
        from .simulate import profile_kw, simulate
        return {r["hook"]: round(r["x"], 3) for r in simulate(pick, runs=60, **profile_kw(cfg))}
    except Exception:  # a missing research dataset must not stop a render
        return {}


def build_segment_job(pick, job, cfg, out):
    """Cut every segment to 1080x1920 with its own layout and join them into `out` (source.mp4 + transcript.json
    with word times shifted onto the joined clip), so the normal render runs on it. Returns the pick to render
    there: start 0, end = total length, a `vertical` layout that keeps the segments' caption positions."""
    out.mkdir(parents=True, exist_ok=True)
    parts, words, t = [], [], 0.0
    layouts = []
    for i, seg in enumerate(pick["segments"]):
        sj = segment_job_dir(seg, job)
        s, e = float(seg["start"]), float(seg["end"])
        layout = seg.get("layout") or pick.get("layout") or {"type": "fit"}
        layouts.append(layout.get("type", "fit"))
        part = out / f"part{i:02d}.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{s:.3f}", "-t", f"{e - s:.3f}",
                        "-i", str(sj / "source.mp4"), "-filter_complex",
                        video_filter(layout, source_size(sj / "source.mp4")) + ";[v1]fps=30,format=yuv420p[v]",
                        "-map", "[v]", "-map", "0:a:0", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
                        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-t", f"{e - s:.3f}",
                        str(part)], check=True)
        parts.append(part)
        src_words = transcribe.drop_repeats(json.loads((sj / "transcript.json").read_text(encoding="utf-8"))["words"])
        words += [dict(w, s=round(w["s"] - s + t, 3), e=round(min(w["e"], e) - s + t, 3))
                  for w in src_words if s <= w["s"] < e]
        t += e - s
    lst = out / "parts.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", str(out / "source.mp4")], check=True)
    (out / "transcript.json").write_text(json.dumps({"words": words}), encoding="utf-8")
    # never cover a face: if any segment shows the facecam on top, the hook sits on the split seam
    as_ = (pick.get("layout") or {}).get("as") or ("split" if "split" in layouts else "fit")
    flat = {k: v for k, v in pick.items() if k != "segments"}
    return {**flat, "start": 0.0, "end": round(t, 3), "layout": {"type": "vertical", "as": as_}}, words


def clip_markdown(n, pick, meta, cfg, variants, prep, creds=None, dur=None):
    creds = creds or credits(pick, None, meta)
    dur = float(pick["end"]) - float(pick["start"]) if dur is None else dur
    titles = pick.get("titles") or [pick.get("title") or pick.get("hook") or "Clip"]
    tags = pick.get("hashtags") or cfg.get("hashtags", [])
    desc = pick.get("description") or titles[0]
    lines = [f"# Video {n}: {titles[0]}", "",
             "Source: " + " + ".join(f"{ch} {link}" for ch, link in creds) + f" ({dur:.0f}s)",
             f"Speakers detected: {prep['speakers']} · captions from {prep['transcript']}"
             f" · voices separated: {'yes' if prep['voices_separated'] else 'no'}"
             + (f" · voiceover: {prep['vo']['provider']}" if prep["vo"] else ""), "",
             "## Hook variants (one video each)"]
    paired = len(titles) == len(variants)
    for i, v in enumerate(variants):
        lines.append(f"- `{Path(v['file']).name}`: {v['hook'] or '(no banner)'}"
                     + (f"  →  post with title: {titles[i][:100]}" if paired else ""))
    lines += ["", "## Title options (YouTube Shorts, 100 max)"]
    lines += [f"{i}. {t[:100]} ({len(t[:100])})" for i, t in enumerate(titles, 1)]
    lines += ["", "## Description", post_description(desc, creds, tags)]
    return "\n".join(lines) + "\n"


def upload_manifest(pick, meta, cfg, variants, titles, creds=None, job=None):
    """What a poster needs per MP4: its hook, hook type, paired title and the caption, plus the footage it uses
    (so it's never posted twice), its predicted multiplier and when the moment happened (best-first queue)."""
    from .hooks import structures
    from .simulate import MODIFIERS, effect_table
    table = effect_table()
    creds = creds or credits(pick, job, meta)
    fp, when, pred = footage(pick, job, meta), moment_at(pick, job, meta), predicted(pick, cfg)
    tags = pick.get("hashtags") or cfg.get("hashtags", [])
    desc = pick.get("description") or titles[0]
    out = []
    for i, v in enumerate(variants):
        types = [t for t in structures(v["hook"]) if t not in MODIFIERS and t in table]
        out.append({"file": v["file"], "rank": i, "hook": v["hook"],
                    "hook_type": max(types, key=lambda t: table[t][0]) if types else None,
                    "title": (titles[i] if len(titles) == len(variants) else titles[0])[:100],
                    "description": post_description(desc, creds, tags),
                    "hashtags": pick.get("hashtags") or [], "clip_type": pick.get("clip_type"),
                    "campaign": pick.get("campaign"),
                    "source": creds[0][1], "sources": [link for _, link in creds],
                    "duration": v["check"].get("duration"), "footage": fp, "moment_at": when,
                    "predicted": pred.get(v["hook"])})
    return out


def export_dir(cfg, day=None):
    """exports/<profile>/<date>: each profile's clips stay separate, so each can post to its own accounts."""
    return EXPORTS / cfg.get("profile", config.PROFILE) / (day or date.today()).isoformat()


def next_video_number(out_dir):
    nums = [int(m.group(1)) for p in out_dir.glob("video *") if (m := re.fullmatch(r"video (\d+)", p.name))]
    return max(nums, default=0) + 1


def render(job, picks, cfg, first_hook_only=False, out_dir=None):
    meta = json.loads((job / "job.json").read_text(encoding="utf-8"))
    fallback = transcribe.drop_repeats(json.loads((job / "transcript.json").read_text(encoding="utf-8"))["words"])
    out_dir = Path(out_dir) if out_dir else export_dir(cfg)
    out_dir.mkdir(parents=True, exist_ok=True)
    first = next_video_number(out_dir)
    results = []
    for n, pick in enumerate(picks, first):
        hooks = pick.get("hooks") or [pick.get("hook", "")]
        if first_hook_only:
            hooks = hooks[:1]
        titles = pick.get("titles") or [pick.get("title") or hooks[0]]
        folder = out_dir / f"video {n}"
        folder.mkdir()
        taken = set()
        creds = credits(pick, job, meta)
        with tempfile.TemporaryDirectory(dir=job) as tmp:
            tmp = Path(tmp)
            src_job, flat, words = job, pick, fallback
            if pick.get("segments"):
                print(f"[render] video {n}: joining {len(pick['segments'])} segments ...", flush=True)
                src_job = tmp / "segments"
                flat, words = build_segment_job(pick, job, cfg, src_job)
            print(f"[render] video {n} ({n - first + 1} of {len(picks)}): separating voices + diarizing ...", flush=True)
            prep = prepare_clip(src_job, flat, words, cfg, tmp)
            variants = []
            for i, hook in enumerate(hooks):
                mp4 = folder / hook_filename(hook, taken)
                print(f"[render]   {mp4.relative_to(out_dir)}", flush=True)
                encode_variant(src_job, flat, prep, hook, cfg, mp4, tmp)
                variants.append({"file": str(mp4), "hook": hook, "check": probe(mp4)})
        (folder / "upload.json").write_text(json.dumps(upload_manifest(pick, meta, cfg, variants, titles, creds, job),
                                                       indent=2, ensure_ascii=False), encoding="utf-8")
        md = folder / "titles and description.md"
        md.write_text(clip_markdown(n, pick, meta, cfg, variants, prep, creds, float(flat["end"]) - float(flat["start"])),
                      encoding="utf-8")
        index = out_dir / "index.md"
        # a re-render of a deleted video N replaces its line instead of listing it twice
        lines = [x for x in (index.read_text(encoding="utf-8").splitlines(keepends=True) if index.exists() else [])
                 if not x.startswith(f"- **video {n}**:")]
        lines.append(f"- **video {n}**: {titles[0]} · {' + '.join(dict.fromkeys(ch for ch, _ in creds))} · "
                     f"{len(variants)} hooks · "
                     f"voiceover: {prep['vo']['provider'] if prep['vo'] else 'none'}\n")
        index.write_text("".join(lines), encoding="utf-8")
        results.append({"video": n, "folder": str(folder), "titles": titles, "metadata": str(md), "speakers": prep["speakers"],
                        "transcript": prep["transcript"], "voiceover": prep["vo"]["provider"] if prep["vo"] else None,
                        "variants": variants})
    return results
