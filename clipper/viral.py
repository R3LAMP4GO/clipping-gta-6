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
    gone = {"videos": len(videos) - len(kept), "files": 0, "measures": 0, "scores": 0}
    if gone["videos"]:
        _save(VIDEOS, kept)
    for f in MEDIA.glob("*") if MEDIA.exists() else []:
        if f.stem.split(".")[0] not in ids or f.stat().st_mtime < cutoff:
            f.unlink()
            gone["files"] += 1
    m = _load(MEASURES, {})
    m2 = {k: v for k, v in m.items() if k in ids and v.get("measured_at", 0) >= cutoff}
    gone["measures"] = len(m) - len(m2)
    if gone["measures"]:
        _save(MEASURES, m2)
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
        pub = datetime.fromisoformat(v["published"].replace("Z", "+00:00")).timestamp()
        v["settling"] = t - pub < settle_h * 3600
    by = {}
    for v in videos:
        if not v["settling"]:
            by.setdefault(v["source"], []).append(v["views"])
    for v in videos:
        base = st.median(by[v["source"]]) if by.get(v["source"]) else None
        v["baseline"] = base
        v["outlier"] = bool(base) and not v["settling"] and v["views"] >= x * base
    return videos


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


def measure(cfg, limit=None):
    videos = _load(VIDEOS, [])
    m = _load(MEASURES, {})
    todo = [v["id"] for v in videos if v["id"] not in m][:limit]
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
    """P(an outlier's value > a non-outlier's), ties half: 0.5 = no difference."""
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


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


def compare(rows, metrics):
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
                within.append((src, st.median(p) - st.median(n), len(p)))
        out[k] = {"outlier_median": st.median(pos), "other_median": st.median(neg),
                  "gap": st.median(pos) - st.median(neg), "auc": auc(pos, neg), "n_outliers": len(pos),
                  "n_other": len(neg), "within": within,
                  "length_rho": None if k == "length_s" else spearman([r.get(k) for r in rows],
                                                                       [r.get("length_s") for r in rows])}
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
    for k, c in compare(rows, metrics).items():
        if c["n_outliers"] >= min_outliers and abs(c["auc"] - 0.5) >= min_edge:
            rules[k] = c["auc"] - 0.5
    return rules


def rank(rows, rules, ref):
    """Score = sum(weight * percentile of the value among the reference rows); missing values count as the middle."""
    def pct(k, x):
        vals = [r[k] for r in ref if r.get(k) is not None]
        if x is None or not vals:
            return 0.5
        return (sum(v < x for v in vals) + 0.5 * sum(v == x for v in vals)) / len(vals)
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
    if action == "collect":
        return collect(args.own, args.per_channel)
    if action == "measure":
        return {"measured": measure(cfg, args.limit)}
    if action == "score":
        names = list(PROMPTS) if args.prompt == "all" else [args.prompt]
        return score(names, args.model, args.limit)
    if action == "report":
        return report(args.runs, args.sample, args.seed)
    return gone
