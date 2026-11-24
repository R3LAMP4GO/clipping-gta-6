"""End to end: the live recorder saves the stream's own video (HLS via yt-dlp -g + ffmpeg -c copy), frame for frame,
not a screen capture. Needs ffmpeg and yt-dlp; skipped without them (CI has neither)."""
import functools
import http.server
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = all(shutil.which(t) for t in ("ffmpeg", "ffprobe", "yt-dlp"))


def frame_hashes(*inputs):
    """Per-frame MD5 of the decoded video, in order (several inputs are decoded as one stream)."""
    with tempfile.TemporaryDirectory() as d:
        if len(inputs) > 1:
            listing = Path(d) / "list.txt"
            listing.write_text("".join(f"file '{p}'\n" for p in inputs))
            src = ["-f", "concat", "-safe", "0", "-i", str(listing)]
        else:
            src = ["-i", str(inputs[0])]
        out = subprocess.run(["ffmpeg", "-loglevel", "error", *src, "-map", "0:v", "-f", "framemd5", "-"],
                             capture_output=True, text=True, check=True).stdout
    return [line.split(",")[-1].strip() for line in out.splitlines() if line and not line.startswith("#")]


def video_info(path):
    return subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                           "stream=codec_name,width,height,r_frame_rate", "-of", "csv=p=0", str(path)],
                          capture_output=True, text=True).stdout.split()[0]  # .ts lists the stream twice


@unittest.skipUnless(TOOLS, "needs ffmpeg, ffprobe and yt-dlp")
class LiveRecordingTests(unittest.TestCase):
    def test_recorded_chunks_are_the_streams_own_frames(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            hls, jobs = d / "hls", d / "jobs"
            hls.mkdir()
            has_drawtext = "drawtext" in subprocess.run(["ffmpeg", "-hide_banner", "-filters"],
                                                        capture_output=True, text=True).stdout
            # testsrc already burns in a running counter; add a per-frame number when this ffmpeg has drawtext
            vf = ["-vf", "drawtext=text='frame %{n}':fontsize=64:fontcolor=white:box=1:boxcolor=black:x=40:y=40"] \
                if has_drawtext else []
            producer = subprocess.Popen(
                ["ffmpeg", "-loglevel", "error", "-re", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30",
                 "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=48000", "-t", "30", *vf,
                 "-c:v", "libx264", "-preset", "veryfast", "-g", "30", "-pix_fmt", "yuv420p",
                 # constant 8 Mbit/s: testsrc compresses so well that 6 s chunks would fall under the
                 # recorder's 1 MB "stray fragment" floor
                 "-b:v", "8M", "-minrate", "8M", "-maxrate", "8M", "-bufsize", "8M", "-x264-params", "nal-hrd=cbr",
                 "-c:a", "aac", "-f", "hls", "-hls_time", "1", "-hls_list_size", "0", str(hls / "live.m3u8")])
            server = http.server.ThreadingHTTPServer(
                ("127.0.0.1", 0), functools.partial(_Quiet, directory=str(hls)))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            url = f"http://127.0.0.1:{server.server_address[1]}/live.m3u8"
            recorder = None
            try:
                for _ in range(40):  # wait for the first segments
                    if len(list(hls.glob("*.ts"))) >= 2:
                        break
                    time.sleep(0.5)
                harness = ("import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); "
                           "from clipper import live; live.JOBS = Path(sys.argv[2]); live.WORK = live.JOBS / '_live'; "
                           "live.record('synth', sys.argv[3], chunk_minutes=0.1)")  # 6 s chunks
                recorder = subprocess.Popen([sys.executable, "-c", harness, str(ROOT), str(jobs), url],
                                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                time.sleep(20)
                recorder.send_signal(signal.SIGTERM)  # what `live` does to stop a recorder
                log = recorder.communicate(timeout=60)[0]
            finally:
                if recorder and recorder.poll() is None:
                    recorder.kill()
                producer.terminate()
                producer.wait()
                server.shutdown()
                server.server_close()
            chunks = sorted(jobs.glob("live-synth-*/source.mp4"))
            self.assertGreaterEqual(len(chunks), 2, log)
            segments = sorted(hls.glob("live*.ts"), key=lambda p: int(p.stem[4:]))
            source = frame_hashes(*segments)
            src_info = video_info(segments[0])
            self.assertEqual(src_info, "h264,1280,720,30/1")
            pos, matched = None, 0
            for chunk in chunks:
                self.assertEqual(video_info(chunk), src_info)  # same codec, size and fps: no re-encode, no capture
                rec = frame_hashes(chunk)
                if chunk == chunks[-1]:
                    rec = rec[:-1]  # the frame being written when the recorder was stopped is cut short
                self.assertTrue(rec)  # the last chunk is cut short by the stop, so it can be brief
                start = source.index(rec[0]) if pos is None else pos
                bad = [i for i, (a, b) in enumerate(zip(rec, source[start:start + len(rec)])) if a != b]
                self.assertEqual(bad, [], f"chunk {chunks.index(chunk) + 1}/{len(chunks)} ({len(rec)} frames) differs "
                                          f"from the stream at frames {bad[:10]}")
                pos = start + len(rec)  # the next chunk continues exactly where this one ended (gapless)
                matched += len(rec)
            self.assertGreater(matched, 300)  # >10 s of the stream, every frame identical


@unittest.skipUnless(TOOLS, "needs ffmpeg, ffprobe and yt-dlp")
class RecorderHandoverTests(unittest.TestCase):
    def test_restart_overlaps_so_no_frame_is_lost(self):
        """A replacement recorder (`live restart`) starts before the old one stops: together their chunks hold every
        frame of the stream across the handover."""
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            hls, jobs = d / "hls", d / "jobs"
            hls.mkdir()
            producer = subprocess.Popen(
                ["ffmpeg", "-loglevel", "error", "-re", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30",
                 "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=48000", "-t", "45",
                 "-c:v", "libx264", "-preset", "veryfast", "-g", "30", "-pix_fmt", "yuv420p",
                 "-b:v", "8M", "-minrate", "8M", "-maxrate", "8M", "-bufsize", "8M", "-x264-params", "nal-hrd=cbr",
                 "-c:a", "aac", "-f", "hls", "-hls_time", "1", "-hls_list_size", "0", str(hls / "live.m3u8")])
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(hls)))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            url = f"http://127.0.0.1:{server.server_address[1]}/live.m3u8"
            harness = ("import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); "
                       "from clipper import live; live.JOBS = Path(sys.argv[2]); live.WORK = live.JOBS / '_live'; "
                       "live.record('synth', sys.argv[3], chunk_minutes=0.1, "
                       "replace_pid=int(sys.argv[4]) or None)")
            old = new = None
            try:
                for _ in range(40):
                    if len(list(hls.glob("*.ts"))) >= 2:
                        break
                    time.sleep(0.5)
                old = subprocess.Popen([sys.executable, "-c", harness, str(ROOT), str(jobs), url, "0"],
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                time.sleep(12)
                new = subprocess.Popen([sys.executable, "-c", harness, str(ROOT), str(jobs), url, str(old.pid)],
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                old_log = old.communicate(timeout=90)[0]  # the new recorder stops it once it's writing
                time.sleep(8)
                new.send_signal(signal.SIGTERM)
                new_log = new.communicate(timeout=60)[0]
            finally:
                for proc in (old, new):
                    if proc and proc.poll() is None:
                        proc.kill()
                producer.terminate()
                producer.wait()
                server.shutdown()
                server.server_close()
            self.assertIn("took over from recorder", new_log)
            self.assertEqual(len(set(jobs.glob("live-synth-*/source.mp4"))), old_log.count("chunk ready") +
                             new_log.count("chunk ready"))  # no chunk overwrote another
            source = frame_hashes(*sorted(hls.glob("live*.ts"), key=lambda p: int(p.stem[4:])))
            covered = set()
            for chunk in sorted(jobs.glob("live-synth-*/source.mp4")):
                rec = frame_hashes(chunk)
                start = source.index(rec[0])
                good = next((i for i, (a, b) in enumerate(zip(rec, source[start:])) if a != b), len(rec))
                self.assertGreaterEqual(good, len(rec) - 1, chunk)  # only a stopped chunk's last frame may be cut
                covered.update(range(start, start + good))
            first, last = min(covered), max(covered)
            missing = sorted(set(range(first, last + 1)) - covered)
            self.assertLessEqual(len(missing), 2, f"frames lost in the handover: {missing[:20]}\n{old_log}\n{new_log}")
            self.assertGreater(last - first, 450)  # >15 s recorded across both recorders


def _streamers_cfg():
    sys.path.insert(0, str(ROOT / "tests"))
    from test_core import streamers_cfg
    return streamers_cfg()


class ProfileRoutingTests(unittest.TestCase):
    @unittest.skipUnless((ROOT / "profiles" / "streamers" / "profile.yaml").exists(), "streamers is a private profile")
    def test_shipped_streamers_profile_excludes_exactly_gta6s_topic(self):
        from clipper import config
        try:
            s, g = config.load(profile="streamers"), config.load(profile="gta6")
        finally:
            config.load()
        self.assertEqual(s["exclude_title_patterns"], g["topic_patterns"])
        self.assertFalse(s["require_topic"])
        self.assertTrue(s["selection_gate"])
        self.assertEqual([c["url"] for c in s["channels"]], [c["url"] for c in g["channels"]])


    def test_a_live_stream_is_on_topic_in_one_profile_only(self):
        """gta6 records a streamer's GTA 6 stream, streamers records everything else they stream; never both."""
        from unittest import mock
        from clipper import config, live
        probes = {"gta": {"live": True, "title": "GTA 6 DAY 3 WE ROB THE BANK"},
                  "irl": {"live": True, "title": "IRL IN TOKYO W SPEED"},
                  "desc": {"live": True, "title": "DAY 3", "description": "playing GTA 6 all night"},
                  "tag": {"live": True, "title": "marathon", "tags": ["GTA6"]},
                  "off": {"live": False}}
        on = {}
        for profile in ("gta6", "streamers"):
            cfg = config.load(profile="gta6") if profile == "gta6" else _streamers_cfg()
            streams = [{"name": k, "url": k, "topic_only": profile == "gta6"} for k in probes]
            with mock.patch.object(live, "load_streams", return_value=streams), \
                    mock.patch.object(live, "probe", side_effect=lambda url: probes[url]), \
                    mock.patch.object(live, "recorder_running", return_value=False):
                on[profile] = {s["name"] for s in live.status(cfg) if s["on_topic"]}
        config.load()
        self.assertEqual(on["gta6"], {"gta", "desc", "tag"})
        self.assertEqual(on["streamers"], {"irl"})

    def test_streamers_watch_drops_gta6_uploads(self):
        from unittest import mock
        from clipper import config, sources
        entries = [{"id": "a", "title": "Kai Cenat Plays GTA 6 For The First Time", "duration": 600},
                   {"id": "b", "title": "Kai Cenat Goes To Japan", "duration": 600},
                   {"id": "c", "title": "Making Connections With Rockstar Employees", "duration": 600}]
        metas = {"b": {"description": "IRL in Tokyo"}, "c": {"description": "We talk about GTA 6 and more"}}
        cfg = {**_streamers_cfg(), "channels": [{"name": "Kai Cenat", "url": "u"}], "search": []}
        gta = {**config.load(profile="gta6"), "channels": cfg["channels"], "search": []}
        config.load()
        with mock.patch.object(sources, "_flat", return_value=({"entries": entries}, None)), \
                mock.patch.object(sources, "_full_meta", side_effect=lambda vid: metas.get(vid)):
            found, _, skipped = sources.watch(cfg)
            claimed, _, _ = sources.watch(gta)
        self.assertEqual([v["id"] for v in found], ["b"])
        self.assertEqual(skipped, 2)
        self.assertEqual([v["id"] for v in claimed], ["a", "c"])  # each upload in exactly one profile


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):  # the recorder hangs up mid-segment when stopped
            pass


if __name__ == "__main__":
    unittest.main()
