"""Data-fitted hook simulator: how a hook's features moved views on 3,481 gaming Shorts (research/gaming-shorts-titles.json).

Each Short's views are compared with the 30 Shorts its own channel posted around it, so channel size and growth cancel
out. A feature's effect is the views multiplier for Shorts that have it vs the same channels' Shorts that don't. The
simulation resamples those Shorts many times, so every effect carries its real uncertainty, and reports how often
each hook comes out on top. These are title-level effects applied to on-screen hooks, so they rank hooks against
each other; they don't forecast views."""
import json
import math
import random
import re
import statistics as st
from functools import lru_cache

from . import hooks
from .config import ROOT

DATA = ROOT / "research" / "gaming-shorts-titles.json"
OWN_DATA = ROOT / "research" / "own-uploads.json"  # our posted clips' views, written by the autopilot
STRATEGY = ROOT / "research" / "hook-strategy.json"


def scope_chain(niche):
    """Our own uploads first once we have them, then the niche, then all gaming."""
    return (["own"] if OWN_DATA.exists() else []) + [niche, None]
FAMOUS = re.compile(r"\b(xqc|kai|cenat|caseoh|tyler1|sketch|speed|ishowspeed|ninja|shroud|tim|timthetatman|nickmercs|"
                    r"swagg|jynxzi|drake|mrbeast|faze|pokimane|adin|duke dennis|fanum|druski|snoop|ed sheeran)\b", re.I)
ANNOUNCE = re.compile(r"\b(update|announce\w*|explained|patch|season \d+|dlc|released?|coming soon|now live|"
                      r"available now)\b", re.I)
OWN = {"KaiCenatLive": "kai|cenat", "xQcOW": "xqc", "TimTheTatman": "tim|timthetatman", "NICKMERCS": "nickmercs",
       "Swagg": "swagg", "Ninja": "ninja", "Jynxzi": "jynxzi"}
FEATURES = ["question", "tease", "withheld / negation", "number promise", "shock fact", "first-person claim",
            "relatable situation", "premise + twist", "superlative", "names a streamer", "vague",
            "all caps", "announcement wording"]


def features(text, own=None, extra_names=()):
    t = re.sub(r"#\S+", "", hooks.plain(text)).strip()
    f = set(hooks.structures(t))
    names = {m.lower() for m in FAMOUS.findall(t)} | {n for n in extra_names if re.search(rf"\b{n}\b", t, re.I)}
    if any(not (own and re.fullmatch(own, n)) for n in names):  # naming yourself on your own channel says nothing
        f.add("names a streamer")
    if len(hooks.content_words(t)) <= 1:
        f.add("vague")
    if re.search("[A-Z]", t) and not re.search("[a-z]", t):
        f.add("all caps")
    if ANNOUNCE.search(t):
        f.add("announcement wording")
    return f


@lru_cache(maxsize=None)
def dataset(niche=None):
    rows = json.loads(DATA.read_text(encoding="utf-8"))
    if OWN_DATA.exists():
        rows += json.loads(OWN_DATA.read_text(encoding="utf-8"))
    return [(r["lift"], features(r["t"], OWN.get(r["ch"]))) for r in rows if niche in (None, r["niche"])]


def effects(rows, rng=None):
    """log10 views multiplier per feature; with rng, one bootstrap resample (for the simulation)."""
    if rng:
        rows = [rng.choice(rows) for _ in rows]
    out = {}
    for k in FEATURES:
        on = [l for l, f in rows if k in f]
        off = [l for l, f in rows if k not in f]
        out[k] = (st.mean(on) - st.mean(off), len(on)) if len(on) >= 10 and off else (0.0, len(on))
    return out


@lru_cache(maxsize=None)
def _intervals(niche, boots=200, seed=3):
    rng = random.Random(seed)
    out = {}
    for scope in scope_chain(niche):
        rows = dataset(scope)
        base = effects(rows)
        samples = [effects(rows, rng) for _ in range(boots)]
        for k in FEATURES:
            b = sorted(x[k][0] for x in samples)
            out[scope, k] = (base[k][0], b[boots // 20], b[-boots // 20 - 1], base[k][1])
    return out


@lru_cache(maxsize=None)
def scopes(niche="gta"):
    """The narrowest scope that is conclusive on its own (n>=15, 90% range excludes 1x); else all gaming."""
    iv = _intervals(niche)

    def conclusive(s, k):
        return iv[s, k][3] >= 15 and (iv[s, k][1] > 0 or iv[s, k][2] < 0)
    return {k: next((s for s in scope_chain(niche)[:-1] if conclusive(s, k)), None) for k in FEATURES}


def effect_table(niche="gta"):
    """{feature: (multiplier, low, high, n, scope)}."""
    iv, sc = _intervals(niche), scopes(niche)
    return {k: (*(10 ** v for v in iv[sc[k], k][:3]), iv[sc[k], k][3], sc[k] or "all gaming") for k in FEATURES}


MODIFIERS = {"names a streamer", "vague", "all caps", "announcement wording"}


def score(feats, effect):
    """A hook's strongest structure plus its modifiers. Structures overlap ("Nobody…" is relatable and withheld), so
    adding them would count one idea twice."""
    structs = [effect(k) for k in feats if k not in MODIFIERS]
    return (max(structs) if structs else 0.0) + sum(effect(k) for k in feats if k in MODIFIERS)


def simulate(pick, runs=200, niche="gta", seed=7):
    rng = random.Random(seed)
    hs = pick.get("hooks") or []
    names = [t.lstrip("#").lower() for t in pick.get("hashtags") or []
             if t.lstrip("#").lower() not in {"shorts", "gta6", "gtavi", "gtarp", "nopixel", "gta", "funny", "gaming"}]
    feats = {h: features(h, extra_names=names) for h in hs}
    pools = {s: dataset(s) for s in scope_chain(niche)}
    scope = scopes(niche)
    scores = {h: [] for h in hs}
    wins = {h: 0 for h in hs}
    for _ in range(runs):
        eff = {s: effects(rows, rng) for s, rows in pools.items()}
        run = {h: score(feats[h], lambda k: eff[scope[k]][k][0]) for h in hs}
        for h in hs:
            scores[h].append(run[h])
        wins[max(run, key=run.get)] += 1
    out = []
    for h in hs:
        s = sorted(scores[h])
        out.append({"hook": h, "x": 10 ** st.mean(s), "low": 10 ** s[runs // 20], "high": 10 ** s[-runs // 20 - 1],
                    "wins": wins[h] / runs, "why": sorted(feats[h]), "check": hooks.check_hook(h)[0]})
    return sorted(out, key=lambda r: -r["x"])


def report(picks, keep=3, **kw):
    lines = []
    for n, pick in enumerate(picks, 1):
        kept, seen = [], set()
        table = effect_table(kw.get("niche", "gta"))
        lines += [f"video {n} ({pick.get('clip_type', 'no clip_type')}):",
                  "  rank  views vs channel norm (90% range)  wins  hook  ← features"]
        for i, r in enumerate(simulate(pick, **kw), 1):
            flag = f"  [FAILS check: {'; '.join(r['check'])}]" if r["check"] else ""
            structs = [k for k in r["why"] if k not in MODIFIERS]
            main = max(structs, key=lambda k: table[k][0]) if structs else None  # the hook's strongest type
            if not r["check"] and len(kept) < keep and main not in seen:
                kept.append(f"{hooks.plain(r['hook'])} [{main}]")
                seen.add(main)
            lines.append(f"  {i:>4}  {r['x']:.2f}x ({r['low']:.2f}–{r['high']:.2f})  {r['wins']:>13.0%}  "
                         f"{hooks.plain(r['hook'])}  ← {', '.join(r['why']) or 'none'}{flag}")
        lines.append(f"  keep (top {keep}, different types): " + " | ".join(kept))
    lines.append("Effects fitted on 3,481 gaming Shorts' titles (research/gaming-shorts-titles.json); they rank hooks, "
                 "they don't forecast views.")
    return "\n".join(lines)


def effects_report(niche="gta"):
    rows = sorted(effect_table(niche).items(), key=lambda kv: -kv[1][0])
    ch = channel_effects()
    return "\n".join(f"{'KEEP ' if lo > 1 else 'DROP ' if hi < 1 else 'meh  '} {x:.2f}x ({lo:.2f}–{hi:.2f}) "
                     f"n={n:<4} [{scope}]  {k}" + (f"  (works on {ch[k][2]} channel{'s' * (ch[k][2] != 1)}: "
                                                   "only for list/info clips)" if k in ch and ch[k][2] < 3 else "")
                     for k, (x, lo, hi, n, scope) in rows)


HOOK_TYPES = ["number promise", "shock fact", "relatable situation", "withheld / negation", "question", "tease",
              "superlative"]
# Which hook types can be written honestly for each clip type (a "4 things…" hook on a skit promises a list the
# clip never delivers). The playbook's hook lists are the ranked subset of these.
FITS = {
    "comedy": {"relatable situation", "withheld / negation", "question", "tease", "superlative"},
    "reaction": {"relatable situation", "withheld / negation", "question", "tease", "superlative"},
    "news": {"number promise", "shock fact", "withheld / negation", "question", "tease", "superlative"},
    "gameplay": {"shock fact", "withheld / negation", "question", "tease", "superlative"},
    "showcase": {"number promise", "shock fact", "question", "tease", "superlative"},
}


@lru_cache(maxsize=None)
def channel_effects(min_on=6):
    """Per hook type: (mean, sd, channels), the effect measured inside each channel separately, so one big
    channel can't carry it. sd is how much the effect changes from channel to channel, i.e. with the content."""
    rows = json.loads(DATA.read_text(encoding="utf-8"))
    by_ch = {}
    for r in rows:
        by_ch.setdefault(r["ch"], []).append((r["lift"], features(r["t"], OWN.get(r["ch"]))))
    out = {}
    for k in HOOK_TYPES + ["vague"]:
        per = []
        for R in by_ch.values():
            on = [l for l, f in R if k in f]
            off = [l for l, f in R if k not in f]
            if len(on) >= min_on and off:
                per.append(st.mean(on) - st.mean(off))
        # shrink toward 0 when few channels back it (number promise rests on MrBossFTW alone)
        out[k] = ((st.mean(per) * len(per) / (len(per) + 3), st.pstdev(per) if len(per) > 1 else 0.15, len(per))
                  if per else (0.0, 0.15, 0))
    return out


def residual_sd():
    return st.pstdev([r["lift"] for r in json.loads(DATA.read_text(encoding="utf-8"))])


def strategies(uploads=8, runs=3000, judgment=(0.0, 0.5, 0.8), clip_sd=0.25, repeat_cost=0.05, seed=11):
    """Same number of uploads, split differently: one clip with a variant per hook type, vs several clips with
    Claude's top-k hooks. Returns {judgment r: {strategy: (mean views x per upload, best upload x)}}."""
    eff = channel_effects()
    noise = residual_sd()
    forced = eff["vague"][0]  # a hook the clip can't pay off reads like a vague one
    rng = random.Random(seed)
    plans = {"every hook type (7 variants, incl. ones that don't fit)": ("all", 7),
             "every hook type that fits (Claude drops misfits)": ("fit", None),
             "Claude's best 4": ("top", 4), "Claude's best 3": ("top", 3), "Claude's best 2": ("top", 2),
             "Claude's best 1 (one per clip)": ("top", 1)}
    kinds = list(FITS)
    results = {}
    for r in judgment:
        res = {name: [[], [], []] for name in plans}
        for _ in range(runs):
            kind = rng.choice(kinds)
            # candidate moments from one source, best first; later clips are weaker
            quality = sorted((rng.gauss(0, clip_sd) for _ in range(12)), reverse=True)
            clips = []
            for q in quality:
                true = {}
                for t in HOOK_TYPES:
                    m, sd, _ = eff[t]
                    true[t] = rng.gauss(m, sd) if t in FITS[kind] else forced
                est = {t: r * v + (1 - r * r) ** 0.5 * rng.gauss(0, 0.12) for t, v in true.items()}
                clips.append((q, true, est))
            for name, (how, k) in plans.items():
                views = []
                for q, true, est in clips:
                    repeat = 0
                    if how == "all":
                        types = HOOK_TYPES
                    else:
                        fit = sorted((t for t in HOOK_TYPES if t in FITS[kind]), key=lambda t: -est[t])
                        types = fit if how == "fit" else fit[:k]
                    for t in types:
                        # each extra variant of the same clip competes for viewers who saw the first
                        views.append(q + true[t] - repeat_cost * repeat + rng.gauss(0, noise))
                        repeat += 1
                        if len(views) == uploads:
                            break
                    if len(views) == uploads:
                        break
                res[name][0].append(st.mean(views))
                res[name][1].append(max(views))
                res[name][2].append(max(views) >= 1.0)  # an upload at 10x the channel norm: a breakout
        results[r] = {n: (10 ** st.mean(v[0]), 10 ** st.mean(v[1]), st.mean(v[2])) for n, v in res.items()}
    return results


def recommended_hooks(default=3):
    """Hooks per clip with the best breakout chance in the last `clipper simulate --strategies` run."""
    if STRATEGY.exists():
        return int(json.loads(STRATEGY.read_text(encoding="utf-8")).get("recommended_hooks", default))
    return default


def strategies_report(uploads=8):
    eff = channel_effects()
    lines = ["Hook type effects measured inside each channel, shrunk when few channels back them:"]
    for t in sorted(HOOK_TYPES, key=lambda t: -eff[t][0]):
        m, sd, n = eff[t]
        lines.append(f"  {10 ** m:.2f}x  ({n:>2} channels, varies ±{sd:.2f} log10 by channel)  {t}")
    lines.append(f"\nSame {uploads} uploads per source, Claude's read of fit r=0.5. Breakout = chance at least one "
                 "upload reaches 10x the channel norm.")
    lines.append("clip gap = how much better a source's best moment is than its 8th; repeat cost = audience lost per "
                 "extra variant of the same clip (log10).")
    breakout = {}
    for clip_sd in (0.1, 0.25, 0.4):
        for cost in (0.0, 0.05, 0.1):
            rows = strategies(uploads, runs=2000, judgment=(0.5,), clip_sd=clip_sd, repeat_cost=cost)[0.5]
            for n, v in rows.items():
                breakout.setdefault(n, []).append(v[2])
            ranked = sorted(rows.items(), key=lambda kv: -kv[1][2])
            lines.append(f"  clip gap {clip_sd:.2f}, repeat cost {cost:.2f}:  "
                         + "  >  ".join(f"{n.split(' (')[0]} {v[2]:.0%}" for n, v in ranked[:3]))
    avg = {n: st.mean(v) for n, v in breakout.items()}
    best_k = max((n for n in avg if n.startswith("Claude's best")), key=avg.get)
    k = int(re.search(r"best (\d)", best_k).group(1))
    STRATEGY.write_text(json.dumps({"recommended_hooks": k, "breakout_chance": avg, "uploads": uploads},
                                   indent=2), encoding="utf-8")
    lines.append("\nAverage breakout chance: " + " · ".join(f"{n.split(' (')[0]} {v:.1%}"
                                                          for n, v in sorted(avg.items(), key=lambda kv: -kv[1])))
    lines.append(f"Recommended hooks per clip: {k} (saved to research/hook-strategy.json; prefs hooks_per_video=auto "
                 "uses it)")
    return "\n".join(lines)
