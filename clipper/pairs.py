"""Same-moment teardown: our Short next to a clip channel's Short of the same moment (confirmed by transcript)."""
import json
import random
import re
import subprocess
import time
from datetime import datetime, timedelta

from . import viral as v

STREAMERS = {"xqc": re.compile(r"\bx\s?qc\b", re.I), "kai": re.compile(r"\bkai\b", re.I)}
SHEET_TIMES = (0.3, 1.0, 2.0, 3.0)
STOP = set("the a an and or but to of in on at for is are was were be it its this that he she they you i we me my "
           "his her their our your with from as by not no so just do did does get got can cant wont dont im".split())


def pairs_path():
    return v.DATA / "pairs.json"


def streamer_of(title):
    return next((k for k, p in STREAMERS.items() if p.search(title or "")), None)


def title_words(title):
    t = re.sub(r"#\S+|\|.*$", "", (title or "").lower())
    return {w for w in re.findall(r"[a-z0-9$]+", t) if w not in STOP and not any(p.match(w) for p in STREAMERS.values())
            and w not in {"cenat", "gta", "rp", "nopixel", "6", "5", "shorts"}}


def candidates(own, others, window_days=3, max_s=60):
    """{our id: [their ids]}: their Shorts naming the same streamer, published within +-window of our clip's stream
    date (`own` items carry "stream_date" as YYYY-MM-DD), most title words in common first."""
    out = {}
    for o in own:
        s, day = o.get("streamer") or streamer_of(o["title"]), datetime.strptime(o["stream_date"], "%Y-%m-%d")
        if not s:
            continue
        lo, hi = day - timedelta(days=window_days), day + timedelta(days=window_days + 1)
        mine = title_words(o["title"])
        near = [x for x in others if x.get("published") and streamer_of(x["title"]) == s
                and (x.get("duration") or 0) <= max_s
                and lo <= datetime.strptime(x["published"][:10], "%Y-%m-%d") < hi]
        near.sort(key=lambda x: (-len(mine & title_words(x["title"])), x["id"]))
        out[o["id"]] = [x["id"] for x in near]
    return out


def tokens(words):
    return [(re.sub(r"[^a-z0-9']", "", w["w"].lower()), w["s"]) for w in words if re.sub(r"[^a-z0-9']", "", w["w"].lower())]


def match(a_words, b_words, n=3):
    """Longest common run of spoken words between two transcripts (and where it sits in each), plus the share of a's
    word n-grams that also occur in b."""
    a, b = tokens(a_words), tokens(b_words)
    best, ai, bi = 0, 0, 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1][0] == b[j - 1][0]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best, ai, bi = cur[j], i - cur[j], j - cur[j]
        prev = cur
    grams = lambda t: {tuple(x[0] for x in t[k:k + n]) for k in range(len(t) - n + 1)}
    ga, gb = grams(a), grams(b)
    share = len(ga & gb) / len(ga) if ga else 0.0
    if not best:
        return {"run": 0, "share": share}
    return {"run": best, "share": round(share, 3), "a_at": a[ai][1], "b_at": b[bi][1],
            "shared": " ".join(x[0] for x in a[ai:ai + best]),
            # same spoken word: a later timestamp in b means b started that many seconds earlier in the source
            "b_starts_earlier_s": round(b[bi][1] - a[ai][1], 2)}


FILLER = STOP | set("oh my god gosh bro yo yeah what wait no yes okay ok like man dude hey huh uh um chat bruh "
                    "nah lets go stop look".split())


def same_moment(m, min_content=4, min_share=0.2):
    """Same moment = a shared spoken run with at least `min_content` distinct non-filler words ("oh my gosh oh my
    gosh" is not a moment), or a run of 4+ words when a fifth of the n-grams are shared."""
    content = {w for w in m.get("shared", "").split() if w not in FILLER}
    return (m["run"] >= 5 and len(content) >= min_content) or (m["run"] >= 4 and m["share"] >= min_share
                                                               and len(content) >= 2)


def words_for(vid, mp4, cfg):
    """Apple's on-device transcript of a Short, cached next to the media (purged with it)."""
    from . import transcribe
    cache = v.MEDIA / f"{vid}.words.json"
    if cache.exists():
        return json.loads(cache.read_text())
    wav = mp4.with_suffix(".wav")
    if not wav.exists():
        transcribe.extract_audio(mp4, wav)
    words, _, _ = transcribe.transcribe(wav, str(mp4.with_suffix("")), {**(cfg or {}), "asr": "apple"})
    cache.write_text(json.dumps(words))
    return words


def first_line(words, max_gap=0.7, max_words=14):
    out = []
    for w in words:
        if out and (w["s"] - out[-1]["e"] > max_gap or len(out) >= max_words):
            break
        out.append(w)
    return " ".join(w["w"] for w in out)


def last_line(words, max_gap=0.7, max_words=14):
    out = []
    for w in reversed(words):
        if out and (out[-1]["s"] - w["e"] > max_gap or len(out) >= max_words):
            break
        out.append(w)
    return " ".join(w["w"] for w in reversed(out))


def features(vid, mp4, words, exe):
    """What a viewer sees and hears: frames at 0.3/1/2/3 s and the last frame (OCR text, faces), length, cuts,
    first and last spoken line, and whether the on-screen text follows the speech (burned-in captions)."""
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(mp4)], capture_output=True, text=True, check=True).stdout.strip())
    scene = subprocess.run(["ffmpeg", "-nostats", "-i", str(mp4), "-vf",
                            f"select='gt(scene,{v.SCENE_CUT})',showinfo", "-an", "-f", "null", "-"],
                           capture_output=True, text=True)
    times = [t for t in SHEET_TIMES if t < dur] + [max(dur - 0.15, 0)]
    paths = []
    for t in times:
        p = v.MEDIA / f"{vid}.p{int(round(t * 10)):03d}.jpg"
        if not p.exists():
            subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", str(mp4),
                            "-frames:v", "1", "-vf", "scale=-2:960", str(p)], check=False)
        paths.append(p)
    res = subprocess.run([str(exe), *map(str, paths)], capture_output=True, text=True)
    frames = json.loads(res.stdout) if res.returncode == 0 and res.stdout else [{"text": [], "faces": []}] * len(paths)
    spoken = {re.sub(r"[^a-z0-9]", "", w["w"].lower()) for w in words} - {""}
    shown = [{"at": round(t, 2), "text": " / ".join(b["s"] for b in f["text"]),
              "face": round(max((x["area"] for x in f["faces"]), default=0.0), 4),
              "face_y": round(max(f["faces"], key=lambda x: x["area"])["y"], 2) if f["faces"] else None}
             for t, f in zip(times, frames)]
    caption_hits = sum(1 for f in frames[1:-1] for b in f["text"]
                       if {re.sub(r"[^a-z0-9]", "", x.lower()) for x in b["s"].split()} & spoken)
    return {"id": vid, "length_s": round(dur, 2), "cuts": v.count_cuts(scene.stderr), "frames": shown,
            "hook_text": shown[0]["text"] if shown else "", "face_max": max((f["face"] for f in shown), default=0.0),
            "captions": caption_hits >= 2, "first_line": first_line(words), "last_line": last_line(words),
            "words": len(words), "frame_paths": [str(p) for p in paths]}


def contact_sheet(rows, out, height=480):
    """One labelled row per Short: frames at 0.3/1/2/3 s and the last frame."""
    from PIL import Image, ImageDraw
    tiles = []
    for label, f in rows:
        imgs = []
        for p, fr in zip(f["frame_paths"], f["frames"]):
            im = Image.open(p).convert("RGB")
            im = im.resize((int(im.width * height / im.height), height))
            ImageDraw.Draw(im).rectangle([0, 0, im.width, 26], fill=(0, 0, 0))
            ImageDraw.Draw(im).text((6, 6), f"{label} @ {fr['at']:.1f}s", fill=(255, 255, 255))
            imgs.append(im)
        tiles.append(imgs)
    w = max(sum(i.width for i in r) for r in tiles)
    sheet = Image.new("RGB", (w, height * len(tiles)), (20, 20, 20))
    for y, r in enumerate(tiles):
        x = 0
        for im in r:
            sheet.paste(im, (x, y * height))
            x += im.width
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=85)
    return out


def find(own, others, cfg, want=15, max_downloads=150, pause=6.0):
    """Download candidates one at a time (pausing, stopping at the first bot check) until `want` of our uploads have
    a confirmed same-moment Short. Saves viral/pairs.json; returns it."""
    from . import transcribe
    exe = transcribe.apple_binary(v.VISION_SRC, "apple-vision")
    saved = v._load(pairs_path(), {})
    cands = candidates(own, others)
    tried, blocked = 0, False
    for o in own:
        if len([k for k, p in saved.items() if p.get("their")]) >= want or blocked:
            break
        if o["id"] in saved or not cands.get(o["id"]) or not (v.MEDIA / f"{o['id']}.mp4").exists():
            continue
        ours = words_for(o["id"], v.MEDIA / f"{o['id']}.mp4", cfg)
        best, capped = None, False
        for their in cands[o["id"]]:
            mp4 = v.MEDIA / f"{their}.mp4"
            if not mp4.exists():
                if tried >= max_downloads:
                    capped = True
                    break
                try:
                    tried += 1
                    ok = v.download([their], pause=0)
                except v.BotCheck:
                    print(f"[pairs] YouTube's bot check at {their}: stopped", flush=True)
                    blocked = True
                    break
                time.sleep(pause + random.random() * pause / 2)
                if not ok:
                    continue
            m = match(ours, words_for(their, mp4, cfg))
            if same_moment(m) and (best is None or m["run"] > best[1]["run"]):
                best = (their, m)
        if best:
            their, m = best
            fo = features(o["id"], v.MEDIA / f"{o['id']}.mp4", ours, exe)
            ft = features(their, v.MEDIA / f"{their}.mp4", words_for(their, v.MEDIA / f"{their}.mp4", cfg), exe)
            sheet = contact_sheet([("OURS", fo), ("THEIRS", ft)], v.MEDIA / "pairs" / f"{o['id']}.vs.{their}.jpg")
            saved[o["id"]] = {"their": their, "match": m, "ours_f": fo, "their_f": ft, "sheet": str(sheet),
                              "paired_at": v.now()}
            print(f"[pairs] {o['id']} = {their} (run {m['run']} words)", flush=True)
        elif not blocked and not capped:
            saved[o["id"]] = {"their": None, "checked": len(cands[o["id"]]), "paired_at": v.now()}
        v._save(pairs_path(), saved)
    return saved


# ---------- Gemini CLI: blind A/B (an outlier and an average Short from the same channel) ----------

CATEGORIES = ["premise", "idea", "spoken_hook", "text_hook", "opening_visuals", "layout", "pacing", "ending",
              "people_on_screen", "audio", "other"]
AB_PROMPT = """Watch @A.mp4 and @B.mp4. Both are YouTube Shorts from the same channel. You are NOT told how they
performed. Return ONLY one JSON object, no prose, with keys:
"A" and "B": each {"premise": one line, "idea": one of [turn_between_people, reaction, fail_or_accident, feat,
banter, commentary, prank, music, scare, other], "cold_readable": true/false (a stranger gets it without lore),
"spoken_hook": the first spoken line, "text_hook": on-screen text in the first second ("" if none),
"opening_visuals": what is on screen in the first 2 s, "opens_on": one of [event, setup, reaction, talking, context],
"layout": short description, "face_share": percent of the frame a face takes (0-100), "turn_at_s": seconds when the
turn/payoff happens or null, "ends_on": one of [reaction, payoff, after, mid_sentence], "energy": 1-10};
"more_views": "A" or "B" (your prediction), "confidence": 0-1,
"main_reason": one of [""" + ", ".join(CATEGORIES) + """],
"reasons": list of {"category": one of the same, "why": one sentence}."""


def parse_ab(text):
    """The JSON object in Gemini's reply, held to the A/B schema."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON in reply")
    d = json.loads(m.group(0))
    if d.get("more_views") not in ("A", "B") or not all(isinstance(d.get(k), dict) for k in "AB"):
        raise ValueError(f"bad A/B reply: {sorted(d)}")
    if d.get("main_reason") not in CATEGORIES:
        d["main_reason"] = "other"
    d["reasons"] = [r for r in d.get("reasons") or [] if isinstance(r, dict) and r.get("category") in CATEGORIES]
    return d


def gemini_ab(a_mp4, b_mp4, workdir, model, key, timeout=300):
    """One blind A/B judgement with the Gemini CLI (files copied in under neutral names). Returns parse_ab()."""
    import os
    import shutil
    workdir.mkdir(parents=True, exist_ok=True)
    for src, name in ((a_mp4, "A.mp4"), (b_mp4, "B.mp4")):
        shutil.copyfile(src, workdir / name)
    res = subprocess.run(["gemini", "--skip-trust", "-m", model, "-p", AB_PROMPT], cwd=workdir, capture_output=True,
                         text=True, timeout=timeout, env={**os.environ, "GEMINI_API_KEY": key})
    if res.returncode != 0:
        tail = (res.stdout + res.stderr)[-400:]
        raise RuntimeError(("quota" if "429" in tail or "quota" in tail.lower() else "gemini failed") + ": " + tail)
    return parse_ab(res.stdout)
