"""Long-form running-bit supercuts (16:9, 8-10 min): one trait of a streamer delivered 25-30 times, escalating, opened
by a flash-forward of the best lines. research/long-form-compilations.md has the outlier study behind every number."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from . import captions, config, hooks, longbank, render

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


KINDS = ("supercut", "mid", "story", "compilation")
# "What happens" videos: one situation and its outcome. Built as a test (research/outlier-questions-2026-11.md found
# 61s-3 min no better than >10 min), so the checks only guard the shape: a stated situation, an early payoff.
MID_S, MID_CLIPS, MID_CLIP_S = (30, 180), (1, 4), (4.0, 180.0)
MID_PAYOFF_MAX = 0.6
# Narrated story videos (4-10 min, AI voice between clips): limits from the plan, not measured outliers.
STORY_S, STORY_CLIP_S = (240, 600), (6.0, 90.0)
STORY_NARRATION_MAX, STORY_QUESTION_BY_S = 0.35, 15.0
STORY_MIN_WORDS = 3             # a clip with fewer transcript words has nobody talking
DUCK, FREEZE_PAD_S = 0.25, 0.3  # clip audio under a ducked line; silence after a line on a frozen frame
# "[Streamer] Funniest Moments (Compilation)" (research/long-form-streamers-2026-11.md): compilation wording on IRL
# footage 29.1% outliers (2.2x), gaming 16.2%, GTA RP 7.8%; 3-6 min is the dead zone (8.2%).
COMP_MIN_CLIPS, COMP_CLIP_S = 10, (6.0, 60.0)
COMP_S, COMP_AIM_S = (360, 900), (480, 720)
COMP_TITLE_MAX = 60
COMP_WORDS = re.compile(r"\b(moments?|best of|funniest|clips?|compilation|highlights?)\b", re.I)
LENGTH_PROMISE = re.compile(r"\b(for|in|over)\s+(\d+|an?|one|two|three|five|ten|\w+teen|twenty|thirty)\s+"
                            r"(min(ute)?s?|hours?|hrs?)\b|\b(min(ute)?s?|hours?) straight\b", re.I)
SERIES_TAG = re.compile(r"\b(ep(isode)?|part|pt|day|vol)\.?\s*#?\d+\b|#\d+", re.I)
NICHES = {"irl": None, "gaming": "gaming footage: compilation wording lifts it less (16.2% outliers vs 29.1% on IRL)",
          "rp": "GTA RP footage is the weakest base (7.8% outliers): IRL / just-chatting moments do best"}
SHORT_TITLE = 40


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


def spec_names(spec):
    """Who the video is about: the spec's `streamer`, plus the channels of its clips' jobs that exist."""
    names = [spec["streamer"]] if spec.get("streamer") else []
    for c in spec.get("clips") or []:
        try:
            ch = hooks.job_channel(config.job_dir(c["job"]))
        except (SystemExit, KeyError, TypeError):
            continue
        if ch and ch not in names:
            names.append(ch)
    return names


def _squash(x):
    return re.sub(r"[^a-z0-9]", "", str(x).lower())


def names_someone(title, names):
    """Whether the title names a person: one of `names` (spaces and case ignored, "Kai Cenat Live" matches
    "Kai Cenat"), else, with no names known, a capitalised word that isn't the first or a stock word."""
    t = _squash(title)
    for n in names:
        parts = [_squash(w) for w in str(n).split() if len(_squash(w)) >= 3 and _squash(w) not in ("live", "tv", "clips")]
        if _squash(n) in t or (parts and all(p in t for p in parts[:2])):
            return True
    if names:
        return False
    stock = {"funniest", "moments", "moment", "best", "of", "the", "compilation", "highlights", "clips", "gta", "rp",
             "most", "funny", "insane", "crazy", "when", "what", "how", "why", "this", "my", "his", "her"}
    words = re.findall(r"[A-Za-z][\w']*", re.sub(r"\(.*?\)", "", title))
    return any(w[0].isupper() and w.lower() not in stock for w in words[1:]) or bool(words and words[0].lower() not in stock)


def shared_notes(spec, names=None):
    """Notes for every long kind (research/long-form-streamers-2026-11.md P6): short plain titles that name the
    streamer, 0-3 thumbnail words."""
    title = str(spec.get("title") or "").strip()
    names = spec_names(spec) if names is None else names
    out = []
    if len(title) > SHORT_TITLE:
        out.append(f"title is {len(title)} chars: titles of 40 or fewer did best (15.6% outliers vs 8.5% at 80+)")
    if "|" in title or "#" in title or SERIES_TAG.search(title):
        out.append("title has a pipe, hashtag or series tag: those did worse (9.7% outliers); keep it plain")
    if title and not names_someone(title, names):
        out.append("the title names nobody: name the streamer" + (f" ({', '.join(names)})" if names else ""))
    if len(str((spec.get("thumbnail") or {}).get("text") or "").split()) > 3:
        out.append("thumbnail text over 3 words: the outliers use 0-3")
    return out


def _check_compilation(spec, clips, flash, fails, notes, known=None, words_for=None):
    title = str(spec.get("title") or "").strip()
    names = spec_names(spec)
    if title:
        if not COMP_WORDS.search(title):
            fails.append("a compilation title says what it is: moments, best of, funniest, clips, compilation or "
                         "highlights (\"Kai Cenat Funniest Moments (Compilation)\")")
        if not names_someone(title, names):
            fails.append("the title names nobody: name the streamer (one or two names)")
        if len(title) > COMP_TITLE_MAX:
            fails.append(f"title is {len(title)} chars: keep a compilation title {COMP_TITLE_MAX} or fewer (aim 40)")
        if "|" in title or "#" in title:
            fails.append("no pipe or hashtag in a compilation title (9.7% outliers with them)")
        if LENGTH_PROMISE.search(title):
            fails.append("no length promise (\"for 10 minutes\"): it gave no lift, and the compilation wording is the "
                         "signal")
    notes.extend(n for n in shared_notes(spec, names) if "pipe" not in n and "names nobody" not in n)
    if flash:
        fails.append("a compilation has no flash-forward: open mid-moment on the first clip")
    if spec.get("counter"):
        fails.append("a compilation has no counter: each moment stands alone")
    if len(clips) < COMP_MIN_CLIPS:
        fails.append(f"{len(clips)} clips: a compilation needs at least {COMP_MIN_CLIPS} moments")
    niche = spec.get("niche")
    if niche not in NICHES:
        notes.append("set `niche` (irl, gaming or rp): IRL / just-chatting compilations did best (29.1% outliers)")
    elif NICHES[niche]:
        notes.append(NICHES[niche])
    for i, c in enumerate(clips, 1):
        try:
            jd = config.job_dir(c["job"])
        except (SystemExit, KeyError, TypeError):
            jd = None
        box = c.get("face") or spec.get("face") or (face_box(c, spec, known) if known is not None and jd else None)
        if not box and niche != "irl":
            fails.append(f"clip {i}: no face: set `face` (the facecam box from `clipper frame`), or \"full\" when "
                         "the streamer fills the frame (IRL)")
    if words_for is not None and clips:
        c = clips[0]
        try:
            words = words_for(c["job"])
        except SystemExit:
            words = None
        if words is not None and not any(float(c["start"]) <= w["s"] < float(c["start"]) + 2 for w in words):
            notes.append("clip 1 opens on silence: start mid-moment, someone talking within 2 s (no intro)")
    try:
        total = sum(_span(c) for c in clips)
    except (KeyError, TypeError, ValueError):
        return
    if clips and not COMP_S[0] <= total <= COMP_S[1]:
        fails.append(f"{total / 60:.1f} min total: keep a compilation {COMP_S[0] // 60}-{COMP_S[1] // 60} min (aim 8-12; "
                     "3-6 min is the dead zone at 8.2% outliers)")
    elif clips and not COMP_AIM_S[0] <= total <= COMP_AIM_S[1]:
        notes.append(f"{total / 60:.1f} min total: aim for 8-12 min (IRL 9-12 min did best, 20.2%)")


def coverage_fails(spec):
    """Fails for clip, flash-forward and thumbnail times whose job's source is deleted and no bank clip holds."""
    th = spec.get("thumbnail") or {}
    items = [(f"clip {i}", c, None) for i, c in enumerate(spec.get("clips") or [], 1)]
    items += [(f"flash-forward {i}", f, None) for i, f in enumerate(spec.get("flash_forward") or [], 1)]
    if th.get("job") and th.get("t") is not None:
        items.append(("thumbnail", th, float(th["t"])))
    out = []
    for label, it, t in items:
        try:
            jd = config.job_dir(it["job"])
            s, e = (t, t) if t is not None else (float(it["start"]), float(it["end"]))
        except (SystemExit, KeyError, TypeError, ValueError):
            continue
        if (jd / "source.mp4").exists() or longbank.covering(jd.name, s, e):
            continue
        out.append(f"{label} ({jd.name} {s:g}s): {coverage_problem(jd.name, s, e)}")
    return out


def check_long(spec, words_for=None, known=None):
    """{'fails': [...], 'notes': [...]} for a long-form spec (see /clip-long). `kind`: "supercut" (default), "mid"
    (a 30s-3 min "what happens" video), "story" (4-10 min, narrated) or "compilation" (8-12 min of a streamer's
    funniest moments). `words_for(job)` -> transcript words, for the story check that every clip has someone
    talking; `known` = hooks.known_facecams, for the compilation face check."""
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
    lo, hi = {"supercut": (CLIP_MIN_S, CLIP_MAX_S), "mid": MID_CLIP_S, "story": STORY_CLIP_S,
              "compilation": COMP_CLIP_S}[kind]
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
    elif kind == "compilation":
        _check_compilation(spec, clips, flash, fails, notes, known, words_for)
    else:
        _check_story(spec, clips, flash, fails, notes, words_for)
    th = spec.get("thumbnail") or {}
    if not (th.get("job") and th.get("t") is not None):
        fails.append("needs a thumbnail: {\"job\", \"t\" (a frame where the face reacts hardest), \"text\"}")
    elif len(str(th.get("text") or "").split()) > 3 and kind != "compilation":
        notes.append("thumbnail text over 3 words: the outliers use 0-3")
    if th.get("style", "ai") not in THUMB_STYLES:
        fails.append(f"thumbnail.style must be one of {', '.join(THUMB_STYLES)}")
    fails.extend(coverage_fails(spec))
    return {k: v for k, v in (("fails", fails), ("notes", notes)) if v}


THUMB_STYLES = ("ai", "raw", "face")


def face_box(item, spec, known):
    """The facecam box (fractions) for a clip: its own, the spec's, or the one its channel used before. "full" (the
    streamer fills the frame, IRL) means no box."""
    for f in (item.get("face"), spec.get("face")):
        if f:
            return None if f == "full" else f
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


def source_for(item, start=None, end=None):
    """(video file, shift) holding [start, end] (default: the item's) of item["job"]; file second = source second -
    shift. The job's source.mp4 while it's on disk, else a clip bank cut that covers the span."""
    jd = config.job_dir(item["job"])
    s = float(item["start"] if start is None else start)
    e = float(item["end"] if end is None else end)
    src = jd / "source.mp4"
    if src.exists():
        return src, 0.0
    hit = longbank.covering(jd.name, s, e)
    if hit:
        return hit[0] / "clip.mp4", float(hit[1]["from"])
    raise SystemExit(f"[long] {jd.name} {s:g}-{e:g}s: {coverage_problem(jd.name, s, e)}")


def coverage_problem(job_name, s, e):
    if longbank.deleted_covering(job_name, s, e):
        return "this moment was already used in a posted long video and deleted"
    return "its source was deleted and no clip bank cut covers it: tag it with `clipper bank tag` while the source is on disk"


def encode_part(item, face, counter_text, out, tmp, narration=()):
    src, shift = source_for(item)
    s, d = float(item["start"]) - shift, _span(item)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{s:.3f}", "-t", f"{d:.3f}", "-i", str(src)]
    if counter_text:
        png = tmp / f"{out.stem}_counter.png"
        counter_png(counter_text, png)
        cmd += ["-loop", "1", "-framerate", "30", "-t", f"{d:.3f}", "-i", str(png)]
    for wav, _, _ in narration:
        cmd += ["-i", str(wav)]
    graph = clip_filter(render.source_size(src), face, bool(counter_text))
    if narration:
        graph += ";" + narration_audio(narration, 2 if counter_text else 1)
    cmd += ["-filter_complex", graph,
            "-map", "[v]", "-map", "[a]" if narration else "0:a:0", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-t", f"{d:.3f}", str(out)]
    subprocess.run(cmd, check=True)


def encode_still(item, at, face, wav, dur, out, tmp):
    """`dur` seconds on the frame at source second `at`, with the narration `wav` as the only sound."""
    src, shift = source_for(item)
    png = tmp / f"{out.stem}.png"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(0.0, at - shift):.3f}", "-i", str(src),
                    "-frames:v", "1", str(png)], check=True)
    graph = (clip_filter(render.source_size(src), face)
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


def grab_frame(item, t):
    """The full source frame at source second `t` of item["job"] (from the source, else a bank clip), as RGB."""
    src, shift = source_for(item, t, t)
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "frame.png"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(0.0, float(t) - shift):.3f}", "-i",
                        str(src), "-frames:v", "1", str(png)], check=True)
        return Image.open(png).convert("RGB")


def thumbnail(spec, out, known):
    """thumbnail.style "face": the streamer's face huge on the left (white outline) over the darkened scene, 0-3
    big words right."""
    th = spec["thumbnail"]
    frame = grab_frame(th, th["t"])
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


# What the study's thumbnails say (research/long-form-streamers-2026-11.md, Apple Vision on 3,461, 288 coded):
# leans, not causes. One list feeds the Codex prompt and is what check_thumbnail measures.
THUMB_PRINCIPLES = {
    "do": [
        "a recognisable face in a real place, not a game frame (game frames 5.4% outliers vs 19.2% real world); "
        "it is the streamer named in the title",
        "the face sits in the scene and does not fill the frame: the biggest face 3-8% of the frame (18.2% outliers; "
        "over 8%: 12.6%)",
        "0-3 words, never a repeat of the title (7+ words: 11.8%)",
        "show the person and the thing they react to",
        "look like a raw stream frame, lightly cleaned up, not a polished composite",
    ],
    "dont": [
        "arrows or circles (8.7%)",
        "cut-out designs (9.3% vs raw frames 12.2%)",
        "the face-against-one-opposing-thing layout (9.4%)",
        "giant face close-ups",
        "borders, logos, watermarks, stream overlays (chat boxes, follower counters)",
    ],
}
THUMB_GEN = (1536, 864)                 # a 16:9 size gpt-image-2 makes; downscaled to TW x TH
THUMB_MAX_BYTES = 2_000_000             # YouTube's thumbnail limit
THUMB_FACE = (0.02, 0.10)               # the check's band around the 3-8% aim
THUMB_MAX_WORDS = 3
THUMB_BADGE = (0.12, 0.08)              # bottom-right: the duration badge covers about this much (w, h)
THUMB_EDGE = 0.04
THUMB_FEED = (168, 94)                  # how big a thumbnail shows in the feed
THUMB_WORD_H = 0.08                     # a text box at least this tall (of the frame) counts as thumbnail words
THUMB_MAIN_FACE = 0.5                   # faces under half the biggest one's area (posters, paintings) aren't counted
THUMB_REFS = 3                          # images Codex gets: the scene, face references, a style exemplar
CODEX_TIMEOUT_S = 120
THUMB_FILES = ("thumbnail.jpg", "thumbnail_source.jpg", "thumbnail_ai.png", "thumbnail_try.jpg",
               "thumbnail_ref*.jpg", "thumbnail_style.jpg")
VISION_SRC = Path(__file__).with_name("apple_vision.swift")
EXEMPLARS = config.ROOT / "viral" / "longform"


def _save_frame(img, path):
    _cover(img, TW, TH).save(path, quality=92)
    return path


def thumbnail_source(spec, folder):
    """thumbnail_source.jpg: the spec's frame, a plain 1280x720 cover-crop. Codex's scene and the raw fallback."""
    th = spec["thumbnail"]
    return _save_frame(grab_frame(th, th["t"]), Path(folder) / "thumbnail_source.jpg")


def thumbnail_refs(spec, folder):
    """Face references (`thumbnail.refs`: [{job, t}], from the job's source only) and an optional style exemplar
    (`thumbnail.exemplar`: a file in viral/longform/): ([paths], [notes]). At most THUMB_REFS - 1 images."""
    th, out, notes = spec.get("thumbnail") or {}, [], []
    for i, r in enumerate(th.get("refs") or [], 1):
        try:
            jd = config.job_dir(r["job"])
        except (SystemExit, KeyError, TypeError):
            notes.append(f"face reference {i} skipped: no job {r.get('job') if isinstance(r, dict) else r}")
            continue
        if not (jd / "source.mp4").exists():
            notes.append(f"face reference {i} skipped: {jd.name}'s source was deleted")
            continue
        out.append(_save_frame(grab_frame(r, r["t"]), Path(folder) / f"thumbnail_ref{i}.jpg"))
    if th.get("exemplar"):
        ex = EXEMPLARS / Path(str(th["exemplar"])).name
        if ex.is_file():
            with Image.open(ex) as im:
                out.append(_save_frame(im.convert("RGB"), Path(folder) / "thumbnail_style.jpg"))
        else:
            notes.append(f"style exemplar skipped: {ex} is missing (viral/ is deleted after 30 days)")
    if len(out) > THUMB_REFS - 1:
        notes.append(f"only {THUMB_REFS - 1} references are sent; dropped {', '.join(p.name for p in out[THUMB_REFS - 1:])}")
        out = out[:THUMB_REFS - 1]
    return out, notes


def thumb_words(text):
    return re.findall(r"[a-z0-9$%']+", str(text or "").lower())


def build_thumbnail_prompt(text="", names=(), refs=(), retry=None):
    """The $imagegen prompt: the principles, the words, the size and safe zones, and what each image is for."""
    words = " ".join(str(text or "").split()[:THUMB_MAX_WORDS]).upper()
    lines = ["$imagegen Make one YouTube long-form thumbnail from the attached images.",
             f"Size: landscape 16:9, {THUMB_GEN[0]}x{THUMB_GEN[1]} pixels; it is shown at {TW}x{TH} and as small as "
             f"{THUMB_FEED[0]}x{THUMB_FEED[1]} in the feed, so it must read at that size. Never vertical.",
             "Image 1 is the scene: keep its place, people, pose and expression."]
    for i, r in enumerate(refs, 2):
        if Path(r).name.startswith("thumbnail_style"):
            lines.append(f"Image {i} is only a layout and lighting example from another channel: never copy its "
                         "people, text or content.")
        else:
            lines.append(f"Image {i} is only a reference for this person's face: match the likeness, never swap or "
                         "invent a face.")
    if names:
        lines.append(f"The person is {' and '.join(names[:2])}, the streamer named in the video title.")
    lines += ["Keep every person exactly as in the references; do not add, remove or restyle people; do not invent "
              "logos or text. Improve only sharpness, brightness, colour and framing so the face sits at 3-8% of the "
              "frame in a real place.",
              "Do: " + "; ".join(THUMB_PRINCIPLES["do"]) + ".",
              "Don't: " + "; ".join(THUMB_PRINCIPLES["dont"]) + ". Remove stream overlays (chat, counters, alerts).",
              (f'Words: exactly "{words}" ({len(words.split())} word{"s" if len(words.split()) > 1 else ""}), big, '
               "bold and readable at feed size; no other text." if words else "Words: none. No text at all."),
              f"Safe zones: keep the face and any words at least {THUMB_EDGE:.0%} from every edge and out of the "
              f"bottom-right corner ({THUMB_BADGE[0]:.0%} wide x {THUMB_BADGE[1]:.0%} tall), where YouTube's duration "
              "badge sits.",
              "Save the final image as thumbnail_ai.png in the current working directory, then reply with only its "
              "absolute path."]
    if retry:
        lines.append(f"The previous attempt failed this check, fix it: {retry}.")
    return "\n".join(lines)


def codex_home():
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def generate_thumbnail(images, prompt, folder, cfg, run=subprocess.run):
    """One `codex exec` $imagegen (gpt-image-2 on the ChatGPT login) call. Codex keeps the original under
    $CODEX_HOME/generated_images/<session>/; it's moved (not copied) to <folder>/thumbnail_ai.png and the session
    folder removed. Returns (png or None, error or None, leftover session dir or None)."""
    from . import schedule
    binary = schedule.find_agent("codex")
    if not binary:
        return None, "codex CLI not found", None
    folder = Path(folder)
    dest = folder / "thumbnail_ai.png"
    dest.unlink(missing_ok=True)
    model = cfg.get("thumbnail_codex_model")
    cmd = [binary, "exec", "--skip-git-repo-check", *(["-m", str(model)] if model else []), "-C", str(folder),
           *schedule.CODEX_ARGS]
    for im in list(images)[:THUMB_REFS]:
        cmd += ["-i", str(im)]
    cmd += ["--", prompt]  # -i takes several values: without -- it swallows the prompt
    try:
        res = run(cmd, capture_output=True, text=True, timeout=CODEX_TIMEOUT_S, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return None, f"codex timed out after {CODEX_TIMEOUT_S}s", None
    except OSError as e:
        return None, f"codex failed to start: {e}", None
    log = f"{res.stdout or ''}\n{res.stderr or ''}"
    sid = re.search(r"session id:\s*([0-9A-Za-z-]{8,})", log)
    leftover = None
    if sid:
        gen = codex_home() / "generated_images"
        sess = gen / sid.group(1)
        if sess.parent == gen and sess.is_dir():
            pngs = sorted(sess.glob("*.png"), key=lambda f: f.stat().st_mtime)
            if pngs:
                shutil.move(str(pngs[-1]), str(dest))
            for f in pngs[:-1]:
                f.unlink(missing_ok=True)
            try:
                sess.rmdir()
            except OSError:
                leftover = str(sess)  # something else is in it: cleanup removes it later
    if not dest.exists():
        tail = " ".join(log.strip().splitlines()[-3:])[-300:]
        return None, f"codex made no image (exit {res.returncode}): {tail}", leftover
    return dest, None, leftover


def finalize_thumbnail(png, out):
    """Cover-resize to exactly TW x TH and save as JPG, lowering quality until it's under THUMB_MAX_BYTES."""
    with Image.open(png) as im:
        img = _cover(im.convert("RGB"), TW, TH)
    for q in (92, 85, 78, 70, 60, 50):
        img.save(out, quality=q)
        if Path(out).stat().st_size <= THUMB_MAX_BYTES:
            break
    return Path(out)


def vision_measure(paths):
    """Apple Vision faces and text per image, or None where it can't run (not a Mac, no swiftc)."""
    from . import transcribe
    try:
        exe = transcribe.apple_binary(VISION_SRC, "apple-vision")
        res = subprocess.run([str(exe), *map(str, paths)], capture_output=True, text=True, timeout=120)
        return json.loads(res.stdout) if res.returncode == 0 and res.stdout else None
    except (SystemExit, OSError, ValueError, subprocess.TimeoutExpired):
        return None


def _read_words(texts):
    return [w for t in texts if float(t.get("h", 0)) >= THUMB_WORD_H for w in thumb_words(t.get("s"))]


def main_faces(faces):
    """The faces that are people in the shot: at least THUMB_MAIN_FACE of the biggest one's area. A painting or
    poster the cleanup sharpens into a detectable face shouldn't count as a person added."""
    big = max((f["area"] for f in faces), default=0.0)
    return [f for f in faces if f["area"] >= big * THUMB_MAIN_FACE]


def _inter(a, b):
    w = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
    h = min(a["top"] + a["h"], b["top"] + b["h"]) - max(a["top"], b["top"])
    return max(0.0, w) * max(0.0, h)


def _scene_text(t, scene):
    """Big text the source frame already had in that place (sharing at least half the smaller box): a shirt print
    or a sign. Small source text (chat lines) never hides the spec's words."""
    return any(_inter(t, b) >= min(t["w"] * t["h"], b["w"] * b["h"]) / 2 > 0 for b in scene
               if float(b.get("h", 0)) >= THUMB_WORD_H / 2)


def _in_badge(b):
    return b["x"] + b["w"] > 1 - THUMB_BADGE[0] and b["top"] + b["h"] > 1 - THUMB_BADGE[1]


def _near_edge(b):
    return b["x"] < THUMB_EDGE or b["top"] < THUMB_EDGE or b["x"] + b["w"] > 1 - THUMB_EDGE or b["top"] + b["h"] > 1 - THUMB_EDGE


def check_thumbnail(path, text="", source_faces=None, measure=None, source_text=()):
    """(ok, [reasons], measured) for a finished thumbnail: exactly TW x TH, <= 2 MB, the source frame's count of
    main faces (main_faces), biggest face 2-10%, the spec's words and no others (big text where the source frame
    already has text, `source_text`, is the scene: a shirt, a sign), main faces and words clear of the bottom-right
    badge and the edges, and face and words still found at feed size (168x94, scaled back up for Vision)."""
    measure = measure or vision_measure
    path = Path(path)
    reasons = []
    with Image.open(path) as im:
        dims = im.size
        small = im.convert("RGB").resize(THUMB_FEED, Image.LANCZOS)
    size = path.stat().st_size
    if dims != (TW, TH):
        reasons.append(f"{dims[0]}x{dims[1]}, not {TW}x{TH}")
    if size > THUMB_MAX_BYTES:
        reasons.append(f"{size / 1e6:.1f} MB, over 2 MB")
    with tempfile.TemporaryDirectory() as tmp:
        feed = Path(tmp) / "feed.png"
        small.resize((THUMB_FEED[0] * 4, THUMB_FEED[1] * 4), Image.BICUBIC).save(feed)
        frames = measure([path, feed])
    if not frames or len(frames) < 2:
        return False, reasons + ["Apple Vision couldn't run, so faces and words can't be checked"], {}
    full, tiny = frames[0], frames[1]
    faces = main_faces(full.get("faces") or [])
    big = max((f["area"] for f in faces), default=0.0)
    scene = [t for t in source_text or () if "x" in t]
    texts = [t for t in full.get("text") or [] if not ("x" in t and _scene_text(t, scene))]
    words, want = _read_words(texts), thumb_words(text)
    if len(want) > THUMB_MAX_WORDS:
        reasons.append(f"{len(want)} words asked for: keep it to {THUMB_MAX_WORDS}")
    if source_faces is not None and len(faces) != source_faces:
        reasons.append(f"{len(faces)} faces, the source frame has {source_faces} (people added or removed)")
    if not faces:
        reasons.append("no face found")
    elif not THUMB_FACE[0] <= big <= THUMB_FACE[1]:
        reasons.append(f"biggest face is {big:.1%} of the frame (keep it {THUMB_FACE[0]:.0%}-{THUMB_FACE[1]:.0%})")
    if sorted(words) != sorted(want):
        reasons.append(f"words on it: {' '.join(words) or 'none'}; the spec's: {' '.join(want) or 'none'}")
    boxes = [("a face", f) for f in faces if "x" in f] + [("words", t) for t in texts
                                                         if "x" in t and float(t.get("h", 0)) >= THUMB_WORD_H]
    for what, b in boxes:
        if _in_badge(b):
            reasons.append(f"{what} in the bottom-right corner, under the duration badge")
            break
    for what, b in boxes:
        if _near_edge(b):
            reasons.append(f"{what} within {THUMB_EDGE:.0%} of the edge")
            break
    if faces and not tiny.get("faces"):
        reasons.append(f"the face is lost at feed size ({THUMB_FEED[0]}x{THUMB_FEED[1]})")
    tiny_words = [w for t in tiny.get("text") or [] for w in thumb_words(t.get("s"))]
    if want and not set(want) & set(tiny_words):
        reasons.append(f"the words can't be read at feed size ({THUMB_FEED[0]}x{THUMB_FEED[1]})")
    measured = {"size": f"{dims[0]}x{dims[1]}", "bytes": size, "faces": len(faces), "face_area": round(big, 4),
                "words": words, "feed_faces": len(tiny.get("faces") or []), "feed_words": tiny_words}
    return not reasons, reasons, measured


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_thumbnail(spec, folder, known, cfg, ai=True, run=subprocess.run, measure=None):
    """thumbnail.jpg for a long video, by `thumbnail.style`: "ai" (Codex $imagegen from the source frame and face
    references, checked; one retry; else the raw frame), "raw" (the source frame) or "face" (the old enlarged-face
    look). Never raises for the AI step: the reason lands in the returned record (for long.json)."""
    th = spec["thumbnail"]
    folder = Path(folder)
    out = folder / "thumbnail.jpg"
    style = th.get("style") or "ai"
    text = str(th.get("text") or "").strip()
    if style == "face":
        thumbnail(spec, out, known)
        return {"style": "face", "path": str(out), "sha256": _sha256(out)}
    src = thumbnail_source(spec, folder)
    info = {"style": "raw", "source": src.name}
    if style == "ai" and not ai:
        info["reason"] = "AI thumbnails are off (--no-ai-thumb)"
    elif style == "ai":
        measure = measure or vision_measure
        refs, notes = thumbnail_refs(spec, folder)
        names = spec_names(spec)
        src_m = measure([src])
        src_faces = len(main_faces(src_m[0].get("faces") or [])) if src_m else None
        src_text = (src_m[0].get("text") or []) if src_m else []
        info.update(refs=[p.name for p in refs], notes=notes, source_faces=src_faces)
        retry = None
        for attempt in (1, 2):
            prompt = build_thumbnail_prompt(text, names, refs, retry)
            print(f"[long] thumbnail: Codex $imagegen, attempt {attempt}", flush=True)
            png, err, leftover = generate_thumbnail([src, *refs], prompt, folder, cfg, run)
            if leftover:
                info["codex_session_dir"] = leftover
            if not png:
                info["reason"] = err
                break
            trial = finalize_thumbnail(png, folder / "thumbnail_try.jpg")
            ok, reasons, measured = check_thumbnail(trial, text, src_faces, measure, src_text)
            info.update(attempts=attempt, measured=measured, prompt=prompt)
            if ok:
                trial.replace(out)
                info.update(style="ai", reason=None)
                break
            trial.unlink(missing_ok=True)
            retry = "; ".join(reasons)
            info["reason"] = f"failed the check: {retry}"
    if info["style"] == "raw":
        shutil.copyfile(src, out)
        if text:
            info["note"] = f"the raw frame has no words; add \"{text}\" by hand if you want them"
    info.update(path=str(out), sha256=_sha256(out))
    return info


def next_long_number(out_dir):
    nums = [int(m.group(1)) for p in out_dir.glob("long *") if (m := re.fullmatch(r"long (\d+)", p.name))]
    return max(nums, default=0) + 1


def reused_footage(spec, exports=None):
    """Fails for a mid or story video whose clips an earlier export of the same kind already used (a Short of the
    same moment is fine). Supercuts and compilations are exempt: they gather moments that were already posted."""
    kind = kind_of(spec)
    clips = spec.get("clips") or []
    if kind in ("supercut", "compilation") or not clips:
        return []
    first = config.job_dir(clips[0]["job"])
    fp = render.footage({"segments": clips}, first, render.load_meta(first))
    hits = render.footage_reuse(fp, exports, shape=kind)
    return hits + [f"pick other moments: this footage already went out as a {kind} video"] if hits else []


def spec_sha256(spec):
    return hashlib.sha256(json.dumps(spec, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def render_long(spec, cfg, out_dir=None, check=True, words_for=None, ai_thumb=False, run=subprocess.run, measure=None):
    """Render a long-form spec to exports/<profile>/<date>/long N/: the MP4, thumbnail.jpg (make_thumbnail;
    `ai_thumb` lets a "ai" style call Codex, the CLI turns it on), long.json (title, description with every source
    credited, footage, bank clips used) and a markdown sheet. Never `video N`: the autopilot only queues
    `video N/upload.json`, so a long video can't be posted as a Short. Bank clips it used are marked used."""
    known = hooks.known_facecams(config.JOBS)
    if check:
        bad = check_long(spec, words_for, known).get("fails", []) + reused_footage(spec)
        if bad:
            raise SystemExit("[long] fix these first:\n" + "\n".join(bad))
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
    th_info = make_thumbnail(spec, folder, known, cfg, ai=ai_thumb, run=run, measure=measure)
    thumb = Path(th_info["path"])
    th = spec.get("thumbnail") or {}
    bank_ids = longbank.ids_for([*clips, *flash, {"job": th["job"], "start": th["t"], "end": float(th["t"]) + 0.01}])
    first = config.job_dir(clips[0]["job"])
    pseudo = {"segments": [{**c, "job": c["job"]} for c in clips]}
    meta = render.load_meta(first)
    creds = render.credits(pseudo, first, meta)
    desc = render.post_description(spec.get("description") or spec["title"], creds, spec.get("hashtags") or [])
    info = render.probe(mp4)
    manifest = {"kind": "long" if kind == "supercut" else kind, "niche": spec.get("niche"), "title": spec["title"],
                "premise_type": spec.get("premise_type"), "question": spec.get("question"), "description": desc, "hashtags": spec.get("hashtags") or [],
                "file": str(mp4), "thumbnail": str(thumb), "thumbnail_text": th.get("text"),
                "thumbnail_style": th_info["style"], "thumbnail_reason": th_info.get("reason"),
                "thumbnail_sha256": th_info["sha256"],
                **{f"thumbnail_{k}": th_info[k] for k in ("measured", "source_faces", "refs", "notes", "note", "attempts",
                                                          "prompt") if th_info.get(k) is not None},
                **({"codex_session_dir": th_info["codex_session_dir"]} if th_info.get("codex_session_dir") else {}),
                "bank_ids": bank_ids, "spec_sha256": spec_sha256(spec), "notes": shared_notes(spec),
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
        f"thumbnail text: {manifest['thumbnail_text'] or '(none)'} · thumbnail: {th_info['style']}"
        + (f" ({th_info['reason']})" if th_info.get("reason") else "")
        + f"\n\n## Description\n\n{desc}\n", encoding="utf-8")
    longbank.mark_used(bank_ids, folder)
    return {"folder": str(folder), "file": str(mp4), "thumbnail": str(thumb), "thumbnail_style": th_info["style"],
            "thumbnail_reason": th_info.get("reason"), "bank_ids": bank_ids, "duration": info["duration"],
            "size": f"{info['width']}x{info['height']}"}
