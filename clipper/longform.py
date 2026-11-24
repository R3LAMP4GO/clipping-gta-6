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


KINDS = ("supercut", "mid", "story")
# "What happens" videos: one situation and its outcome. Built as a test (research/outlier-questions-2026-11.md found
# 61s-3 min no better than >10 min), so the checks only guard the shape: a stated situation, an early payoff.
MID_S, MID_CLIPS, MID_CLIP_S = (30, 180), (1, 4), (4.0, 180.0)
MID_PAYOFF_MAX = 0.6
# Narrated story videos (4-10 min, AI voice between clips): limits from the plan, not measured outliers.
STORY_S, STORY_CLIP_S = (240, 600), (6.0, 90.0)
STORY_NARRATION_MAX, STORY_QUESTION_BY_S = 0.35, 15.0
STORY_MIN_WORDS = 3             # a clip with fewer transcript words has nobody talking
DUCK, FREEZE_PAD_S = 0.25, 0.3  # clip audio under a ducked line; silence after a line on a frozen frame


def kind_of(spec):
    return spec.get("kind") or "supercut"


def title_situation(title):
    """A title that states a situation or asks a question: not a bare mood or reaction ("INSANE MOMENT 😱",
    "Kai Cenat Was Not Ready")."""
    t = hooks.plain(title)
    if "?" in t or hooks.loop_frame(t) == "hypothetical":
        return True
    if hooks.REACTION_ONLY.search(t) and not hooks.STAKE.search(t):
        return False
    return len([w for w in hooks.content_words(t) if w not in hooks.TOPIC_WORDS]) >= 3


def payoff_position(spec):
    """(seconds into the video, total seconds) of `payoff` {"clip": n (1-based), "t": source s}; raises ValueError."""
    clips, p = spec.get("clips") or [], spec.get("payoff") or {}
    n, t = int(p["clip"]), float(p["t"])
    if not 1 <= n <= len(clips):
        raise ValueError(f"payoff clip {n} doesn't exist")
    c = clips[n - 1]
    if not float(c["start"]) <= t <= float(c["end"]):
        raise ValueError(f"payoff {t:g}s is outside clip {n} ({float(c['start']):g}-{float(c['end']):g}s)")
    before = sum(_span(x) for x in clips[:n - 1])
    return before + t - float(c["start"]), sum(_span(x) for x in clips)


def narration_secs(text):
    return len(str(text or "").split()) / hooks.NARRATION_WPS + FREEZE_PAD_S


def story_timeline(spec, durs=None):
    """Where each narration line plays: [{"n", "at", "mode", "start" (video s), "dur", "offset" (s into its clip,
    ducked lines)}], plus total and narrated seconds. `durs` are the voiced lengths; estimated from words if None."""
    clips, lines = spec.get("clips") or [], spec.get("narration") or []
    durs = list(durs) if durs is not None else [narration_secs(x.get("text")) for x in lines]
    out, t, narrated = [], 0.0, 0.0
    for i in range(1, len(clips) + 2):
        offset = 0.0
        for n, (x, d) in enumerate(zip(lines, durs), 1):
            if x.get("at") != i:
                continue
            mode = x.get("mode") or "freeze"
            out.append({"n": n, "at": i, "mode": mode, "start": t + (offset if mode == "duck" else 0.0), "dur": d,
                        "offset": offset})
            narrated += d
            if mode == "duck":
                offset += d
            else:
                t += d
        if i <= len(clips):
            t += _span(clips[i - 1])
    return out, t, narrated


def _check_story(spec, clips, flash, fails, notes, words_for):
    if flash:
        fails.append("a story video has no flash-forward: the narrator states the question up front instead")
    lines = spec.get("narration") or []
    if not lines:
        fails.append("no `narration`: [{\"at\": clip n, \"text\": \"...\", \"mode\": \"freeze\"|\"duck\"}], the "
                     "question first, then the lines that carry the story between clips")
        return
    for n, x in enumerate(lines, 1):
        if not str(x.get("text") or "").strip():
            fails.append(f"narration {n} has no text")
        if x.get("mode", "freeze") not in ("freeze", "duck"):
            fails.append(f"narration {n}: mode must be freeze or duck")
        if not isinstance(x.get("at"), int) or not 1 <= x["at"] <= len(clips) + (x.get("mode") != "duck"):
            fails.append(f"narration {n}: `at` must be a clip number (1-{len(clips)}; {len(clips) + 1} = after the last, "
                         "freeze only)")
    if fails:
        return
    try:
        timeline, total, narrated = story_timeline(spec)
    except (KeyError, TypeError, ValueError):
        return
    if not STORY_S[0] <= total <= STORY_S[1]:
        fails.append(f"{total / 60:.1f} min total: keep a story video {STORY_S[0] // 60}-{STORY_S[1] // 60} min")
    if total and narrated / total > STORY_NARRATION_MAX:
        fails.append(f"the narrator takes {narrated / total:.0%} of the runtime (max {STORY_NARRATION_MAX:.0%}): "
                     "let the streamers carry it; narrate only what the footage can't show")
    fails.extend(story_overlap(spec, timeline))
    q = next((e for e in timeline if lines[e["n"] - 1].get("question") or "?" in str(lines[e["n"] - 1].get("text"))),
             None)
    if q is None:
        fails.append("no narration line states the question: mark it {\"question\": true} or end it with \"?\"")
    elif q["start"] + q["dur"] > STORY_QUESTION_BY_S:
        fails.append(f"the question is stated by {q['start'] + q['dur']:.0f}s: state it by "
                     f"{STORY_QUESTION_BY_S:g}s (open on it, before or over the first clip)")
    if words_for is not None:
        for i, c in enumerate(clips, 1):
            words = words_for(c["job"])
            if words is None:
                notes.append(f"clip {i}: no transcript in {c['job']}, so who talks can't be checked")
            elif sum(1 for w in words if float(c["start"]) <= w["s"] < float(c["end"])) < STORY_MIN_WORDS:
                fails.append(f"clip {i}: nobody talks in it: a story is told by the streamers, the narrator only links "
                             "their clips (the recycled-content rule targets voice-over on silent footage)")


def story_overlap(spec, timeline):
    """Fails for a ducked line that covers its clip's `payoff_at` or runs past the clip."""
    clips, out = spec.get("clips") or [], []
    for e in timeline:
        if e["mode"] != "duck":
            continue
        c = clips[e["at"] - 1]
        a = float(c["start"]) + e["offset"]
        b = a + e["dur"]
        if b > float(c["end"]):
            out.append(f"narration {e['n']} runs {b - float(c['end']):.1f}s past clip {e['at']}: freeze it or cut it")
        if c.get("payoff_at") is not None and a <= float(c["payoff_at"]) <= b:
            out.append(f"narration {e['n']} talks over clip {e['at']}'s payoff ({float(c['payoff_at']):g}s): never "
                       "narrate the payoff; freeze before the clip instead")
    return out


def _check_supercut(spec, clips, flash, fails, notes):
    if len(clips) < MIN_CLIPS:
        fails.append(f"{len(clips)} clips: a running-bit supercut needs at least {MIN_CLIPS} (aim {AIM_CLIPS[0]}-{AIM_CLIPS[1]})")
    elif not AIM_CLIPS[0] <= len(clips) <= AIM_CLIPS[1]:
        notes.append(f"{len(clips)} clips: the 97x and 95x outliers ran about {AIM_CLIPS[0]}-{AIM_CLIPS[1]}")
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


def _check_mid(spec, clips, flash, fails, notes):
    title = str(spec.get("title") or "")
    if title and not title_situation(title):
        fails.append("the title states no situation or question: say who does what (\"Lucia Joins A Cult In GTA 6\") or "
                     "ask it (\"What Happens If You Leave Lucia In Prison?\")")
    if flash:
        fails.append("a \"what happens\" video has no flash-forward: it opens on the setup, not the answer")
    if not MID_CLIPS[0] <= len(clips) <= MID_CLIPS[1]:
        fails.append(f"{len(clips)} clips: a \"what happens\" video is {MID_CLIPS[0]}-{MID_CLIPS[1]} clips of one situation")
    try:
        total = sum(_span(c) for c in clips)
    except (KeyError, TypeError, ValueError):
        return
    if clips and not MID_S[0] <= total <= MID_S[1]:
        fails.append(f"{total:.0f}s total: keep a \"what happens\" video {MID_S[0]}s-{MID_S[1] // 60} min")
    if not spec.get("payoff"):
        fails.append("no `payoff`: {\"clip\": n, \"t\": source seconds} where the outcome lands (no outcome, no video)")
        return
    try:
        at, total = payoff_position(spec)
    except (KeyError, TypeError, ValueError) as e:
        fails.append(f"payoff: {e}" if isinstance(e, ValueError) and "payoff" in str(e)
                     else "payoff needs {\"clip\": n, \"t\": source seconds}")
        return
    if total and at / total > MID_PAYOFF_MAX:
        fails.append(f"the payoff lands {at:.0f}s into {total:.0f}s ({at / total:.0%}): bring it before "
                     f"{MID_PAYOFF_MAX:.0%} by trimming the setup; the rest is the fallout")


def check_long(spec, words_for=None):
    """{'fails': [...], 'notes': [...]} for a long-form spec (see /clip-long). `kind`: "supercut" (default), "mid"
    (a 30s-3 min "what happens" video) or "story" (4-10 min, narrated). `words_for(job)` -> transcript words, for
    the story check that every clip has someone talking."""
    fails, notes = [], []
    kind = kind_of(spec)
    if kind not in KINDS:
        return {"fails": [f"kind {kind!r} must be one of {', '.join(KINDS)}"]}
    clips, flash = spec.get("clips") or [], spec.get("flash_forward") or []
    title = str(spec.get("title") or "").strip()
    if not title:
        fails.append("needs a title")
    elif len(title) > 100:
        fails.append(f"title is {len(title)} chars (max 100)")
    lo, hi = {"supercut": (CLIP_MIN_S, CLIP_MAX_S), "mid": MID_CLIP_S, "story": STORY_CLIP_S}[kind]
    for i, c in enumerate(clips, 1):
        try:
            d = _span(c)
        except (KeyError, TypeError, ValueError):
            fails.append(f"clip {i} needs job, start and end")
            continue
        if not c.get("job"):
            fails.append(f"clip {i} needs a job")
        if not lo <= d <= hi:
            fails.append(f"clip {i} is {d:.0f}s: keep each clip {lo:g}-{hi:g}s"
                         + (" (15-30s is the sweet spot)" if kind == "supercut" else ""))
    by_job = {}
    for i, c in enumerate(clips, 1):
        if c.get("job") and "start" in c and "end" in c:
            for j, (a, b) in by_job.get(c["job"], []):
                if float(c["start"]) < b and float(c["end"]) > a:
                    fails.append(f"clips {j} and {i} overlap in {c['job']}")
            by_job.setdefault(c["job"], []).append((i, (float(c["start"]), float(c["end"]))))
    if kind == "supercut":
        _check_supercut(spec, clips, flash, fails, notes)
    elif kind == "mid":
        _check_mid(spec, clips, flash, fails, notes)
    else:
        _check_story(spec, clips, flash, fails, notes, words_for)
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


STEREO = "aformat=sample_rates=48000:channel_layouts=stereo"


def narration_audio(lines, first_input):
    """Audio graph: the clip's sound [0:a] ducked while each (wav, offset, dur) narration line (inputs from
    `first_input`) plays over it."""
    on = "+".join(f"between(t,{o:.3f},{o + d:.3f})" for _, o, d in lines)
    f = f"[0:a:0]volume='if({on},{DUCK},1)':eval=frame,{STEREO}[ca]"
    for k, (_, o, _) in enumerate(lines):
        f += f";[{first_input + k}:a]adelay={int(o * 1000)}:all=1,{STEREO}[n{k}]"
    return f + f";[ca]{''.join(f'[n{k}]' for k in range(len(lines)))}amix=inputs={len(lines) + 1}:duration=first:normalize=0[a]"


def encode_part(item, face, counter_text, out, tmp, narration=()):
    jd = config.job_dir(item["job"])
    s, d = float(item["start"]), _span(item)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{s:.3f}", "-t", f"{d:.3f}", "-i", str(jd / "source.mp4")]
    if counter_text:
        png = tmp / f"{out.stem}_counter.png"
        counter_png(counter_text, png)
        cmd += ["-loop", "1", "-framerate", "30", "-t", f"{d:.3f}", "-i", str(png)]
    for wav, _, _ in narration:
        cmd += ["-i", str(wav)]
    graph = clip_filter(render.source_size(jd / "source.mp4"), face, bool(counter_text))
    if narration:
        graph += ";" + narration_audio(narration, 2 if counter_text else 1)
    cmd += ["-filter_complex", graph,
            "-map", "[v]", "-map", "[a]" if narration else "0:a:0", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-t", f"{d:.3f}", str(out)]
    subprocess.run(cmd, check=True)


def encode_still(item, at, face, wav, dur, out, tmp):
    """`dur` seconds on the frame at source second `at`, with the narration `wav` as the only sound."""
    jd = config.job_dir(item["job"])
    png = tmp / f"{out.stem}.png"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(0.0, at):.3f}", "-i", str(jd / "source.mp4"),
                    "-frames:v", "1", str(png)], check=True)
    graph = (clip_filter(render.source_size(jd / "source.mp4"), face)
             + f";[1:a]apad=whole_dur={dur:.3f},{STEREO}[a]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", "30", "-t", f"{dur:.3f}",
                    "-i", str(png), "-i", str(wav), "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "192k",
                    "-ar", "48000", "-ac", "2", "-t", f"{dur:.3f}", str(out)], check=True)


def voice_lines(spec, cfg, tmp):
    """Voice every narration line with tts.synth: [(wav, seconds)], and the providers used."""
    from . import tts
    out, used = [], set()
    for n, x in enumerate(spec.get("narration") or [], 1):
        wav = tmp / f"n{n:02d}.wav"
        secs, provider = tts.synth(str(x["text"]), cfg, wav)
        out.append((wav, secs + FREEZE_PAD_S))
        used.add(provider)
    return out, sorted(used)


def story_parts(spec, known, voiced, tmp):
    """Encode a story's parts in order: frozen-frame lines, then each clip with its ducked lines mixed in."""
    clips = spec["clips"]
    timeline, _, _ = story_timeline(spec, [d for _, d in voiced])
    bad = story_overlap(spec, timeline)
    if bad:  # the voiced lines can run longer than the word-count estimate the check used
        raise SystemExit("[long] the voiced narration doesn't fit:\n" + "\n".join(bad))
    parts = []
    for i in range(1, len(clips) + 2):
        c = clips[min(i, len(clips)) - 1]
        face = face_box(c, spec, known)
        for e in (e for e in timeline if e["at"] == i and e["mode"] == "freeze"):
            p = tmp / f"s{len(parts):03d}.mp4"
            at = float(c["start"]) if i <= len(clips) else float(c["end"]) - 0.05
            encode_still(c, at, face, voiced[e["n"] - 1][0], e["dur"], p, tmp)
            parts.append(p)
        if i <= len(clips):
            ducks = [(voiced[e["n"] - 1][0], e["offset"], e["dur"]) for e in timeline
                     if e["at"] == i and e["mode"] == "duck"]
            p = tmp / f"s{len(parts):03d}.mp4"
            print(f"[long] clip {i} of {len(clips)}", flush=True)
            encode_part(c, face, None, p, tmp, ducks)
            parts.append(p)
    return parts, timeline


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


def reused_footage(spec, exports=None):
    """Fails for a mid or story video whose clips an earlier export of the same kind already used (a Short of the
    same moment is fine). Supercuts are exempt: they gather moments that were already posted."""
    kind = kind_of(spec)
    clips = spec.get("clips") or []
    if kind == "supercut" or not clips:
        return []
    first = config.job_dir(clips[0]["job"])
    fp = render.footage({"segments": clips}, first, render.load_meta(first))
    hits = render.footage_reuse(fp, exports, shape=kind)
    return hits + [f"pick other moments: this footage already went out as a {kind} video"] if hits else []


def render_long(spec, cfg, out_dir=None, check=True, words_for=None):
    """Render a long-form spec to exports/<profile>/<date>/long N/: the MP4, thumbnail.jpg, long.json (title,
    description with every source credited, footage) and a markdown sheet. Never `video N`: the autopilot only
    queues `video N/upload.json`, so a long video can't be posted as a Short."""
    if check:
        bad = check_long(spec, words_for).get("fails", []) + reused_footage(spec)
        if bad:
            raise SystemExit("[long] fix these first:\n" + "\n".join(bad))
    known = hooks.known_facecams(config.JOBS)
    out_dir = Path(out_dir) if out_dir else render.export_dir(cfg)
    out_dir.mkdir(parents=True, exist_ok=True)
    folder = out_dir / f"long {next_long_number(out_dir)}"
    folder.mkdir()
    kind = kind_of(spec)
    counter = spec.get("counter") if kind == "supercut" else None
    clips = spec["clips"]
    flash = (spec.get("flash_forward") or []) if kind == "supercut" else []
    voices, timeline = [], []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        parts = []
        if kind == "story":
            voiced, voices = voice_lines(spec, cfg, tmp)
            try:
                parts, timeline = story_parts(spec, known, voiced, tmp)
            except SystemExit:
                folder.rmdir()  # nothing was written into it yet
                raise
            clips = []  # already encoded
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
    clips = spec["clips"]
    thumb = thumbnail(spec, folder / "thumbnail.jpg", known)
    first = config.job_dir(clips[0]["job"])
    pseudo = {"segments": [{**c, "job": c["job"]} for c in clips]}
    meta = render.load_meta(first)
    creds = render.credits(pseudo, first, meta)
    desc = render.post_description(spec.get("description") or spec["title"], creds, spec.get("hashtags") or [])
    info = render.probe(mp4)
    manifest = {"kind": "long" if kind == "supercut" else kind, "title": spec["title"],
                "premise_type": spec.get("premise_type"), "question": spec.get("question"), "description": desc, "hashtags": spec.get("hashtags") or [],
                "file": str(mp4), "thumbnail": str(thumb), "thumbnail_text": (spec.get("thumbnail") or {}).get("text"),
                "duration": info["duration"], "width": info["width"], "height": info["height"],
                "clips": len(clips), "flash_forward_s": round(sum(_span(f) for f in flash), 2),
                "sources": [link for _, link in creds], "footage": render.footage(pseudo, first, meta),
                **({"narration": [{"text": spec["narration"][e["n"] - 1]["text"], "mode": e["mode"],
                                   "from": round(e["start"], 2), "to": round(e["start"] + e["dur"], 2)}
                                  for e in timeline], "voice": voices} if kind == "story" else {}),
                "clipper_version": config.code_version()}
    (folder / "long.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (folder / "titles and description.md").write_text(
        f"# {spec['title']}\n\n**Length:** {info['duration'] / 60:.1f} min · {len(clips)} clips · "
        f"thumbnail text: {manifest['thumbnail_text'] or '(none)'}\n\n## Description\n\n{desc}\n", encoding="utf-8")
    return {"folder": str(folder), "file": str(mp4), "thumbnail": str(thumb), "duration": info["duration"],
            "size": f"{info['width']}x{info['height']}"}
