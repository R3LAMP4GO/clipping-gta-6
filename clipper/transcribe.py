import json
import os
import re
import subprocess

EVENT_RE = re.compile(r"^[\[\(\*].*[\]\)\*]$")
SENTENCE_END = (".", "?", "!")


def extract_audio(src, wav):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vn", "-ac", "1",
                    "-ar", "16000", "-c:a", "pcm_s16le", str(wav)], check=True)


PARAKEET = "nemo-parakeet-tdt-0.6b-v3"  # NVIDIA Parakeet TDT 0.6B v3 via onnx-asr: CPU-fast, 25 languages
PUNCT = set(".,!?;:…")


def asr_threads():
    return int(os.environ.get("CLIPPER_ASR_THREADS") or os.environ.get("CLIPPER_WHISPER_THREADS") or os.cpu_count() or 4)


def tokens_to_words(tokens, starts, offset, seg_end):
    """Parakeet sub-word tokens (" fi", "x"; a leading space starts a word) -> [{"w", "s", "e"}]. A word ends where
    the next one starts, capped at 1s, or at the end of its speech segment."""
    words = []
    for tok, t in zip(tokens, starts):
        piece = tok.strip()
        if not piece:
            continue
        if words and (not tok.startswith(" ") or piece in PUNCT):
            words[-1]["w"] += piece
        else:
            words.append({"w": piece, "s": round(offset + float(t), 2)})
    for i, w in enumerate(words):
        nxt = words[i + 1]["s"] if i + 1 < len(words) else offset + seg_end
        w["e"] = round(min(max(nxt, w["s"] + 0.05), w["s"] + 1.0), 2)
    return words


_PARAKEET = {}


def parakeet_model(name, quantization):
    """Loaded once per process (~5-50s), then reused for every chunk."""
    key = (name, quantization, asr_threads())
    if key not in _PARAKEET:
        import onnx_asr
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = asr_threads()
        # CPU only: onnxruntime picks CoreML first on Macs, and it leaks memory until macOS kills the process
        cpu = ["CPUExecutionProvider"]
        model = onnx_asr.load_model(name, quantization=quantization, sess_options=opts, providers=cpu)
        _PARAKEET[key] = model.with_vad(onnx_asr.load_vad("silero", providers=cpu)).with_timestamps()
    return _PARAKEET[key]


def run_parakeet(wav, cfg):
    """(words, events) from Parakeet with voice-activity segmentation, so hour-long streams fit in memory."""
    import wave

    import numpy as np
    asr = parakeet_model(cfg.get("parakeet_model", PARAKEET), cfg.get("parakeet_quantization", "int8"))
    with wave.open(str(wav)) as w:
        if w.getframerate() != 16000 or w.getnchannels() != 1:
            raise SystemExit(f"{wav} must be 16 kHz mono")
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    words = []
    for seg in asr.recognize(audio, sample_rate=16000):
        words += tokens_to_words(seg.tokens or [], seg.timestamps or [], float(seg.start),
                                 float(seg.end) - float(seg.start))
    return words, []  # Parakeet doesn't tag sound events like (screaming); loudness signals cover those moments


def transcribe(wav, prefix, cfg, fast=False):
    """(words, events, model name): Parakeet by default, whisper.cpp when `asr: whisper` or onnx-asr is missing."""
    if cfg.get("asr", "parakeet") == "parakeet":
        try:
            words, events = run_parakeet(wav, cfg)
            return words, events, cfg.get("parakeet_model", PARAKEET)
        except ImportError:
            print("[asr] onnx-asr not installed (pip install 'onnx-asr[cpu,hub]'); using whisper.cpp", flush=True)
    from .config import find_model
    model = find_model(cfg, fast=fast)
    words, events = parse_words(run_whisper(wav, prefix, model, cfg.get("language", "en")))
    return words, events, model.name


def run_whisper(wav, prefix, model, language="en"):
    cmd = ["whisper-cli", "-m", str(model), "-f", str(wav), "-l", language, "-ml", "1", "-sow",
           "-oj", "-of", str(prefix), "-np", "-mc", "0",
           "-t", str(asr_threads())]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise SystemExit("whisper-cli failed:\n" + "\n".join(res.stderr.strip().splitlines()[-15:]))
    with open(f"{prefix}.json", encoding="utf-8") as f:
        return json.load(f)


def parse_words(data):
    """whisper.cpp word-level JSON -> (words, events). Bracketed tags like (screaming) become events."""
    words, events, pending = [], [], None
    for seg in data.get("transcription", []):
        text = seg.get("text", "").strip()
        if not text:
            continue
        s, e = seg["offsets"]["from"] / 1000, seg["offsets"]["to"] / 1000
        if pending is not None:
            pending["text"] += " " + text
            pending["e"] = e
            if text[-1] in "])*":
                events.append(pending)
                pending = None
            continue
        if text[0] in "[(*" and not EVENT_RE.match(text):
            pending = {"text": text, "s": s, "e": e}
            continue
        if EVENT_RE.match(text):
            events.append({"text": text, "s": s, "e": e})
            continue
        words.append({"w": text, "s": round(s, 2), "e": round(e, 2)})
    for ev in events:
        ev["text"] = ev["text"].strip("[]()* ").lower()
    events = [ev for ev in events if ev["text"] and "blank_audio" not in ev["text"]]
    return words, events


# Lines Whisper invents over music or silence (it was trained on subtitled video).
HALLUCINATIONS = re.compile(r"^(thank you( so much)?( for watching)?|thanks for watching|transcription by.*|translation by.*|"
                            r"subtitles by.*|please subscribe.*|the lone ranger|you)$")


def drop_hallucinations(words):
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if w["w"].endswith(SENTENCE_END) or nxt is None or nxt["s"] - w["e"] > 0.8 or w["w"].endswith(("—", "-")):
            if not HALLUCINATIONS.match(_norm(" ".join(x["w"] for x in cur))):
                out += cur
            cur = []
    return out


def _norm(text):
    return re.sub(r"[^a-z ]", "", text.lower()).strip()


def drop_repeats(words, min_run=3):
    """Whisper can loop on one line for minutes; keep the first copy of any line repeated min_run+ times."""
    sents, idx, cur = [], [], []
    for i, w in enumerate(words):
        cur.append(i)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if w["w"].endswith(SENTENCE_END) or nxt is None or nxt["s"] - w["e"] > 0.8:
            sents.append(_norm(" ".join(words[j]["w"] for j in cur)))
            idx.append(cur)
            cur = []
    keep, i = [], 0
    while i < len(sents):
        j = i
        while j + 1 < len(sents) and sents[j + 1] == sents[i] and sents[i]:
            j += 1
        if j - i + 1 >= min_run:
            keep += idx[i]
        else:
            for k in range(i, j + 1):
                keep += idx[k]
        i = j + 1
    return drop_hallucinations([words[k] for k in keep])


def group_sentences(words, max_gap=0.8, max_words=30):
    sentences, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if (w["w"].endswith(SENTENCE_END) or nxt is None or nxt["s"] - w["e"] > max_gap
                or len(cur) >= max_words):
            sentences.append({"s": cur[0]["s"], "e": cur[-1]["e"],
                              "text": " ".join(x["w"] for x in cur)})
            cur = []
    return sentences
