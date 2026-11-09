import os
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
JOBS = ROOT / "jobs"

IS_MAC = sys.platform == "darwin"
MODEL_SEARCH = [
    "~/Library/Application Support/vape-n-vibe/models/ggml-large-v3-turbo-q5_0.bin",
    "/opt/homebrew/share/whisper-cpp/ggml-large-v3-turbo-q5_0.bin",
    "~/.cache/whisper/ggml-large-v3-turbo-q5_0.bin",
    "~/.cache/whisper/ggml-base.en.bin",
    "~/.cache/whisper/ggml-small.en.bin",
    "/opt/homebrew/share/whisper-cpp/ggml-base.en.bin",
    "~/Library/Application Support/supahscreenrecordah/whisper/ggml-base.bin",
]
FAST_MODEL_SEARCH = [p for p in MODEL_SEARCH if "base" in p] + MODEL_SEARCH


def demucs_device(cfg):
    """`auto`: the Apple GPU on a Mac, CUDA with an NVIDIA card, else the CPU."""
    dev = cfg.get("demucs_device", "auto")
    if dev != "auto":
        return dev
    if IS_MAC:
        return "mps"
    return "cuda" if shutil.which("nvidia-smi") else "cpu"


def timestamp_link(url, seconds):
    """A link to the moment; live recordings point at the channel, which has no timestamp to jump to."""
    if "youtube.com/watch" in url:
        return f"{url}&t={int(seconds)}s"
    return url


def load_env():
    """Read KEY=VALUE lines from .env (e.g. FISH_API_KEY) without overriding the real environment."""
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def load(path=None):
    path = Path(path) if path else ROOT / "watchlist.yaml"
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    creators = ROOT / "creators.yaml"
    if "channels" not in cfg and creators.exists():
        cfg["channels"] = (yaml.safe_load(creators.read_text(encoding="utf-8")) or {}).get("creators") or []
    return cfg


def find_model(cfg, fast=False):
    key = "whisper_model_fast" if fast else "whisper_model"
    configured = os.environ.get("CLIPPER_WHISPER_MODEL") or cfg.get(key, "auto")
    if configured and configured != "auto":
        p = Path(configured).expanduser()
        if not p.exists():
            raise SystemExit(f"whisper model not found: {p}")
        return p
    for cand in FAST_MODEL_SEARCH if fast else MODEL_SEARCH:
        p = Path(cand).expanduser()
        if p.exists():
            return p
    raise SystemExit("no ggml whisper model found; set whisper_model in watchlist.yaml")


def job_dir(job):
    p = Path(job)
    if p.is_dir():
        return p.resolve()
    p = JOBS / job
    if not p.is_dir():
        raise SystemExit(f"no job '{job}' (run `clipper fetch` first)")
    return p
