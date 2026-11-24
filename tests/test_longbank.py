import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def make_job(root, name="src1", secs=40, meta=None):
    job = root / "jobs" / name
    job.mkdir(parents=True)
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=s=1280x720:d={secs}",
                    "-f", "lavfi", "-i", f"sine=f=440:d={secs}", "-shortest", "-pix_fmt", "yuv420p",
                    str(job / "source.mp4")], check=True)
    (job / "job.json").write_text(json.dumps({"id": name, "url": f"https://www.youtube.com/watch?v={name}",
                                              "title": "stream", "channel": "Speed", **(meta or {})}))
    return job


def frame_md5(path, at):
    return subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-ss", f"{at:.3f}", "-i", str(path),
                           "-frames:v", "1", "-vf", "scale=320:180", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                          capture_output=True, check=True).stdout


def diff(a, b):
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


class BankTagTest(unittest.TestCase):
    def setUp(self):
        from clipper import config
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patch = mock.patch.object(config, "JOBS", self.root / "jobs")
        self.patch.start()
        self.job = make_job(self.root)

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_tag_cuts_a_padded_clip_and_records_it(self):
        from clipper import longbank, render
        x = longbank.tag("src1", 10, 18, {"longbank_pad_s": 3}, note="scream", niche="irl")
        d = self.root / "jobs" / "_longbank" / x["id"]
        self.assertTrue((d / "clip.mp4").exists())
        saved = json.loads((d / "clip.json").read_text())
        self.assertEqual((saved["job"], saved["start"], saved["end"], saved["from"], saved["to"]), ("src1", 10, 18, 7, 21))
        self.assertEqual((saved["status"], saved["niche"], saved["note"], saved["channel"]), ("tagged", "irl", "scream", "Speed"))
        self.assertEqual(saved["bytes"], (d / "clip.mp4").stat().st_size)
        self.assertEqual(render.source_size(d / "clip.mp4"), (1280, 720))  # same size, so facecam boxes still fit
        self.assertAlmostEqual(longbank._duration(d / "clip.mp4"), 14, delta=0.2)
        self.assertTrue(longbank.tag("src1", 11, 17, {})["already_banked"])  # already held: not cut twice
        edge = longbank.tag("src1", 1, 4, {"longbank_pad_s": 3})
        self.assertEqual(edge["from"], 0)  # the pad stops at the start of the source
        with self.assertRaises(SystemExit):
            longbank.tag("src1", 30, 50, {})  # past the end

    def test_source_for_falls_back_to_the_bank_once_the_source_is_gone(self):
        from clipper import longbank, longform
        item = {"job": "src1", "start": 10, "end": 18}
        self.assertEqual(longform.source_for(item), (self.job / "source.mp4", 0.0))
        x = longbank.tag("src1", 10, 18, {"longbank_pad_s": 3})
        before = frame_md5(self.job / "source.mp4", 12.0)
        (self.job / "source.mp4").unlink()
        src, shift = longform.source_for(item)
        self.assertEqual((src.name, shift), ("clip.mp4", 7.0))
        self.assertLess(diff(frame_md5(src, 12.0 - shift), before), 1)  # same picture at the same source second
        self.assertGreater(diff(frame_md5(src, 12.0), before), 2)        # (testsrc2's clock: a wrong offset shows)
        with self.assertRaises(SystemExit) as e:
            longform.source_for({"job": "src1", "start": 25, "end": 30})
        self.assertIn("clipper bank tag", str(e.exception))
        d = self.root / "jobs" / "_longbank" / x["id"]
        (d / "clip.mp4").unlink()
        longbank.save(d, {**longbank.load(d), "deleted_at": 1.0})
        with self.assertRaises(SystemExit) as e:
            longform.source_for(item)
        self.assertIn("already used in a posted long video", str(e.exception))

    def test_tag_needs_the_source(self):
        from clipper import longbank
        (self.job / "source.mp4").unlink()
        with self.assertRaises(SystemExit) as e:
            longbank.tag("src1", 10, 18, {})
        self.assertIn("already deleted", str(e.exception))

    def test_short_moments_reads_the_shorts_footage(self):
        from clipper import longbank
        short = self.root / "exports" / "streamers" / "2026-11-23" / "video 1"
        short.mkdir(parents=True)
        (short / "upload.json").write_text(json.dumps([{"footage": [{"source": "src1", "from": 12, "to": 20}]}]))
        self.assertEqual(longbank.short_moments(short), [("src1", 12.0, 20.0)])
        live = make_job(self.root, "live-x-1", 30, {"live": True, "url": "https://www.twitch.tv/speed",
                                                     "recorded_at": 1000.0})
        (short / "upload.json").write_text(json.dumps([{"footage": [{"source": "twitch:speed", "from": 1005, "to": 1012}]}]))
        self.assertEqual(longbank.short_moments(short), [(live.name, 5.0, 12.0)])

    def test_bank_only_render_matches_a_source_render(self):
        from clipper import longbank, longform
        spec = {"kind": "mid", "title": "Speed Asks A Stranger For $1,000 😳",
                "clips": [{"job": "src1", "start": 2, "end": 6}, {"job": "src1", "start": 10, "end": 13}],
                "payoff": {"clip": 1, "t": 4}, "thumbnail": {"job": "src1", "t": 3, "style": "raw"}}
        a = longform.render_long(spec, {"profile": "streamers"}, self.root / "out", check=False)
        longbank.tag("src1", 2, 6, {"longbank_pad_s": 3})
        longbank.tag("src1", 10, 13, {"longbank_pad_s": 3})
        (self.job / "source.mp4").unlink()
        b = longform.render_long(spec, {"profile": "streamers"}, self.root / "out", check=False)
        self.assertEqual((a["size"], b["size"]), ("1920x1080", "1920x1080"))
        self.assertAlmostEqual(a["duration"], b["duration"], delta=0.1)
        for t in (1.0, 5.0):
            self.assertLess(diff(frame_md5(a["file"], t), frame_md5(b["file"], t)), 1)


if __name__ == "__main__":
    unittest.main()


DAY = 86400.0
NOW = 1_800_000_000.0


class GuardDrillTest(unittest.TestCase):
    """The deletion rules on a temp copy: only what's used-and-posted past grace, or expired after a warning, goes."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.jobs, self.exports, self.codex = self.root / "jobs", self.root / "exports", self.root / "codex"
        self.bank = self.jobs / "_longbank"
        self.cfg = {"keep_after_post_days": 2, "bank_expire_days": 30, "keep_sources_days": 2,
                    "keep_live_sources_hours": 3}
        self.l1 = self.long("long 1", posted=NOW - 3 * DAY)      # posted, grace over
        self.l2 = self.long("long 2", posted=None)               # rendered, not posted
        self.l3 = self.long("long 3", posted=NOW - 1 * DAY)      # posted, still in grace
        self.a = self.clip("a", "used", [self.l1])
        self.b = self.clip("b", "used", [self.l2])
        self.c = self.clip("c", "tagged", tagged=NOW - 2 * DAY)
        self.d = self.clip("d", "tagged", tagged=NOW - 40 * DAY)
        self.e = self.clip("e", "used", [self.l1, self.l2])
        self.g = self.clip("g", "used", [self.l3])
        src = self.jobs / "vod1"
        src.mkdir(parents=True)
        (src / "source.mp4").write_bytes(b"s" * 50)
        __import__("os").utime(src / "source.mp4", (NOW - DAY, NOW - DAY))  # 1 day old: the age rule keeps it

    def tearDown(self):
        self.tmp.cleanup()

    def long(self, name, posted):
        folder = self.exports / "streamers" / "2026-11-20" / name
        folder.mkdir(parents=True)
        for f in ("thumbnail.jpg", "thumbnail_source.jpg", "thumbnail_ai.png", "thumbnail_ref1.jpg", "Kai.mp4"):
            (folder / f).write_bytes(b"x" * 100)
        (folder / "long.json").write_text(json.dumps({"kind": "compilation", "spec_sha256": f"sha-{name}",
                                                      **({"posted_at": posted} if posted else {})}))
        return folder

    def clip(self, cid, status, used_in=(), tagged=NOW - 5 * DAY, start=10):
        from clipper import longbank
        d = self.bank / cid
        d.mkdir(parents=True)
        (d / "clip.mp4").write_bytes(b"c" * 1000)
        longbank.save(d, {"id": cid, "job": f"job-{cid}", "start": start, "end": start + 8, "from": start - 3,
                          "to": start + 11, "status": status, "used_in": [str(u) for u in used_in],
                          "tagged_at": tagged, "bytes": 1000})
        return d

    def run_cleanup(self, dry=False, cfg=None):
        from clipper import cleanup
        return cleanup.run(cfg or self.cfg, dry, self.jobs, self.exports, NOW, self.codex)

    def alive(self):
        return sorted(d.name for d in self.bank.iterdir() if (d / "clip.mp4").exists())

    def test_drill(self):
        from clipper import longbank
        dry = self.run_cleanup(dry=True)["longform"]
        self.assertEqual(self.alive(), ["a", "b", "c", "d", "e", "g"])       # dry run deletes nothing
        self.assertEqual(dry["files"], 1 + 4)                                 # a's clip + long 1's four thumbnail files
        self.assertEqual(dry["expiring_next_run"], ["d"])                      # listed one run before it goes
        self.assertFalse((self.bank / "ledger.jsonl").exists())
        self.assertNotIn("expire_warned_at", longbank.load(self.d))

        first = self.run_cleanup()["longform"]
        self.assertEqual((first["files"], first["bytes"]), (5, 1000 + 400))
        self.assertEqual(self.alive(), ["b", "c", "d", "e", "g"])
        self.assertEqual(longbank.load(self.a)["deleted_reason"], "used in long 1, posted, 2 days grace over")
        self.assertTrue(longbank.load(self.a)["deleted_at"])                   # the record stays
        second = self.run_cleanup()["longform"]
        self.assertEqual([Path(x["path"]).parent.name for x in second["deleted"]], ["d"])
        self.assertEqual(self.alive(), ["b", "c", "e", "g"])                  # used-unposted, recent, shared, in grace

        self.assertFalse(list(self.l1.glob("thumbnail*")))
        self.assertTrue((self.l1 / "Kai.mp4").exists() and (self.l1 / "long.json").exists())  # never deleted
        self.assertTrue(json.loads((self.l1 / "long.json").read_text())["thumbnail_deleted_at"])
        for folder in (self.l2, self.l3):
            self.assertEqual(len(list(folder.glob("thumbnail*"))), 4)         # unposted / in grace: kept
        self.assertTrue((self.jobs / "vod1" / "source.mp4").exists())          # sources only follow the age rule
        rows = [json.loads(x) for x in (self.bank / "ledger.jsonl").read_text().splitlines()]
        self.assertEqual(len(rows), 6)                                         # one line per deletion
        self.assertEqual({r["reason"] for r in rows if r["path"].endswith("clip.mp4")},
                         {"used in long 1, posted, 2 days grace over", "unused for 30 days"})

    def test_paths_outside_what_owns_them_are_refused(self):
        outside = self.root / "precious.mp4"
        outside.write_bytes(b"p" * 10)
        h = self.clip("h", "used", [self.l1])
        (h / "clip.mp4").unlink()
        (h / "clip.mp4").symlink_to(outside)
        gen = self.codex / "generated_images" / "sess1"
        gen.mkdir(parents=True)
        (gen / "exec-1.png").write_bytes(b"i" * 10)
        stray = self.root / "not-codex"
        stray.mkdir()
        (stray / "keep.png").write_bytes(b"k")
        m = json.loads((self.l2 / "long.json").read_text())
        (self.l2 / "long.json").write_text(json.dumps({**m, "codex_session_dir": str(gen)}))
        m3 = json.loads((self.l3 / "long.json").read_text())
        (self.l3 / "long.json").write_text(json.dumps({**m3, "codex_session_dir": str(stray)}))
        out = self.run_cleanup()["longform"]
        self.assertTrue(outside.exists())
        self.assertTrue((stray / "keep.png").exists())
        self.assertEqual(sorted(Path(p).name for p in out["refused"]), ["clip.mp4", "keep.png"])
        self.assertFalse(gen.exists())                                         # Codex's own leftover goes, folder too

    def test_a_draft_spec_on_disk_keeps_its_clip(self):
        from clipper import longbank
        (self.jobs / "long-kai.json").write_text(json.dumps({"clips": [{"job": "job-a", "start": 12, "end": 16}]}))
        self.run_cleanup()
        self.assertIn("a", self.alive())
        posted_spec = {"clips": [{"job": "job-a", "start": 12, "end": 16}]}
        from clipper.longform import spec_sha256
        m = json.loads((self.l1 / "long.json").read_text())
        (self.l1 / "long.json").write_text(json.dumps({**m, "spec_sha256": spec_sha256(posted_spec)}))
        (self.jobs / "long-kai.json").write_text(json.dumps(posted_spec))        # the posted spec itself doesn't hold it
        self.run_cleanup()
        self.assertNotIn("a", self.alive())
        self.assertTrue(longbank.load(self.a)["deleted_at"])

    def test_bank_done_starts_the_grace(self):
        from clipper import longbank
        res = longbank.mark_posted(self.l2, self.cfg, "yt123", self.bank, now=NOW - 3 * DAY)
        self.assertEqual(sorted(res["bank_clips"]), [])                        # long 2 lists no bank_ids yet
        m = json.loads((self.l2 / "long.json").read_text())
        (self.l2 / "long.json").write_text(json.dumps({**m, "posted_at": None, "bank_ids": ["b", "e"]}))
        res = longbank.mark_posted(self.l2, self.cfg, "yt123", self.bank, now=NOW - 3 * DAY)
        self.assertEqual(sorted(res["bank_clips"]), ["b", "e"])
        self.assertEqual(longbank.load(self.b)["purge_after"], NOW - 1 * DAY)
        self.assertEqual(json.loads((self.l2 / "long.json").read_text())["youtube_id"], "yt123")
        self.run_cleanup()
        self.assertEqual(self.alive(), ["c", "d", "g"])                        # b and e: every long posted now
        with self.assertRaises(SystemExit):
            longbank.mark_posted(self.root / "nowhere", self.cfg)

    def test_short_exports_stay_unless_opted_in(self):
        short = self.exports / "streamers" / "2026-11-01" / "video 1"
        short.mkdir(parents=True)
        (short / "Clip.mp4").write_bytes(b"v" * 10)
        (short / "upload.json").write_text(json.dumps([{"youtube_id": "abc", "footage": []}]))
        import os
        os.utime(short / "upload.json", (NOW - 20 * DAY, NOW - 20 * DAY))
        unposted = self.exports / "streamers" / "2026-11-01" / "video 2"
        unposted.mkdir()
        (unposted / "Clip.mp4").write_bytes(b"v")
        (unposted / "upload.json").write_text(json.dumps([{"footage": []}]))
        os.utime(unposted / "upload.json", (NOW - 20 * DAY, NOW - 20 * DAY))
        self.run_cleanup()
        self.assertTrue((short / "Clip.mp4").exists())                         # null (default): kept
        held = self.clip("s", "tagged", tagged=NOW - DAY)
        from clipper import longbank
        longbank.save(held, {**longbank.load(held), "short": str(short)})
        self.run_cleanup(cfg={**self.cfg, "keep_posted_short_exports_days": 7})
        self.assertTrue((short / "Clip.mp4").exists())                         # an unused bank clip points to it
        (held / "clip.mp4").unlink()
        self.run_cleanup(cfg={**self.cfg, "keep_posted_short_exports_days": 7})
        self.assertFalse((short / "Clip.mp4").exists())
        self.assertTrue((short / "upload.json").exists())                      # reuse checks still see it
        self.assertTrue((unposted / "Clip.mp4").exists())
