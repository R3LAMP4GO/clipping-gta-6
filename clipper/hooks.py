"""Hook and title rules derived from 28 GTA Shorts with 500k+ views (research/viral-gta-shorts.md).

Every structure below appeared on a 500k+ video; a hook passes if it uses at least one. Labels pass with a note
(they only worked as a creator's series tag, with the spoken first line carrying the loop)."""
import re
from pathlib import Path

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
                                           r"easiest|hardest|cheapest|richest|dumbest|wildest|scariest|luckiest|"
                                           r"world'?s|#1|ever)\b", re.I), "World's Best Sniper in Black Ops 7"))
# Words that describe the clip instead of teasing it; fine inside a tease ("Wait for his reaction...").
# A question that hands the viewer a verdict to argue about ("Is He Cheating?!", 7.8M, 29x; ~1.28x on 36 titles).
DEBATE = re.compile(r"\?.*$|^(is|was|did|does|should|would|who)\b", re.I)
VERDICT = re.compile(r"\b(legit|fair|cheat\w*|wrong|right|real|fake|better|worse|worth|deserved?|should|scripted|"
                     r"rigged|lying|overreact\w*|too far|guilty|innocent|who won|who'?s|looks? like|same (guy|person))\b", re.I)
# A concrete stake: a number or amount, a consequence, or a named character/thing that isn't the streamer. On our
# channel the top 3 had one ("Trevor", "13", "$500K") and the bottom 4 didn't ("USB", "marlin", "the betrayal").
STAKE = re.compile(r"\d|\$|\b(one|two|three|four|five|ten|hundred|thousand|million|billion|grand|dead|dies?|died|kill\w*|"
                   r"shot|shoots?|arrest\w*|banned|fired|rob\w*|crash\w*|hostage|cheat\w*|hack\w*|jail|prison|sued|"
                   r"broke|quit\w*|kicked|caught|exposed)\b", re.I)
STARTERS = {"when", "why", "how", "what", "who", "whose", "where", "which", "pov", "me", "us", "nobody", "wait",
            "should", "did", "does", "is", "was", "are", "were", "can", "could", "would", "will", "never", "only",
            "everyone", "someone", "half", "even", "watch", "look", "guess", "imagine", "every", "you", "your"}
NOT_A_STAKE = {"GTA", "RP", "VI", "POV", "NPC", "I", "OK", "PD", "NoPixel", "Rockstar"}
STREAMERS = {"xqc", "kai", "cenat", "caseoh", "speed", "ishowspeed", "jynxzi", "ninja", "timthetatman", "nickmercs",
             "swagg", "sypherpk", "darkviperau", "chat"}
# Rage-bait words that measured ~0.84x on 97 gaming Shorts titles: provoke with a verdict, not an insult.
RAGE_BAIT = re.compile(r"\b(overrated|unpopular opinion|trash|garbage|ruined|sucks|disgusting|nobody asked)\b", re.I)
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


def has_stake(hook, names=()):
    """A number/amount, a consequence word, or a capitalised name (not the hook's first word) other than the streamer."""
    text = re.sub(r"\bgta ?(\d|vi?)\b", "GTA", plain(hook), flags=re.I)  # the game's number isn't a stake
    if STAKE.search(text):
        return True
    skip = STREAMERS | {n.lower() for n in names}
    words = re.findall(r"[A-Za-z][A-Za-z0-9']*", text)
    first = re.sub(r"'(s|re|ll|ve|d)$", "", words[0]).lower() if words else ""
    if words and (first in STOP or first in STARTERS):  # sentence case, not a name
        words = words[1:]
    return any(w[0].isupper() and w not in NOT_A_STAKE and not w.isupper() and re.sub(r"'s$", "", w).lower() not in skip
               for w in words)


# Characters a cold viewer knows; roleplay names (Mickey, Marty, Avery) aren't. Our hooks naming them got 164-840 views
# vs a 1.2k median for the rest (research "Cold hooks", 2026-11-19).
KNOWN_CHARACTERS = {"jason", "lucia", "trevor", "franklin", "michael", "lamar", "cj", "niko", "tommy", "arthur", "dutch",
                    "lester", "smoke", "ice", "spice"}
NAME_SKIP = {"Season", "Episode", "Part", "Chapter", "Week", "Day", "Mr", "Mrs", "Ms", "Dr"}
# Proper nouns everyone knows: places, nationalities, brands, figures.
KNOWN_WORDS = set("""vice city leonida florida miami los santos liberty america american usa mexico mexican spanish english
latina latino french chinese japanese uber lambo lamborghini ferrari corvette tesla bugatti walmart mcdonald playstation
xbox nintendo rockstar twitch youtube tiktok instagram discord bigfoot santa god jesus christmas halloween""".split())
LORE = re.compile(r"\b(\w+'s|his|her|their) (crew|gang|faction|war)\b|\bthe betrayal\b|\bbetrayal\b|"
                  r"\breally (leave|left|quit)\b|\bhear \w+ out\b", re.I)


def unknown_names(text, names=()):
    """Capitalised names in sentence-case text that aren't a known streamer, creator or game character."""
    words = re.findall(r"[A-Za-z][A-Za-z0-9']*", re.sub(r"#\S+", "", plain(text)))
    if not words or sum(w[0].isupper() for w in words) > len(words) / 2:  # Title Case: capitals don't mark names
        return []
    first = re.sub(r"'s$", "", words[0])
    if first == words[0] or first.lower() in STOP | STARTERS:  # sentence case capitalises it; "Mickey's crew…" counts
        words = words[1:]
    skip = STREAMERS | KNOWN_CHARACTERS | {n.lower() for n in names}
    skip |= KNOWN_WORDS
    out = [re.sub(r"'s$", "", w) for w in words  # NPCs/PS5 are acronyms, I'm/I'll aren't names
           if w[0].isupper() and not w[:2].isupper() and not re.match(r"I'", w) and w not in NOT_A_STAKE | NAME_SKIP]
    return list(dict.fromkeys(w for w in out if w.lower() not in skip))


def check_cold(pick, names=()):
    """Notes when a hook, title or premise needs prior knowledge: a name a stranger won't know or crew lore."""
    if pick.get("campaign"):
        return []
    notes, seen = [], []
    for field in (pick.get("hooks") or [pick.get("hook", "")]) + [pick.get("cold_premise") or "", pick.get("turn") or ""]:
        seen += [n for n in unknown_names(field, names) if n not in seen]
    hooks_titles = (pick.get("hooks") or [pick.get("hook", "")]) + (pick.get("titles") or [])
    named = [n for n in seen if any(re.search(rf"\b{re.escape(n)}\b", x or "", re.I) for x in hooks_titles)]
    if named:
        notes.append(f"names {', '.join(named)}: a stranger won't know who that is. Say who they are in plain words "
                     "(\"a 13-year-old\", \"his old boss\") unless it's a famous streamer or game character; our hooks "
                     "naming roleplay characters (Mickey, Marty, Avery) got 164-840 views vs a 1.2k median")
    lore = [x for x in hooks_titles if x and LORE.search(x)]
    if lore:
        notes.append(f"leans on lore ({LORE.search(lore[0]).group(0)!r}): a stranger doesn't know the crew or what came "
                     "before; name the act itself (\"xQc steals a Corvette with cops searching\")")
    return notes


EMOJI_IN_HOOK = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50\u2B55]")
# Opening text that announces a reaction instead of the situation ("xQc did NOT expect this from the PD", 636 views):
# 100K+ GTA openings label the setup (*EASIEST MISSION*, *PUTS ON NIKE*) and let the footage show what happens.
REACTION_ONLY = re.compile(r"\b(did ?n[o']?t expect|(was|were|is) not ready|was ?n'?t ready|nobody (warned|expected|saw)|"
                           r"did (he|she|they|\w+) really|could ?n[o']?t believe|did ?n[o']?t see (this|that|it)|"
                           r"(not|never) see (this|that|it) coming)\b", re.I)
REACTION_NOTE = ("announces the reaction, not the situation: set up what's about to happen with the concrete detail "
                 "(\"THE EASIEST MISSION\", \"ONE GUN COSTS $590?!\") and let the footage show the surprise")
# Banned outright (Ken/user 2026-11-21): reaction-explaining and meme openers. The opening text is a 2-6 word setup
# label for what's about to happen ("THE FINAL *BRIDGE* SHOOTOUT"), never how someone reacts to it.
BANNED_HOOK = re.compile(r"^\s*(when|me|pov)\b|\bpov\b|\b(nobody|no one)\b|\bdid ?n[o']?t\b|\b(was|were) ?n[o']?t\b|"
                         r"\b(could ?n[o']?t|can'?t) (believe|unsee)\b|\bwould ?n[o']?t\b|\bnever saw\b|\bexpected\b|"
                         r"\bsaw (this|that|it) coming\b", re.I)
BANNED_NOTE = ("old-style opener (Nobody / NOT ready / did NOT / didn't expect / When... / Me... / POV / a reaction): "
               "write a 2-6 word setup label for what's about to happen (\"THE FINAL *BRIDGE* SHOOTOUT\", "
               "\"STEALING HIS OWN *UBER*\", \"ONE GUN COSTS $590?!\")")


def banned_hook(hook):
    text = plain(hook or "")
    return bool(BANNED_HOOK.search(text) or REACTION_ONLY.search(text))


TOPIC_WORDS = {"gta", "gta6", "6", "vi", "v", "5", "graphics", "trailer", "gameplay", "update", "map", "leak", "leaks",
               "news", "game", "rp", "nopixel", "moments", "moment", "funny", "clip", "clips", "stream", "live"}
# The opening-text angles the hook-angle A/B compares (research/outlier-analysis-2026-11-20.md, user-approved);
# the reaction arm was dropped 2026-11-21 when reaction openers were banned.
ANGLES = ("label", "detail")


def situation_label(hook):
    """A 2-6 word label that sets up the situation (\"THE EASIEST MISSION\", \"DRIVING IN SCUBA GEAR\"): at least two
    content words that aren't topic words, so \"GTA 6 GRAPHICS\" still counts as a bare topic label."""
    text = plain(hook)
    words = re.sub(r"\bgta (6|vi)\b", "GTA6", text, flags=re.I).split()
    if not 2 <= len(words) <= 6 or "?" in text or SPOILERS.search(text):
        return False
    return len([w for w in content_words(text) if w.lower().strip("'") not in TOPIC_WORDS]) >= 2


def hook_angle(hook):
    """'reaction' (announces how someone reacts), 'label' (a 2-6 word situation label), 'detail' (names the concrete
    surprising detail), or None for an empty or unclassifiable hook."""
    text = plain(hook or "").strip()
    if not text:
        return None
    if banned_hook(text):
        return "reaction"
    if situation_label(hook):
        return "label"
    return "detail" if has_stake(hook) or "?" in text else None


def check_hook(hook, gta=True, names=()):
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
    if banned_hook(hook):
        fails.append(BANNED_NOTE)
    if gta and found and not has_stake(hook, names):
        notes.append("no concrete stake: name the number, amount, consequence or a character viewers already know (\"NOT ready for "
                     "*Trevor*\", \"him to be *13*\", \"$500K painting\"); our flops named only a vague object "
                     "(\"USB\", \"marlin\", \"the betrayal\")")
    if DID_YOU_KNOW.search(text):
        notes.append(DID_YOU_KNOW_NOTE)
    if RAGE_BAIT.search(text):
        notes.append("rage-bait wording measured ~0.84x on 3,481 gaming Shorts: ask the viewer for a verdict instead "
                     "(\"Is xQc's aim *legit*?!\")")
    if EMOJI_IN_HOOK.search(hook or ""):  # the hook fonts have no emoji glyphs: they burn in as empty boxes
        notes.append("emoji in the hook: the on-screen font has none, so the render drops it; keep emoji for the title")
    if (hook or "").count("*") not in (0, 2):
        fails.append("unbalanced *keyword* markup")
    if not found:
        if SPOILERS.search(text):
            fails.append("labels the clip instead of teasing it (drop 'reaction'/'highlights'/…)")
        elif situation_label(hook):
            notes.append("situation label: works when the first second of footage shows the contrast it sets up; bare "
                         "topic labels measured 0.88x, so this is the 'label' arm of the hook-angle test")
        elif len(words) <= 4:
            fails.append("topic label (no structure measured 0.88x on GTA Shorts): turn it into a question, number, "
                         "negation or relatable line (\"GTA 6 GRAPHICS\" -> \"Are these *GTA 6* graphics real?\")")
        elif gta and loop_frame(hook) == "closed":
            notes.append("plain statement with no open loop: tell the setup and hold back how it ends (\"Ron tried to "
                         "surprise Lacy with a *PS5 Pro*\", \"He took a hostage and only asked for *two bags of chips*\")")
        else:  # 100K+ clip channels narrate what happened ("Kai Cenat Pranked Lil RT! 😭"); this check failed 82% of them
            notes.append("plain statement: fine when it tells the setup and withholds how it ends (\"He took a hostage "
                         "and only asked for *two bags of chips*\"); it fails the loop if it says the outcome")
    return fails, notes


TURN_MAX_WORDS = 12

# Open-loop frames, measured against each channel's own norm (research "Open loops", 2026-11-19): hypotheticals 1.12x
# on 30 story-game channels, a told setup with the ending withheld 1.13x on 27 streamer-clip channels, "did you know"
# 0.71x and teases 0.86x on story-game channels, questions 0.87x on clip channels.
LOOP_FRAMES = [
    ("hypothetical", re.compile(r"^(what (happens|would happen|if)|what if)\b|\b(happens|would happen) (if|when)\b|"
                                r"^if (you|he|she|they|i|\w+) ", re.I)),
    ("did you know", re.compile(r"did you know|didn'?t know|never knew|nobody (knows|noticed)|you missed|hidden detail|"
                                r"easter egg", re.I)),
    ("setup, ending withheld", re.compile(r"\b(tried to|wanted to|tries to|attempts? to|almost|thought (he|she|they|it)|"
                                          r"didn'?t expect|did not expect|(was|were|is)n'?t ready|was not ready|accidentally|"
                                          r"got (tricked|fooled|pranked|caught|exposed)|finds? out|found out|realiz(es|ed)|"
                                          r"only (asked|wanted|had)|then|until|before (he|she|they))\b", re.I)),
    ("tease", re.compile(r"\.\.\.|…|\bwait (for|till|until)\b|\bwatch (till|until|this)\b", re.I)),
    ("question", re.compile(r"\?|^(why|how|who|is|did|does|was|can|would|should|which)\b", re.I)),
]
DID_YOU_KNOW = LOOP_FRAMES[1][1]
DID_YOU_KNOW_NOTE = ("\"did you know\" / hidden-detail framing measured 0.71x on 30 story-game channels: name the extreme "
                     "fact itself and withhold the outcome")


def loop_frame(text):
    """The open-loop frame a hook or title uses ('closed' when none): recorded per upload so `clipper stats` can
    compare frames on our own channel."""
    t = re.sub(r"#\S+", "", plain(text))
    return next((name for name, pat in LOOP_FRAMES if pat.search(t)), "closed")


# Own channel, 23 Nov 2026: our top 10 GTA 6 Shorts all paid off by ~16s and ended on it (avg 89-137% viewed);
# 1k-stuck ones kept 0.43 of viewers at 90% vs 0.69 for breakouts.
PAYOFF_BY_S = 20
PAYOFF_TAIL_S = 5


def check_loop(pick):
    """(fails, notes) for the reframe: the pick names the question a viewer is left with after the first second
    (`loop`) and the moment the clip answers it (`payoff_at`, source seconds; clip seconds for a segment pick, like
    labels). A loop the footage never closes is the clickbait the research bans; one closed early loses the viewer."""
    fails, notes = [], []
    if not str(pick.get("loop") or "").strip():
        fails.append("no `loop`: the question a stranger has after the first second (\"will they really pay a ransom of "
                     "chips?\"); the hook opens it, the clip closes it")
    at = pick.get("payoff_at")
    if at is None:
        fails.append("no `payoff_at`: when the clip answers the loop (no payoff in the footage, no clip)")
        return fails, notes
    try:
        at = float(at)
    except (TypeError, ValueError):
        return fails + [f"payoff_at {pick.get('payoff_at')!r} must be seconds"], notes
    lo, hi = clip_bounds(pick)
    if lo is None or hi is None:
        return fails, notes
    lo, hi = float(lo), float(hi)
    if not lo <= at <= hi:
        fails.append(f"payoff_at {at:g}s is outside the clip ({lo:g}-{hi:g}s): the loop never closes on screen")
    elif hi > lo and (at - lo) / (hi - lo) < 0.5:
        notes.append(f"the loop closes {at - lo:.0f}s into a {hi - lo:.0f}s clip: viewers leave once it's answered; end "
                     "a few seconds after the payoff or start later on the setup line")
    elif hi - at > PAYOFF_TAIL_S:
        notes.append(f"the clip runs {hi - at:.0f}s past the payoff: our breakouts end on the punchline so they loop; "
                     f"cut the end to within {PAYOFF_TAIL_S:g}s of it")
    if lo <= at <= hi and at - lo > PAYOFF_BY_S:
        notes.append(f"the payoff lands {at - lo:.0f}s in: our top 10 Shorts all paid off by ~16s; "
                     "start on the last setup line")
    return fails, notes


def check_stranger(pick):
    """Fails unless the pick names its turn (what changes between people, or the visible act at stake) and a cold
    premise a stranger gets in one read. Our flops needed lore ("OG ordered", "Lee's USB"); every 100K+ outlier didn't."""
    fails = []
    if pick.get("campaign"):  # the brand chose the stream and timestamps
        return fails
    if not str(pick.get("turn") or "").strip():
        fails.append("no `turn`: name what changes between people (a gift, prank, betrayal, meeting, confrontation) or "
                     "the visible act at stake (a theft, a chase, money spent); no turn, no clip")
    premise = str(pick.get("cold_premise") or "").strip()
    if not premise:
        fails.append("no `cold_premise`: the premise in <=12 words for someone who never saw the stream")
    elif len(premise.split()) > TURN_MAX_WORDS:
        fails.append(f"cold_premise is {len(premise.split())} words: a stranger must get it in one read "
                     f"(<= {TURN_MAX_WORDS}); if it needs backstory, skip the clip")
    return fails


# 2,911 100K+ clip Shorts vs our 73 (research/outlier-analysis-2026-11-20.md): a style gap, not a proven cause.
TAG_SUFFIX = re.compile(r"\s[|•–-]\s*[^|]*\b(gta|rp|nopixel|roleplay|shorts?)\b[^|]*$", re.I)
TAG_SUFFIX_NOTE = ("series tag after a pipe (\"| GTA RP\"): 71% of our titles, 3% of 100K+ clip Shorts; our tagged ones got a "
                   "median 1,044 views vs 1,399 untagged. Work the game into the sentence (\"…In GTA RP 😭\") or drop it")
END_EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50\u2B55]\ufe0f?" + r"\s*$")
END_EMOJI_NOTE = "no emoji at the end: 81% of 100K+ GTA clip Shorts end on one (ours 23%); pick the clip's emotion (😳 💀 😭 🤯)"
PREMISE_TYPES = {
    "contradiction": "an obvious contradiction (fails the easiest mission)",
    "recognition": "a famous moment in a new situation (Kai and Pudgie redo Big Smoke's order)",
    "consequence": "a consequence with stakes (loses hours of progress, loses his car in a bet)",
    "interaction": "people with an unpredictable outcome (buys a fan GTA 6, the dad says no)",
    "discovery": "an unusual discovery (GTA VI is 200GB)",
    # the only type over 2x plain in research/outlier-questions-2026-11.md (streamer Shorts), mostly award-show clips
    "event": "a live event the audience is following right now (wins Streamer of the Year, a marathon's 24-hour mark)",
}
# The question a viewer can't answer without watching (research/outlier-questions-2026-11.md); recorded per upload so
# `clipper stats` can test the types on our channel, where the outlier study found no reliable winner.
QUESTION_TYPES = {
    "choice": "does it react if I do X? (if you pick up Lucia in a sports car this happens)",
    "tries": "how badly will this go? (awkward NPC tries to rob Lucia)",
    "collision": "who snaps first? (Lucia finds out about Mandy)",
    "recognition": "is that real? (Speed finds a Hulk-like monster)",
    "event": "what is this world? (Lucia joins a cult, Speed wins Streamer of the Year)",
}
SELECTION = {"standalone": "makes sense without the stream", "unexpected": "something actually surprising happens",
             "payoff": "a visible or audible payoff", "six_words": "the premise fits in about 6 words",
             "story": "setup, development and payoff inside the clip"}
SELECTION_MIN = 4


def check_selection(pick):
    """Fails unless the pick names a `premise_type` and scores >= 4 of the 5 `selection` points (user-approved gate,
    2026-11-21): a heuristic for which moments are worth clipping, not a validated predictor."""
    if pick.get("campaign"):
        return []
    fails = []
    kind = pick.get("premise_type")
    if kind not in PREMISE_TYPES:
        fails.append(f"`premise_type` must be one of {', '.join(PREMISE_TYPES)} "
                     f"({'got ' + repr(kind) if kind else 'missing'}); if none fits, find a stronger moment")
    sel = pick.get("selection")
    if not isinstance(sel, dict):
        return fails + ["no `selection`: score the moment {" + ", ".join(f'"{k}": true/false' for k in SELECTION) + "}"]
    missed = [k for k in SELECTION if sel.get(k) is not True]
    if len(SELECTION) - len(missed) < SELECTION_MIN:
        fails.append(f"selection {len(SELECTION) - len(missed)}/5 (needs {SELECTION_MIN}): missing "
                     + "; ".join(f"{k} ({SELECTION[k]})" for k in missed) + ". Find a stronger moment")
    return fails


def check_question(pick):
    """(fails, notes): `question` names which of QUESTION_TYPES the clip answers; a note when missing."""
    if pick.get("campaign"):
        return [], []
    q = pick.get("question")
    if q is None:
        return [], ["no `question`: name the one question the clip answers (" + ", ".join(QUESTION_TYPES) +
                    ") so `clipper stats` can compare them on our channel"]
    if q not in QUESTION_TYPES:
        return [f"`question` must be one of {', '.join(QUESTION_TYPES)} (got {q!r})"], []
    return [], []


def check_angles(pick):
    """(fails, notes): the hook-angle A/B leads each video with one angle, so 3+ hooks must cover each."""
    hs = [h for h in pick.get("hooks") or [] if (h or "").strip()]
    have = {hook_angle(h) for h in hs}
    missing = [a for a in ANGLES if a not in have]
    if pick.get("campaign"):
        return [], []
    banned = [h for h in hs if banned_hook(h)]
    if banned:
        return [f"reaction/old-style hooks ({', '.join(repr(h) for h in banned)}): {BANNED_NOTE}"], []
    if not missing:
        return [], []
    msg = (f"hook-angle test: no {'/'.join(missing)} hook (label = 2-6 word situation \"THE EASIEST MISSION\"; "
           f"detail = the concrete surprise \"ONE GUN COSTS $590?!\")")
    return ([msg], []) if len(hs) >= 3 else ([], [msg])


MOOD_TITLE = re.compile(r"\s*(me|us|pov|when (you|your|ur))\b", re.I)
MOOD_NOTE = ("\"Me…\" / \"POV:\" / \"When you…\" hides the streamer and names a mood, not a moment: tell the setup with "
             "the streamer first and withhold the ending (\"Kai Cenat Tried To Steal A Car Off A Moving Truck In GTA 6 😱\")")


def streamer_clip(pick, names=()):
    """True when the pick's description or source names a streamer: its titles must name them, not say "Me…"."""
    text = " ".join(str(pick.get(k) or "") for k in ("description", "source")) + " " + " ".join(pick.get("sources") or [])
    if re.search(r"\b(twitch\.tv|kick\.com)/", text, re.I):  # a live stream is a streamer's clip
        return True
    words = {w.lower() for w in re.findall(r"[A-Za-z0-9_]+", text)}
    return bool(words & (STREAMERS | {n.lower() for n in names}))


def check_title(title, hashtags=(), topic=GTA6_TITLE, narrate=True):
    fails, notes = [], []
    if len(title) > 100:
        fails.append(f"{len(title)} chars (max 100)")
    caps = [w for w in re.findall(r"[A-Za-z']+", title) if len(w) > 1 and w.isupper() and w not in ("GTA", "POV", "VI")]
    if len(caps) > 2:
        fails.append(f"{len(caps)} CAPS words: emphasise 1-2 (\"Cost HOW MUCH!?\")")
    if re.search("[A-Z]", title) and not re.search("[a-z]", title):
        fails.append("all-caps title (0.90x on 3,481 gaming Shorts, 0.68x on GTA): capitalise 1-2 words")
    if narrate and (re.search(r"\b(NOT|NEVER|CAN'?T|WON'?T|DIDN'?T|NOBODY)\b", title) or "?" in title):
        notes.append("500K+ clip Shorts narrate what happened (1 of 45 used NOT/nobody, 0 asked a question): "
                     "\"Kai Cenat Finds ICE SPICE In GTA 5 😂\"; keep the twist in the hook, not the title")
    if DID_YOU_KNOW.search(title):
        notes.append(DID_YOU_KNOW_NOTE)
    rest = re.sub(r"\bgta ?(\d|vi?)\b", " ", REACTION_ONLY.sub(" ", title), flags=re.I)
    known = set(re.findall(r"[a-z]+", rest.lower())) & (KNOWN_CHARACTERS | KNOWN_WORDS)  # Title Case hides real names
    if narrate and REACTION_ONLY.search(title) and not (STAKE.search(rest) or known):
        notes.append("title " + REACTION_NOTE + "; \"Kai Cenat Fails The Easiest Mission In GTA 5\" over "
                     "\"Kai Cenat Was NOT Ready For This Mission\"")
    if narrate and TAG_SUFFIX.search(title):
        notes.append(TAG_SUFFIX_NOTE)
    if narrate and not END_EMOJI.search(title):
        notes.append(END_EMOJI_NOTE)
    if narrate and MOOD_TITLE.match(title):
        notes.append(MOOD_NOTE)
    elif narrate and loop_frame(title) == "closed":
        notes.append("no open loop: tell the setup on the clip's most extreme fact and hold back how it ends "
                     "(\"xQc Refused To Give An Armed Robber $5 In GTA 6 😭\"), or ask what happens if…")
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


MAX_CLIP_S = 45  # our cap; YouTube Shorts allow longer
# Own channel, 23 Nov 2026: our 4k-28k-view Shorts ran 12-25 s and paid off by ~16 s; 500K+ clip Shorts median 23 s.
AIM_CLIP_S = 25


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


OPENING_LABEL_S = 3.0  # strangers swipe when the first seconds don't say what's going on


def check_length_note(pick):
    """A note (not a fail) for a clip over 25 s: long clips lose viewers before the payoff."""
    if check_segments(pick):
        return None
    try:
        d = pick_duration(pick)
    except (KeyError, TypeError, ValueError):
        return None
    if AIM_CLIP_S < d <= MAX_CLIP_S:
        return (f"{d:.0f}s: aim for 12-{AIM_CLIP_S}s (our 4k-28k-view Shorts ran 12-25 s; the ones stuck at ~1k kept "
                "0.43 of viewers at 90% vs 0.69); keep it longer only while a streak or story keeps escalating")
    return None


def check_streamer_reacts(pick):
    """A note when the pick says the streamer isn't talking or reacting through the clip (`streamer_reacts: false`):
    cutscenes and scenes where only other people talk were among our ~1k-stuck Shorts (own channel, 23 Nov 2026)."""
    if pick.get("streamer_reacts") is not False or pick.get("campaign"):
        return None
    return ("the streamer isn't talking or reacting through this clip: our 4k-28k-view Shorts keep them on the mic "
            "throughout, while cutscenes and scenes where only other people talk stuck at ~1k; pick a stretch where they react")


def clip_bounds(pick):
    return (0.0, pick_duration(pick)) if pick.get("segments") and not check_segments(pick) else \
        (pick.get("start"), pick.get("end"))


def check_context_note(pick):
    """A note (not a fail) when no context caption starts in the first 3 s: ~1 in 4 500K+ gaming clips use them."""
    if not (pick.get("segments") or pick.get("start") is not None):
        return None
    lo, _ = clip_bounds(pick)
    for lab in pick.get("labels") or []:
        try:
            if float(lab["s"]) < float(lo or 0) + OPENING_LABEL_S:
                return None
        except (KeyError, TypeError, ValueError):
            continue
    return (f"no context caption in the first {OPENING_LABEL_S:g} s: if nobody talks or the situation isn't obvious, "
            "add a label that says what's happening (*put in handcuffs*, *in disbelief*)")


NARRATION_WPS = 2.6  # Fish Audio's pace, about 2.6 words a second


def check_narration(pick):
    """Fails for `narrate` without a voiceover or with narration longer than the clip; notes one that leaves no time
    for the streamer's own payoff line (the research rule: never narrate over the payoff)."""
    if not pick.get("narrate"):
        return []
    text = str(pick.get("voiceover") or "").strip()
    if not text:
        return ["narrate needs a voiceover: the narrator's script"]
    try:
        d = pick_duration(pick)
    except (KeyError, TypeError, ValueError):
        return []
    est = len(text.split()) / NARRATION_WPS
    if est > d:
        return [f"narration runs about {est:.0f}s for a {d:.0f}s clip: cut the script or lengthen the clip"]
    if d - est < 3:
        return [f"narration ends about {d - est:.1f}s before the end: leave 3-8s for the streamer's own payoff line"]
    return []


def check_labels(pick):
    """Context captions must sit inside the clip and stay short: 1-4 words, e.g. *in disbelief*. A segment pick's
    labels use seconds of the finished clip (0 = its first frame)."""
    bad = []
    lo, hi = clip_bounds(pick)
    for lab in pick.get("labels") or []:
        try:
            a, b, text = float(lab["s"]), float(lab["e"]), str(lab["text"]).strip()
        except (KeyError, TypeError, ValueError):
            bad.append(f"label {lab!r} needs s, e (source seconds) and text")
            continue
        if not text or len(text.strip("*").split()) > 4:
            bad.append(f"label \"{text}\": 1-4 words, e.g. *in disbelief*")
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
    gate = (cfg or {}).get("selection_gate", gta)  # the own-channel selection rules; `streamers` opts in
    names = [w for c in (cfg or {}).get("channels") or [] for w in str(c.get("name", "")).split()]
    report = {}
    for n, pick in enumerate(picks, 1):
        entry = {}
        for h in pick.get("hooks") or [pick.get("hook", "")]:
            f, nt = check_hook(h, gta, names)
            if f or nt:
                entry.setdefault("hooks", {})[h] = {"fails": f, "notes": nt} if nt else {"fails": f}
        tags = pick.get("hashtags") or []
        for t in pick.get("titles") or []:
            f, nt = check_title(t, tags, topic, gta)
            if MOOD_NOTE in nt and streamer_clip(pick, names):  # a note alone lost to the ranker's 1.5x "relatable" score
                f, nt = f + [MOOD_NOTE], [x for x in nt if x != MOOD_NOTE]
            if f or nt:
                entry.setdefault("titles", {})[t] = {"fails": f, "notes": nt} if nt else {"fails": f}
        hs, ts = pick.get("hooks") or [], pick.get("titles") or []
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
        elif check_length_note(pick):
            entry["length_note"] = check_length_note(pick)
        if check_labels(pick):
            entry["labels"] = check_labels(pick)
        if check_narration(pick):
            entry["narration"] = check_narration(pick)
        if check_context_note(pick):
            entry["context_note"] = check_context_note(pick)
        if check_streamer_reacts(pick):
            entry["reacts"] = check_streamer_reacts(pick)
        if check_fx(pick):
            entry["fx"] = check_fx(pick)
        if check_stranger(pick):
            entry["stranger"] = check_stranger(pick)
        if gate and check_selection(pick):
            entry["selection"] = check_selection(pick)
        a_fails, a_notes = check_angles(pick) if gta else ([], [])
        if a_fails or a_notes:
            entry["angles"] = {"fails": a_fails, "notes": a_notes} if a_notes else {"fails": a_fails}
        if gate and check_cold(pick, names):
            entry["cold"] = check_cold(pick, names)
        q_fails, q_notes = check_question(pick)
        q_notes = q_notes if gate else []  # only the gta6/streamers selection-gate profiles track it
        if q_fails or q_notes:
            entry["question"] = {"fails": q_fails, "notes": q_notes} if q_notes else {"fails": q_fails}
        loop_fails, loop_notes = check_loop(pick)
        if loop_fails or loop_notes:
            entry["loop"] = {"fails": loop_fails, "notes": loop_notes} if loop_notes else {"fails": loop_fails}
        edit = check_spoiler(pick, None)
        cw = clip_words(pick, words, load) if words is not None and not check_segments(pick) else None
        if cw is not None:
            edit = check_spoiler(pick, cw) + [x for x in [check_opening(pick, cw)] if x] + check_dead_air(pick, cw) \
                + [x for x in [check_music(pick, cw)] if x]
        if edit:
            entry["edit"] = edit
        if gta and len(hs) >= 2 and not any(is_debate(x) for x in hs + ts):
            entry["debate"] = ("no hook or title asks the viewer for a verdict: if the clip has a real disagreement, "
                               "add one (\"Is xQc's aim *legit*?!\", \"Was Kai *wrong* for this?\"); skip if it has none")
        if len(pick.get("hooks") or []) >= 3 and len(used) < 3:
            entry["variety"] = f"hooks only use {sorted(used)}: give each variant a different structure to A/B test"
        if entry:
            report[f"video {n}"] = entry
    return report


# First 1.5 s of the source: our dark openings (USB, calling, Mickey) measured 21-39 brightness and flopped; our top
# Shorts opened at 75-98 with motion 7-18, our static flops at 0.7-2.9 (frames 32x56 grey, 8 fps, 0-255).
DARK_OPENING, STATIC_OPENING = 45, 3.5


def opening_frames(src, start, secs=1.5):
    """(brightness, motion) of the first `secs` of a clip from its source video; None when it can't be read."""
    import subprocess
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-ss", f"{float(start):.3f}", "-t", str(secs),
                          "-i", str(src), "-vf", "scale=32:56,fps=8", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         capture_output=True).stdout
    if len(raw) < 2 * 32 * 56:
        return None
    f = np.frombuffer(raw[:len(raw) // (32 * 56) * 32 * 56], np.uint8).reshape(-1, 56, 32).astype(float)
    return round(float(f.mean()), 1), round(float(np.abs(np.diff(f, axis=0)).mean()), 2)


def check_opening_frames(pick, job_dir):
    """{'fails': [...], 'notes': [...]} for a clip that opens dark (fail) or static (note); {} when it opens fine."""
    from .config import job_dir as resolve
    first = (pick.get("segments") or [pick])[0]
    src = (resolve(first["job"]) if first.get("job") else job_dir) / "source.mp4"
    got = src.exists() and opening_frames(src, first["start"])
    if not got:
        return {}
    bright, motion = got
    out = {}
    if bright < DARK_OPENING:
        out["fails"] = [f"opens dark (brightness {bright:.0f}, our flops 21-39, top Shorts 75-98): start on a lit "
                        "moment, the face reacting or visible action, or drop the clip"]
    if motion < STATIC_OPENING:
        out["notes"] = [f"opens static (motion {motion:.1f}, our flops 0.7-2.9, top Shorts 7-18): start where something "
                        "visibly happens or the streamer reacts, not on driving or standing around"]
    return out


def known_facecams(jobs_root, extra=()):
    """{channel: (job, face box)} from split picks in earlier jobs (newest wins), plus `extra` (job_dir, picks)."""
    import json
    found = []
    for pf in Path(jobs_root).glob("*/picks.json"):
        try:
            found.append((pf.stat().st_mtime, pf.parent, json.loads(pf.read_text(encoding="utf-8"))))
        except (OSError, ValueError):
            continue
    found.sort(key=lambda x: x[0])
    out = {}
    for _, jd, picks in found + [(0, Path(j), p) for j, p in extra]:
        channel = job_channel(jd)
        for pick in picks if channel and isinstance(picks, list) else []:
            for seg in (pick.get("segments") or [pick]) if isinstance(pick, dict) else []:
                lay = seg.get("layout") or pick.get("layout") or {}
                if lay.get("type") == "split" and lay.get("face") and not seg.get("job"):
                    out[channel] = (jd.name, lay["face"])
    return out


def job_channel(jd):
    import json
    try:
        return json.loads((Path(jd) / "job.json").read_text(encoding="utf-8")).get("channel")
    except (OSError, ValueError):
        return None


REQUIRE_FACE_FAIL = ("no face on screen: this profile needs the streamer's face in every clip (split clips kept 50% of "
                     "viewers vs 38% faceless, half the views): pick a moment where the facecam is on, or skip it")


def check_facecam(pick, job_dir, known, require=False):
    """Fails for a letterboxed (fit) clip from a channel whose earlier clips used the facecam: the faceless openings
    kept 38% of viewers vs 50% with a face. `"facecam": "hidden"` in the layout says the cam is off in that stretch;
    with `require` (the profile's `require_facecam`) every fit clip fails, hidden cam or not."""
    from .config import job_dir as resolve
    fails = []
    for seg in pick.get("segments") or [pick]:
        lay = seg.get("layout") or pick.get("layout") or {"type": "fit"}
        if lay.get("type", "fit") != "fit":
            continue
        if require:
            if REQUIRE_FACE_FAIL not in fails:
                fails.append(REQUIRE_FACE_FAIL)
            continue
        if lay.get("facecam") in ("hidden", "none"):
            continue
        jd = resolve(seg["job"]) if seg.get("job") else Path(job_dir)
        channel = job_channel(jd)
        if channel in known:
            job, face = known[channel]
            msg = (f"letterbox with no face, but {channel}'s streams have a facecam (job {job} used face {face}): "
                   f"run `clipper frame {jd.name} <s>` and use {{\"type\": \"split\", \"face\": [x, y, w, h]}}, or "
                   "add \"facecam\": \"hidden\" to the layout if the cam is off in this stretch")
            if msg not in fails:
                fails.append(msg)
    return fails


def is_debate(text):
    """A verdict question the viewer can argue in the comments."""
    t = plain(text)
    return bool("?" in t and DEBATE.search(t) and VERDICT.search(t))


def has_fails(report):
    return any(v.get("fails") for e in report.values() for k in ("hooks", "titles") for v in e.get(k, {}).values()) \
        or any((e.get("opening") or {}).get("fails") for e in report.values()) \
        or any("variety" in e or "length" in e or "labels" in e or "footage" in e or "fx" in e or "facecam" in e or "narration" in e
               or "stranger" in e or "selection" in e or (e.get("loop") or {}).get("fails") or (e.get("question") or {}).get("fails")
               or (e.get("angles") or {}).get("fails")
               for e in report.values())
