"""Streamer and subject demand: how often a clip naming a streamer (or about a subject) is 100K+ on the 25 watched
clip channels, inside each channel (research/streamer-demand-2026-11.json). Printed in candidates.md and used to
order sources."""
import json
import re
from datetime import datetime
from pathlib import Path

from . import profile100k as p

DEMAND = p.RES / "streamer-demand-2026-11.json"
MIN_TITLES = 15  # fewer titles than this: the rate is shown but not used to order sources
SUBJECTS = {
    "gta": r"\bgta\b|grand theft|los santos|vice city",
    "irl": r"\birl\b|\bin public\b|\bstreet\b|\bmall\b|\bstore\b|\brestaurant\b|\bairport\b",
    "sports": r"\bbasketball\b|\bnba\b|\bfootball\b|\bsoccer\b|\bnfl\b|\bboxing\b|\bufc\b|\bronaldo\b|\bmessi\b|"
              r"\blebron\b",
    "music": r"\bsings?\b|\bsang\b|\bsong\b|\brap(s|ped|per)?\b|\bconcert\b|\bbeat\b|\bfreestyle\b",
    "family": r"\bmom\b|\bmum\b|\bdad\b|\bmother\b|\bfather\b|\bsister\b|\bbrother\b|\bgrandma\b|\bfamily\b",
    "dating": r"\bgirlfriend\b|\bgf\b|\bdate\b|\bdating\b|\bcrush\b|\brizz\b|\bkiss(es|ed)?\b",
    "money": r"\$|\bmoney\b|\bmillion\b|\bthousand\b|\bpaid\b|\bbuys?\b|\bbought\b|\bgift(s|ed)?\b",
    "scare": r"\bscar(e|ed|y)\b|\bjumpscare\b|\bhorror\b|\bghost\b",
    "fortnite": r"\bfortnite\b",
    "minecraft": r"\bminecraft\b",
    "celebrity": r"\bdrake\b|\bkanye\b|\bye\b|\bsnoop\b|\bmrbeast\b|\bcelebrity\b|\brapper\b",
}
SUBJECT_RES = {k: re.compile(v, re.I) for k, v in SUBJECTS.items()}


def subjects_in(title):
    return [k for k, pat in SUBJECT_RES.items() if pat.search(title or "")]


def build(split, reps=p.REPS, seed=p.SEED):
    rows = []
    for v in split["videos"]:
        names, subs = p.streamers_in(p.title_body(v["t"])), subjects_in(v["t"])
        rows.append({"ch": v["ch"], "group": v["group"], "names": names, "subjects": subs})
    out = {}
    for kind, field in (("streamers", "names"), ("subjects", "subjects")):
        keys = sorted({k for r in rows for k in r[field]})
        table = {}
        for k in keys:
            rs = [dict(r, has=k in r[field]) for r in rows]
            n = sum(r["has"] for r in rs)
            hi = sum(r["has"] and r["group"] == "high" for r in rs)
            t = p.compare(rs, "has", "binary", reps=reps, seed=seed)
            table[k] = {"titles": n, "high": hi, "high_rate": round(hi / n, 3) if n else None, "lift": t.get("lift"),
                        "range": t.get("range"), "verdict": t.get("verdict") if n >= MIN_TITLES else "too few"}
        out[kind] = dict(sorted(table.items(), key=lambda kv: (kv[1]["verdict"] == "too few", -(kv[1]["lift"] or 0))))
    base = sum(r["group"] == "high" for r in rows)
    return {"built": datetime.now().strftime("%Y-%m-%d"), "base_high_rate": round(base / len(rows), 3) if rows else None,
            "titles": len(rows), "channels": len({r["ch"] for r in rows}), "min_titles": MIN_TITLES,
            "note": "lift = in-channel Mantel-Haenszel; high = 100K+ and 5x+, low = <100K and <1x", **out}


def build_files(split=p.SPLIT, out=DEMAND):
    d = build(p.load_json(split, {"videos": []}))
    Path(out).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return d


def load(path=DEMAND):
    return p.load_json(path, {})


def score_for(text, demand=None):
    """The best usable streamer lift among names in `text` (a channel name, title or transcript snippet), else None."""
    d = demand if demand is not None else load()
    best = None
    for name in p.streamers_in(text or ""):
        row = (d.get("streamers") or {}).get(name)
        if row and row.get("verdict") != "too few" and row.get("lift") is not None:
            best = max(best or 0, row["lift"])
    return best


def line_for(text, demand=None):
    """One line for candidates.md: each named streamer's and subject's 100K+ rate and in-channel lift."""
    d = demand if demand is not None else load()
    if not d:
        return None
    parts = []
    for kind, keys in (("streamers", p.streamers_in(text or "")), ("subjects", subjects_in(text or ""))):
        for k in keys:
            row = (d.get(kind) or {}).get(k)
            if row:
                rng = f" [{row['range'][0]}-{row['range'][1]}]" if row.get("range") else ""
                parts.append(f"{k} {row['high_rate']:.0%} 100K+ of {row['titles']} titles, {row['lift']}x{rng} "
                             f"({row['verdict']})")
    if not parts:
        return None
    return f"Demand (base {d['base_high_rate']:.0%} 100K+ on {d['channels']} clip channels): " + "; ".join(parts)


def show(d):
    lines = [f"Demand built {d['built']}: base 100K+ rate {d['base_high_rate']:.0%} over {d['titles']} titles, "
             f"{d['channels']} channels"]
    for kind in ("streamers", "subjects"):
        lines.append(f"\n{kind}:")
        for k, r in d.get(kind, {}).items():
            rng = f"[{r['range'][0]}-{r['range'][1]}]" if r.get("range") else ""
            lines.append(f"  {k:<16} {r['high']:>4}/{r['titles']:<5} {r['high_rate']:.0%}  {r['lift']}x {rng} {r['verdict']}")
    return "\n".join(lines)
