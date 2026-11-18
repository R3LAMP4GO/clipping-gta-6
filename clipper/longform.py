"""Long-form running-bit supercuts (16:9, 8-10 min): one trait of a streamer delivered 25-30 times, escalating, opened
by a flash-forward of the best lines. research/long-form-compilations.md has the outlier study behind every number."""
import json
import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from . import captions, config, hooks, render

W, H = 1920, 1080
TW, TH = 1280, 720
MIN_S, MAX_S = 360, 720         # outliers: median 10.1 min, 43% at 6-9 min; same channels' normal uploads 12.1 min
AIM_S = (480, 600)
MIN_CLIPS, AIM_CLIPS = 12, (25, 30)
CLIP_MIN_S, CLIP_MAX_S = 6.0, 45.0
FLASH_MAX_S = 20.0
FACE_H = 454                    # the enlarged facecam: 42% of the frame height
MARGIN = 24


def _span(x):
    return float(x["end"]) - float(x["start"])


def check_long(spec):
    """{'fails': [...], 'notes': [...]} for a long-form spec (see /clip-long)."""
    fails, notes = [], []
    clips, flash = spec.get("clips") or [], spec.get("flash_forward") or []
    title = str(spec.get("title") or "").strip()
    if not title:
        fails.append("needs a title")
    elif len(title) > 100:
        fails.append(f"title is {len(title)} chars (max 100)")
    for i, c in enumerate(clips, 1):
        try:
            d = _span(c)
        except (KeyError, TypeError, ValueError):
            fails.append(f"clip {i} needs job, start and end")
            continue
        if not c.get("job"):
            fails.append(f"clip {i} needs a job")
        if not CLIP_MIN_S <= d <= CLIP_MAX_S:
            fails.append(f"clip {i} is {d:.0f}s: keep each clip {CLIP_MIN_S:g}-{CLIP_MAX_S:g}s (15-30s is the sweet spot)")
    if len(clips) < MIN_CLIPS:
        fails.append(f"{len(clips)} clips: a running-bit supercut needs at least {MIN_CLIPS} (aim {AIM_CLIPS[0]}-{AIM_CLIPS[1]})")
    elif not AIM_CLIPS[0] <= len(clips) <= AIM_CLIPS[1]:
        notes.append(f"{len(clips)} clips: the 97x and 95x outliers ran about {AIM_CLIPS[0]}-{AIM_CLIPS[1]}")
    by_job = {}
    for i, c in enumerate(clips, 1):
        if c.get("job") and "start" in c and "end" in c:
            for j, (a, b) in by_job.get(c["job"], []):
                if float(c["start"]) < b and float(c["end"]) > a:
                    fails.append(f"clips {j} and {i} overlap in {c['job']}")
            by_job.setdefault(c["job"], []).append((i, (float(c["start"]), float(c["end"]))))
    fd = 0.0
    for i, f in enumerate(flash, 1):
        try:
            fd += _span(f)
            inside = any(f.get("job") == c.get("job") and float(c["start"]) <= float(f["start"])
                         and float(f["end"]) <= float(c["end"]) for c in clips)
        except (KeyError, TypeError, ValueError):
            fails.append(f"flash-forward {i} needs job, start and end")
            continue
        if not inside:
            fails.append(f"flash-forward {i} must replay a moment from one of the clips (it promises what's coming)")
    if fd > FLASH_MAX_S:
        fails.append(f"flash-forward is {fd:.0f}s: keep it to {FLASH_MAX_S:g}s or less (3 lines, back to back)")
    if not flash:
        notes.append("no flash-forward: the Jeffy (64x) and Perfect Timing (97x) outliers open on the best lines from later")
    try:
        total = fd + sum(_span(c) for c in clips)
    except (KeyError, TypeError, ValueError):
        total = None
    if total is not None:
        if not MIN_S <= total <= MAX_S:
            fails.append(f"{total / 60:.1f} min total: keep it {MIN_S // 60}-{MAX_S // 60} min (aim 8-10)")
        elif not AIM_S[0] <= total <= AIM_S[1]:
            notes.append(f"{total / 60:.1f} min total: the outliers' sweet spot is 8-10 min")
    th = spec.get("thumbnail") or {}
    if not (th.get("job") and th.get("t") is not None):
        fails.append("needs a thumbnail: {\"job\", \"t\" (a frame where the face reacts hardest), \"text\"}")
    elif len(str(th.get("text") or "").split()) > 3:
        notes.append("thumbnail text over 3 words: the outliers use 0-3")
    return {k: v for k, v in (("fails", fails), ("notes", notes)) if v}


def face_box(item, spec, known):
    """The facecam box (fractions) for a clip: its own, the spec's, or the one its channel used before."""
    if item.get("face"):
        return item["face"]
    if spec.get("face"):
        return spec["face"]
    hit = known.get(hooks.job_channel(config.job_dir(item["job"])))
    return hit[1] if hit else None


def corner(face):
    """Overlay position (ffmpeg expressions) in the facecam's own corner, so the enlarged face covers the small one."""
    fx, fy, fw, fh = face
    x = f"{MARGIN}" if fx + fw / 2 < 0.5 else f"main_w-overlay_w-{MARGIN}"
    y = f"{MARGIN}" if fy + fh / 2 < 0.5 else f"main_h-overlay_h-{MARGIN}"
    return x, y


def clip_filter(size, face=None, counter=False):
    """16:9 frame with the facecam enlarged in its corner (white border) and an optional counter overlay (input 1)."""
    sw, sh = size
    g = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,setsar=1")
    if face:
        fx, fy, fw, fh = face
        x, y = corner(face)
        vf = (f"[0:v]split[a][b];[a]{g}[g];[b]crop={render._even(fw * sw)}:{render._even(fh * sh)}:"
              f"{int(fx * sw)}:{int(fy * sh)},scale=-2:{FACE_H},pad=iw+16:ih+16:8:8:white[f];"
              f"[g][f]overlay={x}:{y}[v0]")
    else:
        vf = f"[0:v]{g}[v0]"
    if counter:
        vf += ";[1:v]format=rgba[c];[v0][c]overlay=0:0[v1]"
    return vf + f";[{'v1' if counter else 'v0'}]fps=30,format=yuv420p[v]"


def counter_png(text, path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = captions.font("montserrat-black", 84)
    d.text(((W - f.getlength(text)) / 2, 30), text, font=f, fill=(255, 225, 60), stroke_width=6, stroke_fill=(0, 0, 0))
    img.save(path)


def encode_part(item, face, counter_text, out, tmp):
    jd = config.job_dir(item["job"])
    s, d = float(item["start"]), _span(item)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{s:.3f}", "-t", f"{d:.3f}", "-i", str(jd / "source.mp4")]
    if counter_text:
        png = tmp / f"{out.stem}_counter.png"
        counter_png(counter_text, png)
        cmd += ["-loop", "1", "-framerate", "30", "-t", f"{d:.3f}", "-i", str(png)]
    cmd += ["-filter_complex", clip_filter(render.source_size(jd / "source.mp4"), face, bool(counter_text)),
            "-map", "[v]", "-map", "0:a:0", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-t", f"{d:.3f}", str(out)]
    subprocess.run(cmd, check=True)


def _cover(img, w, h):
    s = max(w / img.width, h / img.height)
    img = img.resize((int(img.width * s + 0.5), int(img.height * s + 0.5)), Image.LANCZOS)
    return img.crop(((img.width - w) // 2, (img.height - h) // 2, (img.width - w) // 2 + w, (img.height - h) // 2 + h))


def thumbnail(spec, out, known):
    """1280x720: the streamer's face huge on the left (white outline) over the darkened scene, 0-3 big words right."""
    th = spec["thumbnail"]
    jd = config.job_dir(th["job"])
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "frame.png"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{float(th['t']):.3f}", "-i",
                        str(jd / "source.mp4"), "-frames:v", "1", str(png)], check=True)
        frame = Image.open(png).convert("RGB")
    bg = ImageEnhance.Brightness(_cover(frame, TW, TH).filter(ImageFilter.GaussianBlur(2))).enhance(0.7)
    face = face_box(th, spec, known)
    left = 60
    if face:
        fx, fy, fw, fh = face
        crop = frame.crop((int(fx * frame.width), int(fy * frame.height),
                           int((fx + fw) * frame.width), int((fy + fh) * frame.height)))
        fh_px = int(TH * 0.9)
        crop = crop.resize((max(1, int(crop.width * fh_px / crop.height)), fh_px), Image.LANCZOS)
        crop = crop.crop((0, 0, min(crop.width, int(TW * 0.58)), crop.height))
        framed = Image.new("RGB", (crop.width + 20, crop.height + 20), (255, 255, 255))
        framed.paste(crop, (10, 10))
        bg.paste(framed, (30, (TH - framed.height) // 2))
        left = 30 + framed.width + 30
    text = str(th.get("text") or "").strip().upper()
    if text:
        words, max_w = text.split(), TW - left - 40
        for size in range(170, 60, -6):
            f = captions.font("montserrat-black", size)
            lines = [[w] for w in words[:1]]
            for w in words[1:]:
                if f.getlength(" ".join(lines[-1] + [w])) <= max_w:
                    lines[-1].append(w)
                else:
                    lines.append([w])
            if len(lines) <= 3 and all(f.getlength(" ".join(l)) <= max_w for l in lines):
                break
        d = ImageDraw.Draw(bg)
        lh = int(size * 1.1)
        y = (TH - lh * len(lines)) // 2
        for l in lines:
            s = " ".join(l)
            d.text((left + (max_w - f.getlength(s)) / 2, y), s, font=f, fill=(255, 225, 60),
                   stroke_width=10, stroke_fill=(0, 0, 0))
            y += lh
    bg.save(out, quality=92)
    return out


def next_long_number(out_dir):
    nums = [int(m.group(1)) for p in out_dir.glob("long *") if (m := re.fullmatch(r"long (\d+)", p.name))]
    return max(nums, default=0) + 1


def render_long(spec, cfg, out_dir=None, check=True):
    """Render a long-form spec to exports/<profile>/<date>/long N/: the MP4, thumbnail.jpg, long.json (title,
    description with every source credited, footage) and a markdown sheet. Never `video N`: the autopilot only
    queues `video N/upload.json`, so a long video can't be posted as a Short."""
    if check and check_long(spec).get("fails"):
        raise SystemExit("[long] fix these first:\n" + "\n".join(check_long(spec)["fails"]))
    known = hooks.known_facecams(config.JOBS)
    out_dir = Path(out_dir) if out_dir else render.export_dir(cfg)
    out_dir.mkdir(parents=True, exist_ok=True)
    folder = out_dir / f"long {next_long_number(out_dir)}"
    folder.mkdir()
    counter = spec.get("counter")
    clips, flash = spec["clips"], spec.get("flash_forward") or []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        parts = []
        for i, f in enumerate(flash):
            p = tmp / f"f{i:02d}.mp4"
            encode_part(f, face_box(f, spec, known), None, p, tmp)
            parts.append(p)
        for i, c in enumerate(clips):
            p = tmp / f"c{i:03d}.mp4"
            label = counter.replace("{n}", str(i + 1)) if counter and c.get("count", True) else None
            print(f"[long] clip {i + 1} of {len(clips)}", flush=True)
            encode_part(c, face_box(c, spec, known), label, p, tmp)
            parts.append(p)
        lst = tmp / "parts.txt"
        lst.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
        joined = tmp / "joined.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-c", "copy", str(joined)], check=True)
        mp4 = folder / render.hook_filename(spec["title"], set())
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(joined), "-c:v", "copy",
                        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                        "-movflags", "+faststart", str(mp4)], check=True)
    thumb = thumbnail(spec, folder / "thumbnail.jpg", known)
    first = config.job_dir(clips[0]["job"])
    pseudo = {"segments": [{**c, "job": c["job"]} for c in clips]}
    meta = render.load_meta(first)
    creds = render.credits(pseudo, first, meta)
    desc = render.post_description(spec.get("description") or spec["title"], creds, spec.get("hashtags") or [])
    info = render.probe(mp4)
    manifest = {"kind": "long", "title": spec["title"], "description": desc, "hashtags": spec.get("hashtags") or [],
                "file": str(mp4), "thumbnail": str(thumb), "thumbnail_text": (spec.get("thumbnail") or {}).get("text"),
                "duration": info["duration"], "width": info["width"], "height": info["height"],
                "clips": len(clips), "flash_forward_s": round(sum(_span(f) for f in flash), 2),
                "sources": [link for _, link in creds], "footage": render.footage(pseudo, first, meta),
                "clipper_version": config.code_version()}
    (folder / "long.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (folder / "titles and description.md").write_text(
        f"# {spec['title']}\n\n**Length:** {info['duration'] / 60:.1f} min · {len(clips)} clips · "
        f"thumbnail text: {manifest['thumbnail_text'] or '(none)'}\n\n## Description\n\n{desc}\n", encoding="utf-8")
    return {"folder": str(folder), "file": str(mp4), "thumbnail": str(thumb), "duration": info["duration"],
            "size": f"{info['width']}x{info['height']}"}
