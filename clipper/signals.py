import re
import subprocess

import numpy as np

M_RE = re.compile(r"t:\s*([\d.]+)\s.*?M:\s*(-?[\d.]+)")
I_RE = re.compile(r"I:\s+(-?[\d.]+) LUFS")
SILENCE = -70.0
LOUD_EVENTS = ("scream", "yell", "shout", "laugh", "cheer", "gasp", "applause", "explosion", "gunshot")


def loudness_per_second(media):
    """Peak momentary loudness (LUFS) for each second, via FFmpeg's ebur128 filter."""
    res = subprocess.run(["ffmpeg", "-nostats", "-i", str(media), "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True, check=True)
    per = {}
    for t, m in M_RE.findall(res.stderr):
        sec = int(float(t))
        per[sec] = max(per.get(sec, SILENCE), max(float(m), SILENCE))
    n = max(per) + 1 if per else 0
    return [per.get(i, SILENCE) for i in range(n)]


def integrated_loudness(media):
    res = subprocess.run(["ffmpeg", "-nostats", "-i", str(media), "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True, check=True)
    found = I_RE.findall(res.stderr)
    return float(found[-1]) if found else None


def norm_spikes(x):
    """Scale so the video's typical level is 0 and its top 2% is 1; clip outside."""
    x = np.asarray(x, dtype=float)
    if not len(x):
        return x
    base, top = np.percentile(x, 50), np.percentile(x, 98)
    if top - base < 1e-6:
        return np.zeros_like(x)
    return np.clip((x - base) / (top - base), 0, 1)


def jump_per_second(lufs, lookback=8, gap=2, full_scale=12.0):
    """How far each second jumps above the few seconds before it (LU), raw and scaled 0-1.
    A scream right after normal talk is what the 500k+ reaction Shorts open on."""
    x = np.asarray(lufs, dtype=float)
    raw = np.zeros(len(x))
    if not len(x):
        return raw, raw
    voiced = x[x > SILENCE + 1]
    # baseline never drops below normal talking level, so speech starting after silence isn't a "jump"
    floor = (np.median(voiced) - 3) if len(voiced) else SILENCE
    for t in range(len(x)):
        a, b = max(0, t - lookback), max(0, t - gap + 1)
        if b - a >= 2:
            raw[t] = max(0.0, x[t] - max(np.median(x[a:b]), floor))
    return np.clip(raw / full_scale, 0, 1), raw


def heatmap_per_second(info, n):
    out = np.zeros(n)
    for h in info.get("heatmap") or []:
        a, b = int(h["start_time"]), max(int(h["start_time"]) + 1, int(h["end_time"]))
        out[a:min(b, n)] = h.get("value", 0)
    return out / out.max() if out.max() > 0 else out


def keywords_per_second(words, events, hype_words, n):
    out = np.zeros(n)
    hits = [[] for _ in range(n)]
    text = [re.sub(r"[^\w' ]", "", w["w"].lower()) for w in words]
    for i, w in enumerate(words):
        for size in (1, 2, 3, 4):
            phrase = " ".join(text[i:i + size])
            if phrase in hype_words:
                sec = min(int(w["s"]), n - 1)
                out[sec] += 1
                hits[sec].append(phrase)
    for ev in events:
        if any(k in ev["text"] for k in LOUD_EVENTS):
            sec = min(int(ev["s"]), n - 1)
            out[sec] += 1.5
            hits[sec].append(f"({ev['text']})")
    return np.clip(out / 2, 0, 1), hits


def speech_rate_per_second(words, n):
    out = np.zeros(n)
    for w in words:
        sec = int(w["s"])
        if sec < n:
            out[sec] += 1
    smooth = np.convolve(out, np.ones(3) / 3, mode="same")
    return norm_spikes(smooth)
