"""The 100K+ profile: what clips with 100K+ views (and 5x+ their channel) do that the same channels' flops (<100K,
<1x) don't, measured inside each channel so channel size cancels out (research/100k-profile-2026-11.md).

`build` turns the split (research/100k-split-2026-11.json), the blind title labels and the measured video sample into
research/100k-profile-2026-11.json: per trait the high and low shares or medians, the in-channel lift with a 90%
channel-bootstrap range, n, and a verdict (clear / lean / no difference)."""
import json
import math
import random
import re
import statistics as st
import subprocess
from datetime import datetime
from pathlib import Path

from .config import ROOT

RES = ROOT / "research"
SPLIT = RES / "100k-split-2026-11.json"
LABELS = RES / "100k-labels-2026-11.json"      # blind title labels: {id: {category, cause, ...}}
MEASURES = RES / "100k-measures-2026-11.json"  # the measured video sample: {id: {trait: value}}
PROFILE = RES / "100k-profile-2026-11.json"
EXAMPLES = RES / "100k-examples.json"
CLEAR, LEAN, NONE, CHANNEL = "clear", "lean", "no difference", "channel-level"
MIN_N = 30            # a clear verdict needs at least this many videos on each side of the comparison
LEAN_RATIO = 1.15     # point estimate at least this far from 1x (either way) without a clean range = lean
REPS = 1000
SEED = 11

# Streamers named in titles (the list scripts/export_studied_videos.py uses): short or common words match only
# capitalised ("Ray", "Speed").
STREAMER_NAMES = [
    ("xQc", r"\bx\s?qc\b", True), ("Kai Cenat", r"\bkai\s?cenat\b", True), ("Kai Cenat", r"\bKai\b", False),
    ("IShowSpeed", r"\bishowspeed\b", True), ("IShowSpeed", r"\bSpeed(?:'s)?\b", False),
    ("CaseOh", r"\bcaseoh_?\b", True), ("Jynxzi", r"\bjynxzi\b", True), ("Fanum", r"\bfanum\b", True),
    ("Marlon", r"\bMarlon\b", False), ("Rakai", r"\bRakai\b", False), ("Ray", r"\bRay\b", False),
    ("Lacy", r"\bLacy\b", False), ("Duke Dennis", r"\bduke\s?dennis\b", True), ("Adin Ross", r"\badin(\s?ross)?\b", True),
    ("Stable Ronaldo", r"\bstable\s?ronaldo\b", True), ("Agent00", r"\bagent\s?00\b", True),
    ("Summit1g", r"\bsummit(1g)?\b", True), ("TimTheTatman", r"\btimthetatman\b", True),
    ("NICKMERCS", r"\bnickmercs\b", True), ("SypherPK", r"\bsypherpk\b", True), ("Ninja", r"\bNinja\b", False),
    ("DarkViperAU", r"\bdarkviperau\b", True), ("Swagg", r"\bSwagg\b", False), ("Valkyrae", r"\bvalkyrae\b", True),
    ("Fuslie", r"\bfuslie\b", True), ("Cinna", r"\bCinna\b", False), ("Buddha", r"\bBuddha\b", False),
    ("Blau", r"\bBlau\b", False), ("Clix", r"\bclix\b", True), ("Peterbot", r"\bpeterbot\b", True),
    ("Tfue", r"\btfue\b", True), ("Jamal", r"\bJamal\b", False), ("Tylil", r"\btylil\b", True),
    ("OhnePixel", r"\bohnepixel\b", True), ("Sketch", r"\bSketch\b", False), ("Hasan", r"\bhasan(abi)?\b", True),
    ("Pokimane", r"\bpokimane\b", True), ("Ludwig", r"\bLudwig\b", False), ("Shroud", r"\bShroud\b", False),
]
STREAMER_RES = [(name, re.compile(pat, re.I if nocase else 0)) for name, pat, nocase in STREAMER_NAMES]
NUMBER = re.compile(r"\d|\$|\b(one|two|three|four|five|six|seven|eight|nine|ten|hundred|thousand|million|billion|"
                    r"grand|first|last)\b", re.I)
END_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐⭕]️?\\s*$")
ANY_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐⭕]")
HASHTAG = re.compile(r"#\w+")
IRREGULAR_PAST = {"got", "went", "found", "made", "gave", "took", "saw", "met", "told", "said", "lost", "won", "left",
                  "bought", "caught", "thought", "brought", "fell", "ran", "came", "became", "broke", "stole", "hit",
                  "beat", "sent", "spent", "paid", "sold", "threw", "drove", "ate", "forgot", "felt", "heard", "kept",
                  "let", "put", "shot", "sang", "began", "chose", "flew", "froze", "knew", "rode", "rang", "fought",
                  "taught", "wrote", "woke", "was", "were", "had", "did", "tried", "cried", "denied", "lied"}
PRESENT_VERB = re.compile(r"\b(gets|goes|finds|makes|gives|takes|sees|meets|tells|says|loses|wins|leaves|buys|"
                          r"catches|tries|pulls|pranks|reacts|exposes|surprises|shows|calls|asks|plays|meets|"
                          r"\w+s)\b", re.I)
HYPE = re.compile(r"\b(insane|crazy|craziest|wild|wildest|unbelievable|epic|legendary|funniest|hilarious|best|"
                  r"worst|ever|most|amazing|shocking|shocked|unreal|goated?|mind ?blowing|chaotic|chaos|"
                  r"crazy moment|biggest|greatest)\b", re.I)
CAPS_SKIP = {"GTA", "RP", "VI", "POV", "NPC", "I", "OK", "TV", "USA", "UK", "PS5", "AI", "NBA", "NFL", "FBI", "CEO", "IRL"}
WITHHELD = {"setup, ending withheld", "tease", "question", "hypothetical"}


def streamers_in(text):
    return list(dict.fromkeys(name for name, pat in STREAMER_RES if pat.search(text or "")))


def title_body(title):
    return re.sub(r"\s+", " ", HASHTAG.sub(" ", title or "")).strip()


def first_streamer_at(text):
    hits = [m.start() for _, pat in STREAMER_RES for m in [pat.search(text)] if m]
    return min(hits) if hits else None


def past_tense(text):
    words = re.findall(r"[A-Za-z']+", text)
    names = {w for n in streamers_in(text) for w in n.split()}
    return any(w.lower() in IRREGULAR_PAST or (len(w) > 4 and w.lower().endswith("ed") and w not in names)
               for w in words[1:])


def title_traits(title):
    """Code-only traits of one title (hashtags dropped first, except for `hashtags`)."""
    from .hooks import has_stake, loop_frame
    body = title_body(title)
    words = re.findall(r"[A-Za-z0-9$'][A-Za-z0-9$',.]*", body)
    names = streamers_in(body)
    at = first_streamer_at(body)
    caps = [w for w in re.findall(r"[A-Za-z']+", body) if len(w) > 1 and w.isupper() and w not in CAPS_SKIP]
    frame = loop_frame(body)
    concrete = bool(NUMBER.search(body)) or has_stake(body, names=[w for n in names for w in n.split()])
    return {"title_words": len(words), "title_chars": len(body),
            "streamer_named": bool(names), "streamer_first": at is not None and at <= 1,
            "two_streamers": len(names) >= 2, "number": bool(NUMBER.search(body)),
            "end_emoji": bool(END_EMOJI.search((title or "").split("#")[0].strip() or body)),
            "emoji": bool(ANY_EMOJI.search(title or "")), "hashtags": bool(HASHTAG.search(title or "")),
            "past_tense": past_tense(body), "withheld_frame": frame in WITHHELD, "question": "?" in body,
            "caps_word": bool(caps), "two_plus_caps": len(caps) >= 2, "hype_no_detail": bool(HYPE.search(body)) and not concrete,
            "concrete_detail_code": concrete}


def meta_traits(v):
    """Duration and upload-time traits from the split row; None where the row lacks the field."""
    out = {"duration_s": v.get("dur"), "likes_per_1k": v.get("likes_k"), "posts_per_day": v.get("freq")}
    pub = v.get("published") or ""
    if pub and "T00:00:00" not in pub:  # date-only rows carry midnight, not an upload hour
        dt = datetime.fromisoformat(pub)
        out.update(upload_slot_utc=f"{dt.hour // 6 * 6:02d}-{dt.hour // 6 * 6 + 6:02d}", posted_12_24_utc=dt.hour >= 12,
                   weekend=dt.weekday() >= 5)
    elif pub:
        out["weekend"] = datetime.fromisoformat(pub).weekday() >= 5
    if v.get("dur") is not None:
        out["under_30s"] = v["dur"] < 30
    return out


# ---------- statistics ----------

def _channels(rows):
    by = {}
    for r in rows:
        by.setdefault(r["ch"], []).append(r)
    return by


def mh_lift(rows, key):
    """Mantel-Haenszel risk ratio of being high with vs without a binary trait, inside each channel."""
    num = den = 0.0
    for rs in _channels(rows).values():
        has = [r for r in rs if r[key] is True]
        not_ = [r for r in rs if r[key] is False]
        n = len(has) + len(not_)
        if not has or not not_:
            continue
        a, c = sum(r["group"] == "high" for r in has), sum(r["group"] == "high" for r in not_)
        num += a * len(not_) / n
        den += c * len(has) / n
    return num / den if den else None


def median_ratio(rows, key, min_each=3):
    """High median / low median of a number inside each channel, pooled on the log scale (weight = smaller side)."""
    tot = wsum = 0.0
    for rs in _channels(rows).values():
        hi = [r[key] for r in rs if r["group"] == "high"]
        lo = [r[key] for r in rs if r["group"] == "low"]
        if len(hi) < min_each or len(lo) < min_each:
            continue
        mh, ml = st.median(hi), st.median(lo)
        if mh <= 0 or ml <= 0:
            continue
        w = min(len(hi), len(lo))
        tot += w * math.log(mh / ml)
        wsum += w
    return math.exp(tot / wsum) if wsum else None


def bootstrap(rows, fn, reps=REPS, seed=SEED):
    """90% range of fn(rows) resampling whole channels."""
    rng = random.Random(seed)
    chans = list(_channels(rows).values())
    vals = []
    for _ in range(reps):
        sample = [r for _ in chans for r in rng.choice(chans)]
        x = fn(sample)
        if x is not None and math.isfinite(x):
            vals.append(x)
    if len(vals) < reps // 2:
        return None
    vals.sort()
    return [round(vals[int(0.05 * len(vals))], 3), round(vals[int(0.95 * len(vals)) - 1], 3)]


def verdict(lift, rng, n):
    if lift is None:
        return NONE
    far = lift >= LEAN_RATIO or lift <= 1 / LEAN_RATIO
    if rng and (rng[0] > 1 or rng[1] < 1):
        return CLEAR if n >= MIN_N else LEAN
    return LEAN if far else NONE


def _q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, int(round(p * (len(xs) - 1)))))]


def compare(rows, key, kind=None, reps=REPS, seed=SEED, source="title"):
    """One trait: shares (binary) or quartiles (number) per group, in-channel lift, 90% range, n and verdict."""
    rows = [r for r in rows if r.get(key) is not None]
    hi = [r[key] for r in rows if r["group"] == "high"]
    lo = [r[key] for r in rows if r["group"] == "low"]
    if not hi or not lo:
        return {"trait": key, "source": source, "n_high": len(hi), "n_low": len(lo), "verdict": NONE}
    kind = kind or ("binary" if all(isinstance(x, bool) for x in hi + lo) else "number")
    out = {"trait": key, "kind": kind, "source": source, "n_high": len(hi), "n_low": len(lo)}
    if kind == "binary":
        out.update(high_share=round(sum(hi) / len(hi), 3), low_share=round(sum(lo) / len(lo), 3))
        fn = lambda rs: mh_lift(rs, key)  # noqa: E731
        n = min(sum(r[key] for r in rows), sum(not r[key] for r in rows))
    else:
        out.update(high={"p25": _q(hi, .25), "median": _q(hi, .5), "p75": _q(hi, .75)},
                   low={"p25": _q(lo, .25), "median": _q(lo, .5), "p75": _q(lo, .75)})
        fn = lambda rs: median_ratio(rs, key)  # noqa: E731
        n = min(len(hi), len(lo))
        if out["high"]["median"] <= 0 or out["low"]["median"] <= 0:  # mostly zeros: medians can't compare it
            return {**out, "lift": None, "range": None, "n": n, "verdict": NONE,
                    "why": "median is 0 on one side; see the yes/no version of this trait"}
    lift = fn(rows)
    rng = bootstrap(rows, fn, reps, seed) if lift is not None else None
    out.update(lift=round(lift, 3) if lift is not None else None, range=rng, n=n, verdict=verdict(lift, rng, n))
    return out


def channel_level(rows, key):
    """A trait that's the same for every video of a channel (posting frequency): pooled medians only."""
    rows = [r for r in rows if r.get(key) is not None]
    hi = [r[key] for r in rows if r["group"] == "high"]
    lo = [r[key] for r in rows if r["group"] == "low"]
    return {"trait": key, "kind": "number", "source": "channel", "n_high": len(hi), "n_low": len(lo),
            "high": {"median": _q(hi, .5)} if hi else None, "low": {"median": _q(lo, .5)} if lo else None,
            "verdict": CHANNEL}


# ---------- build ----------

def load_json(path, default):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def rows_from(split, labels=None, measures=None):
    """One flat row per video: title traits, metadata traits, label fields and measured fields."""
    out = []
    for v in split["videos"]:
        r = {"id": v.get("id"), "ch": v["ch"], "group": v["group"], **title_traits(v["t"]), **meta_traits(v)}
        for k, val in ((labels or {}).get(v.get("id")) or {}).items():
            r[f"label_{k}"] = val
        for k, val in ((measures or {}).get(v.get("id")) or {}).items():
            r[f"m_{k}"] = val
        if isinstance(r.get("label_payoff_at_s"), (int, float)) and r.get("m_length_s"):
            r["label_tail_after_payoff_s"] = round(r["m_length_s"] - r["label_payoff_at_s"], 2)
            r["label_payoff_share"] = round(r["label_payoff_at_s"] / r["m_length_s"], 2)
        out.append(r)
    return out


def expand_categorical(rows, key, values=None):
    """label_category -> label_category=reward (True/False) per value; rows without the key stay None."""
    vals = values or sorted({r[key] for r in rows if isinstance(r.get(key), str)})
    for r in rows:
        for x in vals:
            r[f"{key}={x}"] = None if not isinstance(r.get(key), str) else r[key] == x
    return [f"{key}={x}" for x in vals]


SKIP = {"id", "ch", "group"}
META_KEYS = {"duration_s", "likes_per_1k", "upload_slot_utc", "posted_12_24_utc", "weekend", "under_30s"}


def build(split, labels=None, measures=None, reps=REPS, seed=SEED):
    """The profile dict (see module doc)."""
    rows = rows_from(split, labels, measures)
    cat_keys = sorted({k for r in rows for k, x in r.items() if isinstance(x, str) and k not in SKIP})
    for k in cat_keys:
        expand_categorical(rows, k)
    keys = sorted({k for r in rows for k, x in r.items() if k not in SKIP and k not in cat_keys
                   and (isinstance(x, (bool, int, float)) and x is not None)})
    traits = {}
    for k in keys:
        if k == "posts_per_day":
            traits[k] = channel_level(rows, k)
            continue
        src = "label" if k.startswith("label_") else "video" if k.startswith("m_") else \
            "metadata" if k.split("=")[0] in META_KEYS else "title"
        traits[k] = compare(rows, k, reps=reps, seed=seed, source=src)
    hi = sum(r["group"] == "high" for r in rows)
    return {"built": datetime.now().strftime("%Y-%m-%d"), "split": {"high": hi, "low": len(rows) - hi,
                                                                   "channels": len(_channels(rows))},
            "rule": split.get("rule"), "verdicts": {"clear": "90% range excludes 1x and n >= 30",
                                                    "lean": f"range includes 1x but lift beyond {LEAN_RATIO}x either "
                                                            "way, or range excludes 1x with n < 30",
                                                    "no difference": "neither"},
            "traits": traits}


TEXT_FIELDS = ("ocr_0_3", "first_line", "last_line", "measured_at", "group", "ch")
VISION_FIELDS = ("text_0_3", "text_0_3_words", "text_0_3_area", "text_0_3_kind", "face_0_3", "layout", "captions",
                 "caption_upper", "caption_y", "caption_words")
DROP = ("ends_mid_sentence",)  # Apple's ASR punctuates the last word, so code can't tell; the blind labels judge it


def export_measures(sample, out=MEASURES):
    """viral/sample100k.json (purged after 30 days) -> the derived numbers the profile needs, without transcripts or
    on-screen text. Vision fields are dropped where Apple Vision failed on that clip."""
    rows = {}
    for vid, m in sample.items():
        r = {k: v for k, v in m.items() if k not in TEXT_FIELDS + DROP}
        if m.get("vision_ok") is False:
            for k in VISION_FIELDS:
                r.pop(k, None)
        r.pop("vision_ok", None)
        if m.get("flashes") is not None:
            r["any_flash"] = m["flashes"] > 0
        if m.get("first_word_s") is not None:
            r["speaks_by_0_5s"] = m["first_word_s"] <= 0.5
        rows[vid] = r
    Path(out).write_text(json.dumps(rows, indent=0, ensure_ascii=False), encoding="utf-8")
    return rows


def build_files(split=SPLIT, labels=LABELS, measures=MEASURES, out=PROFILE):
    prof = build(load_json(split, {"videos": []}), load_json(labels, {}), load_json(measures, {}))
    Path(out).write_text(json.dumps(prof, ensure_ascii=False, indent=1), encoding="utf-8")
    return prof


def fmt_trait(t):
    if t.get("kind") == "binary":
        val = f"high {t['high_share']:.0%} vs low {t['low_share']:.0%}"
    elif t.get("high"):
        val = f"high median {t['high']['median']} vs low {t['low']['median']}" if t.get("low") else ""
    else:
        val = ""
    rng = f" [{t['range'][0]}-{t['range'][1]}]" if t.get("range") else ""
    lift = f"{t['lift']}x{rng}" if t.get("lift") is not None else "-"
    return f"{t['trait']:<34} {t['verdict']:<14} {lift:<22} n {t.get('n', '-')!s:<5} {val}"


def show(prof):
    order = {CLEAR: 0, LEAN: 1, CHANNEL: 2, NONE: 3}
    lines = [f"100K+ profile built {prof['built']}: {prof['split']['high']} high vs {prof['split']['low']} low on "
             f"{prof['split']['channels']} channels (lift = in-channel, 90% channel-bootstrap range)"]
    for t in sorted(prof["traits"].values(), key=lambda t: (order.get(t["verdict"], 9), t["trait"])):
        lines.append(fmt_trait(t))
    return "\n".join(lines)


# ---------- checks: a pick (and its rendered clip) against the 100K+ profile ----------

MODES = ("off", "shadow", "on")
# Trait -> what a reader calls it. Only traits a pick or render can be measured on are checked.
CHECKED = {
    "m_length_s": "length (s)",
    "m_first_word_s": "first word (s)",
    "label_premise_at_s": "time to premise (s)",
    "label_payoff_at_s": "time to payoff (s)",
    "label_tail_after_payoff_s": "tail after the payoff (s)",
    "label_payoff_share": "payoff position (share of the clip)",
    "m_biggest_jump_s": "time to the loudest jump (s)",
    "m_tail_after_jump_s": "tail after the loudest jump (s)",
    "m_jump_share": "loudest jump position (share of the clip)",
    "m_dead_share": "dead space (share of the clip)",
    "m_cuts_per_min": "cuts per minute",
    "m_text_0_3": "text on screen at 0.3 s",
    "m_text_0_3_words": "words of opening text",
    "m_captions": "burned-in captions",
    "m_flashes": "flashes",
    "m_any_flash": "a flash or impact frame",
    "m_words_per_s": "words per second",
    "m_loops_visually": "last frame matches the first (loop)",
    "m_ends_mid_sentence": "ends mid-sentence",
}
# Traits that only ever note, whatever their verdict, and don't count toward the profile match.
# Length: clear but tiny (1.09x), and our own 12-25 s winners contradict its 18.3 s floor. Talking speed (0.87x) and
# the loudest jump's timing (1.18x): as fails at the 100K+ quartile edge they rejected 38% of the measured 100K+
# clips against 48% of flops (2026-11-25), too blunt to gate on.
NOTE_ONLY = {"m_length_s", "m_words_per_s", "m_biggest_jump_s"}
CHECKED_PREFIX = {"m_layout=": "facecam layout", "m_text_0_3_kind=": "opening text type",
                  "label_opening=": "opening structure", "label_ending=": "ending"}


def mode_of(cfg):
    m = (cfg or {}).get("principles")
    m = {True: "on", False: "off"}.get(m, m) if isinstance(m, bool) else str(m or "off").lower()  # YAML reads on/off as booleans
    return m if m in MODES else "off"


def load_profile(path=PROFILE):
    return load_json(path, None)


def checkable(prof):
    """{trait: profile row} for clear/lean traits the checks can measure."""
    out = {}
    for k, t in (prof or {}).get("traits", {}).items():
        if t.get("verdict") not in (CLEAR, LEAN):
            continue
        if k in CHECKED or any(k.startswith(p) for p in CHECKED_PREFIX):
            out[k] = t
    return out


def trait_name(k):
    if k in CHECKED:
        return CHECKED[k]
    for p, name in CHECKED_PREFIX.items():
        if k.startswith(p):
            return f"{name} {k[len(p):]}"
    return k


def judge(k, t, value):
    """None when the value fits the 100K+ side (or can't be judged), else a message."""
    if value is None:
        return None
    if t.get("kind") == "binary":
        want = (t.get("lift") or 1) > 1
        if bool(value) == want:
            return None
        return (f"{trait_name(k)}: {'missing' if want else 'present'} (100K+ {t['high_share']:.0%} vs flops "
                f"{t['low_share']:.0%}, {t['lift']}x in-channel, {t['verdict']})")
    hi, lo = t.get("high") or {}, t.get("low") or {}
    if not hi or not lo or hi.get("p25") is None:
        return None
    flops_lower = lo["median"] < hi["median"]
    off = (value < hi["p25"] and flops_lower) or (value > hi["p75"] and not flops_lower)
    if not off:
        return None
    return (f"{trait_name(k)}: {round(value, 2)} vs 100K+ {hi['p25']}-{hi['p75']} (median {hi['median']}; flops "
            f"median {lo['median']}, {t['verdict']})")


def _clip_words(pick, words):
    if words is None or pick.get("segments"):
        return words if pick.get("segments") else None
    s, e = float(pick["start"]), float(pick["end"])
    return [dict(w, s=w["s"] - s, e=min(w["e"], e) - s) for w in words if s <= w["s"] < e]


def jump_values(lufs):
    """When the clip's biggest loudness jump lands, measured as on the 100K+ sample (`viral.measure_sample_one`)."""
    from . import signals
    if not lufs:
        return {}
    length = float(len(lufs))
    peak = max(range(len(lufs)), key=lambda i: lufs[i]) + 0.5
    jumps = signals.jump_per_second(lufs)[1]
    at = (max(range(len(jumps)), key=lambda i: jumps[i]) + 0.5) if len(jumps) and max(jumps) > 0 else peak
    return {"m_biggest_jump_s": at, "m_tail_after_jump_s": round(length - at, 1), "m_jump_share": round(at / length, 2)}


def clip_loudness(pick, job):
    """Per-second loudness of a single-span pick's footage in the job's audio, or None (segments, no audio, ffmpeg
    error): one short ffmpeg pass over the pick only."""
    from . import signals
    if pick.get("segments") or not job:
        return None
    media = next((Path(job) / n for n in ("audio.wav", "source.mp4") if (Path(job) / n).exists()), None)
    try:
        s, e = float(pick["start"]), float(pick["end"])
        return signals.loudness_per_second(media, s, e - s) if media and e > s else None
    except (KeyError, TypeError, ValueError, subprocess.CalledProcessError, OSError):
        return None


def pick_values(pick, words=None, lufs=None):
    """{trait: value} the pick (plus its clip-second transcript `words` and per-second loudness `lufs`, when known)
    shows before it renders."""
    from . import hooks, viral
    out = {}
    try:
        dur = hooks.pick_duration(pick)
    except (KeyError, TypeError, ValueError):
        return out
    lo, hi = hooks.clip_bounds(pick)
    out["m_length_s"] = round(dur, 2)
    for key, field in (("label_premise_at_s", "premise_at"), ("label_payoff_at_s", "payoff_at")):
        try:
            at = float(pick[field]) - float(lo or 0)
            if 0 <= at <= dur:
                out[key] = round(at, 2)
        except (KeyError, TypeError, ValueError):
            pass
    if "label_payoff_at_s" in out:
        out["label_tail_after_payoff_s"] = round(dur - out["label_payoff_at_s"], 2)
        out["label_payoff_share"] = round(out["label_payoff_at_s"] / dur, 2) if dur else None
    hs = [h for h in pick.get("hooks") or [pick.get("hook") or ""] if (h or "").strip()]
    out["m_text_0_3"] = bool(hs) and not pick.get("no_hook")
    if hs:
        out["m_text_0_3_words"] = len(re.findall(r"[A-Za-z0-9']+", hooks.plain(hs[0])))
        kinds = {viral.text_kind(hooks.plain(h)) for h in hs}  # any variant of that kind can lead the post
        for k in ("question", "label", "detail", "other"):
            out[f"m_text_0_3_kind={k}"] = k in kinds
        out["m_text_0_3_kind=none"] = False
    layout = (pick.get("segments") or [pick])[0].get("layout") or pick.get("layout") or {"type": "fit"}
    lay = {"split": "split", "vertical": layout.get("as", "fit")}.get(layout.get("type", "fit"), layout.get("type"))
    lay = "split" if lay == "split" else "game" if layout.get("facecam") in ("hidden", "none") else lay
    if lay in ("split", "game") and layout.get("facecam") not in ("hidden", "none"):  # no cam in the stream: not judged
        for k in ("split", "full", "game", "face_low"):
            out[f"m_layout={k}"] = lay == k
    out["m_captions"] = pick.get("captions") is not False
    cw = _clip_words(pick, words)
    if cw:
        out["m_first_word_s"] = round(max(0.0, cw[0]["s"]), 2)
        out["m_dead_share"] = round(viral.dead_space(cw, dur) / dur, 2) if dur else None
        last = cw[-1]
        out["m_ends_mid_sentence"] = bool(dur - last["e"] < 0.4 and not re.search(r"[.!?]$", str(last["w"])))
    fx = pick.get("fx")
    out["m_any_flash"] = any(isinstance(f, dict) and f.get("type") == "flash" for f in fx) if isinstance(fx, list) \
        else pick.get("payoff_at") is not None and not pick.get("fx_no_payoff")  # auto_fx flashes on the payoff
    if cw:
        out["m_words_per_s"] = round(len(cw) / dur, 2) if dur else None
    if pick.get("segments"):
        out["m_cuts_per_min"] = round((len(pick["segments"]) - 1) / dur * 60, 1) if dur else None
    out.update(jump_values(lufs))
    return out


def check_values(values, prof, mode):
    """{'fails', 'notes', 'match': [met, of]}: a clear trait the values miss fails (a note in shadow mode), a lean
    or NOTE_ONLY one notes; `match` counts the clear, gating traits met out of those measurable."""
    fails, notes, met, of = [], [], 0, 0
    for k, t in checkable(prof).items():
        msg = judge(k, t, values.get(k))
        if values.get(k) is None:
            continue
        gate = t["verdict"] == CLEAR and k not in NOTE_ONLY
        if gate:
            of += 1
            met += msg is None
        if msg:
            (fails if gate and mode == "on" else notes).append(msg)
    return {"fails": fails, "notes": notes, "match": [met, of]}


def check_pick(pick, prof, mode, words=None, lufs=None):
    if mode == "off" or not prof:
        return None
    return check_values(pick_values(pick, words, lufs), prof, mode)


def profile_match(result):
    """The share of measurable clear 100K+ traits a pick meets (None when none could be measured)."""
    met, of = (result or {}).get("match") or (0, 0)
    return round(met / of, 2) if of else None


def rendered_values(mp4):
    """{trait: value} measured on a rendered MP4 with code (length, cuts, flashes, loop; opening text via Apple
    Vision on macOS)."""
    import sys
    from . import viral
    mp4 = Path(mp4)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(mp4)], capture_output=True, text=True, check=True).stdout.strip())
    scene = subprocess.run(["ffmpeg", "-nostats", "-i", str(mp4), "-vf", f"select='gt(scene,{viral.SCENE_CUT})',showinfo",
                            "-an", "-f", "null", "-"], capture_output=True, text=True)
    out = {"m_length_s": round(dur, 2), "m_cuts_per_min": round(viral.count_cuts(scene.stderr) / dur * 60, 1)}
    luma = viral.luma_series(mp4)
    if luma is not None and len(luma) > 1:
        out["m_flashes"] = viral.flash_count([float(x.mean()) for x in luma])
        out["m_loops_visually"] = float(abs(luma[0] - luma[-1]).mean()) < viral.LOOP_DIFF
    if sys.platform == "darwin":
        from . import transcribe
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            frame = Path(tmp) / "f03.jpg"
            subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-ss", "0.3", "-i", str(mp4),
                            "-frames:v", "1", "-vf", "scale=-2:960", str(frame)], check=False)
            try:
                exe = transcribe.apple_binary(viral.VISION_SRC, "apple-vision")
                res = subprocess.run([str(exe), str(frame)], capture_output=True, text=True)
                frames = json.loads(res.stdout) if res.returncode == 0 and res.stdout else []
            except SystemExit:
                frames = []
            if frames:
                text = " ".join(b["s"] for b in frames[0]["text"])
                out["m_text_0_3"] = bool(text.strip())
                out["m_text_0_3_words"] = len(re.findall(r"[A-Za-z0-9']+", text))
    return out


NO_TEXT_TRAITS = ("label_text_role=none", "m_text_0_3_kind=none", "m_text_0_3")


def no_hook_share(cfg, prof=None):
    """The render's no-hook share: 0 with `principles: on` when the profile says openings without text do worse
    (clear or lean), else the config's `no_hook_share`."""
    share = (cfg or {}).get("no_hook_share", 0.5)
    if mode_of(cfg) != "on":
        return share
    prof = prof if prof is not None else load_profile()
    for k in NO_TEXT_TRAITS:
        t = ((prof or {}).get("traits") or {}).get(k) or {}
        worse = (t.get("lift") or 1) < 1 if k.endswith("=none") else (t.get("lift") or 1) > 1
        if t.get("verdict") in (CLEAR, LEAN) and worse:
            return 0.0
    return share


def check_rendered(mp4, prof, mode):
    if mode == "off" or not prof:
        return None
    return check_values(rendered_values(mp4), prof, mode)


# ---------- blind video labels and 100K+ examples ----------

LABEL_VALUES = {
    "category": {"misunderstanding", "chemistry", "consequence", "character_behaviour", "discovery", "crossover",
                 "reward", "live_event", "other"},
    "cause_shown": {"cause_and_reaction", "reaction_only", "event_only"},
    "opening": {"setup_first", "action_first", "reaction_first", "payoff_preview", "talking"},
    "visual_hook": {"face_reaction", "action", "text_card", "static_gameplay", "other"},
    "text_role": {"adds_context", "repeats_visual", "label_only", "question", "none"},
    "ending": {"reaction", "punchline", "mid_sentence", "after"},
}


def merge_labels(paths, lengths=None):
    """JSONL label files -> {id: label fields}; values outside LABEL_VALUES or times outside the clip become None."""
    out = {}
    for path in paths:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            vid = d.pop("id")
            row = {k: (v if v in LABEL_VALUES[k] else None) for k, v in d.items() if k in LABEL_VALUES}
            for k in ("premise_at_s", "payoff_at_s"):
                v = d.get(k)
                ok = isinstance(v, (int, float)) and v >= 0 and (not lengths or v <= lengths.get(vid, 1e9) + 0.5)
                row[k] = round(float(v), 1) if ok else None
            row["streamers"] = [s for s in d.get("streamers") or [] if isinstance(s, str)]
            out[vid] = row
    return out


def build_examples(split, sample, labels, per=6):
    """100K+ examples for the prompt: per category and per streamer, the title, the opening text, the first spoken
    line, and how the clip opens and ends (high group only, highest lift first)."""
    vids = {v["id"]: v for v in split["videos"]}
    rows = []
    for vid, m in sample.items():
        v, lab = vids.get(vid), labels.get(vid) or {}
        if not v or v["group"] != "high":
            continue
        rows.append({"id": vid, "channel": v["ch"], "views": v["views"], "lift": v["lift"], "title": v["t"],
                     "opening_text": m.get("ocr_0_3") or "", "first_line": m.get("first_line") or "",
                     "category": lab.get("category"), "opening": lab.get("opening"), "text_role": lab.get("text_role"),
                     "ending": lab.get("ending"), "premise_at_s": lab.get("premise_at_s"),
                     "payoff_at_s": lab.get("payoff_at_s"), "length_s": m.get("length_s"),
                     "streamers": lab.get("streamers") or streamers_in(v["t"])})
    rows.sort(key=lambda r: -r["lift"])
    by_cat, by_streamer = {}, {}
    for r in rows:
        if r["category"] and len(by_cat.setdefault(r["category"], [])) < per:
            by_cat[r["category"]].append(r)
        for s in r["streamers"][:2]:
            if len(by_streamer.setdefault(s, [])) < per:
                by_streamer[s].append(r)
    return {"built": datetime.now().strftime("%Y-%m-%d"), "note": "100K+ (5x+ channel) clips from the measured sample; "
            "opening_text is OCR at 0.3 s", "by_category": by_cat,
            "by_streamer": {k: v for k, v in by_streamer.items() if len(v) >= 2}}


def examples_for(category=None, streamers=(), n=3, path=EXAMPLES):
    """A few 100K+ examples for one category and the clip's streamers (the prompt shows these)."""
    ex = load_json(path, {})
    out = list((ex.get("by_category") or {}).get(category) or [])[:n]
    for s in streamers:
        out += [r for r in (ex.get("by_streamer") or {}).get(s) or [] if r not in out][:n]
    return out
