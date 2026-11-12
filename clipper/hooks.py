"""Hook and title rules derived from 28 GTA Shorts with 500k+ views (research/viral-gta-shorts.md).

Every structure below appeared on a 500k+ video; a hook passes if it uses at least one. Labels pass with a note
(they only worked as a creator's series tag, with the spoken first line carrying the loop)."""
import re

STRUCTURES = [
    # name, pattern, sample it came from
    ("question", r"\?|^(why|how|what|who|which|where|did you|have you|do you|would you|can you|will i)\b",
     "What Happens If You Shoot The Moon In GTA 6? (1.7M)"),
    ("tease", r"\.\.\.|…|\b(this|these|wait|watch|until|guess|happens|the reason|here'?s why)\b",
     "I Can't Believe It's Real... (1.3M)"),
    ("withheld / negation", r"\b(can'?t|won'?t|didn'?t|couldn'?t|wasn'?t|isn'?t|not|never|nobody|no one|only)\b",
     "KIDS CAN'T PLAY GTA 6 (51M)"),
    ("number promise", r"^\s*(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(\w+\s+){0,2}"
                       r"(things|features|reasons|ways|secrets|details|clips|facts|changes|mistakes|easter eggs)\b",
     "4 NEW FEATURES COMING IN GTA 6 (10M)"),
    ("shock fact", r"\b\d+[\d,.]*\s*(x|%|years?|hours?|minutes?|days?|million|billion|k|times|miles?|dollars?)\b|\$\d",
     "HE'S 72 YEARS OLD (1M)"),
    ("first-person claim", r"^(i|i'm|im|i'll|i've|we|we're)\b", "I'M GONNA PLAY GTA 6! (2M)"),
    ("relatable situation", r"^(me|us|my|when|whenever|pov|how|that moment|every|you|your)\b|"
                            r"\b(my|your|his|her) (mom|mum|dad|parents?|girlfriend|gf|boyfriend|wife|brother|sister|"
                            r"teacher|boss|friends?)\b|\bin the room\b|\bwalks? in\b",
     "How Playing GTA 6 Is Gonna Be 😂 (5M)"),
]
# A short "who does what" premise with one shouted twist word: the creators' own titles do this
# ("xQc FORCES Weazel News Ron Otterman to Rob a Bank", "Kids WON'T Be Able To Play GTA 6!").
CAPS_TWIST = re.compile(r"\b(?!(?:GTA|RP|VI|POV|NPC|I|OK)\b)[A-Z][A-Z']+\b")
STRUCTURES = [(n, re.compile(p, re.I), ex) for n, p, ex in STRUCTURES]
STRUCTURES.append(("premise + twist", CAPS_TWIST, "xQc FORCES Weazel News Ron Otterman to Rob a Bank (source title)"))
STRUCTURES.append(("superlative", re.compile(r"\b(best|fastest|worst|biggest|craziest|smartest|most|first ever|"
                                           r"world'?s|#1|ever)\b", re.I), "World's Best Sniper in Black Ops 7"))
# Words that describe the clip instead of teasing it; fine inside a tease ("Wait for his reaction...").
SPOILERS = re.compile(r"\b(reaction|compilation|highlights?|recap|full video|part \d+|episode)\b", re.I)
# Spoken first lines the viral clips opened on (cold opens), vs filler that loses the swipe.
OPENING_TYPES = [
    ("action cold open", re.compile(r"!|^(go|run|look|wait|watch|stop|no|yo|oh|bro|so i|get)\b", re.I)),
    # dropped straight into the scene: interjections, sound effects, someone mid-conversation
    ("in-scene cold open", re.compile(r"^(\*|\[|ooh|ah+|oh|hey|sir|ma'?am|bro|dude|take|i'?m (ready|gonna|going)|"
                                      r"i'?m about to|let'?s)\b|^\*", re.I)),
    ("question", re.compile(r"\?|^(did you|have you|do you|what|why|how|will|would|can)\b", re.I)),
    ("number promise", STRUCTURES[3][1]),
    ("claim / news", re.compile(r"^(this is|it looks like|it doesn'?t|sorry|we know|according|breaking|"
                                r"there'?s only|nobody|the \w+ of|\w+ fans)\b", re.I)),
    ("setup tease", re.compile(r"^(if you|you want to see|you won'?t believe|imagine|picture this)\b", re.I)),
]
FILLER_OPEN = re.compile(r"^(um+|uh+|so yeah|anyway|okay so|alright so|like,|hey guys|what'?s up guys|welcome back|"
                         r"first of all|before we|(chat|chap|guys),? before|alright chat|okay chat|let'?s go ahead|"
                         r"in today'?s video)\b", re.I)


STOP = set("the a an in on of to and for is are you your this that these with at it be was just my i me we so he she "
           "his her they them him its im i'm it's what why how who when wait watch end guys nobody expected did does "
           "do can will would gta rp vi pov mid really actually".split())


def content_words(text):
    """Words that say what's happening; "Wait for the harmony..." has one, "Why are the hostages singing?" two."""
    return [w for w in re.findall(r"[a-z0-9']+", plain(text).lower()) if w not in STOP and len(w) > 2]


def plain(text):
    return re.sub(r"\*", "", text or "").strip()


def structures(hook):
    text = plain(hook)
    return [name for name, pat, _ in STRUCTURES if pat.search(text) and (name != "premise + twist" or
                                                                       len(text.split()) >= 3 and re.search("[a-z]", text))]


# The title must name the topic, or (as a note) carry its hashtag or a looser mention. Profiles set `title_topic`.
GTA6_TITLE = {"pattern": r"\bgta ?(6|vi)\b|grand theft auto (6|vi)", "loose": r"\bgta\b|grand theft auto",
              "hashtag": r"gta ?(6|vi)",
              "note": "no 'GTA 6' in the title: fine for a joke title if #gta6 is in the hashtags (RDCworld1, 5M)"}


def is_gta(cfg):
    """GTA research rules apply: no cfg means the original GTA 6 behaviour."""
    return cfg is None or cfg.get("research") == "gta"


def title_topic(cfg):
    if cfg is None:
        return GTA6_TITLE
    return cfg.get("title_topic") or (GTA6_TITLE if is_gta(cfg) else None)


def check_hook(hook, gta=True):
    """(fails, notes): fails break a rule every 500k+ hook followed; notes are judgment calls."""
    text = plain(hook)
    words = (re.sub(r"\bgta (6|vi)\b", "GTA6", text, flags=re.I) if gta else text).split()  # "GTA 6" is one word
    found = structures(hook)
    fails, notes = [], []
    limit = 9 if "relatable situation" in found else 8  # a relatable scene needs a few more words
    if not 2 <= len(words) <= limit:
        fails.append(f"{len(words)} words (keep hooks 2-6, max {limit})")
    if found and len(content_words(text)) <= 1:  # bare labels get their own note below
        fails.append("vague: say what's happening (who/what), e.g. \"Why are the hostages singing?\" not \"Wait for the "
                     "harmony...\" (vague hooks got 0.67x views on GTA Shorts)")
    if "first-person claim" in found and len(found) == 1:
        notes.append("first-person claims measured 0.94x on 3,481 gaming Shorts: add a number, question or negation")
    if found == ["premise + twist"]:
        notes.append("a CAPS word alone measured 0.97x: the premise works when it names the streamer "
                     "(\"xQc forces the hostages to *SING*\", 1.21x) or adds a question/negation")
    if (hook or "").count("*") not in (0, 2):
        fails.append("unbalanced *keyword* markup")
    if not found:
        if SPOILERS.search(text):
            fails.append("labels the clip instead of teasing it (drop 'reaction'/'highlights'/…)")
        elif len(words) <= 4:
            fails.append("topic label (no structure measured 0.88x on GTA Shorts): turn it into a question, number, "
                         "negation or relatable line (\"GTA 6 GRAPHICS\" -> \"Are these *GTA 6* graphics real?\")")
        else:
            fails.append("plain statement: use a structure (question, tease, withheld/negation, number promise, "
                         "shock fact, first-person claim, relatable situation)")
    return fails, notes


def check_title(title, hashtags=(), topic=GTA6_TITLE):
    fails, notes = [], []
    if len(title) > 100:
        fails.append(f"{len(title)} chars (max 100)")
    caps = [w for w in re.findall(r"[A-Za-z']+", title) if len(w) > 1 and w.isupper() and w not in ("GTA", "POV", "VI")]
    if len(caps) > 2:
        fails.append(f"{len(caps)} CAPS words: emphasise 1-2 (\"Cost HOW MUCH!?\")")
    if re.search("[A-Z]", title) and not re.search("[a-z]", title):
        fails.append("all-caps title (0.90x on 3,481 gaming Shorts, 0.68x on GTA): capitalise 1-2 words")
    if re.search(r"\b(update|announce\w*|explained|patch|now live|available now)\b", title, re.I):
        notes.append("announcement wording measured 0.85x: lead with what changed (\"GTA 6 Map Is 2x BIGGER\")")
    if topic and not re.search(topic["pattern"], title, re.I):
        tagged = any(re.search(topic["hashtag"], h, re.I) for h in hashtags)
        loose = topic.get("loose") and re.search(topic["loose"], title, re.I)
        (notes if tagged or loose else fails).append(topic["note"])
    return fails, notes


def opening_type(first_line):
    line = (first_line or "").strip()
    if FILLER_OPEN.match(line):
        return "filler (trim the start)"
    for name, pat in OPENING_TYPES:
        if pat.search(line):
            return name
    return "statement"


MAX_CLIP_S = 60  # our cap; YouTube Shorts allow longer


def pick_duration(pick):
    """Seconds in the finished clip: a story cut / multi-streamer edit sums its segments."""
    if pick.get("segments"):
        return sum(float(s["end"]) - float(s["start"]) for s in pick["segments"])
    return float(pick["end"]) - float(pick["start"])


def check_segments(pick):
    bad = []
    for i, seg in enumerate(pick.get("segments") or [], 1):
        try:
            if float(seg["end"]) - float(seg["start"]) < 0.5:
                bad.append(f"segment {i}: end must be at least 0.5s after start")
        except (KeyError, TypeError, ValueError):
            bad.append(f"segment {i} needs start and end (source seconds of its job)")
    return bad


def check_length(pick):
    if check_segments(pick):
        return "; ".join(check_segments(pick))
    try:
        d = pick_duration(pick)
    except (KeyError, TypeError, ValueError):
        return None
    if d > MAX_CLIP_S:
        return f"{d:.0f}s is over the {MAX_CLIP_S}s maximum: cut it to {MAX_CLIP_S}s or less"
    return None


def check_labels(pick):
    """Action captions must sit inside the clip and stay short: 1-3 words, e.g. *GETS CLOSER*. A segment pick's
    labels use seconds of the finished clip (0 = its first frame)."""
    bad = []
    lo, hi = (0.0, pick_duration(pick)) if pick.get("segments") and not check_segments(pick) else \
        (pick.get("start"), pick.get("end"))
    for lab in pick.get("labels") or []:
        try:
            a, b, text = float(lab["s"]), float(lab["e"]), str(lab["text"]).strip()
        except (KeyError, TypeError, ValueError):
            bad.append(f"label {lab!r} needs s, e (source seconds) and text")
            continue
        if not text or len(text.strip("*").split()) > 3:
            bad.append(f"label \"{text}\": 1-3 words, e.g. *GETS CLOSER*")
        if not (float(a if lo is None else lo) <= a < b <= float(b if hi is None else hi)):
            bad.append(f"label \"{text}\" ({a}-{b}s) must sit inside the clip ({lo}-{hi}s)")
    return bad


OPENING_FILLER = {"so", "um", "umm", "uh", "uhh", "like", "okay", "ok", "alright", "yeah", "anyway", "well", "great",
                  "and", "but", "chat", "bro", "hmm"}


def clip_labels(pick):
    """The pick's labels as (s, e, text) in seconds of the finished clip."""
    off = 0.0 if pick.get("segments") else float(pick.get("start") or 0)
    out = []
    for lab in pick.get("labels") or []:
        try:
            out.append((float(lab["s"]) - off, float(lab["e"]) - off, str(lab.get("text") or "")))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def clip_words(pick, words, load=None):
    """Transcript words (source seconds) moved onto the finished clip; a segment from another job needs `load(job)`
    to return its words. None when some segment's words can't be had."""
    if not pick.get("segments"):
        s, e = float(pick["start"]), float(pick["end"])
        return [dict(w, s=w["s"] - s, e=min(w["e"], e) - s) for w in words or [] if s <= w["s"] < e]
    out, t = [], 0.0
    for seg in pick["segments"]:
        src = load(seg["job"]) if seg.get("job") and load else (None if seg.get("job") else words)
        if src is None:
            return None
        s, e = float(seg["start"]), float(seg["end"])
        out += [dict(w, s=w["s"] - s + t, e=min(w["e"], e) - s + t) for w in src if s <= w["s"] < e]
        t += e - s
    return out


def _bare(w):
    return re.sub(r"[^a-z0-9']", "", str(w).lower())


def check_opening(pick, words):
    """A note when the clip's first 1.5s open on filler instead of the first meaningful word."""
    first = [w for w in words or [] if w["s"] < 1.5 and not w.get("label")]
    if not first:
        return None
    text = " ".join(str(w["w"]) for w in first)
    if _bare(first[0]["w"]) in OPENING_FILLER or FILLER_OPEN.match(text):
        return f"opens on filler (\"{text}\"): move the start to the first meaningful word"
    return None


def check_spoiler(pick, words=None):
    """A note per hook that repeats a word from the ending (the last segment's labels or the final 3s of speech):
    the hook must not say the outcome."""
    try:
        dur = pick_duration(pick)
    except (KeyError, TypeError, ValueError):
        return []
    last = dur - 3.0
    if pick.get("segments"):
        last = min(last, dur - (float(pick["segments"][-1]["end"]) - float(pick["segments"][-1]["start"])))
    ending = [text for a, b, text in clip_labels(pick) if b > last]
    ending += [str(w["w"]) for w in words or [] if w["s"] >= dur - 3.0]
    end_words = {_bare(x) for x in " ".join(ending).split()} - STOP - {""}
    end_words = {w for w in end_words if len(w) >= 3}
    out = []
    for h in pick.get("hooks") or [pick.get("hook", "")]:
        hit = sorted({_bare(x) for x in (h or "").split()} & end_words)
        if hit:
            out.append(f"hook \"{h}\" says the ending ({', '.join(hit)}): withhold the outcome")
    return out


DEAD_AIR_S = 2.0


def check_dead_air(pick, words):
    """Gaps of 2s+ in the finished clip with no word or label."""
    try:
        dur = pick_duration(pick)
    except (KeyError, TypeError, ValueError):
        return []
    spans = sorted([(w["s"], w["e"]) for w in words or []] + [(a, b) for a, b, _ in clip_labels(pick)])
    out, t = [], 0.0
    for a, b in spans + [(dur, dur)]:
        if a - t >= DEAD_AIR_S:
            out.append(f"dead air {t:.1f}-{a:.1f}s ({a - t:.1f}s): cut it with segments")
        t = max(t, b)
    return out


def check_fx(pick):
    """Errors for flashes whose `color` the render would reject."""
    from .render import flash_colour
    out = []
    for f in pick.get("fx") or []:
        if isinstance(f, dict) and f.get("type") == "flash" and f.get("color") is not None:
            try:
                flash_colour(f["color"])
            except ValueError as e:
                out.append(str(e))
    return out


QUIET_FOR_MUSIC_S = 3.0


def check_music(pick, words):
    """A note when the clip has a 3s+ stretch with no speech (labels don't count) and the pick has no `music` key:
    music may add there. An explicit `"music": []` means none on purpose."""
    if "music" in pick:
        return None
    try:
        dur = pick_duration(pick)
    except (KeyError, TypeError, ValueError):
        return None
    t, best = 0.0, (0.0, 0.0, 0.0)
    for a, b in sorted((w["s"], w["e"]) for w in words or [] if not w.get("label")) + [(dur, dur)]:
        if a - t > best[0]:
            best = (a - t, t, a)
        t = max(t, b)
    if best[0] < QUIET_FOR_MUSIC_S:
        return None
    return (f"{best[0]:.1f}s with no speech at {best[1]:.1f}-{best[2]:.1f}s and no `music` key: add a music window "
            f"in the moment's mood if it adds, or set \"music\": [] to skip on purpose")


def check_picks(picks, cfg=None, words=None, load=None):
    """{'video N': {...}} with 'fails' (fix these) and 'notes' (judgment calls) per hook/title; `edit` notes need the
    job's transcript `words` (source seconds; `load(job)` for other jobs' segments)."""
    from .playbook import for_profile
    gta, topic, playbook = is_gta(cfg), title_topic(cfg), for_profile(cfg)
    report = {}
    for n, pick in enumerate(picks, 1):
        entry = {}
        for h in pick.get("hooks") or [pick.get("hook", "")]:
            f, nt = check_hook(h, gta)
            if f or nt:
                entry.setdefault("hooks", {})[h] = {"fails": f, "notes": nt} if nt else {"fails": f}
        tags = pick.get("hashtags") or []
        for t in pick.get("titles") or []:
            f, nt = check_title(t, tags, topic)
            if f or nt:
                entry.setdefault("titles", {})[t] = {"fails": f, "notes": nt} if nt else {"fails": f}
        hs, ts = pick.get("hooks") or [], pick.get("titles") or []
        if hs and len(ts) == len(hs):
            for h, t in zip(hs, ts):
                if structures(h) and not set(structures(h)) & set(structures(t)):
                    entry.setdefault("pairing", []).append(
                        f"title \"{t}\" doesn't use its hook's type ({', '.join(structures(h))})")
        used = {s for h in pick.get("hooks") or [] for s in structures(h)}
        kind = pick.get("clip_type")
        if kind:
            play = playbook.get(kind)
            if not play:
                entry["clip_type"] = f"unknown clip_type '{kind}' (use {', '.join(playbook)})"
            else:
                missing = [s for s in play["hooks"][:2] if s not in used]
                if missing:
                    entry.setdefault("playbook", []).append(
                        f"{kind} clips win with {play['hooks'][:2]}; missing {missing} (e.g. \"{play['examples'][0]}\")")
                for key in ("hook_style", "caption_style"):
                    if pick.get(key) and pick[key] != play[key]:
                        entry.setdefault("playbook", []).append(
                            f"{key} '{pick[key]}' differs from the {kind} default '{play[key]}': keep it only on purpose")
        if check_length(pick):
            entry["length"] = check_length(pick)
        if check_labels(pick):
            entry["labels"] = check_labels(pick)
        if check_fx(pick):
            entry["fx"] = check_fx(pick)
        edit = check_spoiler(pick, None)
        cw = clip_words(pick, words, load) if words is not None and not check_segments(pick) else None
        if cw is not None:
            edit = check_spoiler(pick, cw) + [x for x in [check_opening(pick, cw)] if x] + check_dead_air(pick, cw) \
                + [x for x in [check_music(pick, cw)] if x]
        if edit:
            entry["edit"] = edit
        if len(pick.get("hooks") or []) >= 3 and len(used) < 3:
            entry["variety"] = f"hooks only use {sorted(used)}: give each variant a different structure to A/B test"
        if entry:
            report[f"video {n}"] = entry
    return report


def has_fails(report):
    return any(v.get("fails") for e in report.values() for k in ("hooks", "titles") for v in e.get(k, {}).values()) \
        or any("variety" in e or "length" in e or "labels" in e or "footage" in e or "fx" in e for e in report.values())
