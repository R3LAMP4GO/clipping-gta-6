import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

FISH_URL = "https://api.fish.audio/v1/tts"


def _duration(path):
    res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          str(path)], capture_output=True, text=True, check=True)
    return float(res.stdout.strip())


def fish(text, cfg, out):
    key = os.environ.get("FISH_API_KEY")
    if not key:
        return False
    body = {"text": text, "format": "wav", "sample_rate": 44100, "normalize": True, "latency": "normal"}
    if cfg.get("fish_voice_id"):
        body["reference_id"] = cfg["fish_voice_id"]
    req = urllib.request.Request(FISH_URL, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
        "model": cfg.get("fish_model", "s2.1-pro-free")})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            out.write_bytes(r.read())
        return True
    except urllib.error.HTTPError as e:
        print(f"[tts] Fish Audio returned {e.code}: {e.read()[:200]!r}; falling back to the system voice", flush=True)
    except urllib.error.URLError as e:
        print(f"[tts] Fish Audio unreachable ({e.reason}); falling back to the system voice", flush=True)
    return False


def say(text, voice, out):
    """The built-in system voice: macOS `say`, or espeak-ng on Linux."""
    if sys.platform != "darwin":
        if not shutil.which("espeak-ng"):
            raise SystemExit("No Fish Audio key and no espeak-ng: run `sudo apt install espeak-ng` or save a Fish key.")
        tmp = out.with_suffix(".raw.wav")
        subprocess.run(["espeak-ng", "-w", str(tmp), text], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp), "-ar", "44100", "-ac", "1", str(out)],
                       check=True)
        tmp.unlink(missing_ok=True)
        return
    cmd = ["say", "-o", str(out), "--data-format=LEI16@44100"]
    if voice:
        cmd += ["-v", voice]
    subprocess.run(cmd + [text], check=True)


def synth(text, cfg, out):
    """Write a voiceover WAV; returns (seconds, provider)."""
    provider = "fish" if fish(text, cfg, out) else "say"
    if provider == "say":
        say(text, cfg.get("voice"), out)
    return _duration(out), provider
