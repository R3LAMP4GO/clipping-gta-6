import json
import re
import subprocess
from pathlib import Path

from .config import IS_MAC, demucs_device
from .transcribe import drop_repeats

WK_MODELS = Path("~/Documents/huggingface/models/argmaxinc/whisperkit-coreml").expanduser()
WK_PREFERRED = ("openai_whisper-large-v3-v20240930_turbo", "openai_whisper-large-v3-v20240930",
                "openai_whisper-small")
TURN_RE = re.compile(r"^SPEAKER\s+\S+\s+\d+\s+([\d.]+)\s+([\d.]+)\s.*\s(\S+)\s+<NA>\s+<NA>$")


def separate(wav, out_dir, cfg):
    """Split a clip into (vocals, game audio) with Demucs, or None if it isn't available."""
    cmd = ["demucs", "--two-stems", "vocals", "-n", "htdemucs", "-d", demucs_device(cfg),
           "-o", str(out_dir), str(wav)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"[voices] demucs unavailable ({e}); using the original mix", flush=True)
        return None
    d = Path(out_dir) / "htdemucs" / Path(wav).stem
    return d / "vocals.wav", d / "no_vocals.wav"


def whisperkit_model(cfg):
    configured = cfg.get("whisperkit_model", "auto")
    if configured != "auto":
        return Path(configured).expanduser()
    for name in WK_PREFERRED:
        if (WK_MODELS / name).is_dir():
            return WK_MODELS / name
    return None


def parse_turns(stdout):
    turns = []
    for line in stdout.splitlines():
        m = TURN_RE.match(line.strip())
        if m:
            s = float(m.group(1))
            turns.append({"s": s, "e": s + float(m.group(2)), "spk": m.group(3)})
    return turns


def assign_speakers(words, turns):
    """Give each word the speaker whose turn overlaps it most; speakers numbered by first appearance."""
    labels = {}
    for w in words:
        best, most = None, 0.0
        for t in turns:
            ov = min(w["e"], t["e"]) - max(w["s"], t["s"])
            if ov > most:
                best, most = t["spk"], ov
        if best is None and turns:
            mid = (w["s"] + w["e"]) / 2
            best = min(turns, key=lambda t: min(abs(mid - t["s"]), abs(mid - t["e"])))["spk"]
        w["spk"] = labels.setdefault(best, len(labels)) if best is not None else 0
    return words


def diarized_words(wav, out_dir, cfg):
    """Word timestamps + speaker ids for a clip via WhisperKit (local CoreML), or None on failure."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    wav16 = out_dir / "voice16k.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-ac", "1", "-ar", "16000",
                    str(wav16)], check=True)
    cmd = ["whisperkit-cli", "transcribe", "--audio-path", str(wav16), "--word-timestamps", "--report",
           "--report-path", str(out_dir), "--language", cfg.get("language", "en")]
    if cfg.get("diarize", True):
        cmd.append("--diarization")
    model = whisperkit_model(cfg)
    if model:
        cmd += ["--model-path", str(model)]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except FileNotFoundError:
        print("[voices] whisperkit-cli not found" + ("" if IS_MAC else " (it's macOS-only)")
              + "; single-speaker captions", flush=True)
        return None
    report = out_dir / "voice16k.json"
    if res.returncode != 0 or not report.exists():
        print(f"[voices] diarization failed: {res.stderr.strip()[-300:]}", flush=True)
        return None
    data = json.loads(report.read_text(encoding="utf-8"))
    words = []
    for seg in data.get("segments", []):
        for x in seg.get("words") or []:
            text = x.get("word", "").strip()
            if not text or text.startswith("<|"):
                continue
            if text[0] in "'’" and words:  # WhisperKit splits contractions: "y" + "'all"
                words[-1]["w"] += text
                words[-1]["e"] = round(x["end"], 2)
            else:
                words.append({"w": text, "s": round(x["start"], 2), "e": round(x["end"], 2)})
    return assign_speakers(drop_repeats(words), parse_turns(res.stdout))
