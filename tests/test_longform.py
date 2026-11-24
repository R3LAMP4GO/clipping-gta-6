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



def comp_spec(job="j", n=12, d=50.0, niche="irl", title="Kai Cenat Funniest Moments"):
    return {"kind": "compilation", "niche": niche, "title": title, "face": "full",
            "clips": [clip(job, 100 + i * 60, d) for i in range(n)], "thumbnail": {"job": job, "t": 105}}


class CompilationCheckTest(unittest.TestCase):
    def test_good_compilation_per_niche(self):
        from clipper import longform
        self.assertEqual(longform.check_long(comp_spec()), {})
        self.assertEqual(longform.check_long(comp_spec(title="Best Of xQc And Speed")), {})
        gaming = longform.check_long({**comp_spec(niche="gaming"), "face": [0, 0, 0.25, 0.28]})
        self.assertEqual(list(gaming), ["notes"])
        self.assertIn("16.2%", gaming["notes"][0])
        rp = longform.check_long({**comp_spec(niche="rp"), "face": [0, 0, 0.25, 0.28]})
        self.assertIn("7.8%", rp["notes"][0])
        self.assertIn("set `niche`", longform.check_long({**comp_spec(), "niche": None})["notes"][0])

    def test_compilation_fails(self):
        from clipper import longform
        fails = lambda s: " | ".join(longform.check_long(s).get("fails", []))
        self.assertIn("9 clips", fails(comp_spec(n=9, d=55)))
        self.assertIn("5.0 min total", fails(comp_spec(n=10, d=30)))           # the 3-6 min dead zone
        self.assertIn("16.0 min total", fails(comp_spec(n=16, d=60)))
        self.assertIn("clip 2 is 61s", fails({**comp_spec(), "clips": [clip("j", 100, 50), clip("j", 200, 61)]
                                              + [clip("j", 300 + i * 60, 50) for i in range(10)]}))
        self.assertIn("clip 1 is 5s", fails({**comp_spec(), "clips": [clip("j", 10, 5)] + comp_spec()["clips"]}))
        overlap = comp_spec(); overlap["clips"][1] = clip("j", 120, 50)
        self.assertIn("overlap", fails(overlap))
        self.assertIn("compilation title says", fails(comp_spec(title="Kai Cenat Loses It In Tokyo")))
        self.assertIn("names nobody", fails(comp_spec(title="Funniest Moments Compilation")))
        self.assertNotIn("names nobody", fails({**comp_spec(title="Funniest Moments Of Kai"), "streamer": "Kai"}))
        self.assertIn("names nobody", fails({**comp_spec(title="Funniest Moments Of The Year"), "streamer": "Kai"}))
        self.assertIn("62 chars", fails(comp_spec(title="Kai Cenat Funniest Moments From The Whole Week Of Streams Ever")))
        self.assertIn("pipe or hashtag", fails(comp_spec(title="Kai Cenat Moments | Ep 2")))
        self.assertIn("pipe or hashtag", fails(comp_spec(title="Kai Cenat Moments #shorts")))
        self.assertIn("length promise", fails(comp_spec(title="Kai Cenat Funny Moments For 10 Minutes")))
        self.assertIn("length promise", fails(comp_spec(title="Kai Cenat Funniest Moments 10 Minutes Straight")))
        self.assertIn("no flash-forward", fails({**comp_spec(), "flash_forward": [clip("j", 101, 3)]}))
        self.assertIn("no counter", fails({**comp_spec(), "counter": "#{n}"}))
        self.assertIn("clip 1: no face", fails({**comp_spec(niche="gaming"), "face": None}))
        self.assertEqual(fails({**comp_spec(), "face": None}), "")             # IRL: the streamer is the frame
        self.assertIn("thumbnail.style", fails({**comp_spec(), "thumbnail": {"job": "j", "t": 105, "style": "neon"}}))

    def test_compilation_notes(self):
        from clipper import longform
        notes = lambda s: " | ".join(longform.check_long(s).get("notes", []))
        self.assertIn("7.0 min total: aim for 8-12", notes(comp_spec(n=12, d=35)))
        self.assertIn("13.0 min total", notes(comp_spec(n=13, d=60)))
        self.assertIn("title is 44 chars", notes(comp_spec(title="Kai Cenat And Speed Funniest Moments Of 2026")))
        self.assertIn("over 3 words", notes({**comp_spec(), "thumbnail": {"job": "j", "t": 105, "text": "HE CAN'T BE SERIOUS"}}))
        words = lambda job: [{"w": "yo", "s": 140.0}]                          # first word 40 s into clip 1
        self.assertIn("opens on silence", " | ".join(longform.check_long(comp_spec(), words).get("notes", [])))
        self.assertNotIn("silence", str(longform.check_long(comp_spec(), lambda job: [{"w": "yo", "s": 100.5}])))

    def test_shared_notes_for_every_kind(self):
        from clipper import longform
        notes = longform.shared_notes(spec_for("j"), names=["xQc"])
        self.assertEqual(len(notes), 2)                                        # long, and a pipe
        self.assertIn("chars", notes[0])
        self.assertIn("pipe", notes[1])
        self.assertIn("names nobody", longform.shared_notes({"title": "Funniest Moments"}, names=[])[0])
        self.assertIn("name the streamer (xQc)", " ".join(longform.shared_notes({"title": "Funny Cop Moments"}, names=["xQc"])))
        self.assertEqual(longform.shared_notes({"title": "Kai Cenat Live Moments"}, names=["Kai Cenat Live"]), [])
        self.assertEqual(longform.shared_notes({"title": "KaiCenat Moments"}, names=["Kai Cenat"]), [])
        self.assertIn("series tag", longform.shared_notes({"title": "Kai Moments Part 3"}, names=["Kai"])[0])

    def test_a_deleted_moment_fails_the_check(self):
        from clipper import config, longbank, longform
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            job = make_job(root, "x1", secs=12)
            spec = {**comp_spec("x1"), "clips": [{"job": "x1", "start": 2, "end": 8}]}
            with mock.patch.object(config, "JOBS", root / "jobs"):
                self.assertFalse([f for f in longform.check_long(spec).get("fails", []) if "x1" in f])
                x = longbank.tag("x1", 2, 8, {"longbank_pad_s": 1})
                (job / "source.mp4").unlink()
                fails = longform.check_long({**spec, "thumbnail": {"job": "x1", "t": 10.5}})["fails"]
                self.assertFalse([f for f in fails if f.startswith("clip 1 (")])     # the bank holds it
                self.assertIn("thumbnail (x1 10.5s): its source was deleted", " | ".join(fails))
                self.assertIn("clipper bank tag", " | ".join(fails))
                bd = root / "jobs" / "_longbank" / x["id"]
                (bd / "clip.mp4").unlink()
                longbank.save(bd, {**longbank.load(bd), "deleted_at": 1.0})
                fails = " | ".join(longform.check_long(spec)["fails"])
                self.assertIn("clip 1 (x1 2s): this moment was already used in a posted long video and deleted", fails)


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


def face(area=0.04, x=0.4, top=0.3):
    side = area ** 0.5
    return {"area": area, "y": top + side / 2, "x": x, "top": top, "w": side, "h": side}


def word_box(s, x=0.1, top=0.1, h=0.12):
    return {"s": s, "area": 0.3 * h, "y": top + h / 2, "x": x, "top": top, "w": 0.3, "h": h}


class FakeCodex:
    """Stands in for `codex exec`: writes the original under CODEX_HOME/generated_images/<session>/ (bigger than
    the shown size) and a copy into the workspace, like the real CLI did in the spike."""
    def __init__(self, home, size=(1672, 941)):
        self.home, self.size, self.calls = Path(home), size, []

    def __call__(self, cmd, **kw):
        from PIL import Image
        self.calls.append((cmd, kw))
        sid = f"01a20f7a-0000-0000-0000-00000000000{len(self.calls)}"
        sess = self.home / "generated_images" / sid
        sess.mkdir(parents=True)
        img = Image.new("RGB", self.size, (40 * len(self.calls), 90, 160))
        img.save(sess / "exec-abc.png")
        img.save(Path(cmd[cmd.index("-C") + 1]) / "thumbnail_ai.png")
        return subprocess.CompletedProcess(cmd, 0, f"session id: {sid}\n", "")


class ThumbnailTest(unittest.TestCase):
    def setUp(self):
        from clipper import config, schedule
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patches = [mock.patch.object(config, "JOBS", self.root / "jobs"),
                        mock.patch.object(schedule, "find_agent", lambda a: "/fake/codex"),
                        mock.patch.dict("os.environ", {"CODEX_HOME": str(self.root / "codex")})]
        for p in self.patches:
            p.start()
        self.job = make_job(self.root, "kai1", secs=12)
        self.folder = self.root / "long 1"
        self.folder.mkdir()
        self.spec = {"kind": "compilation", "title": "Kai Cenat Funniest Moments", "streamer": "Kai Cenat",
                     "clips": [{"job": "kai1", "start": 1, "end": 8}],
                     "thumbnail": {"job": "kai1", "t": 3, "text": "NO WAY", "refs": [{"job": "kai1", "t": 6}]}}

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def measure(self, gen):
        """Vision stand-in: the source frame has one face; generated thumbnails get `gen` (full, feed)."""
        def m(paths):
            return [{"faces": [face()], "text": []} if Path(p).name == "thumbnail_source.jpg"
                    else (gen[0] if Path(p).suffix == ".jpg" else gen[1]) for p in paths]
        return m

    GOOD = ({"faces": [face()], "text": [word_box("NO WAY")]}, {"faces": [face()], "text": [word_box("NO WAY")]})

    def test_prompt_carries_every_principle_the_words_size_and_reference_rules(self):
        from clipper import longform
        p = longform.build_thumbnail_prompt("no way at all", ["Kai Cenat"], ["thumbnail_ref1.jpg", "thumbnail_style.jpg"])
        self.assertTrue(p.startswith("$imagegen"))
        for rule in longform.THUMB_PRINCIPLES["do"] + longform.THUMB_PRINCIPLES["dont"]:
            self.assertIn(rule, p)
        for bit in ('exactly "NO WAY AT"', "1536x864", "1280x720", "168x94", "Never vertical", "bottom-right corner",
                    "4% from every edge", "Image 1 is the scene", "Image 2 is only a reference for this person's face",
                    "never swap or invent a face", "Image 3 is only a layout", "do not add, remove or restyle people",
                    "Kai Cenat", "thumbnail_ai.png"):
            self.assertIn(bit, p)
        self.assertIn("Words: none", longform.build_thumbnail_prompt(""))
        self.assertIn("fix it: 2 faces", longform.build_thumbnail_prompt("", retry="2 faces"))

    def test_ai_thumbnail_is_moved_checked_and_exactly_youtube_size(self):
        from clipper import longform
        from PIL import Image
        codex = FakeCodex(self.root / "codex")
        info = longform.make_thumbnail(self.spec, self.folder, {}, {"thumbnail_codex_model": "gpt-6.1-terra"},
                                       run=codex, measure=self.measure(self.GOOD))
        self.assertEqual((info["style"], info["attempts"], info["reason"]), ("ai", 1, None))
        cmd, kw = codex.calls[0]
        self.assertEqual(cmd[:3], ["/fake/codex", "exec", "--skip-git-repo-check"])
        self.assertEqual(cmd[cmd.index("-m") + 1], "gpt-6.1-terra")
        self.assertIn("workspace-write", cmd)
        self.assertIn('approval_policy="never"', cmd)
        self.assertEqual([cmd[i + 1].split("/")[-1] for i, x in enumerate(cmd) if x == "-i"],
                         ["thumbnail_source.jpg", "thumbnail_ref1.jpg"])
        self.assertEqual(cmd[-2], "--")
        self.assertEqual(kw["timeout"], longform.CODEX_TIMEOUT_S)
        out = self.folder / "thumbnail.jpg"
        with Image.open(out) as im:
            self.assertEqual(im.size, (1280, 720))
        self.assertLessEqual(out.stat().st_size, 2_000_000)
        with Image.open(self.folder / "thumbnail_ai.png") as im:
            self.assertEqual(im.size, (1672, 941))  # the original, moved in over Codex's resized copy
        self.assertFalse(list((self.root / "codex" / "generated_images").iterdir()))  # moved, not copied
        self.assertFalse((self.folder / "thumbnail_try.jpg").exists())
        self.assertEqual(info["sha256"], longform._sha256(out))

    def test_a_failed_check_retries_once_then_falls_back_to_the_raw_frame(self):
        from clipper import longform
        two = ({"faces": [face(), face(0.03, x=0.1)], "text": [word_box("NO WAY")]}, self.GOOD[1])
        codex = FakeCodex(self.root / "codex")
        info = longform.make_thumbnail(self.spec, self.folder, {}, {}, run=codex, measure=self.measure(two))
        self.assertEqual(len(codex.calls), 2)
        self.assertIn("fix it: 2 faces", codex.calls[1][0][-1])
        self.assertEqual(info["style"], "raw")
        self.assertIn("2 faces, the source frame has 1", info["reason"])
        self.assertEqual((self.folder / "thumbnail.jpg").read_bytes(), (self.folder / "thumbnail_source.jpg").read_bytes())
        self.assertIn("raw frame has no words", info["note"])

    def test_check_rejects_each_miss(self):
        from clipper import longform
        from PIL import Image
        jpg = self.folder / "t.jpg"
        Image.new("RGB", (1280, 720), (20, 20, 20)).save(jpg)

        def why(full, tiny=None, text="NO WAY", path=jpg, src=1):
            ok, reasons, _ = longform.check_thumbnail(path, text, src, lambda ps: [full, tiny or full])
            return "" if ok else " | ".join(reasons)
        good = {"faces": [face()], "text": [word_box("NO WAY")]}
        self.assertEqual(why(good), "")
        small = self.folder / "small.jpg"
        Image.new("RGB", (1000, 600)).save(small)
        self.assertIn("1000x600, not 1280x720", why(good, path=small))
        big = self.folder / "big.png"
        Image.frombytes("RGB", (1280, 720), __import__("os").urandom(1280 * 720 * 3)).save(big)
        self.assertIn("over 2 MB", why(good, path=big))
        self.assertIn("2 faces, the source frame has 1", why({**good, "faces": [face(), face(0.03, x=0.1)]}))
        self.assertIn("biggest face is 15.0%", why({**good, "faces": [face(0.15, x=0.3)]}))
        self.assertIn("biggest face is 1.0%", why({**good, "faces": [face(0.01)]}))
        self.assertIn("words on it: no way subscribe", why({**good, "text": [word_box("NO WAY"), word_box("SUBSCRIBE", top=0.5)]}))
        self.assertEqual(why({**good, "text": [word_box("NO WAY"), word_box("chat: lol", h=0.03)]}), "")  # small overlay text
        self.assertIn("4 words asked for", why(good, text="WAIT FOR IT NOW"))
        self.assertIn("words in the bottom-right corner", why({**good, "text": [word_box("NO WAY", x=0.75, top=0.86)]}))
        self.assertIn("a face in the bottom-right corner", why({**good, "faces": [face(0.03, x=0.85, top=0.8)]}))
        self.assertIn("within 4% of the edge", why({**good, "faces": [face(0.03, x=0.01, top=0.3)]}))
        self.assertIn("face is lost at feed size", why(good, {"faces": [], "text": good["text"]}))
        self.assertIn("words can't be read at feed size", why(good, {"faces": [face()], "text": []}))
        self.assertIn("Apple Vision couldn't run", longform.check_thumbnail(jpg, "", 1, lambda ps: None)[1][0])
        # the real run's false alarms: a painting sharpened into a small face at the edge, and the T-shirt print
        painting = {**good, "faces": [face(0.04, x=0.45), face(0.018, x=0.94, top=0.47)]}  # 45% of the main face
        self.assertEqual(why(painting), "")
        shirt = {**good, "text": [word_box("NO WAY"), {**word_box("A CD 15 BIGGER", x=0.409, top=0.671, h=0.182), "w": 0.18}]}
        self.assertIn("words on it: no way a cd 15 bigger", why(shirt))
        ok, reasons, _ = longform.check_thumbnail(jpg, "NO WAY", 1, lambda ps: [shirt, shirt],
                                                  [{**word_box("IS BIGGER THE", x=0.449, top=0.666, h=0.083), "w": 0.14}])
        self.assertEqual(reasons, [])                                          # already in the source frame
        self.assertIn("2 faces", why({**good, "faces": [face(), face(0.02, x=0.1)]}))  # a real second person
        chat = [word_box("lol", x=0.15, top=0.12, h=0.03), word_box("W", x=0.2, top=0.16, h=0.03)]
        self.assertEqual(longform.check_thumbnail(jpg, "NO WAY", 1, lambda ps: [good, good], chat)[1], [])  # touches chat

    def test_finalize_is_exactly_1280x720_under_2mb(self):
        import os
        from clipper import longform
        from PIL import Image
        noisy = self.folder / "noisy.png"
        Image.frombytes("RGB", (2048, 1152), os.urandom(2048 * 1152 * 3)).save(noisy)
        out = longform.finalize_thumbnail(noisy, self.folder / "o.jpg")
        with Image.open(out) as im:
            self.assertEqual(im.size, (1280, 720))
        self.assertLessEqual(out.stat().st_size, 2_000_000)

    def test_codex_missing_timeout_off_raw_and_face_never_fail_the_render(self):
        from clipper import longform, schedule

        def slow(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, kw["timeout"])
        m = self.measure(self.GOOD)
        self.assertIn("timed out", longform.make_thumbnail(self.spec, self.folder, {}, {}, run=slow, measure=m)["reason"])
        self.assertIn("--no-ai-thumb", longform.make_thumbnail(self.spec, self.folder, {}, {}, ai=False)["reason"])
        raw = {**self.spec, "thumbnail": {**self.spec["thumbnail"], "style": "raw"}}
        self.assertEqual(longform.make_thumbnail(raw, self.folder, {}, {}, run=slow)["style"], "raw")
        old = {**self.spec, "thumbnail": {**self.spec["thumbnail"], "style": "face"}}
        self.assertEqual(longform.make_thumbnail(old, self.folder, {}, {}, run=slow)["style"], "face")
        with mock.patch.object(schedule, "find_agent", lambda a: None):
            info = longform.make_thumbnail(self.spec, self.folder, {}, {}, run=slow, measure=m)
        self.assertEqual((info["style"], info["reason"]), ("raw", "codex CLI not found"))

    def test_references_from_deleted_sources_and_missing_exemplars_are_skipped(self):
        from clipper import longform
        other = make_job(self.root, "kai2", secs=4)
        (other / "source.mp4").unlink()
        spec = {**self.spec, "thumbnail": {**self.spec["thumbnail"], "exemplar": "nope.jpg",
                                           "refs": [{"job": "kai2", "t": 1}, {"job": "kai1", "t": 5}]}}
        refs, notes = longform.thumbnail_refs(spec, self.folder)
        self.assertEqual([p.name for p in refs], ["thumbnail_ref2.jpg"])
        self.assertIn("kai2's source was deleted", notes[0])
        self.assertIn("nope.jpg is missing", notes[1])


class CompilationRenderTest(unittest.TestCase):
    def test_compilation_renders_from_the_bank_and_marks_its_clips_used(self):
        from clipper import config, longbank, longform
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            job = make_job(root, "kai1", secs=20)
            spec = {"kind": "compilation", "niche": "irl", "title": "Speed Funniest Moments", "face": "full",
                    "counter": "#{n}", "flash_forward": [{"job": "kai1", "start": 3, "end": 4}],
                    "clips": [{"job": "kai1", "start": 2, "end": 6}, {"job": "kai1", "start": 10, "end": 13}],
                    "thumbnail": {"job": "kai1", "t": 3, "text": "NO WAY"}}
            with mock.patch.object(config, "JOBS", root / "jobs"):
                a = longbank.tag("kai1", 2, 6, {"longbank_pad_s": 1})
                b = longbank.tag("kai1", 10, 13, {"longbank_pad_s": 1})
                spare = longbank.tag("kai1", 15, 18, {"longbank_pad_s": 1})
                (job / "source.mp4").unlink()
                res = longform.render_long(spec, {"profile": "streamers"}, root / "out", check=False)
                self.assertAlmostEqual(res["duration"], 7.0, delta=0.5)        # no flash-forward
                m = json.loads((Path(res["folder"]) / "long.json").read_text())
                self.assertEqual((m["kind"], m["niche"], m["flash_forward_s"]), ("compilation", "irl", 0.0))
                self.assertEqual(sorted(m["bank_ids"]), sorted([a["id"], b["id"]]))
                self.assertEqual((m["thumbnail_style"], m["thumbnail_reason"]), ("raw", "AI thumbnails are off (--no-ai-thumb)"))
                self.assertEqual(len(m["thumbnail_sha256"]), 64)
                self.assertEqual(m["spec_sha256"], longform.spec_sha256(spec))
                self.assertTrue((Path(res["folder"]) / "thumbnail_source.jpg").exists())
                for x, status in ((a, "used"), (b, "used"), (spare, "tagged")):
                    saved = longbank.load(root / "jobs" / "_longbank" / x["id"])
                    self.assertEqual(saved["status"], status)
                self.assertEqual(longbank.load(root / "jobs" / "_longbank" / a["id"])["used_in"],
                                 [str(Path(res["folder"]).resolve())])
                self.assertEqual(longform.reused_footage(spec, root / "out"), [])  # exempt, like supercuts
