"""Check and install everything the clipper needs, and install its agent commands for Claude Code and Codex."""
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from .config import IS_MAC, MODEL_SEARCH, ROOT

BREW = {"ffmpeg": "ffmpeg", "ffprobe": "ffmpeg", "yt-dlp": "yt-dlp", "whisper-cli": "whisper-cpp",
        "whisperkit-cli": "whisperkit-cli"}
# Ubuntu/Debian: tools from apt, yt-dlp from pip (apt's is too old for YouTube), whisper.cpp built from source.
# WhisperKit is macOS-only, so Linux captions are single-speaker.
APT = {"ffmpeg": "ffmpeg", "ffprobe": "ffmpeg", "espeak-ng": "espeak-ng", "cmake": "cmake", "git": "git",
       "c++": "build-essential"}
WHISPER_SRC = Path("~/.local/src/whisper.cpp").expanduser()
LOCAL_BIN = Path("~/.local/bin").expanduser()
FAST_MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin"
PIP = {"yaml": "pyyaml", "PIL": "pillow", "numpy": "numpy", "onnx_asr": "onnx-asr[cpu,hub]==0.12.0"}
MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q5_0.bin"
COMMANDS = [(ROOT / ".claude/commands", Path("~/.claude/commands").expanduser()),
            (ROOT / ".codex/prompts", Path("~/.codex/prompts").expanduser())]


def _has_module(name):
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def uses_whisper():
    from .config import load
    return load().get("asr", "parakeet") == "whisper"


def missing():
    need = dict(BREW if IS_MAC else APT)
    if IS_MAC and not uses_whisper():  # Parakeet is the default; whisper.cpp only for `asr: whisper`
        need.pop("whisper-cli", None)
    tools = [b for b in need if not shutil.which(b)]
    mods = [m for m in PIP if not _has_module(m)]
    demucs = not shutil.which("demucs")
    model = uses_whisper() and not any(Path(p).expanduser().exists() for p in MODEL_SEARCH)
    return tools, mods, demucs, model


def global_command(text):
    """Project commands assume the project root; a global copy has to cd there first."""
    note = f"\n> Run every command below from `{ROOT}` (cd there first).\n"
    if text.startswith("---"):
        end = text.index("---", 3) + 3
        return text[:end] + "\n" + note + text[end:]
    return note + text


def install_commands(dry_run=False):
    done = []
    for src, dst in COMMANDS:
        for f in sorted(src.glob("*.md")):
            target = dst / f.name
            new = global_command(f.read_text(encoding="utf-8"))
            if target.exists() and target.read_text(encoding="utf-8") == new:
                done.append(f"up to date  {target}")
                continue
            existed = target.exists()
            if not dry_run:
                dst.mkdir(parents=True, exist_ok=True)
                if existed:
                    shutil.copy2(target, target.with_suffix(".md.bak"))
                target.write_text(new, encoding="utf-8")
            done.append(f"{'would install' if dry_run else 'installed'}  {target}"
                        + ("  (old copy saved as .md.bak)" if existed and not dry_run else ""))
    return done


def linux_plan(tools, mods, demucs):
    plan, lines = [], []
    if tools:
        plan.append(["sudo", "apt-get", "install", "-y", *sorted({APT[t] for t in tools}), "fonts-dejavu-core"])
    managed = list(Path(sys.base_prefix, "lib").glob("python3*/EXTERNALLY-MANAGED"))
    if managed and sys.prefix == sys.base_prefix:
        lines.append(f"This Python is system-managed: create a venv first, then rerun setup with it:\n"
                     f"  python3 -m venv {ROOT / '.venv'} && {ROOT / '.venv/bin/python'} -m clipper setup --install")
        return plan, lines
    pip = [m for m in mods] + (["yt-dlp"] if not shutil.which("yt-dlp") else [])
    if pip:
        plan.append([sys.executable, "-m", "pip", "install", *sorted(PIP.get(m, m) for m in pip)])
    if demucs:  # CPU wheels keep torch small on a machine without an NVIDIA card
        plan.append([sys.executable, "-m", "pip", "install", "torch", "torchaudio", "--index-url",
                     "https://download.pytorch.org/whl/" + ("cu121" if shutil.which("nvidia-smi") else "cpu")])
        plan.append([sys.executable, "-m", "pip", "install", "demucs"])
    if uses_whisper() and not shutil.which("whisper-cli"):
        plan += [["git", "clone", "--depth", "1", "https://github.com/ggml-org/whisper.cpp", str(WHISPER_SRC)],
                 ["cmake", "-S", str(WHISPER_SRC), "-B", str(WHISPER_SRC / "build"), "-DCMAKE_BUILD_TYPE=Release"],
                 ["cmake", "--build", str(WHISPER_SRC / "build"), "-j", "--config", "Release"],
                 ["install", "-D", str(WHISPER_SRC / "build/bin/whisper-cli"), str(LOCAL_BIN / "whisper-cli")]]
        lines.append(f"whisper-cli goes to {LOCAL_BIN}; make sure it's on PATH.")
    return plan, lines


def run(install=False, dry_run=False):
    lines = []
    tools, mods, demucs, model = missing()
    plan = []
    if not IS_MAC:
        plan, extra = linux_plan(tools, mods, demucs)
        lines += extra
        tools = []  # handled by the apt line
    if tools:
        pkgs = sorted({BREW[t] for t in tools})
        if not shutil.which("brew"):
            lines.append("Homebrew is missing: install it from https://brew.sh, then rerun setup.")
        else:
            plan.append(["brew", "install", *pkgs])
    if mods and IS_MAC:
        plan.append([sys.executable, "-m", "pip", "install", *sorted(PIP[m] for m in mods)])
    if demucs and IS_MAC:
        plan.append([sys.executable, "-m", "pip", "install", "demucs"])
    names = BREW if IS_MAC else {**APT, "yt-dlp": ""}
    if uses_whisper() and not IS_MAC:
        names["whisper-cli"] = ""
    if not uses_whisper():
        names = {k: v for k, v in names.items() if k != "whisper-cli"}
    checks = [*((t, bool(shutil.which(t))) for t in names), *((PIP[m], m not in mods) for m in PIP),
              ("demucs (voice separation, optional)", not demucs)]
    if uses_whisper():
        checks.append(("whisper model", not model))
    for name, ok in checks:
        lines.append(f"{'ok     ' if ok else 'MISSING'}  {name}")
    for cmd in plan:
        lines.append(("running  " if install and not dry_run else "to install:  ") + " ".join(cmd))
        if install and not dry_run:
            subprocess.run(cmd, check=True)
    downloads = [(MODEL_URL, "ggml-large-v3-turbo-q5_0.bin", "~550 MB")] if model else []
    fast = Path("~/.cache/whisper/ggml-base.en.bin").expanduser()
    if uses_whisper() and not IS_MAC and not fast.exists():  # live chunks on CPU use the fast model
        downloads.append((FAST_MODEL_URL, fast.name, "~150 MB"))
    for url, name, size in downloads:
        dest = Path("~/.cache/whisper").expanduser() / name
        lines.append(f"{'downloading' if install and not dry_run else 'to download:'}  {url} -> {dest} ({size})")
        if install and not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(".part")
            urllib.request.urlretrieve(url, tmp)
            tmp.rename(dest)
    lines += install_commands(dry_run)
    if not install and (plan or downloads):
        lines.append("Run `python3 -m clipper setup --install` to install the missing pieces.")
    return "\n".join(lines)
