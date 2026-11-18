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
