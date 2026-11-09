import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from .config import ROOT
from .tts import FISH_URL

KEY_PAGE = "https://fish.audio/app/developers/get-started/"
NOTE = """Paste your Fish Audio API key on the empty line below, then press Cmd+S.
(Get one free at {url} -> "Get your API key". This note is deleted right after.)

"""


def mask(key):
    return key[:4] + "…" + key[-4:] if len(key) > 10 else "…"


def check_key(key, model="s2.1-pro-free"):
    """(ok, message): a 1-word TTS request with the free model."""
    req = urllib.request.Request(FISH_URL, method="POST", data=json.dumps({"text": "Hi.", "format": "mp3"}).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                          "model": model})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            r.read()
        return True, "key works"
    except urllib.error.HTTPError as e:
        return False, f"Fish Audio rejected the key (HTTP {e.code})"
    except urllib.error.URLError as e:
        return False, f"couldn't reach Fish Audio ({e.reason})"


def save_key(key, env_path=None):
    env = Path(env_path) if env_path else ROOT / ".env"
    lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    lines = [ln for ln in lines if not ln.strip().startswith("FISH_API_KEY=")] + [f"FISH_API_KEY={key}"]
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    env.chmod(0o600)
    os.environ["FISH_API_KEY"] = key


def read_pasted_key(path):
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    body = text.split("deleted right after.)", 1)[-1]
    found = re.findall(r"[A-Za-z0-9_\-]{20,}", body)
    return found[0] if found else None


def _close_note(path):
    script = (f'tell application "TextEdit" to close (every document whose path is "{path}") saving no')
    subprocess.run(["osascript", "-e", script], capture_output=True)


def _setup_terminal(cfg):
    """Linux/headless: paste the key at a hidden prompt (or put FISH_API_KEY in .env yourself)."""
    import getpass
    print(f"Get a free Fish Audio API key at {KEY_PAGE}")
    for _ in range(3):
        key = getpass.getpass("Paste it here (hidden): ").strip()
        if not key:
            break
        ok, msg = check_key(key, cfg.get("fish_model", "s2.1-pro-free"))
        if ok:
            save_key(key)
            print(f"Saved Fish Audio key {mask(key)} to .env: {msg}.")
            return True
        print(f"{msg}. Try again.")
    print("No key saved; voiceovers will use the system voice (espeak-ng).")
    return False


def setup(cfg, timeout=600):
    """Open the Fish Audio key page and a TextEdit note; wait for a pasted key, verify, save to .env."""
    existing = os.environ.get("FISH_API_KEY")
    if existing:
        ok, msg = check_key(existing, cfg.get("fish_model", "s2.1-pro-free"))
        if ok:
            print(f"Fish Audio key already saved ({mask(existing)}): {msg}.")
            return True
        print(f"Saved key {mask(existing)} failed: {msg}. Let's replace it.")
    if sys.platform != "darwin":
        return _setup_terminal(cfg)
    fd, note = tempfile.mkstemp(prefix="fish-api-key-", suffix=".txt")
    os.close(fd)
    Path(note).write_text(NOTE.format(url=KEY_PAGE), encoding="utf-8")
    subprocess.run(["open", KEY_PAGE])
    subprocess.run(["open", "-e", note])
    print(f"Opened {KEY_PAGE} and a TextEdit note. Paste the key there and press Cmd+S (waiting {timeout // 60} min)...",
          flush=True)
    try:
        deadline = time.time() + timeout
        while time.time() < deadline:
            key = read_pasted_key(note)
            if key:
                ok, msg = check_key(key, cfg.get("fish_model", "s2.1-pro-free"))
                if ok:
                    save_key(key)
                    print(f"Saved Fish Audio key {mask(key)} to .env: {msg}.")
                    return True
                print(f"{msg}. Paste a different key and save again...", flush=True)
                Path(note).write_text(NOTE.format(url=KEY_PAGE), encoding="utf-8")
            time.sleep(1.5)
        print("Timed out waiting for a key; voiceovers will use the system voice.")
        return False
    finally:
        _close_note(note)
        Path(note).unlink(missing_ok=True)
