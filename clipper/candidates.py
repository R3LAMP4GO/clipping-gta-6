import math
import re

import numpy as np

# Clip length by content type, from research/viral-gta-shorts.md: reactions 9-25s, info clips up to ~58s.
PROFILES = {"reaction": {"target": 22, "min": 9, "max": 35}, "info": {"target": 45, "min": 20, "max": 58}}


REACTION_TITLE = re.compile(r"\breact(s|ion|ing)?\b|\blive\b|\bstream|\bvod\b|\bfirst time\b", re.I)


def clip_profile(lufs, events, title="", hype_per_min=0.0):
    """'reaction' or 'info'. Reactions show up as real loudness peaks, loud sound events, a title that says so
    (the trailer audio in a reaction often drowns out the streamer), or dense hype words."""
    x = np.asarray([v for v in lufs if v > -69], dtype=float)
    spread = float(np.percentile(x, 98) - np.percentile(x, 50)) if len(x) else 0.0
    loud_events = any(k in e["text"] for e in events for k in ("scream", "yell", "shout", "laugh", "cheer", "gasp"))
    reaction = spread >= 7 or loud_events or bool(REACTION_TITLE.search(title or "")) or hype_per_min >= 2
    return ("reaction" if reaction else "info"), round(spread, 1)


def auto_candidate_count(duration_s):
    """Longer videos get more candidates: about one per 2.5 minutes, between 4 and 25."""
    return max(4, min(25, round(duration_s / 150)))


def tier(score, jump_lu, hype, events, heat):
    """'strong' / 'maybe' / 'skip': is this moment worth posting, judged on signals the viral sample shared."""
    evidence = jump_lu >= 8 or hype >= 2 or events >= 1 or heat >= 0.6
    some = jump_lu >= 5 or hype >= 1 or heat >= 0.4
    if score >= 45 and evidence:
        return "strong"
    if score >= 30 and (evidence or some):
        return "maybe"
    return "skip"


def recommend(tiers, duration_s):
    """How many videos are worth exporting: every strong moment plus half the maybes, at most one per 3 minutes."""
    n = tiers.count("strong") + tiers.count("maybe") // 2
    return min(n, max(1, math.floor(duration_s / 180))) if n else 0


def smooth(x, k=5):
    if len(x) < k:
        return np.asarray(x, dtype=float)
    return np.convolve(x, np.ones(k) / k, mode="same")


def peaks(score, radius=5, limit=40):
    idx = []
    for i, v in enumerate(score):
        lo, hi = max(0, i - radius), min(len(score), i + radius + 1)
        if v > 0 and v >= score[lo:hi].max():
            idx.append(i)
    return sorted(idx, key=lambda i: score[i], reverse=True)[:limit]


def snap_window(start, end, sentences, min_s, max_s, peak=None):
    """Move start/end onto sentence boundaries so clips never cut mid-sentence."""
    starts = [s["s"] for s in sentences if start - 6 <= s["s"] <= start + 2]
    if starts:
        before = [s for s in starts if s <= start]
        start = max(before) if before else min(starts)
    ends = [s["e"] for s in sentences if end - 3 <= s["e"] <= end + 6]
    if ends:
        after = [e for e in ends if e >= end]
        end = min(after) if after else max(ends)
    if peak is not None and end < peak + 2:
        end = peak + 3
    if end - start < min_s:
        end = start + min_s
    if end - start > max_s:
        end = start + max_s
        inside = [s["e"] for s in sentences if start + min_s <= s["e"] <= end]
        if inside:
            end = max(inside)
    return round(max(0.0, start), 2), round(end, 2)


def overlap(a, b):
    inter = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    return inter / min(a[1] - a[0], b[1] - b[0])


def window_score(score, start, end):
    vals = np.sort(score[int(start):max(int(start) + 1, int(end))])[::-1]
    top = vals[:max(1, len(vals) * 3 // 10)]
    return float(0.5 * vals[0] + 0.5 * top.mean())


def pick_windows(score, sentences, duration, target, min_s, max_s, count, max_overlap=0.3):
    sm = smooth(score)
    chosen = []
    for p in peaks(sm):
        start, end = snap_window(max(0.0, p - 0.4 * target), min(duration, p + 0.6 * target),
                                 sentences, min_s, max_s, peak=p)
        end = min(end, duration)
        if end - start < min_s * 0.8:
            continue
        if any(overlap((start, end), (c["start"], c["end"])) > max_overlap for c in chosen):
            continue
        chosen.append({"start": start, "end": end, "peak": int(p),
                       "score": round(100 * window_score(sm, start, end))})
        if len(chosen) >= count:
            break
    chosen.sort(key=lambda c: c["score"], reverse=True)
    return chosen
