"""Benchmark for the moment finder's signals: 83 pairs of a 100K+ outlier and a flop from the same streamer-clip channel
(research/moment-pairs.json; transcripts and per-second loudness, no media). A signal is useful when it rates the hit
above the flop well over half the time on the held-out split (pairs nobody read while writing rules)."""
import json
import random

import numpy as np

from . import signals
from .config import ROOT

DATA = ROOT / "research" / "moment-pairs.json"


def _words(clip):
    return [{"w": w, "s": s, "e": e} for w, s, e in clip["words"]]


def _loud_spread(clip, cfg):
    x = np.asarray([v for v in clip["lufs"] if v > -69] or [-70.0])
    return float(np.percentile(x, 98) - np.percentile(x, 50))


def _jump(clip, cfg):
    _, raw = signals.jump_per_second(clip["lufs"])
    return float(raw.max()) if len(raw) else 0.0


def _hype(clip, cfg):
    n = max(len(clip["lufs"]), 1)
    events = [{"text": t, "s": s} for t, s in clip["events"]]
    _, hits = signals.keywords_per_second(_words(clip), events, set(cfg.get("hype_words", [])), n)
    return sum(len(h) for h in hits) / (n / 60)


SIGNALS = {"loudness spread (LU)": _loud_spread, "volume jump (LU)": _jump, "hype words per minute": _hype}


def win_rate(pairs, fn, cfg, boots=2000, seed=1):
    """(share of pairs whose hit scores higher, ties half, 5th and 95th bootstrap percentile)."""
    w = [1.0 if a > b else 0.5 if a == b else 0.0 for a, b in ((fn(p["hit"], cfg), fn(p["flop"], cfg)) for p in pairs)]
    if not w:
        return None
    rng = random.Random(seed)
    b = sorted(sum(rng.choice(w) for _ in w) / len(w) for _ in range(boots))
    return round(sum(w) / len(w), 3), round(b[boots // 20], 3), round(b[-boots // 20 - 1], 3)


def run(cfg, path=DATA, extra=None):
    pairs = json.loads(path.read_text(encoding="utf-8"))
    splits = {s: [p for p in pairs if p["split"] == s] for s in ("seen", "held-out")}
    lines = ["| signal | " + " | ".join(f"{s} ({len(v)} pairs)" for s, v in splits.items()) + " |", "|---|---|---|"]
    out = {}
    for name, fn in {**SIGNALS, **(extra or {})}.items():
        out[name] = {s: win_rate(v, fn, cfg) for s, v in splits.items()}
        lines.append(f"| {name} | " + " | ".join(f"{r[0]:.0%} ({r[1]:.0%}-{r[2]:.0%})" for r in out[name].values()) + " |")
    return out, "Hit rated above the flop (90% range); 50% is a coin flip.\n\n" + "\n".join(lines)
