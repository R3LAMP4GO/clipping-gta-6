import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def clip(job, s, d=20.0):
    return {"job": job, "start": s, "end": s + d}


def spec_for(job, n=26, d=20.0):
    clips = [clip(job, 100 + i * 30, d) for i in range(n)]
    return {"title": "xQc Lies To The Cops For 10 Minutes Straight 💀 | NoPixel GTA RP", "counter": "LIE #{n}",
            "clips": clips, "flash_forward": [{"job": job, "start": clips[-1]["start"] + 2, "end": clips[-1]["start"] + 6}],
            "thumbnail": {"job": job, "t": 105, "text": "I'M INNOCENT"}}


class LongCheckTest(unittest.TestCase):
    def test_good_spec_passes(self):
        from clipper import longform
        self.assertEqual(longform.check_long(spec_for("j")), {})

    def test_bad_specs_fail(self):
        from clipper import longform
        fails = lambda s: " | ".join(longform.check_long(s).get("fails", []))
        self.assertIn("min total", fails(spec_for("j", n=13)))                     # 4.4 min
        self.assertIn("at least 12", fails(spec_for("j", n=5, d=40)))
        s = spec_for("j"); s["clips"][3] = clip("j", 100 + 3 * 30, 60)
        self.assertIn("clip 4 is 60s", fails(s))
        s = spec_for("j"); s["clips"][1] = clip("j", 110)                          # overlaps clip 1
        self.assertIn("overlap", fails(s))
        s = spec_for("j"); s["flash_forward"] = [{"job": "j", "start": 5, "end": 9}]
        self.assertIn("must replay a moment", fails(s))
        s = spec_for("j"); s["flash_forward"] = [{"job": "j", "start": c["start"], "end": c["end"]} for c in s["clips"][-2:]]
        self.assertIn("flash-forward is 40s", fails(s))
        s = spec_for("j"); del s["thumbnail"]
        self.assertIn("needs a thumbnail", fails(s))
        self.assertIn("no flash-forward", longform.check_long({**spec_for("j"), "flash_forward": []})["notes"][0])

    def test_face_goes_in_its_own_corner_enlarged(self):
        from clipper import longform
        vf = longform.clip_filter((1920, 1080), [0.0, 0.0, 0.25, 0.28], counter=True)
        self.assertIn("crop=480:302:0:0,scale=-2:454", vf)
        self.assertIn("overlay=24:24", vf)
        self.assertIn("[v0][c]overlay=0:0[v1]", vf)
        self.assertIn("overlay=main_w-overlay_w-24:24", longform.clip_filter((1920, 1080), [0.75, 0.0, 0.25, 0.28]))
        self.assertNotIn("crop=", longform.clip_filter((1920, 1080), None))


class LongRenderTest(unittest.TestCase):
    def test_renders_16x9_with_thumbnail_and_manifest_outside_video_folders(self):
        from clipper import config, longform
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            job = root / "jobs" / "src1"
            job.mkdir(parents=True)
            subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=1280x720:d=30",
                            "-f", "lavfi", "-i", "sine=f=440:d=30", "-shortest", "-pix_fmt", "yuv420p",
                            str(job / "source.mp4")], check=True)
            (job / "job.json").write_text(json.dumps({"id": "src1", "url": "https://www.youtube.com/watch?v=src1",
                                                      "title": "stream", "channel": "xQc"}))
            spec = {"title": "xQc Test Supercut", "counter": "LIE #{n}", "face": [0.0, 0.0, 0.25, 0.28],
                    "clips": [{"job": str(job), "start": 2, "end": 5}, {"job": str(job), "start": 10, "end": 13}],
                    "flash_forward": [{"job": str(job), "start": 11, "end": 12}],
                    "thumbnail": {"job": str(job), "t": 3, "text": "I'M INNOCENT"}}
            with mock.patch.object(config, "JOBS", root / "jobs"):
                res = longform.render_long(spec, {"profile": "gta-rp"}, root / "out", check=False)
            folder = Path(res["folder"])
            self.assertEqual(folder.name, "long 1")
            self.assertEqual(res["size"], "1920x1080")
            self.assertAlmostEqual(res["duration"], 7.0, delta=0.5)
            from PIL import Image
            with Image.open(folder / "thumbnail.jpg") as im:
                self.assertEqual(im.size, (1280, 720))
            m = json.loads((folder / "long.json").read_text())
            self.assertEqual((m["kind"], m["clips"], m["flash_forward_s"]), ("long", 2, 1.0))
            self.assertIn("watch?v=src1", m["description"])
            self.assertFalse(list((root / "out").glob("video */upload.json")))  # never picked up as a Short
        with self.assertRaises(SystemExit):
            longform.render_long({"title": "x", "clips": []}, {}, None)


def mid_spec(job="j", title="What Happens If You Leave Lucia In Prison In GTA 6?"):
    return {"kind": "mid", "title": title, "clips": [clip(job, 100, 40), clip(job, 200, 30)],
            "payoff": {"clip": 1, "t": 130}, "thumbnail": {"job": job, "t": 105, "text": "SHE'S STILL THERE"}}


class MidCheckTest(unittest.TestCase):
    def test_good_mid_passes_and_narrated_situation_titles_pass(self):
        from clipper import longform
        self.assertEqual(longform.check_long(mid_spec()), {})
        self.assertEqual(longform.check_long(mid_spec(title="Speed Asks A Stranger For $1,000 In Tokyo 😳")), {})

    def test_mid_fails(self):
        from clipper import longform
        fails = lambda s: " | ".join(longform.check_long(s).get("fails", []))
        self.assertIn("no situation or question", fails(mid_spec(title="INSANE GTA 6 MOMENT 😱")))
        self.assertIn("no situation or question", fails(mid_spec(title="Kai Cenat Was Not Ready")))
        late = {**mid_spec(), "payoff": {"clip": 2, "t": 225}}                  # 65s into 70s
        self.assertIn("payoff lands 65s into 70s", fails(late))
        self.assertIn("no `payoff`", fails({k: v for k, v in mid_spec().items() if k != "payoff"}))
        self.assertIn("outside clip 1", fails({**mid_spec(), "payoff": {"clip": 1, "t": 300}}))
        self.assertIn("no flash-forward", fails({**mid_spec(), "flash_forward": [clip("j", 101, 3)]}))
        five = {**mid_spec(), "clips": [clip("j", 100 + i * 20, 10) for i in range(5)]}
        self.assertIn("5 clips", fails(five))
        self.assertIn("200s total", fails({**mid_spec(), "clips": [clip("j", 100, 120), clip("j", 300, 80)]}))
        self.assertIn("kind 'reel'", fails({**mid_spec(), "kind": "reel"}))


def make_job(root, name="src1", secs=30):
    job = root / "jobs" / name
    job.mkdir(parents=True)
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=s=1280x720:d={secs}",
                    "-f", "lavfi", "-i", f"sine=f=440:d={secs}", "-shortest", "-pix_fmt", "yuv420p",
                    str(job / "source.mp4")], check=True)
    (job / "job.json").write_text(json.dumps({"id": name, "url": f"https://www.youtube.com/watch?v={name}",
                                              "title": "stream", "channel": "Speed"}))
    return job


class MidRenderTest(unittest.TestCase):
    def test_mid_renders_without_flash_forward_or_counter(self):
        from clipper import config, longform
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            job = make_job(root)
            spec = {"kind": "mid", "title": "Speed Asks A Stranger For $1,000 😳", "counter": "ASK #{n}",
                    "clips": [{"job": str(job), "start": 2, "end": 6}, {"job": str(job), "start": 10, "end": 12}],
                    "flash_forward": [{"job": str(job), "start": 3, "end": 4}],
                    "payoff": {"clip": 1, "t": 4}, "thumbnail": {"job": str(job), "t": 3, "text": "$1,000"}}
            with mock.patch.object(config, "JOBS", root / "jobs"):
                res = longform.render_long(spec, {"profile": "streamers"}, root / "out", check=False)
            self.assertAlmostEqual(res["duration"], 6.0, delta=0.5)  # the flash-forward isn't rendered
            m = json.loads((Path(res["folder"]) / "long.json").read_text())
            self.assertEqual((m["kind"], m["clips"], m["flash_forward_s"]), ("mid", 2, 0.0))


def story_spec(job="j", n=10, d=30.0):
    clips = [{**clip(job, 100 + i * 60, d), "payoff_at": 100 + i * 60 + d - 4} for i in range(n)]
    return {"kind": "story", "title": "How IShowSpeed Ended Up Lost In Tokyo With No Money",
            "clips": clips, "thumbnail": {"job": job, "t": 105, "text": "NO MONEY"},
            "narration": [{"at": 1, "text": "Speed landed in Tokyo with no money. How does he get home?"},
                          {"at": 4, "text": "Three hours later, nobody had helped him.", "mode": "duck"},
                          {"at": n + 1, "text": "He made it home the next morning."}]}


class StoryCheckTest(unittest.TestCase):
    def test_good_story_passes(self):
        from clipper import longform
        talk = lambda job: [{"w": "yo", "s": 100 + i * 2.0, "e": 100.5 + i * 2.0} for i in range(400)]
        self.assertEqual(longform.check_long(story_spec(), talk), {})
        timeline, total, narrated = longform.story_timeline(story_spec())
        self.assertEqual([e["mode"] for e in timeline], ["freeze", "duck", "freeze"])
        self.assertAlmostEqual(total, 300 + timeline[0]["dur"] + timeline[2]["dur"])

    def test_story_fails(self):
        from clipper import longform
        fails = lambda s, w=None: " | ".join(longform.check_long(s, w).get("fails", []))
        over = story_spec()
        over["narration"][1] = {"at": 4, "mode": "duck", "text": " ".join(["word"] * 70)}  # ~27 s over a 30 s clip
        self.assertIn("talks over clip 4's payoff", fails(over))
        chatty = story_spec()
        chatty["narration"].append({"at": 5, "text": " ".join(["word"] * 500)})  # ~40%
        self.assertIn("narrator takes", fails(chatty))
        late = story_spec()
        late["narration"][0] = {"at": 2, "text": "How does he get home?"}  # after a 30 s clip
        self.assertIn("by 15s", fails(late))
        none = story_spec()
        none["narration"][0]["text"] = "Speed landed in Tokyo with no money."
        self.assertIn("states the question", fails(none))
        none["narration"][0]["question"] = True
        self.assertNotIn("states the question", fails(none))
        silent = lambda job: [{"w": "yo", "s": 101.0, "e": 101.5}]  # only clip 1 has anyone talking
        self.assertIn("clip 2: nobody talks", fails(story_spec(), silent))
        self.assertIn("no transcript", longform.check_long(story_spec(), lambda job: None)["notes"][0])
        self.assertIn("min total", fails(story_spec(n=5)))
        self.assertIn("no `narration`", fails({**story_spec(), "narration": []}))
        self.assertIn("freeze only", fails({**story_spec(), "narration": [{"at": 11, "text": "x?", "mode": "duck"}]}))


class StoryRenderTest(unittest.TestCase):
    def test_story_freezes_and_ducks_narration_and_keeps_it_off_the_payoff(self):
        from clipper import config, longform, tts
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            job = make_job(root)

            def fake_synth(text, cfg, out):  # 1 s of tone at 880 Hz stands in for the voice
                subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                                "sine=f=880:d=1", "-ar", "44100", "-ac", "1", str(out)], check=True)
                return 1.0, "say"
            spec = {"kind": "story", "title": "Speed Lost In Tokyo",
                    "clips": [{"job": str(job), "start": 2, "end": 6, "payoff_at": 5.5},
                              {"job": str(job), "start": 10, "end": 13}],
                    "narration": [{"at": 1, "text": "How does he get home?"},
                                  {"at": 2, "text": "Hours later.", "mode": "duck"}],
                    "thumbnail": {"job": str(job), "t": 3, "text": "LOST"}}
            with mock.patch.object(config, "JOBS", root / "jobs"), mock.patch.object(tts, "synth", fake_synth):
                res = longform.render_long(spec, {"profile": "streamers"}, root / "out", check=False)
                m = json.loads((Path(res["folder"]) / "long.json").read_text())
                self.assertEqual(m["kind"], "story")
                self.assertAlmostEqual(res["duration"], 4 + 3 + 1.3, delta=0.5)  # clips + one frozen line
                self.assertEqual([(x["mode"], x["from"], x["to"]) for x in m["narration"]],
                                 [("freeze", 0.0, 1.3), ("duck", 5.3, 6.6)])
                late = {**spec, "narration": [{"at": 1, "text": "x?", "mode": "duck"}]}
                late["clips"] = [{**spec["clips"][0], "payoff_at": 2.5}, spec["clips"][1]]
                with self.assertRaises(SystemExit):  # the voiced line covers the payoff
                    longform.render_long(late, {"profile": "streamers"}, root / "out2", check=False)
                self.assertFalse((root / "out2" / "long 1").exists())


class ShapeReuseTest(unittest.TestCase):
    def test_one_moment_once_per_shape(self):
        from clipper import config, longform, render
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            job = make_job(root, "x1", secs=2)
            exports = root / "exports"
            short = exports / "streamers" / "2026-11-23" / "video 1"
            short.mkdir(parents=True)
            (short / "upload.json").write_text(json.dumps([{"footage": [{"source": "x1", "from": 100, "to": 140}]}]))
            spec = {"kind": "mid", "clips": [{"job": str(job), "start": 100, "end": 140}]}
            self.assertEqual(longform.reused_footage(spec, exports), [])  # a Short of it is fine
            fp = [{"source": "x1", "from": 100, "to": 140}]
            self.assertEqual(len(render.footage_reuse(fp, exports)), 1)  # but not a second Short
            mid = exports / "streamers" / "2026-11-23" / "long 1"
            mid.mkdir()
            (mid / "long.json").write_text(json.dumps({"kind": "mid", "footage": fp}))
            fails = longform.reused_footage(spec, exports)
            self.assertIn("long 1 already uses 40s", fails[0])
            self.assertEqual(longform.reused_footage({**spec, "kind": "story"}, exports), [])
            self.assertEqual(longform.reused_footage({**spec, "kind": "supercut"}, exports), [])
            self.assertEqual(len(render.footage_reuse(fp, exports)), 1)  # Shorts don't see long videos
