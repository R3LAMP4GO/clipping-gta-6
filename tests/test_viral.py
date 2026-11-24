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
                         ("SCORES", "gemini"), ("REPORT", "report.md"), ("LABELS", "labels.json"),
                         ("OPENINGS", "openings.json"))]
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
        self.assertEqual(gone, {"videos": 1, "files": 1, "derived": 1, "scores": 1})
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


class PurgeIsolationTests(TempData):
    def test_purge_only_touches_the_patched_data_folder(self):
        # regression: derived-file paths were bound at import, so a purge in a test emptied the real viral/ files
        viral.purge(t=viral.now())
        for path in (viral.MEASURES, viral.LABELS, viral.OPENINGS):
            self.assertTrue(str(path).startswith(self.tmp.name), path)


class ImportTests(TempData):
    def test_merge_dedupes_keeps_fresher_record_and_original_fetch_date(self):
        d = Path(self.tmp.name)
        viral._save(viral.VIDEOS, [video(1, 999)])
        ext = d / "ext.json"
        ext.write_text(json.dumps([{"ch": "A", "cid": "UCa", "id": "v1", "views": 500, "t": "dup"},
                                   {"ch": "A", "cid": "UCa", "id": "v2", "views": 700, "t": "new"}]))
        os.utime(ext, (1_790_000_000, 1_790_000_000))
        grouped = d / "grouped.json"
        grouped.write_text(json.dumps({"hit": [{"id": "v1", "dur": 21}, {"id": "v2", "dur": 33, "pub": "2026-09-01"}],
                                       "flop": []}))
        self.assertEqual(viral.import_study(ext, grouped), {"added": 1, "total": 2})
        v = {x["id"]: x for x in viral._load(viral.VIDEOS, [])}
        self.assertEqual(v["v1"]["views"], 999)  # the fresher, exact record wins
        self.assertEqual(v["v1"]["duration"], 30)  # it already had one
        self.assertEqual((v["v2"]["fetched_at"], v["v2"]["duration"]), (1_790_000_000, 33))
        self.assertEqual(viral.purge(t=1_790_000_000 + 31 * 86400)["videos"], 1)  # the import is 31 days old
        self.assertEqual([v["id"] for v in viral._load(viral.VIDEOS, [])], ["v1"])

    def test_outliers_grouped_by_channel_id_across_imports(self):
        vs = [{**video(i, 100, source="xQc Clips"), "channel_id": "UCx"} for i in range(3)]
        vs += [{**video(9, 400, source="xQc Clips (old name)"), "channel_id": "UCx", "published": None}]
        viral.flag_outliers(vs)
        self.assertTrue(vs[-1]["outlier"])
        self.assertFalse(vs[-1]["settling"])


class TitleAndOpeningFeatureTests(TempData):
    def test_title_code_features(self):
        f = viral.title_code("Kai Cenat Did NOT Expect Him To Be 13 💀 #shorts #gta", 31)
        self.assertEqual(f, {"question": 0, "negation": 1, "emoji": 1, "word_count": 9, "length_s": 31})
        self.assertEqual(viral.title_code("Why Is xQc Driving?!", None)["question"], 1)

    def test_opening_features_from_vision_and_words(self):
        frames = [{"text": [{"s": "WAS KAI WRONG FOR", "area": 0.04, "y": 0.5}], "faces": [{"area": 0.03, "y": 0.3}]},
                  {"text": [], "faces": [{"area": 0.05, "y": 0.3}]}, {"text": [], "faces": []},
                  {"text": [], "faces": [{"area": 0.5, "y": 0.3}]}]
        words = [{"w": "yo", "s": 0.4, "e": 0.6}, {"w": "what", "s": 4.9, "e": 5.2}, {"w": "late", "s": 6.0, "e": 6.2}]
        f = viral.opening_features(frames, words)
        self.assertEqual((f["hook_text"], f["hook_words"], f["face_area"]), (1, 4, 0.05))  # faces from the first 1.5 s
        self.assertEqual((f["speech_0_5_words"], f["first_word_s"], f["transcript_0_5"]), (2, 0.4, "yo what"))

    def test_labels_merge_and_unknown_trigger_becomes_none(self):
        out = Path(self.tmp.name) / "b00.jsonl"
        out.write_text(json.dumps({"id": "v1", "premise": "p", "cold_readable": True, "turn": False,
                                   "trigger": "made_up", "setup_withheld": True, "streamer_first": True}) + "\n")
        self.assertEqual(viral.add_title_labels([out]), 1)
        lab = viral._load(viral.LABELS, {})["v1"]
        self.assertEqual((lab["trigger"], lab["cold_readable"]), ("none", True))
        rows = viral.title_rows(viral.flag_outliers([video(1, 10)]), viral._load(viral.LABELS, {}))
        self.assertEqual((rows[0]["trigger_none"], rows[0]["setup_withheld"]), (1, 1))

    def test_frame_names_keep_ids_with_underscores_for_the_purge(self):
        self.assertEqual(viral.frame_path("_y45PqBLLDY", 0.3).name.split(".")[0], "_y45PqBLLDY")


class HookAndSliceTests(TempData):
    def test_hook_question_by_mark_or_opening_word(self):
        self.assertEqual([viral.hook_is_question(t) for t in
                          ["HOW DID JASON END UP IN A TREE?", "was kai wrong", "NOBODY TOLD XQC", "", None]],
                         [1, 1, 0, 0, 0])

    def test_hook_labels_merge_and_videos_without_hook_text_count_zero(self):
        vs = [video(1, 1000, "a"), video(2, 1000, "a")]
        viral._save(viral.OPENINGS, {
            "v1": {"hook_text": 1, "ocr_0_3": "WHY IS HE HERE?", "face_area": 0.1, "opened_at": viral.now()},
            "v2": {"hook_text": 0, "ocr_0_3": "", "face_area": 0.0, "opened_at": viral.now()}})
        f = Path(self.tmp.name) / "h.jsonl"
        f.write_text(json.dumps({"id": "v1", "hook_states_setup": True, "hook_matches_premise": False,
                                 "hook_title_loop": True}) + "\n")
        self.assertEqual(viral.add_hook_labels([f]), 1)
        rows = {r["id"]: r for r in viral.opening_rows(viral.flag_outliers(vs), viral._load(viral.OPENINGS, {}))}
        self.assertEqual((rows["v1"]["hook_question"], rows["v1"]["hook_states_setup"], rows["v1"]["hook_title_loop"]),
                         (1, 1, 1))
        self.assertEqual((rows["v2"]["hook_question"], rows["v2"]["hook_states_setup"]), (0, 0))

    def test_slice_queue_puts_channels_with_both_kinds_first_and_alternates(self):
        vs = []
        for i in range(8):  # channel "a": measured outlier + other; "b": only others measured
            vs.append(video(i, 9000 if i < 4 else 1000, "a"))
        for i in range(8, 14):
            vs.append(video(i, 1000, "b"))
        vs.append(video(14, 9000, "b"))
        vs = viral.flag_outliers(vs)
        by = {v["id"]: v for v in vs}
        opens = {"v0": {}, "v7": {}, "v8": {}}
        q = viral.slice_queue(vs, opens)
        self.assertNotIn("v0", q)
        self.assertEqual({by[i]["source"] for i in q[:5]}, {"a"})
        kinds = [bool(by[i]["outlier"]) for i in q[:4]]
        self.assertEqual(kinds, [kinds[0], not kinds[0]] * 2)  # alternates outlier / other

    def test_slice_downloads_only_the_first_seconds_and_stops_at_a_bot_check(self):
        blocked = mock.Mock(returncode=1, stdout="", stderr="Sign in to confirm you're not a bot")
        with mock.patch.object(viral.subprocess, "run", return_value=blocked) as run:
            with self.assertRaises(viral.BotCheck):
                viral.download_slice("v1")
        cmd = run.call_args[0][0]
        self.assertEqual(cmd[cmd.index("--download-sections") + 1], "*0-6")

        viral._save(viral.VIDEOS, [video(1, 1000), video(2, 1000)])
        with mock.patch.object(viral.subprocess, "run", return_value=blocked) as run, \
                mock.patch.object(viral.time, "sleep"):
            self.assertEqual(viral.grow_openings({})["slices"], 0)
        self.assertEqual(run.call_count, 1)  # no second request after the block

    def test_opening_report_states_when_the_sample_is_too_small(self):
        rng = random.Random(1)
        vs, opens = [], {}
        for i in range(60):
            vs.append(video(i, 9000 if i % 6 == 0 else 1000, "a" if i % 2 else "b"))
            opens[f"v{i}"] = {"hook_text": 1, "hook_words": rng.randint(1, 6), "ocr_0_3": "WHY?", "face_area": 0.1,
                              "shows_action": rng.randint(0, 1), "opened_at": viral.now(),
                              **{k: rng.randint(0, 1) for k in viral.HOOK_LABELS}}
        viral._save(viral.VIDEOS, vs)
        viral._save(viral.OPENINGS, opens)
        text = viral.report(runs=5)
        self.assertIn("## First 5 seconds and the text hook (60 measured settled videos, 10 outliers", text)
        self.assertIn("Still too small to conclude (only 10 outliers", text)
        self.assertIn("(n=10)", text)


class SameMomentPairTests(TempData):
    def words(self, text, start=0.0, step=0.4):
        return [{"w": w, "s": start + i * step, "e": start + i * step + 0.3} for i, w in enumerate(text.split())]

    def test_candidates_same_streamer_within_three_days_and_short(self):
        from clipper import pairs
        own = [{"id": "o1", "title": "xQc Steals A Corvette With Cops Searching", "stream_date": "2026-11-18"}]
        others = [{"id": "a", "title": "XQC steals a corvette 😭", "published": "2026-11-19T10:00:00Z", "duration": 30},
                  {"id": "b", "title": "xQc reacts to GTA 6", "published": "2026-11-21T23:00:00Z", "duration": 30},
                  {"id": "c", "title": "xQc corvette", "published": "2026-11-23T00:00:00Z", "duration": 30},
                  {"id": "d", "title": "Kai Cenat corvette", "published": "2026-11-18T00:00:00Z", "duration": 30},
                  {"id": "e", "title": "xQc corvette long", "published": "2026-11-18T00:00:00Z", "duration": 90}]
        self.assertEqual(pairs.candidates(own, others)["o1"], ["a", "b"])  # most shared title words first

    def test_transcripts_confirm_the_moment_and_give_the_start_offset(self):
        from clipper import pairs
        ours = self.words("oh my god he took the car with the cops right there bro", start=0.5)
        theirs = self.words("wait wait look oh my god he took the car with the cops right there", start=0.2)
        m = pairs.match(ours, theirs)
        self.assertTrue(pairs.same_moment(m))
        self.assertGreaterEqual(m["run"], 10)
        self.assertAlmostEqual(m["b_starts_earlier_s"], 0.9, places=2)  # "oh" at 1.4 s in theirs vs 0.5 s in ours
        other = pairs.match(ours, self.words("what is this game even about chat i have no idea"))
        self.assertFalse(pairs.same_moment(other))
        filler = pairs.match(self.words("oh my gosh oh my gosh he is crazy"), self.words("no oh my gosh oh my gosh what"))
        self.assertFalse(pairs.same_moment(filler))  # a shared exclamation is not the same moment

    def test_first_and_last_spoken_line_split_on_pauses(self):
        from clipper import pairs
        w = self.words("yo look at this") + self.words("no way he did that", start=5.0)
        self.assertEqual((pairs.first_line(w), pairs.last_line(w)), ("yo look at this", "no way he did that"))


class GeminiABTests(unittest.TestCase):
    def test_reply_parsed_and_unknown_categories_dropped(self):
        from clipper import pairs
        reply = 'Here you go:\n{"A": {"premise": "x"}, "B": {"premise": "y"}, "more_views": "B", "confidence": 0.7, ' \
                '"main_reason": "vibes", "reasons": [{"category": "premise", "why": "w"}, {"category": "zzz"}]}'
        d = pairs.parse_ab(reply)
        self.assertEqual((d["more_views"], d["main_reason"], len(d["reasons"])), ("B", "other", 1))
        with self.assertRaises(ValueError):
            pairs.parse_ab('{"A": {}, "B": {}, "more_views": "C"}')
