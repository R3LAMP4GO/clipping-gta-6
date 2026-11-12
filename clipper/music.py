import hashlib
import subprocess

import yaml

from .config import ROOT

MUSIC = ROOT / "assets" / "music"
MOODS = ("suspense", "sneaky", "epic", "sad", "funny")
UNDER_SPEECH_DB, FADE_S, SPEECH_PAD_S = -18.0, 0.3, 0.15


def load_library(folder=None):
    """Tracks from library.yaml, each with its `path` resolved inside the music folder."""
    folder = folder or MUSIC
    f = folder / "library.yaml"
    if not f.exists():
        return []
    tracks = (yaml.safe_load(f.read_text(encoding="utf-8")) or {}).get("tracks") or []
    return [{**t, "path": folder / str(t["file"])} for t in tracks if isinstance(t, dict) and t.get("file")]


def usable(track, cfg):
    """Approved by the user, and not Content ID claimable unless `music.allow_claimable` is on, and on disk."""
    allow = bool((cfg.get("music") or {}).get("allow_claimable", False))
    return track.get("approved") is True and (not track.get("claimable", True) or allow) and track["path"].exists()


def choose(lib, cfg, kind, mood=None, seed="", want=None):
    """One usable track of that kind (and mood, for music), the same one for the same seed; the `want` id when it's
    usable; None when none fits."""
    fits = [t for t in lib if t.get("kind") == kind and usable(t, cfg)
            and (kind != "music" or t.get("mood") == mood)]
    if want and any(t.get("id") == want for t in fits):
        fits = [t for t in fits if t.get("id") == want]
    if not fits:
        return None
    return fits[int(hashlib.sha1(f"{seed}:{kind}:{mood}".encode()).hexdigest(), 16) % len(fits)]


def clip_windows(pick, dur):
    """The pick's `music` windows ({s, e, mood}; source seconds, clip seconds for a segment pick) in clip seconds."""
    off = float(pick.get("start") or 0)
    out = []
    for m in pick.get("music") or []:
        try:
            a, b = max(0.0, float(m["s"]) - off), min(dur, float(m["e"]) - off)
        except (KeyError, TypeError, ValueError):
            continue
        if b - a >= 1.0 and m.get("mood") in MOODS:
            out.append({"s": round(a, 3), "e": round(b, 3), "mood": m["mood"]})
    return out


def speech_spans(words):
    """Merged (start, end) clip seconds where someone talks, padded a little so the music ducks before a word."""
    spans = []
    for w in sorted((w for w in words or [] if not w.get("label")), key=lambda w: w["s"]):
        a, b = max(0.0, w["s"] - SPEECH_PAD_S), w["e"] + SPEECH_PAD_S
        if spans and a <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], b)
        else:
            spans.append([a, b])
    return spans


def gain_expr(spans):
    """FFmpeg volume expression: -18 dB while someone talks, full level otherwise."""
    if not spans:
        return "1"
    talk = "+".join(f"between(t,{a:.2f},{b:.2f})" for a, b in spans)
    return f"if(gt({talk},0),{10 ** (UNDER_SPEECH_DB / 20):.4f},1)"


def plan(pick, words, fx, dur, cfg, seed="", lib=None):
    """[(track, start, length, kind)] to mix: music under the pick's windows and a hit at every `hit` beat."""
    lib = load_library() if lib is None else lib
    out = []
    for w in clip_windows(pick, dur):
        t = choose(lib, cfg, "music", w["mood"], f"{seed}:{w['s']}")
        if t:
            out.append((t, w["s"], w["e"] - w["s"], "music"))
    for f in fx or []:
        if f["type"] == "hit" and f["t"] < dur:
            t = choose(lib, cfg, "hit", seed=f"{seed}:{f['t']}", want=f.get("sound"))
            if t:
                out.append((t, f["t"], min(2.0, dur - f["t"]), "hit"))
    return out


def mix(bed, words, layers, dur, out):
    """Mix the planned layers into the bed (music ducked under speech, faded 0.3s at each end). Returns the bed to
    use and the track ids used."""
    if not layers:
        return bed, []
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(bed)]
    chains, labels = [], []
    gain = gain_expr(speech_spans(words))
    for i, (track, start, length, kind) in enumerate(layers, 1):
        cmd += (["-stream_loop", "-1"] if kind == "music" else []) + ["-i", str(track["path"])]
        f = f"[{i}:a]aformat=sample_rates=44100:channel_layouts=stereo,atrim=0:{length:.3f},asetpts=PTS-STARTPTS"
        if kind == "music":
            f += f",afade=t=in:d={FADE_S},afade=t=out:st={max(0.0, length - FADE_S):.3f}:d={FADE_S}"
        f += f",adelay={int(start * 1000)}:all=1"
        if kind == "music":  # after the delay, t is clip time, so it lines up with the words
            f += f",volume='{gain}':eval=frame"
        chains.append(f + f"[m{i}]")
        labels.append(f"[m{i}]")
    graph = ";".join(chains) + f";[0:a]{''.join(labels)}amix=inputs={len(layers) + 1}:duration=first:normalize=0"
    subprocess.run(cmd + ["-filter_complex", graph, "-t", f"{dur:.3f}", str(out)], check=True)
    return out, list(dict.fromkeys(str(t.get("id") or t["file"]) for t, *_ in layers))
