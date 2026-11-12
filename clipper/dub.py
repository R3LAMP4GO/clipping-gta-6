"""Re-render a clip in another language, in each streamer's cloned voice (Fish Audio), keeping the emotion.

  python3 -m clipper dub segments <job> --pick N      the clip's lines to translate, with speaker, pitch and loudness
  python3 -m clipper dub render <job> --pick N --lang ru --translation FILE

The translation file: {"lang", "lines": [one per segment, optionally starting with Fish delivery cues like
[screaming]], "hooks": [>=3], "titles": [...], "description", optional "speakers", "hashtags", "credit",
"disclosure"}. Output: exports/<profile>-<lang>/<date>/video N, apart from the profile's own exports.
"""
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from . import captions, config, render, speakers, transcribe

FISH_URL = "https://api.fish.audio/v1/tts"
MAX_SPEED = 1.35  # faster than this sounds rushed (VideoLingo and SoniTranslate cap atempo about here)
REF_MAX, REF_MIN = 30.0, 3.0  # seconds of a speaker's own audio sent as the clone reference
LOW_HZ, HIGH_HZ = 150, 180  # median pitch below/above: clearly a low/high voice; between: trust diarization
DISCLOSURE = {"es": "Doblaje con IA: voz generada a partir del audio original.",
              "en": "AI dub: voice generated from the original audio.",
              "ru": "ИИ-дубляж: голос создан на основе оригинального аудио."}
CREDIT = {"es": "Clip de", "en": "Clip from", "ru": "Клип с канала"}
CUE = re.compile(r"\[[^\]]*\]")  # Fish S2 delivery cues ([screaming], [hysterical]): voiced, never captioned


def spoken(text):
    """A dub line without its delivery cues: what's said and captioned."""
    return re.sub(r"\s+", " ", CUE.sub(" ", text or "")).strip()


# ---------- MessagePack (Fish needs it for inline reference audio; msgpack isn't installed) ----------

def msgpack(o):
    if o is None:
        return b"\xc0"
    if o is True or o is False:
        return b"\xc3" if o else b"\xc2"
    if isinstance(o, int):
        if 0 <= o < 0x80 or -32 <= o < 0:
            return struct.pack(">b" if o < 0 else ">B", o)
        if o >= 0:
            for tag, fmt, lim in ((0xcc, "B", 1 << 8), (0xcd, "H", 1 << 16), (0xce, "I", 1 << 32), (0xcf, "Q", 1 << 64)):
                if o < lim:
                    return bytes([tag]) + struct.pack(">" + fmt, o)
        for tag, fmt, lim in ((0xd0, "b", 1 << 7), (0xd1, "h", 1 << 15), (0xd2, "i", 1 << 31), (0xd3, "q", 1 << 63)):
            if o >= -lim:
                return bytes([tag]) + struct.pack(">" + fmt, o)
        raise ValueError("int out of range")
    if isinstance(o, float):
        return b"\xcb" + struct.pack(">d", o)
    if isinstance(o, str):
        b = o.encode("utf-8")
        n = len(b)
        head = bytes([0xa0 | n]) if n < 32 else _len(n, 0xd9, 0xda, 0xdb)
        return head + b
    if isinstance(o, (bytes, bytearray)):
        return _len(len(o), 0xc4, 0xc5, 0xc6) + bytes(o)
    if isinstance(o, (list, tuple)):
        head = bytes([0x90 | len(o)]) if len(o) < 16 else _len(len(o), None, 0xdc, 0xdd)
        return head + b"".join(msgpack(x) for x in o)
    if isinstance(o, dict):
        head = bytes([0x80 | len(o)]) if len(o) < 16 else _len(len(o), None, 0xde, 0xdf)
        return head + b"".join(msgpack(k) + msgpack(v) for k, v in o.items())
    raise TypeError(f"can't msgpack {type(o).__name__}")


def _len(n, t8, t16, t32):
    if t8 is not None and n < 1 << 8:
        return bytes([t8, n])
    if n < 1 << 16:
        return bytes([t16]) + struct.pack(">H", n)
    return bytes([t32]) + struct.pack(">I", n)


# ---------- voice ----------

def fish_clone(text, ref_audio, ref_text, out, model):
    """One line in the cloned voice; the reference travels with the request, nothing is saved on the account."""
    key = os.environ.get("FISH_API_KEY")
    if not key:
        raise SystemExit("[dub] FISH_API_KEY isn't set (clipper .env)")
    body = {"text": text, "references": [{"audio": ref_audio, "text": ref_text}], "format": "wav",
            "sample_rate": 44100, "normalize": True, "latency": "normal"}
    req = urllib.request.Request(FISH_URL, data=msgpack(body), method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/msgpack", "model": model})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            out.write_bytes(r.read())
    except urllib.error.HTTPError as e:
        # no system-voice fallback: a robot voice defeats the point of a dub
        raise SystemExit(f"[dub] Fish Audio refused the cloned line ({e.code}): {e.read()[:300]!r}")
    except urllib.error.URLError as e:
        raise SystemExit(f"[dub] Fish Audio unreachable: {e.reason}")


def speaker_spans(segs, spk, cap=REF_MAX):
    """A speaker's own lines, whole, up to cap seconds: the clone reference audio and its exact text."""
    spans, texts, total = [], [], 0.0
    for g in segs:
        if g["spk"] != spk:
            continue
        d = g["e"] - g["s"]
        if total + d > cap and spans:
            continue
        spans.append((g["s"], min(g["e"], g["s"] + cap)))
        texts.append(g["text"])
        total += min(d, cap)
    return spans, " ".join(texts), total


def speaker_refs(vocals, segs, tmp):
    """{speaker: (wav bytes, text)}, each cloned from that speaker's own lines, so a woman never gets a man's voice."""
    refs = {}
    for spk in sorted({g["spk"] for g in segs}):
        spans, text, total = speaker_spans(segs, spk)
        if total < REF_MIN:
            raise SystemExit(f"[dub] speaker {spk} has only {total:.1f}s of speech in the clip (a clone needs "
                             f"{REF_MIN:.0f}s); set \"speakers\" in the translation to fix the assignment")
        chains = [f"[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS[r{i}]" for i, (a, b) in enumerate(spans)]
        joined = "".join(f"[r{i}]" for i in range(len(spans)))
        out = tmp / f"ref_{spk}.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(vocals), "-filter_complex",
                        ";".join(chains) + f";{joined}concat=n={len(spans)}:v=0:a=1[out]", "-map", "[out]",
                        "-ac", "1", "-ar", "44100", str(out)], check=True)
        refs[spk] = (out.read_bytes(), text)
    return refs


def loudness_db(audio, sr, s, e):
    """How loud a line is delivered: the 90th-percentile 50 ms RMS in dBFS (its peaks, so a shout reads as one)."""
    import numpy as np
    win = int(sr * 0.05)
    x = audio[int(s * sr):int(e * sr)]
    frames = [x[i:i + win] for i in range(0, len(x) - win + 1, win)]
    if not frames:
        return None
    rms = np.array([np.sqrt((f ** 2).mean()) for f in frames])
    return round(float(20 * np.log10(np.percentile(rms, 90) + 1e-9)), 1)


def energy(db, clip_median):
    """loud / quiet relative to the rest of the clip; None when it's ordinary."""
    if db is None or clip_median is None:
        return None
    return "loud" if db - clip_median >= 4 else "quiet" if db - clip_median <= -6 else None


def match_gain(dub_db, orig_db, lo=-15.0, hi=10.0):
    """dB to bring a dub line to the original line's loudness: Fish returns every line at one level, which would
    flatten a shout and a whisper alike. Clamped so a bad reading can't blow a line out or bury it."""
    if dub_db is None or orig_db is None:
        return 0.0
    return round(min(max(orig_db - dub_db, lo), hi), 1)


def median_f0(audio, sr, s, e):
    """Median pitch (Hz) of the voiced frames in [s, e], by autocorrelation; None if nothing is voiced."""
    import numpy as np
    fs, win = [], int(sr * 0.04)
    lo, hi = int(sr / 400), int(sr / 70)
    for i in range(int(s * sr), int(e * sr) - win, win // 2):
        x = audio[i:i + win] - audio[i:i + win].mean()
        if np.sqrt((x ** 2).mean()) < 0.02:
            continue
        c = np.correlate(x, x, "full")[win - 1:]
        k = lo + int(np.argmax(c[lo:hi]))
        if c[k] > 0.4 * c[0]:
            fs.append(sr / k)
    return round(float(np.median(fs))) if fs else None


# ---------- text ----------

def source_words(job):
    return transcribe.drop_repeats(json.loads((job / "transcript.json").read_text(encoding="utf-8"))["words"])


def voice(hz):
    return None if hz is None else "low" if hz < LOW_HZ else "high" if hz > HIGH_HZ else None


def label_lines(words, dwords, hz_of, group):
    """Lines split wherever the speaker changes. Speakers come from diarization (dwords); a line whose pitch
    clearly contradicts its speaker's voice moves to a speaker with that voice (a new one if needed)."""
    for w in words:
        best, most = 0, 0.0
        for d in dwords:
            ov = min(w["e"], d["e"]) - max(w["s"], d["s"])
            if ov > most:
                best, most = d["spk"], ov
        w["spk"] = best
    runs = []
    for w in words:
        if runs and runs[-1][-1]["spk"] == w["spk"]:
            runs[-1].append(w)
        else:
            runs.append([w])
    for i, r in enumerate(runs):  # a one-word or sub-0.4 s flip is diarization noise, not a new speaker
        if len(runs) > 1 and (len(r) == 1 or r[-1]["e"] - r[0]["s"] < 0.4):
            spk = runs[i - 1][-1]["spk"] if i else runs[1][0]["spk"]
            for x in r:
                x["spk"] = spk
    segs, run = [], []
    for i, w in enumerate(words):
        run.append(w)
        if i + 1 == len(words) or words[i + 1]["spk"] != w["spk"]:
            segs += [dict(x, spk=w["spk"]) for x in group(run)]
            run = []
    for g in segs:
        g["hz"] = hz_of(g["s"], g["e"])
    weight = {}
    for g in segs:
        if voice(g["hz"]):
            weight.setdefault(g["spk"], {"low": 0.0, "high": 0.0})[voice(g["hz"])] += g["e"] - g["s"]
    kind = {k: max(v, key=v.get) for k, v in weight.items()}
    for g in segs:
        v = voice(g["hz"])
        if v and kind.get(g["spk"], v) != v:
            match = [k for k, kv in kind.items() if kv == v]
            if not match:
                match = [max(kind) + 1]
                kind[match[0]] = v
            g["spk"] = max(match, key=lambda k: sum(x["e"] - x["s"] for x in segs if x["spk"] == k))
    merged = []
    for g in segs:  # a sentence cut only by a speaker flip that pitch undid becomes one line again
        p = merged[-1] if merged else None
        if p and p["spk"] == g["spk"] and g["s"] - p["e"] < 0.8 and not p["text"].endswith((".", "?", "!")):
            merged[-1] = dict(p, e=g["e"], text=f"{p['text']} {g['text']}", hz=hz_of(p["s"], g["e"]))
        else:
            merged.append(g)
    segs = merged
    order = {}
    for g in segs:
        order.setdefault(g["spk"], len(order))
    return [{"i": i, "s": round(g["s"], 3), "e": round(g["e"], 3), "text": g["text"], "spk": order[g["spk"]],
             "hz": g["hz"]} for i, g in enumerate(segs)]


def load16(wav, tmp):
    import wave
    import numpy as np
    out = tmp / "pitch16.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-ac", "1", "-ar", "16000",
                    "-c:a", "pcm_s16le", str(out)], check=True)
    with wave.open(str(out)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768, 16000


def clip_audio(job, pick, tmp, cfg):
    s, e = float(pick["start"]), float(pick["end"])
    clip_wav = tmp / "clip.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{s:.3f}", "-t", f"{e - s:.3f}", "-i",
                    str(job / "source.mp4"), "-vn", "-ac", "2", "-ar", "44100", str(clip_wav)], check=True)
    stems = speakers.separate(clip_wav, tmp, cfg)
    if not stems:
        raise SystemExit("[dub] Demucs is needed to isolate the voices")
    return stems


def segments(job, words, pick, cfg):
    """The pick's spoken lines per speaker, clip-relative: what the translation must match one-for-one. Cached in the
    job so `segments` and `render` always agree (delete dub-lines-*.json to redo it)."""
    s, e = float(pick["start"]), float(pick["end"])
    cache = job / f"dub-lines-{s:g}-{e:g}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    inside = [dict(w, s=w["s"] - s, e=min(w["e"], e) - s) for w in words if s <= w["s"] < e]
    with tempfile.TemporaryDirectory(dir=job) as tmp:
        tmp = Path(tmp)
        print("[dub] separating and diarizing the voices ...", file=sys.stderr, flush=True)
        vocals, _ = clip_audio(job, pick, tmp, cfg)
        dwords = speakers.diarized_words(vocals, tmp / "wk", cfg) or []
        audio, sr = load16(vocals, tmp)
        segs = label_lines(inside, dwords, lambda a, b: median_f0(audio, sr, a, b), transcribe.group_sentences)
        for g in segs:
            g["db"] = loudness_db(audio, sr, g["s"], g["e"])
    cache.write_text(json.dumps(segs, indent=1, ensure_ascii=False), encoding="utf-8")
    return segs


def _norm(text):
    return re.sub(r"\s+", " ", (text or "").replace("*", "")).strip().lower()


def english_texts(pick, upload):
    out = []
    for src in [pick] + list(upload or []):
        out += list(src.get("hooks") or []) + list(src.get("titles") or [])
        for k in ("hook", "title", "description"):
            if src.get(k):
                out.append(src[k])
                if k == "description":
                    out.append(src[k].split("\n\n")[0])  # upload.json appends the credit and tags
    return {_norm(t) for t in out if _norm(t)}


def validate_translation(tr, lang, pick, upload, n_lines):
    """Everything wrong with a translation file; empty means it's safe to spend audio work on."""
    errs = []
    if not lang:
        return ["--lang is required (e.g. --lang es)"]
    if tr.get("lang") != lang:
        errs.append(f"translation lang is {tr.get('lang')!r}, but --lang is {lang!r}")

    def texts(key):
        v = tr.get(key)
        return [x for x in v if isinstance(x, str) and x.strip()] if isinstance(v, list) else []
    hooks, titles = texts("hooks"), texts("titles")
    if len(hooks) < 3:
        errs.append(f"need at least 3 hooks in {lang}, got {len(hooks)}")
    if not titles:
        errs.append("titles is missing or empty")
    desc = tr.get("description")
    if not isinstance(desc, str) or not desc.strip():
        errs.append("description is missing or empty")
        desc = ""
    lines = tr.get("lines")
    if not isinstance(lines, list) or len(lines) != n_lines:
        errs.append(f"need {n_lines} lines (one per segment), got {len(lines) if isinstance(lines, list) else 0}")
    elif not all(isinstance(x, str) and spoken(x) for x in lines):
        errs.append("every line needs spoken text, not only [cues]")
    spk = tr.get("speakers")
    if spk is not None and (not isinstance(spk, list) or len(spk) != n_lines
                            or not all(isinstance(x, int) and x >= 0 for x in spk)):
        errs.append(f"speakers must list one speaker number per line ({n_lines})")
    english = english_texts(pick, upload)
    for kind, items in (("hook", hooks), ("title", titles), ("description", [desc] if desc else [])):
        for t in items:
            if _norm(t) in english:
                errs.append(f"{kind} is still the English text, not {lang}: {t!r}")
    return errs


# ---------- timing ----------

def fit(dur, window, slot, max_speed=MAX_SPEED):
    """(speed, seconds) for a dub line: sped up to its original window (never past max_speed); what's still too
    long spills into the gap, and is cut at the next line (slot)."""
    speed = min(max(dur / window, 1.0), max_speed) if window > 0 else max_speed
    return speed, min(dur / speed, slot)


def caption_words(lines, placements, spks=None):
    """Translated words, each line's time split across its words by length."""
    out = []
    for n, (text, (s, length)) in enumerate(zip(lines, placements)):
        ws = spoken(text).split()
        total = sum(len(w) for w in ws) or 1
        t = s
        for w in ws:
            d = length * len(w) / total
            out.append({"w": w, "s": round(t, 3), "e": round(t + d, 3), "spk": spks[n] if spks else 0})
            t += d
        if ws:
            out[-1]["e"] = round(s + length, 3)
    return out


def _duration(path):
    res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          str(path)], capture_output=True, text=True, check=True)
    return float(res.stdout.strip())


def build_track(wavs, segs, clip_dur, tmp):
    """Each dub line at its original start, sped/cut to fit, mixed into one clip-length vocal track."""
    trimmed, placements = [], []
    for i, wav in enumerate(wavs):
        t = tmp / f"trim_{i}.wav"
        sil = "silenceremove=start_periods=1:start_threshold=-45dB"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-af",
                        f"{sil},areverse,{sil},areverse", "-ac", "1", "-ar", "44100", str(t)], check=True)
        trimmed.append(t)
    gains = []
    for t, seg in zip(trimmed, segs):
        audio, sr = load16(t, tmp)
        gains.append(match_gain(loudness_db(audio, sr, 0, len(audio) / sr), seg.get("db")))
    inputs, chains = [], []
    for i, (t, seg) in enumerate(zip(trimmed, segs)):
        nxt = segs[i + 1]["s"] if i + 1 < len(segs) else clip_dur
        raw = _duration(t)
        speed, length = fit(raw, seg["e"] - seg["s"], nxt - seg["s"])
        if raw / speed > length + 0.05:
            print(f"[dub] warning: line {i + 1} is {raw / speed - length:.2f}s too long even at {speed:.2f}x and is cut "
                  "at the next line; shorten it", flush=True)
        placements.append((seg["s"], length))
        ms = int(seg["s"] * 1000)
        inputs += ["-i", str(t)]
        chains.append(f"[{i}:a]volume={gains[i]}dB,atempo={speed:.4f},atrim=0:{length:.3f},afade=t=out:st={max(0, length - 0.06):.3f}:"
                      f"d=0.06,adelay={ms}|{ms}[d{i}]")
    mix = "".join(f"[d{i}]" for i in range(len(trimmed)))
    track = tmp / "dub_vocals.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex",
                    ";".join(chains) + f";{mix}amix=inputs={len(trimmed)}:normalize=0,apad,atrim=0:{clip_dur:.3f}[out]",
                    "-map", "[out]", "-ac", "2", "-ar", "44100", str(track)], check=True)
    return track, placements


def finish_manifest(entries, lang, channel, credit, disclosure):
    """Localise the credit line, end the description with the AI disclosure and tag every entry with lang."""
    old = entries[0]["description"] if entries else ""
    new = old.replace(f"Clip from {channel}:", f"{credit} {channel}:") + f"\n\n{disclosure}"
    return [dict(e, description=new, lang=lang) for e in entries], old, new


# ---------- render ----------

def english_upload(render, config, pick, meta):
    link = config.timestamp_link(meta["url"], int(float(pick["start"]) + meta.get("offset", 0)))
    out = []
    for p in render.EXPORTS.glob("**/upload.json"):
        try:
            entries = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out += [x for x in entries if isinstance(x, dict) and x.get("source") == link and not x.get("lang")]
    return out


def load_job(job, pick_n):
    picks = json.loads((job / "picks.json").read_text(encoding="utf-8"))
    if not 1 <= pick_n <= len(picks):
        raise SystemExit(f"[dub] pick {pick_n} doesn't exist ({len(picks)} picks)")
    return json.loads((job / "job.json").read_text(encoding="utf-8")), picks[pick_n - 1]


def render_dub(job, pick_n, lang, tr, cfg):
    meta, pick = load_job(job, pick_n)
    words = source_words(job)
    segs = segments(job, words, pick, cfg)
    upload = english_upload(render, config, pick, meta)
    errs = validate_translation(tr, lang, pick, upload, len(segs))
    if errs:
        raise SystemExit("[dub] translation rejected:\n  - " + "\n  - ".join(errs))
    s, e = float(pick["start"]), float(pick["end"])
    dur = e - s
    hooks, titles, lines = tr["hooks"], tr["titles"], tr["lines"]
    if tr.get("speakers"):
        segs = [dict(g, spk=k) for g, k in zip(segs, tr["speakers"])]
    spks = [g["spk"] for g in segs]
    dpick = dict(pick, hooks=hooks, titles=titles, description=tr["description"],
                 hashtags=tr.get("hashtags") or pick.get("hashtags"))
    out_dir = render.EXPORTS / f"{cfg.get('profile', config.PROFILE)}-{lang}" / date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    n = render.next_video_number(out_dir)
    cache = job / f"dub-{lang}-cache"
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=job) as tmp:
        tmp = Path(tmp)
        print("[dub] isolating each speaker's voice ...", flush=True)
        stems = clip_audio(job, pick, tmp, cfg)
        refs = speaker_refs(stems[0], segs, tmp)
        model = cfg.get("fish_model", "s2.1-pro-free")
        wavs = []
        for i, line in enumerate(lines):
            ref_audio, ref_text = refs[spks[i]]
            key = hashlib.sha1(f"{model}\n{ref_text}\n{line}".encode()).hexdigest()[:16]
            wav = cache / f"{key}.wav"
            if not wav.exists():
                print(f"[dub] line {i + 1}/{len(lines)} (speaker {spks[i]}): {line}", flush=True)
                fish_clone(line, ref_audio, ref_text, wav, model)
            wavs.append(wav)
        track, placements = build_track(wavs, segs, dur, tmp)
        (job / f"dub-{lang}-vocals.wav").write_bytes(track.read_bytes())
        bed = tmp / "bed.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(track), "-i", str(stems[1]),
                        "-filter_complex", f"[1:a]volume={cfg.get('game_volume', 0.7)}[g];"
                        "[0:a][g]amix=inputs=2:duration=first:normalize=0", str(bed)], check=True)
        cwords = caption_words(lines, placements, spks)
        layout = pick.get("layout") or {"type": "fit"}
        caps = captions.write_overlay(cwords, 0.0, dur, tmp / "caps", layout.get("type", "fit"),
                                      pick.get("caption_style") or cfg.get("caption_style", "bold"))
        prep = {"captions": caps, "bed": bed, "vo": None, "layout": layout, "speakers": len(set(spks)),
                "transcript": f"translation ({lang}) timed to the source", "voices_separated": True, "words": cwords}
        folder = out_dir / f"video {n}"
        folder.mkdir()
        taken, variants = set(), []
        for hook in hooks:
            mp4 = folder / render.hook_filename(hook, taken)
            print(f"[dub]   {mp4.relative_to(out_dir)}", flush=True)
            render.encode_variant(job, dpick, prep, hook, cfg, mp4, tmp)
            variants.append({"file": str(mp4), "hook": hook, "check": render.probe(mp4)})
    entries = render.upload_manifest(dpick, meta, cfg, variants, titles)
    entries, old, new = finish_manifest(entries, lang, meta["channel"], tr.get("credit") or CREDIT.get(lang, "Clip:"),
                                        tr.get("disclosure") or DISCLOSURE.get(lang, DISCLOSURE["en"]))
    (folder / "upload.json").write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    md = render.clip_markdown(n, dpick, meta, cfg, variants, prep).replace(old, new)
    md += (f"\n## Dub\nLanguage: {lang} (lang: \"{lang}\") · voices: Fish Audio clones of the {len(set(spks))} "
           f"original speaker(s), each from their own audio, translated from what they said.\nWhen uploading to YouTube, tick \"Altered or synthetic content\" "
           f"(and the AI label on TikTok/Instagram).\n")
    (folder / "titles and description.md").write_text(md, encoding="utf-8")
    index = out_dir / "index.md"
    rows = [x for x in (index.read_text(encoding="utf-8").splitlines(keepends=True) if index.exists() else [])
            if not x.startswith(f"- **video {n}**:")]
    rows.append(f"- **video {n}**: {titles[0]} · {meta['channel']} · {len(variants)} hooks · dub: {lang}\n")
    index.write_text("".join(rows), encoding="utf-8")
    return {"video": n, "folder": str(folder), "lang": lang, "speakers": spks, "placements": placements, "variants": variants}


def segments_report(job, pick_n, cfg):
    """The clip's lines to translate, each with its speaker, pitch (voice) and loudness (energy), plus a template."""
    _, pick = load_job(job, pick_n)
    segs = segments(job, source_words(job), pick, cfg)
    dbs = sorted(g["db"] for g in segs if g.get("db") is not None)
    mid = dbs[len(dbs) // 2] if dbs else None
    for g in segs:
        g["voice"] = voice(g["hz"]) or "unclear"
        g["energy"] = energy(g.get("db"), mid) or "normal"
    return {"segments": segs,
            "english": {k: pick.get(k) for k in ("hooks", "titles", "description")},
            "template": {"lang": "<code>", "lines": [
                "one per segment; start it with Fish delivery cues that match how it was said "
                "([screaming], [hysterical], [shocked], [laughing]); energy/db show which lines were "
                "shouted. Cues are voiced, never captioned"],
                         "speakers": ["optional: one speaker number per line, to fix a wrong one"],
                         "hooks": ["3+"],
                         "titles": ["..."], "description": "..."}}
