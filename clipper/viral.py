"""What our outliers have in common: pull Shorts (ours + the big clip channels), measure each with code, optionally score
it with Gemini, compare outliers (3x their channel's median views) with everything else, then check the rules on
videos whose views are hidden. Raw YouTube data lives in viral/ (git-ignored) and is deleted after 30 days, as the
YouTube API Services policies require; every command purges first."""
import base64
import json
import math
import os
import random
import re
import statistics as st
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import stats as yt
from .config import ROOT

DATA = ROOT / "viral"
MEDIA = DATA / "media"
VIDEOS = DATA / "videos.json"
MEASURES = DATA / "measures.json"
SCORES = DATA / "gemini"
REPORT = DATA / "report.md"
LABELS = DATA / "labels.json"      # blind title labels: {id: {..., "labeled_at"}}
OPENINGS = DATA / "openings.json"  # first-5s features of cached media: {id: {..., "opened_at"}}
TRIGGERS = ["curiosity_gap", "viewer_judge", "play_along", "suspense", "irony", "confession", "status_celebrity",
            "absurd_premise", "none"]
LABEL_FIELDS = ["cold_readable", "turn", "setup_withheld", "streamer_first"]
TITLE_CODE = ["question", "negation", "emoji", "word_count", "length_s"]
TITLE_METRICS = TITLE_CODE + LABEL_FIELDS + [f"trigger_{x}" for x in TRIGGERS]
OPENING_METRICS = ["hook_text", "hook_words", "hook_states_setup", "hook_question", "hook_matches_premise",
                   "hook_title_loop", "face_area", "shows_action"]
HOOK_LABELS = ["hook_states_setup", "hook_matches_premise", "hook_title_loop"]
SLICE_S = 6           # a slice is the first ~6 s of a Short: enough for the 0.3/1.5/3/5 s frames and the 0-5 s speech
CHANNELS = ROOT / "research" / "viral-channels.txt"
KEEP_DAYS = 30
OUTLIER_X = 3.0       # the user's cutoff: views >= 3x the channel's median
SHORT_MAX_S = 180     # Shorts can run up to 3 minutes
SCENE_CUT = 0.3       # ffmpeg scene score above which a frame counts as a cut
CODE_METRICS = ["length_s", "cuts", "first_word_s", "words_per_s", "loudness_lufs"]
GEMINI_FIELDS = ["hook", "tone", "energy", "genuine", "motion"]
GEMINI_MODEL = "gemini-2.5-flash"
INLINE_MAX_BYTES = 18 * 1024 * 1024  # generateContent's inline limit is ~20 MB per request

PROMPTS = {
    "full": ("You are rating a YouTube Short (a vertical clip of a streamer). Watch the whole video with sound. Score each "
             "item from 1 (worst) to 10 (best) and give a one-line reason that points at something in this video:\n"
             "- hook: how strongly the first 3 seconds make a viewer want to keep watching\n"
             "- tone: how well the mood (funny, tense, shocking) comes across and stays consistent\n"
             "- energy: how much energy the streamer and the scene carry\n"
             "- genuine: how real and unscripted the reaction feels\n"
             "- motion: how much on-screen movement there is (camera, action, cuts)\n"
             "Judge only what is in the video. Return JSON with exactly the fields hook, tone, energy, genuine, motion; "
             "each is {\"score\": integer 1-10, \"reason\": one line}."),
    "short1": ("Rate this YouTube Short 1-10 on: hook (first 3 seconds), tone, energy, genuine (feels real), motion "
               "(on-screen movement). One-line reason each. JSON: hook, tone, energy, genuine, motion, each "
               "{score, reason}."),
    "short2": "Score 1-10 with a one-line reason: hook (first 3 s), tone, energy, genuine, motion. JSON only.",
    "short3": ("Watch this Short. For hook (first 3 s), tone, energy, genuine and motion give a 1-10 score and a "
               "one-line reason."),
    "short4": "hook (first 3s), tone, energy, genuine, motion: score 1-10, one-line reason each.",
    "short5": "Rate this clip: hook, tone, energy, genuine, motion (1-10, one-line reason).",
}


def now():
    return time.time()


def _load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def purge(keep_days=KEEP_DAYS, t=None):
    """Delete YouTube data (and everything measured from it) older than `keep_days`. Returns how much went."""
    cutoff = (t or now()) - keep_days * 86400
    videos = _load(VIDEOS, [])
    kept = [v for v in videos if v.get("fetched_at", 0) >= cutoff]
    ids = {v["id"] for v in kept}
    gone = {"videos": len(videos) - len(kept), "files": 0, "derived": 0, "scores": 0}
    if gone["videos"]:
        _save(VIDEOS, kept)
    for f in MEDIA.rglob("*") if MEDIA.exists() else []:
        if f.is_file() and (f.name.split(".")[0] not in ids or f.stat().st_mtime < cutoff):  # <id>.mp4, <id>.t03.jpg
            f.unlink()
            gone["files"] += 1
    for path, key in ((MEASURES, "measured_at"), (LABELS, "labeled_at"), (OPENINGS, "opened_at"),
                      (DATA / "pairs.json", "paired_at"), (DATA / "ab.json", "ab_at")):
        m = _load(path, {})
        m2 = {k: v for k, v in m.items() if k in ids and v.get(key, 0) >= cutoff}
        if len(m2) != len(m):
            gone["derived"] += len(m) - len(m2)
            _save(path, m2)
    for f in SCORES.glob("*.json") if SCORES.exists() else []:
        s = _load(f, {})
        s2 = {k: v for k, v in s.items() if k in ids and v.get("scored_at", 0) >= cutoff}
        if len(s2) != len(s):
            gone["scores"] += len(s) - len(s2)
            _save(f, s2)
    return gone


# ---------- 1. data collection ----------

def _videos(token, ids, source, channel_id, fetched_at):
    rows = []
    for i in range(0, len(ids), 50):
        r = yt.get(f"{yt.API}/videos", token, part="snippet,statistics,contentDetails,status", id=",".join(ids[i:i + 50]))
        for v in r["items"]:
            dur = yt.seconds(v["contentDetails"]["duration"])
            if v["status"].get("privacyStatus") != "public" or not dur or dur > SHORT_MAX_S:
                continue
            s = v["statistics"]
            rows.append({"id": v["id"], "source": source, "channel_id": channel_id, "title": v["snippet"]["title"],
                         "published": v["snippet"]["publishedAt"], "duration": dur,
                         "views": int(s.get("viewCount", 0)), "likes": int(s["likeCount"]) if "likeCount" in s else None,
                         "avg_view_s": None, "fetched_at": fetched_at})
    return rows


def _playlist(token, playlist, limit):
    ids, page = [], None
    while len(ids) < limit:
        r = yt.get(f"{yt.API}/playlistItems", token, part="contentDetails", playlistId=playlist,
                   maxResults=min(50, limit - len(ids)), **({"pageToken": page} if page else {}))
        ids += [i["contentDetails"]["videoId"] for i in r["items"]]
        page = r.get("nextPageToken")
        if not page:
            break
    return ids[:limit]


def collect(own=100, per_channel=40, channels=None):
    """Our last `own` Shorts (views, likes, average view duration) + each clip channel's last `per_channel` uploads that
    are Shorts (views and likes: the API gives view duration only for our own channel)."""
    token, t = yt.access_token(), now()
    ch = yt.get(f"{yt.API}/channels", token, part="contentDetails,snippet", mine="true")["items"][0]
    mine = _videos(token, _playlist(token, ch["contentDetails"]["relatedPlaylists"]["uploads"], own),
                   "own", ch["id"], t)
    avg = own_view_duration(token)
    for v in mine:
        v["avg_view_s"] = avg.get(v["id"])
    rows = list(mine)
    for cid, name in channels if channels is not None else load_channels():
        try:
            rows += _videos(token, _playlist(token, "UU" + cid[2:], per_channel), name, cid, t)
        except urllib.error.HTTPError as e:
            print(f"[viral] {name}: {e.code}, skipped", flush=True)
    keep = {v["id"]: v for v in _load(VIDEOS, [])}
    keep.update({v["id"]: v for v in rows})
    _save(VIDEOS, list(keep.values()))
    return {"own": len(mine), "channels": len(rows) - len(mine), "total": len(keep)}


def own_view_duration(token):
    end = datetime.now(timezone.utc).date().isoformat()
    r = yt.get(yt.ANALYTICS, token, ids="channel==MINE", startDate="2020-01-01", endDate=end, dimensions="video",
               metrics="views,averageViewDuration", sort="-views", maxResults=200)
    cols = [c["name"] for c in r["columnHeaders"]]
    return {d["video"]: d["averageViewDuration"] for d in (dict(zip(cols, x)) for x in r.get("rows") or [])}


def load_channels(path=CHANNELS):
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            cid, _, name = line.strip().partition(" ")
            out.append((cid, name.strip() or cid))
    return out


def flag_outliers(videos, x=OUTLIER_X, settle_h=yt.SETTLE_HOURS, t=None):
    """Baseline = each source's median views (settled videos only); outlier = views >= x * baseline. Videos younger
    than `settle_h` are still being served their first audience: marked settling and left out of the comparison."""
    t = t or now()
    for v in videos:
        if v.get("published"):
            pub = datetime.fromisoformat(v["published"].replace("Z", "+00:00")).timestamp()
            v["settling"] = t - pub < settle_h * 3600
        else:  # imported without a date: the study already skipped each channel's 10 newest
            v["settling"] = False
    by = {}
    key = lambda v: v.get("channel_id") or v["source"]  # one channel, whichever import named it
    for v in videos:
        if not v["settling"]:
            by.setdefault(key(v), []).append(v["views"])
    for v in videos:
        base = st.median(by[key(v)]) if by.get(key(v)) else None
        v["baseline"] = base
        v["outlier"] = bool(base) and not v["settling"] and v["views"] >= x * base
    return videos


def import_study(ext_path, grouped_path=None):
    """Merge an earlier study's Shorts (ext.json: ch, cid, id, views, t) into viral/videos.json, deduped by id. Each
    record keeps its original fetch date (the file's mtime) so the 30-day purge still applies; a record already
    here (fresher, exact API views) wins, and only gains a duration or date it lacked."""
    ext_path = Path(ext_path)
    fetched = ext_path.stat().st_mtime
    extra = {}
    if grouped_path and Path(grouped_path).exists():
        g = json.loads(Path(grouped_path).read_text(encoding="utf-8"))
        extra = {x["id"]: x for k in ("hit", "flop") for x in g.get(k, [])}
    names = dict(load_channels()) if CHANNELS.exists() else {}
    have = {v["id"]: v for v in _load(VIDEOS, [])}
    added = 0
    for x in json.loads(ext_path.read_text(encoding="utf-8")):
        e = extra.get(x["id"], {})
        if x["id"] in have:
            v = have[x["id"]]
            v["duration"] = v.get("duration") or e.get("dur")
            continue
        have[x["id"]] = {"id": x["id"], "source": names.get(x["cid"], x["ch"]), "channel_id": x["cid"], "title": x["t"],
                         "published": e.get("pub") and f"{e['pub']}T00:00:00Z", "duration": e.get("dur"),
                         "views": int(x["views"]), "likes": e.get("likes"), "avg_view_s": None,
                         "fetched_at": fetched, "origin": ext_path.name}
        added += 1
    _save(VIDEOS, list(have.values()))
    return {"added": added, "total": len(have)}


# ---------- 2. code-only measurements ----------

class BotCheck(Exception):
    """YouTube asked yt-dlp to sign in: stop downloading instead of hammering it (it blocks the whole IP)."""


def download(ids, height=480, pause=2.0):
    MEDIA.mkdir(parents=True, exist_ok=True)
    done = []
    for vid in ids:
        out = MEDIA / f"{vid}.mp4"
        if not out.exists():
            res = subprocess.run(["yt-dlp", "-q", "--no-warnings", "-f",
                                  f"bv*[height<={height}]+ba/b[height<={height}]/b", "--merge-output-format", "mp4",
                                  "-o", str(out), f"https://www.youtube.com/watch?v={vid}"], capture_output=True, text=True)
            if "confirm you" in res.stderr and "not a bot" in res.stderr:
                raise BotCheck(vid)
            time.sleep(pause)
        if out.exists():
            done.append(vid)
    return done


def slice_path(vid):
    return MEDIA / f"{vid}.slice.mp4"


def media_for(vid):
    """The full download when cached, else the first-seconds slice, else None."""
    for p in (MEDIA / f"{vid}.mp4", slice_path(vid)):
        if p.exists():
            return p
    return None


def download_slice(vid, secs=SLICE_S, height=480):
    """Only the first `secs` seconds (yt-dlp download sections), never the whole Short."""
    MEDIA.mkdir(parents=True, exist_ok=True)
    out = slice_path(vid)
    if not out.exists():
        res = subprocess.run(["yt-dlp", "-q", "--no-warnings", "-f", f"bv*[height<={height}]+ba/b[height<={height}]/b",
                              "--download-sections", f"*0-{secs}", "--merge-output-format", "mp4", "-o", str(out),
                              f"https://www.youtube.com/watch?v={vid}"], capture_output=True, text=True)
        if "confirm you" in res.stderr and "not a bot" in res.stderr:
            raise BotCheck(vid)
    return out if out.exists() else None


def slice_queue(videos, opens, seed=5):
    """Settled videos with no opening yet. Channels that already have both an outlier and a non-outlier measured
    come first, round-robin, alternating outlier / non-outlier inside each (so the thin outlier side grows)."""
    rng = random.Random(seed)
    have = {}
    for v in videos:
        if v["id"] in opens and not v.get("settling"):
            have.setdefault(v["source"], set()).add(bool(v["outlier"]))
    todo = {}
    for v in videos:
        if v["id"] not in opens and not v.get("settling") and not slice_path(v["id"]).exists():
            todo.setdefault(v["source"], {True: [], False: []})[bool(v["outlier"])].append(v["id"])
    for lanes in todo.values():
        for lane in lanes.values():
            rng.shuffle(lane)

    def order(srcs):
        out, flip = [], True
        lanes = {s: [todo[s][True][:], todo[s][False][:]] for s in srcs}
        while any(a or b for a, b in lanes.values()):
            for s in srcs:
                a, b = lanes[s]
                for lane in ((a, b) if flip else (b, a)):
                    if lane:
                        out.append(lane.pop())
                        break
            flip = not flip
        return out
    both = sorted(s for s in todo if have.get(s) == {True, False})
    rest = sorted(s for s in todo if s not in both)
    return order(both) + order(rest)


def grow_openings(cfg, limit=None, pause=6.0, max_failures=5):
    """Download the first seconds of settled Shorts one at a time, pausing between, stop at the first bot check;
    then run the frames + Apple OCR/faces + Apple speech on each slice."""
    videos = flag_outliers(_load(VIDEOS, []))
    todo = slice_queue(videos, _load(OPENINGS, {}))[:limit]
    got, failures = 0, 0
    for i, vid in enumerate(todo, 1):
        try:
            ok = download_slice(vid)
        except BotCheck:
            print(f"[viral] YouTube's bot check at {vid}: stopped after {got} slices; try again later", flush=True)
            break
        if not ok:
            failures += 1
            print(f"[viral] {vid}: slice download failed", flush=True)
            if failures >= max_failures:
                print(f"[viral] {failures} failures in a row: stopping", flush=True)
                break
        else:
            failures = 0
            openings(cfg, ids={vid})
            got += 1
        if i % 10 == 0:
            print(f"[viral] {got} slices ({i}/{len(todo)})", flush=True)
        time.sleep(pause + random.random() * pause / 2)
    return {"slices": got, "openings": len(_load(OPENINGS, {}))}


def count_cuts(stderr):
    return len(re.findall(r"pts_time:", stderr))


def first_word_and_rate(words, duration):
    if not words:
        return None, 0.0
    return round(float(words[0]["s"]), 2), round(len(words) / duration, 2) if duration else 0.0


def measure_one(mp4, cfg):
    from . import signals, transcribe
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(mp4)], capture_output=True, text=True, check=True).stdout.strip())
    scene = subprocess.run(["ffmpeg", "-nostats", "-i", str(mp4), "-vf", f"select='gt(scene,{SCENE_CUT})',showinfo",
                            "-an", "-f", "null", "-"], capture_output=True, text=True)
    wav = mp4.with_suffix(".wav")
    if not wav.exists():
        transcribe.extract_audio(mp4, wav)
    words, _, _ = transcribe.transcribe(wav, str(mp4.with_suffix("")), {**cfg, "asr": "apple"})  # Apple's local model
    first, rate = first_word_and_rate(words, dur)
    return {"length_s": round(dur, 2), "cuts": count_cuts(scene.stderr), "first_word_s": first, "words_per_s": rate,
            "loudness_lufs": signals.integrated_loudness(mp4), "measured_at": now()}


def measure(cfg, limit=None, cached_only=False):
    videos = _load(VIDEOS, [])
    m = _load(MEASURES, {})
    todo = [v["id"] for v in videos if v["id"] not in m
            and (not cached_only or (MEDIA / f"{v['id']}.mp4").exists())][:limit]
    for i, vid in enumerate(todo, 1):  # one download at a time: parallel ones tripped YouTube's bot check
        try:
            ok = download([vid])
        except BotCheck:
            print(f"[viral] YouTube's bot check at {vid}: stopped downloading ({len(m)} measured so far); "
                  "try again later", flush=True)
            break
        if not ok:
            print(f"[viral] {vid}: download failed", flush=True)
            continue
        try:
            m[vid] = measure_one(MEDIA / f"{vid}.mp4", cfg)
        except (subprocess.CalledProcessError, ValueError, SystemExit) as e:
            print(f"[viral] {vid}: measure failed ({e})", flush=True)
            continue
        if i % 25 == 0:
            _save(MEASURES, m)
            print(f"[viral] measured {i}/{len(todo)}", flush=True)
    _save(MEASURES, m)
    return len(m)


# ---------- 2b. the first 5 seconds (cached media only) ----------

FRAME_TIMES = (0.3, 1.5, 3.0, 5.0)
VISION_SRC = Path(__file__).with_name("apple_vision.swift")


def frame_path(vid, at):
    return MEDIA / f"{vid}.t{int(at * 10):02d}.jpg"  # <id>.t03.jpg: the purge reads the id before the first dot


def opening_features(frames, words):
    """Hook text = OCR text on the first frame (0.3 s); face = the biggest face in the first 1.5 s; speech = words
    starting before 5 s. `frames` is apple-vision's output in FRAME_TIMES order."""
    first = frames[0]["text"] if frames else []
    hook = " ".join(b["s"] for b in first)
    faces = [f["area"] for fr in frames[:2] for f in fr["faces"]]
    early = [w for w in words if w["s"] < 5]
    return {"hook_text": int(bool(first)), "hook_words": len(re.findall(r"[A-Za-z0-9']+", hook)),
            "text_area": round(sum(b["area"] for b in first), 4), "face_area": round(max(faces, default=0.0), 4),
            "speech_0_5_words": len(early), "first_word_s": early[0]["s"] if early else None,
            "ocr_0_3": hook, "transcript_0_5": " ".join(w["w"] for w in early)}


def openings(cfg=None, ids=None):
    """First-5s features for videos whose media is already cached: no downloads."""
    from . import transcribe
    exe = transcribe.apple_binary(VISION_SRC, "apple-vision")
    o = _load(OPENINGS, {})
    videos = [v for v in _load(VIDEOS, []) if media_for(v["id"]) and (ids is None or v["id"] in ids)]
    for v in videos:
        vid, mp4 = v["id"], media_for(v["id"])
        if vid in o:
            continue
        for at in FRAME_TIMES:
            if not frame_path(vid, at).exists():
                subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-ss", str(at), "-i", str(mp4),
                                "-frames:v", "1", "-vf", "scale=-2:960", str(frame_path(vid, at))], check=False)
        paths = [str(frame_path(vid, at)) for at in FRAME_TIMES if frame_path(vid, at).exists()]
        sheet = MEDIA / f"{vid}.sheet.jpg"
        if len(paths) == len(FRAME_TIMES) and not sheet.exists():
            subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", *sum((["-i", x] for x in paths), []),
                            "-filter_complex", "".join(f"[{i}:v]scale=-2:480[s{i}];" for i in range(4)) +
                            "[s0][s1][s2][s3]hstack=4", str(sheet)], check=False)
        res = subprocess.run([str(exe), *paths], capture_output=True, text=True)
        frames = json.loads(res.stdout) if res.returncode == 0 and res.stdout else []
        wav = mp4.with_suffix(".wav")
        if not wav.exists():
            transcribe.extract_audio(mp4, wav)
        words, _, _ = transcribe.transcribe(wav, str(mp4.with_suffix("")), {**(cfg or {}), "asr": "apple"})
        o[vid] = {**opening_features(frames, words), "shows_action": o.get(vid, {}).get("shows_action"),
                  "opened_at": now()}
        _save(OPENINGS, o)
    return len(o)


def add_action_labels(path):
    """Merge `shows_action` labels (JSONL: {id, shows_action, why}) judged from the 0.3/1.5/3/5 s contact sheets."""
    o = _load(OPENINGS, {})
    n = 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            if d["id"] in o:
                o[d["id"]].update(shows_action=int(bool(d["shows_action"])), action_why=d.get("why", ""))
                n += 1
    _save(OPENINGS, o)
    return n


QUESTION_START = re.compile(r"^(why|how|what|who|whom|whose|where|when|which|is|are|was|were|do|does|did|can|could|"
                            r"will|would|should|am|have|has)\b", re.I)


def hook_is_question(text):
    """On-screen hook that reads as a question: a question mark, or it opens with a question word."""
    t = (text or "").strip()
    return int(bool(t) and ("?" in t or bool(QUESTION_START.match(t))))


def add_hook_labels(paths):
    """Merge blind hook labels (JSONL: {id, hook_states_setup, hook_matches_premise, hook_title_loop}) into the
    openings, judged from the on-screen hook + title + premise only (views hidden)."""
    o, n = _load(OPENINGS, {}), 0
    for path in paths:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                if d["id"] in o:
                    o[d["id"]].update({k: int(bool(d.get(k))) for k in HOOK_LABELS})
                    n += 1
    _save(OPENINGS, o)
    return n


def add_title_labels(paths):
    """Merge blind title labels (JSONL from the labellers) into viral/labels.json, stamped for the purge."""
    labels, t = _load(LABELS, {}), now()
    for path in paths:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                if d.get("trigger") not in TRIGGERS:
                    d["trigger"] = "none"
                labels[d["id"]] = {**{k: d.get(k) for k in ["premise", "trigger"] + LABEL_FIELDS}, "labeled_at": t}
    _save(LABELS, labels)
    return len(labels)


# ---------- 3. Gemini scoring ----------

def response_schema():
    item = {"type": "OBJECT", "properties": {"score": {"type": "INTEGER"}, "reason": {"type": "STRING"}},
            "required": ["score", "reason"]}
    return {"type": "OBJECT", "properties": {f: item for f in GEMINI_FIELDS}, "required": GEMINI_FIELDS}


def parse_scores(text):
    """The model's JSON, held to exactly the five fields, integer scores 1-10 and one-line reasons."""
    d = json.loads(text)
    if not isinstance(d, dict) or set(d) != set(GEMINI_FIELDS):
        raise ValueError(f"fields {sorted(d) if isinstance(d, dict) else type(d).__name__}, want {GEMINI_FIELDS}")
    out = {}
    for f in GEMINI_FIELDS:
        s, r = d[f].get("score"), str(d[f].get("reason") or "").strip()
        if not isinstance(s, int) or not 1 <= s <= 10 or not r or "\n" in r:
            raise ValueError(f"{f}: score {s!r} / reason {r!r}")
        out[f] = {"score": s, "reason": r}
    return out


def gemini_request(mp4, prompt):
    data = base64.b64encode(Path(mp4).read_bytes()).decode()
    return {"contents": [{"parts": [{"inline_data": {"mime_type": "video/mp4", "data": data}}, {"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "responseSchema": response_schema(),
                                 "temperature": 0}}


def score_one(mp4, prompt, key, model=GEMINI_MODEL):
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(gemini_request(mp4, prompt)).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=300) as r:
        body = json.load(r)
    return parse_scores(body["candidates"][0]["content"]["parts"][0]["text"])


def score(prompt_names, model=GEMINI_MODEL, limit=None):
    """Sends each measured video to Gemini (external, billed): only runs when GEMINI_API_KEY is set."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("[viral] GEMINI_API_KEY isn't set: Gemini scoring skipped (nothing was sent)")
    ids = [v["id"] for v in _load(VIDEOS, []) if (MEDIA / f"{v['id']}.mp4").exists()][:limit]
    done = {}
    for name in prompt_names:
        path = SCORES / f"{name}.json"
        s = _load(path, {})
        for vid in ids:
            mp4 = MEDIA / f"{vid}.mp4"
            if vid in s or mp4.stat().st_size > INLINE_MAX_BYTES:
                continue
            try:
                s[vid] = {**score_one(mp4, PROMPTS[name], key, model), "scored_at": now(), "model": model}
            except (urllib.error.URLError, ValueError, KeyError) as e:
                print(f"[viral] {name} {vid}: {e}", flush=True)
            _save(path, s)
        done[name] = len(s)
    return done


# ---------- 4. comparison ----------

NEGATION = re.compile(r"\b(not|never|nobody|no one|can'?t|won'?t|didn'?t|doesn'?t|isn'?t|wasn'?t|wouldn'?t|couldn'?t)\b",
                      re.I)
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF]")


def title_code(title, duration):
    """The title features code can read exactly (hashtags dropped first)."""
    t = re.sub(r"#\S+", "", title or "").strip()
    return {"question": int("?" in t), "negation": int(bool(NEGATION.search(t))), "emoji": int(bool(EMOJI.search(t))),
            "word_count": len(re.findall(r"[A-Za-z0-9']+", t)), "length_s": duration}


def title_rows(videos, labels):
    rows = []
    for v in videos:
        if v.get("settling") or v["id"] not in labels:
            continue
        lab = labels[v["id"]]
        r = {"id": v["id"], "source": v["source"], "outlier": v["outlier"], "views": v["views"],
             **title_code(v["title"], v.get("duration")), **{k: int(bool(lab.get(k))) for k in LABEL_FIELDS}}
        r.update({f"trigger_{x}": int(lab.get("trigger") == x) for x in TRIGGERS})
        rows.append(r)
    return rows


def opening_rows(videos, openings):
    """One row per settled video with an opening. Hook features read the OCR text of the 0.3 s frame; a video with no
    on-screen text at 0.3 s has no hook, so its hook labels are 0."""
    rows = []
    for v in videos:
        o = openings.get(v["id"])
        if v.get("settling") or not o:
            continue
        r = {"id": v["id"], "source": v["source"], "outlier": v["outlier"], "views": v["views"],
             "length_s": v.get("duration"), **{k: o.get(k) for k in OPENING_METRICS}}
        r["hook_question"] = hook_is_question(o.get("ocr_0_3"))
        for k in HOOK_LABELS:
            r[k] = o.get(k) if o.get("hook_text") and o.get(k) is not None else (0 if not o.get("hook_text") else None)
        rows.append(r)
    return rows


def rows_for(videos, measures, scores=None):
    """One row per settled, measured video: its code metrics, plus one prompt's Gemini scores when given."""
    rows = []
    for v in videos:
        m = measures.get(v["id"])
        if not m or v.get("settling"):
            continue
        r = {"id": v["id"], "source": v["source"], "outlier": v["outlier"], "views": v["views"],
             **{k: m.get(k) for k in CODE_METRICS}}
        if scores is not None:
            s = scores.get(v["id"])
            r.update({f: s[f]["score"] if s else None for f in GEMINI_FIELDS})
        rows.append(r)
    return rows


def auc(pos, neg):
    """P(an outlier's value > a non-outlier's), ties half: 0.5 = no difference (Mann-Whitney, via ranks)."""
    if not pos or not neg:
        return None
    vals = sorted([(x, 1) for x in pos] + [(x, 0) for x in neg])
    rank_sum, i = 0.0, 0
    while i < len(vals):
        j = i
        while j + 1 < len(vals) and vals[j + 1][0] == vals[i][0]:
            j += 1
        r = (i + j) / 2 + 1
        rank_sum += r * sum(1 for k in range(i, j + 1) if vals[k][1])
        i = j + 1
    return (rank_sum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def auc_interval(pos, neg, reps=300, seed=3):
    """95% bootstrap interval for the AUC (outliers and others resampled separately)."""
    if not pos or not neg:
        return None
    rng, vals = random.Random(seed), []
    for _ in range(reps):
        vals.append(auc([rng.choice(pos) for _ in pos], [rng.choice(neg) for _ in neg]))
    vals.sort()
    return vals[int(0.025 * reps)], vals[int(0.975 * reps) - 1]


def strata_auc(rows, k, reps=300, seed=3):
    """AUC computed inside each channel (>= 1 outlier and >= 3 others), averaged by pair count, with a 95% bootstrap
    interval that resamples inside channels: a channel's house style cannot pass for an outlier trait."""
    strata = []
    for src in sorted({r["source"] for r in rows}):
        p = [r[k] for r in rows if r["source"] == src and r["outlier"] and r.get(k) is not None]
        n = [r[k] for r in rows if r["source"] == src and not r["outlier"] and r.get(k) is not None]
        if p and len(n) >= 3:
            strata.append((p, n))
    if not strata:
        return None

    def combine(parts):
        w = [len(p) * len(n) for p, n in parts]
        return sum(wi * auc(p, n) for wi, (p, n) in zip(w, parts)) / sum(w)
    rng, vals = random.Random(seed), []
    for _ in range(reps):
        vals.append(combine([([rng.choice(p) for _ in p], [rng.choice(n) for _ in n]) for p, n in strata]))
    vals.sort()
    return combine(strata), vals[int(0.025 * reps)], vals[int(0.975 * reps) - 1], len(strata)


def _centre(xs):
    """Rate for yes/no features (a median of 0/1 hides the difference), median otherwise."""
    return st.mean(xs) if set(xs) <= {0, 1} else st.median(xs)


def spearman(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 3:
        return None

    def ranks(a):
        order = sorted(range(len(a)), key=lambda i: a[i])
        r = [0.0] * len(a)
        i = 0
        while i < len(a):
            j = i
            while j + 1 < len(a) and a[order[j + 1]] == a[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r
    rx, ry = ranks([p[0] for p in pairs]), ranks([p[1] for p in pairs])
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else None


def compare(rows, metrics, with_length=True):
    """Per metric: outlier vs other medians, the gap, AUC, the gap inside each source (so a channel's house style
    can't pass for an outlier trait), and how much it moves with length."""
    out = {}
    for k in metrics:
        pos = [r[k] for r in rows if r["outlier"] and r.get(k) is not None]
        neg = [r[k] for r in rows if not r["outlier"] and r.get(k) is not None]
        if not pos or not neg:
            continue
        within = []
        for src in sorted({r["source"] for r in rows}):
            p = [r[k] for r in rows if r["source"] == src and r["outlier"] and r.get(k) is not None]
            n = [r[k] for r in rows if r["source"] == src and not r["outlier"] and r.get(k) is not None]
            if p and len(n) >= 3:
                within.append((src, _centre(p) - _centre(n), len(p)))
        out[k] = {"outlier_median": _centre(pos), "other_median": _centre(neg), "binary": set(pos + neg) <= {0, 1},
                  "gap": _centre(pos) - _centre(neg), "auc": auc(pos, neg), "n_outliers": len(pos),
                  "n_other": len(neg), "within": within,
                  "length_rho": None if k == "length_s" or not with_length else
                  spearman([r.get(k) for r in rows], [r.get("length_s") for r in rows])}
    return out


def explain(k, c):
    """Where the gap comes from, in numbers only."""
    parts = [f"outliers {c['outlier_median']:.2f} vs others {c['other_median']:.2f} (gap {c['gap']:+.2f}, "
             f"AUC {c['auc']:.2f} on {c['n_outliers']} outliers / {c['n_other']} others)"]
    w = c["within"]
    if w:
        same = sum(1 for _, g, _ in w if (g > 0) == (c["gap"] > 0) and g != 0)
        parts.append(f"inside a single source the gap points the same way in {same} of {len(w)} sources "
                     f"(median within-source gap {st.median(g for _, g, _ in w):+.2f})")
        own = next((x for x in w if x[0] == "own"), None)
        if own:
            parts.append(f"our channel alone: {own[1]:+.2f} ({own[2]} outliers)")
        top = max(w, key=lambda x: abs(x[1]) * x[2])
        parts.append(f"biggest gap inside one source: {top[0]} ({top[1]:+.2f}, {top[2]} outliers)")
    if c["length_rho"] is not None and abs(c["length_rho"]) >= 0.3:
        parts.append(f"moves with video length (rho {c['length_rho']:+.2f}), so part of the gap tracks length")
    return "; ".join(parts)


# ---------- 5. validation ----------

def derive_rules(rows, metrics, min_edge=0.05, min_outliers=3):
    """Metric -> signed weight (AUC - 0.5) for metrics that separated outliers on these rows."""
    rules = {}
    for k, c in compare(rows, metrics, with_length=False).items():
        if c["n_outliers"] >= min_outliers and abs(c["auc"] - 0.5) >= min_edge:
            rules[k] = c["auc"] - 0.5
    return rules


def rank(rows, rules, ref):
    """Score = sum(weight * percentile of the value among the reference rows); missing values count as the middle."""
    import bisect
    ref_vals = {k: sorted(r[k] for r in ref if r.get(k) is not None) for k in rules}

    def pct(k, x):
        vals = ref_vals[k]
        if x is None or not vals:
            return 0.5
        lo, hi = bisect.bisect_left(vals, x), bisect.bisect_right(vals, x)
        return (lo + 0.5 * (hi - lo)) / len(vals)
    return sorted(rows, key=lambda r: -sum(w * pct(k, r.get(k)) for k, w in rules.items()))


def validate(rows, metrics, runs=50, sample=30, seed=7):
    """Hide views on `sample` random videos, learn rules on the rest, rank the hidden ones. Per run: is #1 an outlier,
    and what share of the top-m are outliers (m = outliers in the sample), against chance (m / sample)."""
    rng = random.Random(seed)
    top1, prec, chance, used, rule_sets = [], [], [], 0, {}
    tries = 0
    while used < runs and tries < runs * 20:
        tries += 1
        hidden = rng.sample(rows, min(sample, len(rows)))
        m = sum(r["outlier"] for r in hidden)
        if not m:
            continue
        ids = {r["id"] for r in hidden}
        train = [r for r in rows if r["id"] not in ids]
        rules = derive_rules(train, metrics)
        order = rank(hidden, rules, train)
        top1.append(order[0]["outlier"])
        prec.append(sum(r["outlier"] for r in order[:m]) / m)
        chance.append(m / len(hidden))
        for k in rules:
            rule_sets[k] = rule_sets.get(k, 0) + 1
        used += 1
    if not used:
        return {"runs": 0}
    return {"runs": used, "top1_outlier_rate": sum(top1) / used, "top_m_precision": st.mean(prec),
            "chance": st.mean(chance), "rules_used": rule_sets}


# ---------- report ----------

def report(runs=50, sample=30, seed=7):
    videos = flag_outliers(_load(VIDEOS, []))
    measures = _load(MEASURES, {})
    lines = ["# What our outliers have in common", "",
             f"Outlier = views >= {OUTLIER_X:g}x its channel's median (settled videos; younger than "
             f"{yt.SETTLE_HOURS} h left out). Raw YouTube data is deleted after {KEEP_DAYS} days.", ""]
    lines += _dataset_lines(videos)
    labels, opens = _load(LABELS, {}), _load(OPENINGS, {})
    rows = title_rows(videos, labels)
    if rows:
        lines += _section(f"Title and length features ({len(rows)} labelled videos, {sum(r['outlier'] for r in rows)} "
                          f"outliers; length known for {sum(r['length_s'] is not None for r in rows)})", rows,
                          TITLE_METRICS, runs, sample, seed, "title/length features")
    rows = opening_rows(videos, opens)
    if rows:
        lines += _opening_section(rows, runs, sample, seed)
    for scope, pick in (("all sources", lambda r: True), ("our channel only", lambda r: r["source"] == "own")):
        rows = [r for r in rows_for(videos, measures) if pick(r)]
        n_out = sum(r["outlier"] for r in rows)
        lines += [f"## Code-only metrics: {scope}", "", f"{len(rows)} measured videos, {n_out} outliers.", ""]
        if n_out < 5:
            lines += [f"Too few outliers ({n_out}) for a comparison to mean much; numbers shown anyway.", ""]
        c = compare(rows, CODE_METRICS)
        lines += ["| metric | outliers | others | gap | AUC |", "|---|---|---|---|---|"]
        lines += [f"| {k} | {v['outlier_median']:.2f} | {v['other_median']:.2f} | {v['gap']:+.2f} | {v['auc']:.2f} |"
                  for k, v in c.items()]
        lines += [""] + [f"- **{k}**: {explain(k, v)}" for k, v in c.items()] + [""]
        val = validate(rows, CODE_METRICS, runs, sample, seed)
        lines += _val_lines(val, sample)
    prompts = sorted(p.stem for p in SCORES.glob("*.json")) if SCORES.exists() else []
    if not prompts:
        lines += ["## Gemini scores", "", "Not run: no scores yet (needs GEMINI_API_KEY and `clipper viral score`).", ""]
    summary = []
    for name in prompts:
        rows = [r for r in rows_for(videos, measures, _load(SCORES / f"{name}.json", {}))
                if r.get("hook") is not None]
        if not rows:
            continue
        c = compare(rows, GEMINI_FIELDS)
        lines += [f"## Gemini prompt `{name}` ({len(rows)} videos, {sum(r['outlier'] for r in rows)} outliers)", "",
                  "| field | outliers | others | gap | AUC |", "|---|---|---|---|---|"]
        lines += [f"| {k} | {v['outlier_median']:.2f} | {v['other_median']:.2f} | {v['gap']:+.2f} | {v['auc']:.2f} |"
                  for k, v in c.items()]
        lines += [""] + [f"- **{k}**: {explain(k, v)}" for k, v in c.items()] + [""]
        val = validate(rows, CODE_METRICS + GEMINI_FIELDS, runs, sample, seed)
        lines += _val_lines(val, sample, "code metrics + this prompt's scores")
        if val.get("runs"):
            summary.append((name, len(PROMPTS.get(name, "")), val))
    if summary:
        lines += ["## Prompt versions compared", "", "| prompt | chars | #1 is an outlier | top-slot precision | chance |",
                  "|---|---|---|---|---|"]
        lines += [f"| {n} | {c} | {v['top1_outlier_rate']:.0%} | {v['top_m_precision']:.0%} | {v['chance']:.0%} |"
                  for n, c, v in summary] + [""]
    text = "\n".join(lines)
    _save_text(REPORT, text)
    return text


def _dataset_lines(videos):
    s = [v for v in videos if not v["settling"]]
    by = {}
    for v in s:
        n, o = by.get(v["source"], (0, 0))
        by[v["source"]] = (n + 1, o + v["outlier"])
    fetched = {}
    for v in videos:
        d = datetime.fromtimestamp(v["fetched_at"]).strftime("%Y-%m-%d %H:%M")
        fetched[d] = fetched.get(d, 0) + 1
    out = ["## Dataset", "", f"{len(videos)} Shorts ({len(s)} settled), {sum(v['outlier'] for v in s)} outliers; "
           f"duration known for {sum(bool(v.get('duration')) for v in s)}. Fetched: "
           + ", ".join(f"{n} on {d}" for d, n in sorted(fetched.items())) + ".", "",
           "| channel | settled | outliers |", "|---|---|---|"]
    out += [f"| {k} | {n} | {o} |" for k, (n, o) in sorted(by.items(), key=lambda kv: -kv[1][1])]
    return out + [""]


def _fmt(v, binary):
    return f"{v:.0%}" if binary else f"{v:.2f}"


def _section(title, rows, metrics, runs, sample, seed, what):
    c = compare(rows, metrics)
    lines = [f"## {title}", "", "| metric | outliers | others | gap | AUC | same direction inside channels |",
             "|---|---|---|---|---|---|"]
    for k, v in c.items():
        same = sum(1 for _, g, _ in v["within"] if g and (g > 0) == (v["gap"] > 0))
        gap = f"{v['gap'] * 100:+.0f} pts" if v["binary"] else f"{v['gap']:+.2f}"
        lines.append(f"| {k} | {_fmt(v['outlier_median'], v['binary'])} | {_fmt(v['other_median'], v['binary'])} | "
                     f"{gap} | {v['auc']:.2f} | {same} of {len(v['within'])} |")
    lines += [""] + [f"- **{k}**: {explain(k, v)}" for k, v in c.items() if abs(v["auc"] - 0.5) >= 0.05] + [""]
    return lines + _val_lines(validate(rows, metrics, runs, sample, seed), sample, what)


def _opening_section(rows, runs, sample, seed):
    n_out = sum(r["outlier"] for r in rows)
    c = compare(rows, OPENING_METRICS, with_length=False)
    by = {}
    for r in rows:
        n, o = by.get(r["source"], (0, 0))
        by[r["source"]] = (n + 1, o + r["outlier"])
    usable = [k for k, (n, o) in by.items() if o and n - o >= 3]
    lines = [f"## First 5 seconds and the text hook ({len(rows)} measured settled videos, {n_out} outliers, "
             f"{len(by)} channels)", "",
             "Hook = the on-screen text Apple OCR reads on the 0.3 s frame (none = no hook). Hook labels (states the "
             "setup, matches the premise, hook + title add a loop) were judged blind from the hook text + title + "
             "premise; videos with no hook count as 0. `shows_action` was judged from the 0.3/1.5/3/5 s frames. "
             "Face size = the biggest face in the first 1.5 s. Videos are downloaded in part (first ~6 s) and chosen "
             "to balance outliers and others inside channels, so the outlier share here is not the channel base "
             "rate; AUC does not depend on that share.", "",
             f"| channel | measured | outliers | others |", "|---|---|---|---|"]
    lines += [f"| {k} | {n} | {o} | {n - o} |" for k, (n, o) in sorted(by.items(), key=lambda kv: (-kv[1][1], kv[0]))]
    lines += ["", f"Within-channel columns use the {len(usable)} channel(s) with at least 1 outlier and 3 others "
                  "measured; the within-channel AUC is computed inside each of them and averaged, so a channel's "
                  "own style cannot pass for an outlier trait.", "",
              "| feature | outliers (rate or median, n) | others (rate or median, n) | gap | AUC pooled (95% interval) | "
              "AUC inside channels (95% interval) | same direction inside channels |", "|---|---|---|---|---|---|---|"]
    clear = []
    for k in OPENING_METRICS:
        v = c.get(k)
        if not v:
            lines.append(f"| {k} | no data | no data | | | | |")
            continue
        pos = [r[k] for r in rows if r["outlier"] and r.get(k) is not None]
        neg = [r[k] for r in rows if not r["outlier"] and r.get(k) is not None]
        lo, hi = auc_interval(pos, neg)
        inner = strata_auc(rows, k)
        same = sum(1 for _, g, _ in v["within"] if g and (g > 0) == (v["gap"] > 0))
        gap = f"{v['gap'] * 100:+.0f} pts" if v["binary"] else f"{v['gap']:+.2f}"
        in_txt = f"{inner[0]:.2f} ({inner[1]:.2f} to {inner[2]:.2f}, {inner[3]} ch.)" if inner else "n/a"
        lines.append(f"| {k} | {_fmt(v['outlier_median'], v['binary'])} (n={v['n_outliers']}) | "
                     f"{_fmt(v['other_median'], v['binary'])} (n={v['n_other']}) | {gap} | "
                     f"{v['auc']:.2f} ({lo:.2f} to {hi:.2f}) | {in_txt} | {same} of {len(v['within'])} |")
        if inner and (inner[1] > 0.5 or inner[2] < 0.5):
            clear.append(f"{k} ({inner[0]:.2f})")
    lines.append("")
    val = validate(rows, OPENING_METRICS, runs, sample, seed)
    lines += _val_lines(val, sample, "opening/hook features only")
    small = n_out < 50 or len(usable) < 8
    why = []
    if n_out < 50:
        why.append(f"only {n_out} outliers")
    if len(usable) < 8:
        why.append(f"only {len(usable)} channel(s) with both outliers and others")
    lines += [f"**Sample size**: {len(rows)} videos with {n_out} outliers across {len(by)} channels "
              f"({len(usable)} with both kinds). Features whose inside-channel AUC interval excludes 0.5: "
              + (", ".join(clear) or "none") + ". "
              + (f"Still too small to conclude ({' and '.join(why)}): the intervals are wide, the effect is read "
                 "from a handful of channels, and the hidden-views test cannot separate a real effect from luck."
                 if small else "Large enough for the intervals above to be read as they stand."), ""]
    return lines


def _val_lines(val, sample, what="code metrics"):
    if not val.get("runs"):
        return ["Validation: no sample had an outlier to find.", ""]
    return [f"**Validation ({what})**: {val['runs']} runs, {sample} videos with views hidden, rules learned on the "
            f"rest. The #1-ranked video was a real outlier in {val['top1_outlier_rate']:.0%} of runs; "
            f"{val['top_m_precision']:.0%} of the top slots went to real outliers vs {val['chance']:.0%} by chance. "
            f"Rules used (runs): {val['rules_used'] or 'none passed'}.", ""]


def _save_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run(action, cfg, args):
    gone = purge()
    if any(gone.values()):
        print(f"[viral] purged data older than {KEEP_DAYS} days: {gone}", flush=True)
    if action == "import":
        return import_study(args.path, args.grouped)
    if action == "labels":
        return {"labels": add_title_labels(sorted(Path(args.path).glob("*.jsonl")))}
    if action == "openings":
        return {"openings": openings(cfg)}
    if action == "actions":
        return {"shows_action": add_action_labels(args.path)}
    if action == "pairs":
        from . import pairs
        own = json.loads(Path(args.path).read_text(encoding="utf-8"))
        others = [x for x in _load(VIDEOS, []) if x["source"] != "own"]
        found = pairs.find(own, others, cfg, pause=args.pause)
        return {"confirmed": sum(1 for p in found.values() if p.get("their")), "checked": len(found)}
    if action == "hooks":
        return {"hook_labels": add_hook_labels(sorted(Path(args.path).glob("*.jsonl")))}
    if action == "collect":
        return collect(args.own, args.per_channel)
    if action == "measure" and args.slices:
        return grow_openings(cfg, args.limit, args.pause)
    if action == "measure":
        return {"measured": measure(cfg, args.limit, args.cached_only)}
    if action == "score":
        names = list(PROMPTS) if args.prompt == "all" else [args.prompt]
        return score(names, args.model, args.limit)
    if action == "report":
        return report(args.runs, args.sample, args.seed)
    return gone
