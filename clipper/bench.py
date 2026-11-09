"""Measure this machine: how fast it transcribes, separates voices and renders, and how many live creators it can
keep up with in real time."""
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from . import config, transcribe

CLIPS_PER_CHUNK = 2   # strong moments a lively 30-minute chunk usually yields
CLIP_SECONDS = 30
HOOKS = 3             # research/hook-strategy.json's recommendation


def _timed(fn):
    t = time.time()
    fn()
    return time.time() - t


def _sample_audio(tmp, seconds):
    wav = Path(tmp) / "sample.wav"
    src = next((p for p in sorted(config.JOBS.glob("*/audio.wav")) if p.stat().st_size > 2_000_000), None)
    if src:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-t", str(seconds), "-ac", "1",
                        "-ar", "16000", str(wav)], check=True)
        return wav, f"speech from {src.parent.name}"
    voice = ["say", "-o", str(Path(tmp) / "v.aiff")] if config.IS_MAC else ["espeak-ng", "-w", str(Path(tmp) / "v.aiff")]
    text = "Bro what is he doing, no way, chat look at this, the cops are right there, go go go. " * 12
    if shutil.which(voice[0]):
        subprocess.run(voice + [text], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-i", str(Path(tmp) / "v.aiff"),
                        "-t", str(seconds), "-ac", "1", "-ar", "16000", str(wav)], check=True)
        return wav, "synthesized speech"
    raise SystemExit("bench needs speech audio: analyze one video first, or install espeak-ng")


def run(cfg, seconds=60):
    lines, cpus = [], os.cpu_count() or 4
    with tempfile.TemporaryDirectory() as tmp:
        wav, what = _sample_audio(tmp, seconds)
        lines.append(f"CPU threads: {cpus} · sample: {seconds}s of {what}")
        rtf = {}
        transcribe.transcribe(wav, Path(tmp) / "warm", cfg, True)  # first load downloads / warms the model
        for label, fast in (("live chunks", True), ("VODs", False)):
            name = []
            t = _timed(lambda: name.append(transcribe.transcribe(wav, Path(tmp) / f"w{int(fast)}", cfg, fast)[2]))
            rtf[fast] = seconds / t
            lines.append(f"{cfg.get('asr', 'parakeet')} ({label}): {name[0]} at {rtf[fast]:.1f}x real time")
        clip = Path(tmp) / "clip.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-t", "20", "-ar", "44100", str(clip)],
                       check=True)
        demucs = None
        if shutil.which("demucs"):
            t = _timed(lambda: subprocess.run(["demucs", "--two-stems", "vocals", "-n", "htdemucs", "-d",
                                               config.demucs_device(cfg), "-o", tmp, str(clip)], capture_output=True))
            demucs = t / 20
            lines.append(f"demucs ({config.demucs_device(cfg)}): {demucs:.2f}s per clip second")
        out = Path(tmp) / "r.mp4"
        t = _timed(lambda: subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                                           "testsrc2=size=1080x1920:rate=30", "-t", "10", "-c:v", "libx264", "-preset",
                                           "medium", "-crf", "20", "-pix_fmt", "yuv420p", str(out)], check=True))
        render = t / 10
        lines.append(f"render (1080x1920 x264 medium): {render:.2f}s per video second")
    chunk = 30 * 60
    per_chunk = (chunk / rtf[True] + CLIPS_PER_CHUNK * CLIP_SECONDS * (demucs or 0)
                 + CLIPS_PER_CHUNK * HOOKS * CLIP_SECONDS * render)
    streams = max(0, int(chunk / per_chunk * 0.8))  # 20% headroom for the agent, downloads and the OS
    workers = max(1, min(streams, cpus // 4)) if streams else 1
    vod_hours = 20 * 1.5 / rtf[False]
    lines += ["", f"One 30-min live chunk: ~{per_chunk / 60:.1f} min of work ({CLIPS_PER_CHUNK} clips x {HOOKS} hooks).",
              f"Keeps up with about {streams} creator(s) live at once (80% load).",
              f"Suggested watchlist.yaml: live_workers: {workers}",
              f"20 VODs of 90 min (the 12-hour batch) take ~{vod_hours:.1f} h to transcribe with the full model"
              + (" -> use --fast for VODs too, or fewer sources" if vod_hours > 10 else "") + "."]
    return "\n".join(lines)
