"""Clip type -> the hook structures, styles and defaults that fit it (research/viral-gta-shorts.md#playbook)."""
import re

PLAYBOOK = {
    "reaction": {
        "what": "a streamer reacting to GTA 6 footage (trailer, gameplay, news); their face and voice are the payoff",
        "hooks": ["relatable situation", "withheld / negation", "question", "tease"],
        "examples": ["Me watching *GTA 6* with my mom in the room", "Kai was NOT ready for *this*",
                     "Why couldn't Kai watch this?", "Wait for Kai's face at the end..."],
        "hook_style": "bold", "caption_style": "boxed", "voiceover": False, "layout": "split if facecam",
        "length": "9–25s", "evidence": "Kai Cenat Live 6.8M / 1.2M: face + 1-word Bebas captions, no narrator",
    },
    "comedy": {
        "what": "an absurd or funny scene with several people (RP, skits, group chaos); the situation is the joke",
        "hooks": ["relatable situation", "withheld / negation", "question", "tease"],
        "examples": ["POV: you're the hostage in *GTA 6*", "Nobody expected the hostages to *SING*",
                     "Why are the hostages singing?", "Wait until the hostages start singing..."],
        "hook_style": "box", "caption_style": "comic", "voiceover": False, "layout": "fit",
        "length": "15–40s (let the bit land)",
        "evidence": "RDCworld1 5M: meme box 'How Playing GTA 6 Is Gonna Be 😂'; Jaden Williams 2M skit",
    },
    "news": {
        "what": "information: features, leaks, prices, dates, facts about GTA 6, usually narrated",
        "hooks": ["number promise", "shock fact", "withheld / negation", "question"],
        "examples": ["4 NEW features coming in *GTA 6*", "The *GTA 6* map is 2x BIGGER",
                     "Kids CAN'T play *GTA 6*", "What happens if you shoot the moon?"],
        "hook_style": "bold", "caption_style": "bold", "voiceover": "if nobody narrates", "layout": "fit",
        "length": "30–58s", "evidence": "MrBossFTW 51M / 10M / 9.7M: Montserrat Black caps pinned all video",
    },
    "gameplay": {
        "what": "a gameplay moment: a stunt, fail, glitch, speedrun or chaos where something surprising happens",
        "hooks": ["shock fact", "superlative", "question", "tease"],
        "examples": ["He beat it in 3 minutes", "The craziest *GTA 6* escape ever",
                     "How did he survive that fall?", "Watch the cop car at the end..."],
        "hook_style": "label", "caption_style": "comic", "voiceover": False, "layout": "split if facecam",
        "length": "9–25s", "evidence": "shock fact 1.68x, question 1.24x on GTA Shorts; Typical Gamer 1.3M comic captions",
    },
    "showcase": {
        "what": "trailer, screenshots or graphics with no one talking; needs context added",
        "hooks": ["shock fact", "number promise", "question", "tease"],
        "examples": ["Rockstar spent 10 years on *this*", "3 details you missed in *GTA 6*",
                     "Are these *GTA 6* graphics real?", "Look at the water physics in *GTA 6*..."],
        "hook_style": "bold", "caption_style": "bold", "voiceover": True, "layout": "fit",
        "length": "20–45s", "evidence": "MrBossFTW 'GTA 6 GRAPHICS' 1.2M, Rockstar cover art 16M",
    },
    "scenario": {
        "what": "a curiosity gap: the streamer makes, finds, tries or shows something NEW (a combo, a trick, a room, "
                "a build, a place, a first try) and the hook names that it exists but withholds what it is or how it "
                "turns out, so the viewer stays to see it; beats escalate to a payoff (a reveal or a face); often "
                "quiet, no scream needed",
        "hooks": ["question", "withheld / negation", "tease", "relatable situation"],
        "examples": ["What new *combo* did Kai just invent?", "Nobody's seen Kai's new *getaway car*",
                     "Wait till you see the room Kai *built*...", "Me showing my friends my new *setup*"],
        "hook_style": "bold", "caption_style": "boxed", "voiceover": False, "layout": "split if facecam",
        "length": "15–55s (cut on the reveal; 60s max)",
        "evidence": "Mitro 'Kai Just Invented A New Sauce' 1.5M on 39.6k subs (18s, near silent); "
                    "Kai Cenat Live 'Visits The AMP House In GTA RP' 3.7M (55s tour)",
    },
}
# Non-GTA profiles: same structures and styles (they hold on 3,481 gaming Shorts), examples without GTA 6.
GENERIC = {
    "reaction": {"what": "a streamer reacting to something on stream; their face and voice are the payoff",
                 "examples": ["Me watching this with my mom in the room", "He was NOT ready for *this*",
                              "Why couldn't he finish the game?", "Wait for his mom's face at the end..."]},
    "comedy": {"what": "an absurd or funny scene with several people (skits, group chaos); the situation is the joke",
               "examples": ["POV: you're the hostage in his *stream*", "Nobody expected the hostages to *SING*",
                            "Why are the hostages singing?", "Wait until the hostages start singing..."]},
    "news": {"what": "information: updates, leaks, prices, dates, facts about the game, usually narrated",
             "examples": ["4 NEW features coming this season", "The new map is 2x BIGGER",
                          "Kids CAN'T play this game", "What happens if you shoot the moon?"]},
    "gameplay": {"examples": ["He beat it in 3 minutes", "The craziest *escape* ever",
                              "How did he survive that fall?", "Watch the cop car at the end..."]},
    "showcase": {"examples": ["They spent 10 years on *this*", "3 details you missed in the *trailer*",
                              "Are these graphics real?", "Look at the water physics..."]},
    "scenario": {"what": "a curiosity gap: the streamer makes, finds, tries or shows something NEW and the hook "
                         "names that it exists but withholds what it is or how it turns out; beats escalate to a "
                         "payoff (a reveal or a face); often quiet",
                 "examples": ["What new *combo* did he just invent?", "Nobody's seen his new *loadout*",
                              "Wait till you see the room he *built*...", "Me showing my friends my new *setup*"]},
}


def for_profile(cfg=None):
    """GTA research playbook for `research: gta` profiles (or no cfg), else the generic one; then the profile's
    `playbook:` overrides, per clip type and key."""
    from .hooks import is_gta
    base = {k: {**v, **({} if is_gta(cfg) else {**GENERIC[k], "evidence": "3,481 gaming Shorts "
                                                 "(research/gaming-shorts-titles.json)"})} for k, v in PLAYBOOK.items()}
    for kind, over in ((cfg or {}).get("playbook") or {}).items():
        base[kind] = {**base.get(kind, {}), **over}
    return base


RP = re.compile(r"\b(rp|roleplay|role-play|nopixel|heist|skit|prank|trolling|funny|hostage|cops?)\b", re.I)
NEWS = re.compile(r"\b(news|update|leak(ed|s)?|features?|price|cost|release|confirmed|details|everything|map|"
                  r"announcement|trophies|rumou?rs?)\b", re.I)
SHOWCASE = re.compile(r"\b(screenshots?|trailer|graphics|cover art|images|footage)\b", re.I)
GAMEPLAY = re.compile(r"\b(speedrun|glitch|stunt|fail|chaos|mod|backflip|challenge|world record|pacifist)\b", re.I)
REACT = re.compile(r"\breact(s|ion|ing)?\b", re.I)


def guess_type(title, profile, words_per_min, loud_events, multi_voice_hint=False):
    """Best-guess clip type for a source; the agent confirms it from the contact sheets and transcript."""
    t = title or ""
    if REACT.search(t):
        return "reaction"
    if RP.search(t) or loud_events and multi_voice_hint:
        return "comedy"
    if words_per_min < 20:  # barely anyone talking
        return "showcase"
    if GAMEPLAY.search(t):
        return "gameplay"
    if NEWS.search(t) or SHOWCASE.search(t):
        return "news" if words_per_min >= 60 else "showcase"
    return "reaction" if profile == "reaction" else "news"


def plan_text(kind, playbook=None):
    p = (playbook or PLAYBOOK)[kind]
    return (f"{kind}: {p['what']}. Hooks in this order: {', '.join(p['hooks'])} (e.g. "
            + "; ".join(f'\"{e}\"' for e in p["examples"]) + f"). hook_style {p['hook_style']}, caption_style "
            f"{p['caption_style']}, voiceover {p['voiceover']}, layout {p['layout']}, length {p['length']}.")
