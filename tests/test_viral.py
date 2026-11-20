import json
import os
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from clipper import viral


class TempData(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.patches = [mock.patch.object(viral, k, d / v) for k, v in
                        (("DATA", "."), ("MEDIA", "media"), ("VIDEOS", "videos.json"), ("MEASURES", "measures.json"),
                         ("SCORES", "gemini"), ("REPORT", "report.md"))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()


def video(i, views, source="own", fetched_at=None, published="2026-11-01T00:00:00Z"):
    return {"id": f"v{i}", "source": source, "channel_id": "c", "title": f"t{i}", "published": published,
            "duration": 30, "views": views, "likes": 1, "avg_view_s": None, "fetched_at": fetched_at or viral.now()}


class PurgeTests(TempData):
    def test_deletes_youtube_data_and_derived_files_after_30_days(self):
        t = viral.now()
        viral._save(viral.VIDEOS, [video(1, 10, fetched_at=t - 31 * 86400), video(2, 10, fetched_at=t - 86400)])
        viral.MEDIA.mkdir(parents=True)
        for vid in ("v1", "v2"):
            (viral.MEDIA / f"{vid}.mp4").write_bytes(b"x")
        viral._save(viral.MEASURES, {"v1": {"measured_at": t}, "v2": {"measured_at": t}})
        viral._save(viral.SCORES / "full.json", {"v1": {"scored_at": t}, "v2": {"scored_at": t}})
        gone = viral.purge(t=t)
        self.assertEqual(gone, {"videos": 1, "files": 1, "measures": 1, "scores": 1})
        self.assertEqual([v["id"] for v in viral._load(viral.VIDEOS, [])], ["v2"])
        self.assertEqual(sorted(p.name for p in viral.MEDIA.iterdir()), ["v2.mp4"])
        self.assertEqual(list(viral._load(viral.MEASURES, {})), ["v2"])
        self.assertEqual(list(viral._load(viral.SCORES / "full.json", {})), ["v2"])

    def test_old_file_goes_even_if_its_record_is_fresh(self):
        t = viral.now()
        viral._save(viral.VIDEOS, [video(1, 10, fetched_at=t)])
        viral.MEDIA.mkdir(parents=True)
        f = viral.MEDIA / "v1.mp4"
        f.write_bytes(b"x")
        os.utime(f, (t - 40 * 86400, t - 40 * 86400))
        self.assertEqual(viral.purge(t=t)["files"], 1)


class OutlierTests(unittest.TestCase):
    def test_three_times_each_sources_median_and_settling_left_out(self):
        t = viral.now()
        vs = [video(i, v) for i, v in enumerate([100, 100, 100, 300, 299])] + \
             [video(9, 50, source="big"), video(10, 50, source="big"), video(11, 400, source="big")]
        vs.append(video(12, 10_000, published="2099-01-01T00:00:00Z"))  # not out yet: settling
        viral.flag_outliers(vs, t=t)
        self.assertEqual([v["id"] for v in vs if v["outlier"]], ["v3", "v11"])
        self.assertEqual(vs[0]["baseline"], 100)
        self.assertTrue(vs[-1]["settling"])
        self.assertFalse(vs[-1]["outlier"])


class MeasureTests(unittest.TestCase):
    def test_cut_count_and_speech_timing(self):
        stderr = "[Parsed_showinfo_1] n:0 pts:1 pts_time:1.2 ...\n[Parsed_showinfo_1] n:1 pts:9 pts_time:4.8 ...\nother"
        self.assertEqual(viral.count_cuts(stderr), 2)
        words = [{"w": "yo", "s": 0.8, "e": 1.0}, {"w": "what", "s": 1.1, "e": 1.3}, {"w": "now", "s": 1.4, "e": 1.6}]
        self.assertEqual(viral.first_word_and_rate(words, 30), (0.8, 0.1))
        self.assertEqual(viral.first_word_and_rate([], 30), (None, 0.0))


class GeminiTests(TempData):
    good = {f: {"score": 7, "reason": "Kai screams the second the car flips"} for f in viral.GEMINI_FIELDS}

    def test_exactly_the_five_fields_with_scores_1_to_10(self):
        self.assertEqual(viral.parse_scores(json.dumps(self.good))["hook"]["score"], 7)
        for bad in ({**self.good, "extra": {"score": 1, "reason": "x"}},
                    {k: v for k, v in self.good.items() if k != "motion"},
                    {**self.good, "tone": {"score": 11, "reason": "x"}},
                    {**self.good, "energy": {"score": 5, "reason": "two\nlines"}}):
            with self.assertRaises(ValueError):
                viral.parse_scores(json.dumps(bad))

    def test_request_sends_the_video_with_a_strict_schema(self):
        mp4 = Path(self.tmp.name) / "a.mp4"
        mp4.write_bytes(b"video")
        req = viral.gemini_request(mp4, viral.PROMPTS["short2"])
        self.assertEqual(req["contents"][0]["parts"][0]["inline_data"]["mime_type"], "video/mp4")
        schema = req["generationConfig"]["responseSchema"]
        self.assertEqual(schema["required"], viral.GEMINI_FIELDS)
        self.assertEqual(req["generationConfig"]["responseMimeType"], "application/json")

    def test_no_key_sends_nothing(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch("urllib.request.urlopen") as u:
            with self.assertRaises(SystemExit):
                viral.score(["full"])
            u.assert_not_called()

    def test_five_shorter_prompts(self):
        shorter = [k for k in viral.PROMPTS if k != "full"]
        self.assertEqual(len(shorter), 5)
        self.assertTrue(all(len(viral.PROMPTS[k]) < len(viral.PROMPTS["full"]) for k in shorter))


class CompareValidateTests(unittest.TestCase):
    def rows(self, n=200, seed=3):
        rng = random.Random(seed)
        out = []
        for i in range(n):
            outlier = i % 7 == 0  # odd and even i, so both sources get outliers
            out.append({"id": f"v{i}", "source": "own" if i % 2 else "big", "outlier": outlier, "views": 1,
                        "length_s": rng.uniform(15, 40), "cuts": rng.randint(8, 14) if outlier else rng.randint(0, 9),
                        "first_word_s": rng.uniform(0, 2), "words_per_s": rng.uniform(1, 3),
                        "loudness_lufs": rng.uniform(-20, -10)})
        return out

    def test_gap_found_where_it_exists_and_explained_per_source(self):
        c = viral.compare(self.rows(), viral.CODE_METRICS)
        self.assertGreater(c["cuts"]["gap"], 0)
        self.assertGreater(c["cuts"]["auc"], 0.8)
        self.assertLess(abs(c["loudness_lufs"]["auc"] - 0.5), 0.2)
        self.assertIn("2 of 2 sources", viral.explain("cuts", c["cuts"]))

    def test_validation_beats_chance_when_a_real_signal_exists_and_not_otherwise(self):
        rows = self.rows()
        v = viral.validate(rows, viral.CODE_METRICS, runs=50, sample=30)
        self.assertEqual(v["runs"], 50)
        self.assertGreater(v["top_m_precision"], v["chance"] + 0.3)
        self.assertIn("cuts", v["rules_used"])
        noise = [{**r, "cuts": random.Random(i).randint(0, 14)} for i, r in enumerate(rows)]
        v = viral.validate(noise, ["cuts"], runs=50, sample=30)
        self.assertLess(v["top_m_precision"], v["chance"] + 0.25)

    def test_rules_learned_without_the_hidden_videos(self):
        rows = self.rows()
        seen = []
        real = viral.derive_rules
        with mock.patch.object(viral, "derive_rules", side_effect=lambda tr, m: seen.append(len(tr)) or real(tr, m)):
            viral.validate(rows, viral.CODE_METRICS, runs=3, sample=30)
        self.assertEqual(seen, [170, 170, 170])  # 200 rows minus the 30 hidden


class ReportTests(TempData):
    def test_report_without_gemini_says_so(self):
        t = viral.now()
        vs = [video(i, 1000 if i % 6 else 5000) for i in range(60)]
        viral._save(viral.VIDEOS, vs)
        viral._save(viral.MEASURES, {v["id"]: {"length_s": 30, "cuts": 12 if v["views"] == 5000 else 3,
                                               "first_word_s": 0.5, "words_per_s": 2, "loudness_lufs": -14,
                                               "measured_at": t} for v in vs})
        text = viral.report(runs=10, sample=20)
        self.assertIn("| cuts |", text)
        self.assertIn("Not run: no scores yet", text)
        self.assertTrue(viral.REPORT.exists())


if __name__ == "__main__":
    unittest.main()


class AppleAsrTests(unittest.TestCase):
    def test_apple_backend_returns_clipper_words(self):
        from clipper import transcribe
        out = json.dumps({"words": [{"w": "Whoa,", "s": 0.06, "e": 0.6000001}, {"w": "okay.", "s": 0.6, "e": 0.96}]})
        done = mock.Mock(returncode=0, stdout=out, stderr="")
        with mock.patch.object(transcribe, "apple_binary", return_value=Path("/x/apple-asr")), \
                mock.patch.object(transcribe.subprocess, "run", return_value=done) as run:
            words, events, model = transcribe.transcribe("a.wav", "a", {"asr": "apple"})
        self.assertEqual(words, [{"w": "Whoa,", "s": 0.06, "e": 0.6}, {"w": "okay.", "s": 0.6, "e": 0.96}])
        self.assertEqual((events, model), ([], "apple-speechtranscriber"))
        self.assertEqual(run.call_args[0][0], ["/x/apple-asr", "a.wav", "en-US"])

    def test_viral_measures_with_apples_model_not_parakeet(self):
        from clipper import signals, transcribe
        with tempfile.TemporaryDirectory() as d:
            mp4 = Path(d, "v.mp4")
            mp4.write_bytes(b"x")
            Path(d, "v.wav").write_bytes(b"x")
            probe = mock.Mock(returncode=0, stdout="20.0\n", stderr="pts_time:1 pts_time:2")
            with mock.patch.object(viral.subprocess, "run", return_value=probe), \
                    mock.patch.object(signals, "integrated_loudness", return_value=-14.0), \
                    mock.patch.object(transcribe, "transcribe", return_value=([{"w": "yo", "s": 1.0, "e": 1.2}], [], "m")) as tr:
                out = viral.measure_one(mp4, {"asr": "parakeet"})
        self.assertEqual(tr.call_args[0][2]["asr"], "apple")
        self.assertEqual((out["length_s"], out["cuts"], out["first_word_s"]), (20.0, 2, 1.0))


class BotCheckTests(TempData):
    def test_stops_downloading_at_youtubes_bot_check(self):
        blocked = mock.Mock(returncode=1, stdout="", stderr="ERROR: Sign in to confirm you’re not a bot.")
        viral._save(viral.VIDEOS, [video(1, 10), video(2, 10), video(3, 10)])
        with mock.patch.object(viral.subprocess, "run", return_value=blocked) as run, \
                mock.patch.object(viral.time, "sleep"):
            self.assertEqual(viral.measure({}), 0)
        self.assertEqual(run.call_count, 1)  # no second request after the block
