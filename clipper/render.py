import json
import re
import subprocess
import tempfile
from datetime import date
from pathlib import Path

from . import captions, signals, speakers, transcribe, tts
from .analyze import fmt
from . import config
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


def video_filter(layout, size):
    if layout.get("type") == "split":
        sw, sh = size
        fx, fy, fw, fh = layout["face"]
        gx = layout.get("game_x", 0.5)
        return (f"[0:v]split[a][b];[a]crop={_even(fw * sw)}:{_even(fh * sh)}:{int(fx * sw)}:{int(fy * sh)},"
                "scale=1080:768:force_original_aspect_ratio=increase,crop=1080:768[top];"
                f"[b]scale=-2:1152,crop=1080:1152:(iw-1080)*{gx}:0[bot];[top][bot]vstack[v1]")
    return ("[0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            "gblur=sigma=40,eq=brightness=-0.18[bg];[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[v1]")


def prepare_clip(job, pick, fallback_words, cfg, tmp):
    """Per-clip work shared by every hook variant: voice separation, diarized captions, audio bed, voiceover."""
    s, e = float(pick["start"]), float(pick["end"])
    dur = e - s
    clip_wav = tmp / "clip.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{s:.3f}", "-t", f"{dur:.3f}",
                    "-i", str(job / "source.mp4"), "-vn", "-ac", "2", "-ar", "44100", str(clip_wav)], check=True)
    stems = speakers.separate(clip_wav, tmp, cfg) if cfg.get("separate_voices", True) else None
    silent = bool(stems) and (signals.integrated_loudness(stems[0]) or -99) < cfg.get("speech_floor_lufs", -40)
    words = [] if silent else speakers.diarized_words(stems[0] if stems else clip_wav, tmp / "wk", cfg)
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
    layout = pick.get("layout") or {"type": "fit"}
    caps = captions.write_overlay(words, 0.0, dur, tmp / "caps", layout.get("type", "fit"),
                                  pick.get("caption_style") or cfg.get("caption_style", "bold"))
    vo = None
    if pick.get("voiceover"):
        vo_path = tmp / "vo.wav"
        vo_dur, provider = tts.synth(pick["voiceover"], cfg, vo_path)
        vo = {"path": vo_path, "duration": vo_dur, "provider": provider}
    speakers_found = len({w.get("spk", 0) for w in words})
    return {"captions": caps, "bed": bed, "vo": vo, "layout": layout, "speakers": speakers_found,
            "transcript": source, "voices_separated": bool(stems), "words": words}


def encode_variant(job, pick, prep, hook, cfg, out_path, tmp):
    s, e = float(pick["start"]), float(pick["end"])
    dur = e - s
    layout = prep["layout"]
    hook_png = tmp / f"hook_{out_path.stem}.png"
    captions.render_hook(hook, hook_png, pick.get("hook_style", "box"), layout.get("type", "fit"))
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


def clip_markdown(n, pick, meta, cfg, variants, prep):
    abs_s = int(float(pick["start"]) + meta.get("offset", 0))
    link = config.timestamp_link(meta['url'], abs_s)
    titles = pick.get("titles") or [pick.get("title") or pick.get("hook") or "Clip"]
    tags = " ".join(pick.get("hashtags") or cfg.get("hashtags", []))
    desc = pick.get("description") or titles[0]
    lines = [f"# Video {n}: {titles[0]}", "",
             f"Source: {link} ({fmt(abs_s)}, {float(pick['end']) - float(pick['start']):.0f}s)",
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
    lines += ["", "## Description", f"{desc}\n\nClip from {meta['channel']}: {link}\n\n{tags}"]
    return "\n".join(lines) + "\n"


def upload_manifest(pick, meta, cfg, variants, titles):
    """What a poster needs per MP4: its hook, hook type, paired title and the caption."""
    from .hooks import structures
    from .simulate import MODIFIERS, effect_table
    table = effect_table()
    abs_s = int(float(pick["start"]) + meta.get("offset", 0))
    link = config.timestamp_link(meta['url'], abs_s)
    tags = " ".join(pick.get("hashtags") or cfg.get("hashtags", []))
    desc = pick.get("description") or titles[0]
    out = []
    for i, v in enumerate(variants):
        types = [t for t in structures(v["hook"]) if t not in MODIFIERS and t in table]
        out.append({"file": v["file"], "rank": i, "hook": v["hook"],
                    "hook_type": max(types, key=lambda t: table[t][0]) if types else None,
                    "title": (titles[i] if len(titles) == len(variants) else titles[0])[:100],
                    "description": f"{desc}\n\nClip from {meta['channel']}: {link}\n\n{tags}",
                    "hashtags": pick.get("hashtags") or [], "clip_type": pick.get("clip_type"),
                    "campaign": pick.get("campaign"),
                    "source": link, "duration": v["check"].get("duration")})
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
        with tempfile.TemporaryDirectory(dir=job) as tmp:
            tmp = Path(tmp)
            print(f"[render] video {n} ({n - first + 1} of {len(picks)}): separating voices + diarizing ...", flush=True)
            prep = prepare_clip(job, pick, fallback, cfg, tmp)
            variants = []
            for i, hook in enumerate(hooks):
                mp4 = folder / hook_filename(hook, taken)
                print(f"[render]   {mp4.relative_to(out_dir)}", flush=True)
                encode_variant(job, pick, prep, hook, cfg, mp4, tmp)
                variants.append({"file": str(mp4), "hook": hook, "check": probe(mp4)})
        (folder / "upload.json").write_text(json.dumps(upload_manifest(pick, meta, cfg, variants, titles), indent=2,
                                                       ensure_ascii=False), encoding="utf-8")
        md = folder / "titles and description.md"
        md.write_text(clip_markdown(n, pick, meta, cfg, variants, prep), encoding="utf-8")
        index = out_dir / "index.md"
        # a re-render of a deleted video N replaces its line instead of listing it twice
        lines = [x for x in (index.read_text(encoding="utf-8").splitlines(keepends=True) if index.exists() else [])
                 if not x.startswith(f"- **video {n}**:")]
        lines.append(f"- **video {n}**: {titles[0]} · {meta['channel']} · {len(variants)} hooks · "
                     f"voiceover: {prep['vo']['provider'] if prep['vo'] else 'none'}\n")
        index.write_text("".join(lines), encoding="utf-8")
        results.append({"video": n, "folder": str(folder), "titles": titles, "metadata": str(md), "speakers": prep["speakers"],
                        "transcript": prep["transcript"], "voiceover": prep["vo"]["provider"] if prep["vo"] else None,
                        "variants": variants})
    return results
