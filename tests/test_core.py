import unittest

import numpy as np

from clipper import candidates as cand
from clipper import captions, transcribe


def W(text, s, e):
    return {"w": text, "s": s, "e": e}


class TranscriptTests(unittest.TestCase):
    def test_parse_words_splits_events(self):
        data = {"transcription": [
            {"text": " Oh", "offsets": {"from": 0, "to": 300}},
            {"text": " (screaming)", "offsets": {"from": 300, "to": 900}},
            {"text": " [BLANK_AUDIO]", "offsets": {"from": 900, "to": 1500}},
            {"text": " no!", "offsets": {"from": 1500, "to": 1800}},
        ]}
        words, events = transcribe.parse_words(data)
        self.assertEqual([w["w"] for w in words], ["Oh", "no!"])
        self.assertEqual([e["text"] for e in events], ["screaming"])

    def test_group_sentences_breaks_on_punctuation_and_gaps(self):
        words = [W("Run.", 0, 0.4), W("Go", 0.5, 0.8), W("now", 0.9, 1.1), W("later", 3.0, 3.4)]
        sents = transcribe.group_sentences(words)
        self.assertEqual([s["text"] for s in sents], ["Run.", "Go now", "later"])


class CandidateTests(unittest.TestCase):
    def test_snap_moves_to_sentence_bounds(self):
        sents = [{"s": 8.0, "e": 15.0}, {"s": 15.5, "e": 41.0}]
        self.assertEqual(cand.snap_window(10, 38, sents, 15, 60), (8.0, 41.0))

    def test_pick_windows_does_not_overlap(self):
        score = np.zeros(300)
        score[50], score[55], score[200] = 1.0, 0.9, 0.8
        picks = cand.pick_windows(score, [], 300.0, 30, 15, 60, 5)
        self.assertEqual(len(picks), 2)
        self.assertLessEqual(cand.overlap((picks[0]["start"], picks[0]["end"]),
                                          (picks[1]["start"], picks[1]["end"])), 0.3)


class CaptionTests(unittest.TestCase):
    def test_timeline_is_relative_and_ordered(self):
        words = [W("no", 10.0, 10.3), W("way", 10.3, 10.6), W("bro.", 10.6, 11.0), W("run", 14.0, 14.4)]
        tl = captions.timeline(words, 9.0, 20.0)
        self.assertEqual(tl[0][:2], (1.0, 1.3))
        self.assertTrue(all(a[1] <= b[0] + 1e-6 for a, b in zip(tl, tl[1:])))
        self.assertEqual(tl[2][4], ["no", "way", "bro."])


if __name__ == "__main__":
    unittest.main()


class RepeatTests(unittest.TestCase):
    def test_drop_repeats_collapses_whisper_loops(self):
        words = [W("Hi.", 0, 0.5)] + [W("Again.", 1 + i, 1.5 + i) for i in range(5)] + [W("Bye.", 9, 9.5)]
        self.assertEqual([w["w"] for w in transcribe.drop_repeats(words)], ["Hi.", "Again.", "Bye."])

    def test_drop_repeats_keeps_short_runs(self):
        words = [W("Go.", 0, 0.3), W("Go.", 1, 1.3), W("Stop.", 2, 2.3)]
        self.assertEqual(len(transcribe.drop_repeats(words)), 3)


class Gta6FilterTests(unittest.TestCase):
    def setUp(self):
        from clipper import config
        self.cfg = config.load()
        from clipper.sources import topic_evidence
        self.ev = topic_evidence

    def test_title_match(self):
        self.assertEqual(self.ev("Leonida Is MASSIVE...the GTA 6 Map", "", [], self.cfg), "title")
        self.assertEqual(self.ev("Kai Cenat Reacts To GTA VI Trailer", "", [], self.cfg), "title")

    def test_other_gta_title_rejected_even_if_description_mentions_gta6(self):
        self.assertIsNone(self.ev("GTA Online - Biohazard Outbreak", "Waiting for GTA 6...", [], self.cfg))
        self.assertIsNone(self.ev("The Casino Heist | GTA RP Nopixel V", "gta 6 soon", [], self.cfg))
        self.assertIsNone(self.ev("100 GTA V Clips You Must See Before GTA 6!", "", [], self.cfg))
        self.assertIsNone(self.ev("GTA memes to watch before GTA 6", "", [], self.cfg))

    def test_description_or_tags_count_when_title_is_neutral(self):
        self.assertEqual(self.ev("I can't believe this", "My first look at GTA 6 gameplay", [], self.cfg), "description")
        self.assertEqual(self.ev("Insane trailer reaction", "", ["gta6", "GTA VI"], self.cfg), "tags")
        self.assertIsNone(self.ev("Fortnite tournament", "Fortnite", ["fortnite"], self.cfg))


class SpeakerTests(unittest.TestCase):
    def test_parse_turns_and_assign(self):
        from clipper import speakers
        out = ("---- Speaker Diarization Results ----\n"
               "SPEAKER v16 1 0.000 6.380 more you need four of you <NA> A <NA> <NA>\n"
               "SPEAKER v16 1 10.540 9.420 oh that's good <NA> B <NA> <NA>\n")
        turns = speakers.parse_turns(out)
        self.assertEqual([(t["s"], t["spk"]) for t in turns], [(0.0, "A"), (10.54, "B")])
        words = speakers.assign_speakers([W("more", 0.1, 0.4), W("oh", 10.6, 10.9), W("hm", 8.0, 8.2)], turns)
        self.assertEqual([w["spk"] for w in words], [0, 1, 0])

    def test_overlapping_speakers_stack(self):
        words = [dict(W("no", 0.0, 0.5), spk=0), dict(W("way", 0.5, 1.0), spk=0),
                 dict(W("yes", 0.2, 0.8), spk=1)]
        states = captions.caption_states(words, 0.0, 2.0)
        both = [s for _, _, s in states if len(s) == 2]
        self.assertTrue(both, "speech overlapping in time should show both speakers")
        self.assertEqual({spk for spk, _, _ in both[0]}, {0, 1})


class HookTests(unittest.TestCase):
    def test_parse_markup(self):
        self.assertEqual(captions.parse_markup("I Can Play *GTA 6 NOW*"),
                         [("I", False), ("Can", False), ("Play", False), ("GTA", True), ("6", True), ("NOW", True)])
        self.assertEqual(captions.parse_markup("*Kids* can't"), [("Kids", True), ("can't", False)])
        self.assertEqual(captions.parse_markup("Why won't Kai watch *THIS*?"),
                         [("Why", False), ("won't", False), ("Kai", False), ("watch", False), ("THIS?", True)])
        self.assertEqual(captions.parse_markup("*Wait*, what"), [("Wait,", True), ("what", False)])

    def test_captions_fall_back_when_whisperkit_misses_speech(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from clipper import render
        said = [{"w": f"w{i}", "s": 100 + i * 0.2, "e": 100.2 + i * 0.2} for i in range(40)]
        missed = [{"w": "I", "s": 0, "e": 1.4, "spk": 0}, {"w": "ain't", "s": 1.4, "e": 10, "spk": 0}]
        with tempfile.TemporaryDirectory() as d, mock.patch.object(render.subprocess, "run"), \
                mock.patch.object(render.speakers, "diarized_words", return_value=missed), \
                mock.patch.object(render.captions, "write_overlay", return_value="caps"):
            prep = render.prepare_clip(Path(d), {"start": 100, "end": 110}, said, {"separate_voices": False}, Path(d))
        self.assertEqual(len(prep["words"]), 40)
        self.assertAlmostEqual(prep["words"][1]["s"], 0.2)
        self.assertEqual(prep["transcript"], "source transcript")

    def test_captions_fall_back_when_whisperkit_is_missing(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from clipper import render
        said = [{"w": f"w{i}", "s": 100 + i * 0.5, "e": 100.4 + i * 0.5} for i in range(10)]
        with tempfile.TemporaryDirectory() as d, mock.patch.object(render.subprocess, "run"), \
                mock.patch.object(render.speakers, "diarized_words", return_value=None), \
                mock.patch.object(render.captions, "write_overlay", return_value="caps"):
            prep = render.prepare_clip(Path(d), {"start": 100, "end": 110}, said, {"separate_voices": False}, Path(d))
        self.assertEqual(len(prep["words"]), 10)
        self.assertEqual(prep["transcript"], "source transcript")

    def test_rerender_replaces_index_line(self):
        import json
        import shutil
        import tempfile
        from pathlib import Path
        from unittest import mock
        from clipper import render
        with tempfile.TemporaryDirectory() as d:
            job, out = Path(d) / "job", Path(d) / "out"
            job.mkdir()
            (job / "job.json").write_text(json.dumps({"channel": "Kai Cenat Live", "url": "u", "title": "t"}))
            (job / "transcript.json").write_text(json.dumps({"words": []}))
            pick = {"start": 0, "end": 5, "hooks": ["a"], "titles": ["T"]}
            with mock.patch.object(render, "prepare_clip", return_value={"vo": None, "speakers": 1, "transcript": ""}), \
                    mock.patch.object(render, "encode_variant"), mock.patch.object(render, "probe", return_value={}), \
                    mock.patch.object(render, "upload_manifest", return_value=[]), \
                    mock.patch.object(render, "clip_markdown", return_value=""):
                render.render(job, [pick], {}, out_dir=out)
                shutil.rmtree(out / "video 1")
                render.render(job, [pick], {}, out_dir=out)
            self.assertEqual((out / "index.md").read_text().count("**video 1**"), 1)


class WhisperKitParseTests(unittest.TestCase):
    def test_contractions_are_rejoined(self):
        import json, tempfile
        from pathlib import Path
        from unittest import mock
        from clipper import speakers
        report = {"segments": [{"words": [{"word": " Y", "start": 0.0, "end": 0.2},
                                          {"word": "'all", "start": 0.2, "end": 0.5},
                                          {"word": " know", "start": 0.5, "end": 0.8}]}]}
        with tempfile.TemporaryDirectory() as d:
            def fake_run(cmd, **kw):
                if cmd[0] == "whisperkit-cli":
                    Path(d, "voice16k.json").write_text(json.dumps(report))
                return mock.Mock(returncode=0, stdout="", stderr="")
            with mock.patch("clipper.speakers.subprocess.run", side_effect=fake_run):
                words = speakers.diarized_words(Path(d, "in.wav"), d, {})
        self.assertEqual([w["w"] for w in words], ["Y'all", "know"])


class OutputNamingTests(unittest.TestCase):
    def test_hook_becomes_file_name(self):
        from clipper.render import hook_filename
        taken = set()
        self.assertEqual(hook_filename("Kai: I waited 12 years for *this*", taken), "Kai I waited 12 years for this.mp4")
        self.assertEqual(hook_filename("POV: the *GTA 6* trailer / drops?", taken), "POV the GTA 6 trailer drops.mp4")
        self.assertEqual(hook_filename("Kai I waited 12 years for this", taken), "Kai I waited 12 years for this (2).mp4")
        self.assertEqual(hook_filename("", taken), "no hook.mp4")


class VoiceSetupTests(unittest.TestCase):
    def test_reads_key_after_instructions_and_saves_env(self):
        import tempfile
        from pathlib import Path
        from clipper import voice_setup
        with tempfile.TemporaryDirectory() as d:
            note = Path(d, "note.txt")
            note.write_text(voice_setup.NOTE.format(url="x"))
            self.assertIsNone(voice_setup.read_pasted_key(note))
            note.write_text(voice_setup.NOTE.format(url="x") + "  abcdef0123456789abcdef0123456789\n")
            self.assertEqual(voice_setup.read_pasted_key(note), "abcdef0123456789abcdef0123456789")
            env = Path(d, ".env")
            env.write_text("OTHER=1\nFISH_API_KEY=old\n")
            voice_setup.save_key("newkey1234567890", env)
            self.assertEqual(env.read_text(), "OTHER=1\nFISH_API_KEY=newkey1234567890\n")
            self.assertEqual(env.stat().st_mode & 0o777, 0o600)


class FontTests(unittest.TestCase):
    def test_bundled_fonts_load_with_weights(self):
        f = captions.font("montserrat-black", 80)
        self.assertIn(b"Black", f.font.style.encode() if isinstance(f.font.style, str) else f.font.style)
        self.assertTrue(captions.FONT_DIR.joinpath("BebasNeue-Regular.ttf").exists())

    def test_each_speaker_gets_a_different_font(self):
        looks = [captions.speaker_look(s, "bold", True) for s in range(3)]
        self.assertEqual(len({l[0] for l in looks}), 3)
        self.assertEqual(captions.speaker_look(1, "bold", False)[0], "montserrat-black")


class LibraryTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from clipper import library
        self.lib = library
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.patches = [mock.patch.object(library, "creators_path", return_value=d / "creators.yaml"),
                        mock.patch.object(library, "prefs_path", return_value=d / "prefs.yaml"),
                        mock.patch.object(library, "lookup_channel", return_value="Kai Cenat")]
        for p in self.patches:
            p.start()
        (d / "prefs.yaml").write_text("voice: auto            # off | all | auto\nvideos_per_run: 2\n")

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_channel_url_normalises(self):
        self.assertEqual(self.lib.channel_url("@KaiCenat"), "https://www.youtube.com/@KaiCenat/videos")
        self.assertEqual(self.lib.channel_url("https://www.youtube.com/@KaiCenat/shorts"),
                         "https://www.youtube.com/@KaiCenat/videos")

    def test_add_list_remove_creator(self):
        entry, _ = self.lib.add_creator("@KaiCenat")
        self.assertEqual(entry["name"], "Kai Cenat")
        self.assertIsNone(self.lib.add_creator("KaiCenat")[0], "duplicates are refused")
        self.assertEqual(self.lib.remove_creator("@KaiCenat"), 1)
        self.assertEqual(self.lib.load_creators(), [])

    def test_set_prefs_validates_and_keeps_comments(self):
        self.lib.set_prefs(["voice=off", "videos_per_run=3", "schedule_time=08:30"])
        text = self.lib.prefs_path().read_text()
        self.assertIn("voice: off            # off | all | auto", text)
        self.assertIn('schedule_time: "08:30"', text)
        self.assertEqual(self.lib.load_prefs()["videos_per_run"], 3)
        with self.assertRaises(ValueError):
            self.lib.set_prefs(["voice=sometimes"])
        with self.assertRaises(ValueError):
            self.lib.set_prefs(["schedule_time=25:00"])


class ExportNumberingTests(unittest.TestCase):
    def test_numbering_continues_in_dated_folder(self):
        import tempfile
        from pathlib import Path
        from clipper.render import next_video_number
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(next_video_number(Path(d)), 1)
            for n in (1, 2, 10):
                Path(d, f"video {n}").mkdir()
            self.assertEqual(next_video_number(Path(d)), 11)


class HallucinationTests(unittest.TestCase):
    def test_music_hallucinations_removed(self):
        words = [W("The", 0, .2), W("Lone", .2, .4), W("Ranger", .4, .6), W("Thank", 2, 2.2), W("you.", 2.2, 2.5),
                 W("Transcription", 4, 4.3), W("by", 4.3, 4.4), W("ESO.", 4.4, 4.8), W("Run", 9, 9.2), W("now!", 9.2, 9.5)]
        self.assertEqual([w["w"] for w in transcribe.drop_repeats(words)], ["Run", "now!"])

    def test_real_thanks_inside_a_sentence_kept(self):
        words = [W("I", 0, .1), W("said", .1, .3), W("thank", .3, .5), W("you", .5, .7), W("bro.", .7, .9)]
        self.assertEqual(len(transcribe.drop_repeats(words)), 5)


class WorthTests(unittest.TestCase):
    def test_jump_catches_a_scream_not_speech_after_silence(self):
        from clipper import signals
        lufs = [-70] * 10 + [-24] * 10 + [-10] + [-24] * 5
        _, raw = signals.jump_per_second(lufs)
        self.assertEqual(int(np.argmax(raw)), 20)
        self.assertGreaterEqual(raw[20], 12)
        self.assertLess(raw[10], 5, "speech starting after silence stays below the 'maybe' jump threshold")

    def test_profile_and_counts_scale_with_length(self):
        self.assertEqual(cand.clip_profile([-25] * 50 + [-12] * 3, [])[0], "reaction")
        self.assertEqual(cand.clip_profile([-20] * 60, [])[0], "info")
        self.assertEqual(cand.clip_profile([-20] * 60, [], "Kai Cenat Reacts To GTA 6")[0], "reaction")
        self.assertEqual(cand.auto_candidate_count(8 * 60), 4)
        self.assertEqual(cand.auto_candidate_count(20 * 60), 8)
        self.assertEqual(cand.auto_candidate_count(50 * 60), 20)

    def test_tiers_and_recommendation(self):
        self.assertEqual(cand.tier(62, 10, 0, 0, 0), "strong")
        self.assertEqual(cand.tier(62, 2, 0, 0, 0), "skip", "high relative score but nothing actually happens")
        self.assertEqual(cand.tier(33, 6, 0, 0, 0), "maybe")
        many = ["strong"] * 6 + ["maybe"] * 4
        self.assertEqual(cand.recommend(many, 20 * 60), 6, "20 min caps at 6")
        self.assertEqual(cand.recommend(many, 50 * 60), 8, "50 min allows all strong + half the maybes")
        self.assertEqual(cand.recommend(["skip", "skip"], 50 * 60), 0)

    def test_prefs_accept_auto_video_count(self):
        from clipper import library
        self.assertIn("auto", library.PREF_RULES["videos_per_run"])


class HookRuleTests(unittest.TestCase):
    VIRAL_HOOKS = ["KIDS CAN'T PLAY GTA 6", "4 NEW FEATURES COMING IN GTA 6", "How Playing GTA 6 Is Gonna Be 😂",
                   "I'M GONNA PLAY GTA 6!", "He Is the ONLY One", "I Can't Believe It's Real...",
                   "I Can Play GTA 6 NOW", "HE'S 72 YEARS OLD"]

    def test_every_structured_viral_hook_passes(self):
        from clipper import hooks
        for h in self.VIRAL_HOOKS:
            self.assertEqual(hooks.check_hook(h)[0], [], h)
            self.assertTrue(hooks.structures(h), h)

    def test_series_labels_are_notes_not_fails(self):
        from clipper import hooks
        self.assertTrue(hooks.check_hook("GTA 6 GRAPHICS")[0])  # labels measured 0.88x on 1,081 GTA Shorts

    def test_spoilers_and_plain_statements_fail(self):
        from clipper import hooks
        self.assertTrue(hooks.check_hook("*GTA 6* Lucia Scene Reaction")[0])
        self.assertTrue(hooks.check_hook("Kai sits in a chair and talks to chat")[0])
        self.assertEqual(hooks.check_hook("Wait for Kai's reaction at the end...")[0], [])

    def test_viral_titles_pass(self):
        from clipper import hooks
        for t in ["GTA 6 Is HUGE (2x BIGGER Map)", "GTA 6 Is Going To Cost HOW MUCH!?",
                  "GTA 6 Is Going To Look REALISTIC Because Of THIS!", "Kids WON'T Be Able To Play GTA 6!"]:
            self.assertEqual(hooks.check_title(t)[0], [], t)
        self.assertEqual(hooks.check_title("There has to be a reason for this game taking this long 😂", ["#gta6"])[0], [])
        self.assertTrue(hooks.check_title("WHY IS KAI CENAT SO LOUD")[0])
        self.assertTrue(hooks.check_title("Kai Cenat Was Not Ready For This Scene")[0])

    def test_picks_report_and_variety(self):
        from clipper import hooks
        report = hooks.check_picks([{"hooks": ["Why is Kai shaking?", "Why did Kai scream?", "Why is Kai crying?"],
                                     "titles": ["Why Kai Cenat Screamed At GTA 6"]}])
        self.assertIn("variety", report["video 1"])
        self.assertTrue(hooks.has_fails(report))

    def test_opening_types(self):
        from clipper import hooks
        self.assertEqual(hooks.opening_type("Go right! Right!"), "action cold open")
        self.assertEqual(hooks.opening_type("Have you ever wondered who Lucia is?"), "question")
        self.assertEqual(hooks.opening_type("4 things coming in GTA 6 that you didn't know about."), "number promise")
        self.assertEqual(hooks.opening_type("um so yeah anyway chat"), "filler (trim the start)")


class RelatableHookTests(unittest.TestCase):
    def test_relatable_situations_pass(self):
        from clipper import hooks
        for good in ("Me watching *GTA 6* with my mom in the room", "When your parents walk in during *GTA 6*",
                     "How playing *GTA 6* is gonna be 😂"):
            self.assertEqual(hooks.check_hook(good)[0], [], good)
        self.assertTrue(hooks.check_hook("Me watching GTA 6 with my mom in the living room tonight bro")[0])


class ColdOpenTests(unittest.TestCase):
    def test_mid_scene_openings_are_cold_opens(self):
        from clipper import hooks
        for line in ("Sir, lock her up in the door a bit.", "Ooh, all the trophies look cool.", "*Dog barking*",
                     "I'm gonna go right at this mountain."):
            self.assertIn("cold open", hooks.opening_type(line), line)
        self.assertEqual(hooks.opening_type("If you look at the GTA 5 map at night"), "setup tease")


class FillerOpenTests(unittest.TestCase):
    def test_stream_preamble_is_filler(self):
        from clipper import hooks
        for line in ("First of all, let's go ahead and get this GTA 6 trailer first.",
                     "Chap, before we get into GTA 6, we are going to refresh our memories."):
            self.assertEqual(hooks.opening_type(line), "filler (trim the start)", line)


class PlaybookTests(unittest.TestCase):
    def test_guess_type(self):
        from clipper import playbook
        self.assertEqual(playbook.guess_type("Kai Cenat Reacts To GTA 6 - Official Launch Trailer", "info", 120, False), "reaction")
        self.assertEqual(playbook.guess_type("xQc FORCES Weazel News Ron Otterman to Rob a Bank | GTA RP NoPixel", "info", 150, False), "comedy")
        self.assertEqual(playbook.guess_type("GTA 6 Launch Screenshots - All 39 New Images Released", "info", 5, False), "showcase")
        self.assertEqual(playbook.guess_type("This GTA 6 Update Is INSANE - Trophies Leaked", "info", 160, False), "news")

    def test_every_playbook_example_passes_and_matches_its_structures(self):
        from clipper import hooks, playbook
        for kind, play in playbook.PLAYBOOK.items():
            for ex, want in zip(play["examples"], play["hooks"]):
                self.assertEqual(hooks.check_hook(ex)[0], [], ex)
                self.assertIn(want, hooks.structures(ex), f"{kind}: {ex}")

    def test_check_flags_wrong_hooks_for_type(self):
        from clipper import hooks
        rep = hooks.check_picks([{"clip_type": "comedy", "hook_style": "bold",
                                  "hooks": ["4 NEW features coming in *GTA 6*", "*GTA 6* costs HOW much?"]}])
        self.assertTrue(rep["video 1"]["playbook"])


class SimulateTests(unittest.TestCase):
    PICK = {"clip_type": "comedy", "hashtags": ["#xqc", "#gtarp"],
            "description": "Mid-heist, xQc forces the hostages to sing a barbershop quartet.",
            "hooks": ["xQc forces the hostages to *SING*", "Wait for the harmony..."]}

    def test_premise_hook_passes_check(self):
        from clipper import hooks
        self.assertEqual(hooks.check_hook("Bank robbers force the hostages to SING")[0], [])
        self.assertIn("premise + twist", hooks.structures("Bank robbers force the hostages to SING"))
        self.assertNotIn("premise + twist", hooks.structures("I Can Play *GTA 6* NOW!"[:9]))

    def test_named_clear_hook_beats_vague_tease(self):
        from clipper import simulate
        res = simulate.simulate(self.PICK, runs=40)
        self.assertEqual(res[0]["hook"], "xQc forces the hostages to *SING*")
        self.assertIn("names a streamer", res[0]["why"])
        self.assertIn("vague", res[1]["why"])


class SetupTests(unittest.TestCase):
    def test_global_command_points_at_project(self):
        from clipper import setup
        out = setup.global_command("---\ndescription: x\n---\n\nBody")
        self.assertTrue(out.startswith("---\ndescription: x\n---"))
        self.assertIn(str(setup.ROOT), out)


class DataBackedRuleTests(unittest.TestCase):
    def test_vague_hooks_fail(self):
        from clipper import hooks
        for h in ("Wait for the harmony...", "Nobody expected *this* mid-heist", "Wait for his reaction..."):
            self.assertTrue(hooks.check_hook(h)[0], h)
        self.assertEqual(hooks.check_hook("Why are the hostages singing?")[0], [])

    def test_fitted_effects_rank_number_promise_above_vague(self):
        from clipper import simulate
        t = simulate.effect_table()
        self.assertGreater(t["number promise"][1], 1)  # lower bound of the 90% range
        self.assertLess(t["vague"][2], 1)              # upper bound

    def test_all_caps_title_fails(self):
        from clipper import hooks
        self.assertTrue(hooks.check_title("XQC MADE THE HOSTAGES SING", ["#gta6"])[0])


class StrategyTests(unittest.TestCase):
    def test_title_must_match_hook_type(self):
        from clipper import hooks
        rep = hooks.check_picks([{"hooks": ["Why is xQc making the hostages sing?"],
                                  "titles": ["xQc Hostage Harmony In GTA RP"]}])
        self.assertIn("pairing", rep["video 1"])

    def test_forcing_every_type_loses_to_best_three(self):
        from clipper import simulate
        res = simulate.strategies(8, runs=400, judgment=(0.5,), repeat_cost=0.05)[0.5]
        self.assertGreater(res["Claude's best 3"][0],
                           res["every hook type (7 variants, incl. ones that don't fit)"][0])


class LiveTests(unittest.TestCase):
    def test_stream_refs_and_names(self):
        from clipper import live
        self.assertEqual(live.stream_url("twitch:xqc"), "https://www.twitch.tv/xqc")
        self.assertEqual(live.stream_url("youtube:@KaiCenat"), "https://www.youtube.com/@KaiCenat/live")
        self.assertEqual(live.stream_name("https://kick.com/xqc"), "xqc-kick")
        self.assertEqual(live.stream_name("https://www.youtube.com/@KaiCenat/live"), "KaiCenat-youtube")

    def test_timestamp_link_only_for_youtube_videos(self):
        from clipper import config
        self.assertEqual(config.timestamp_link("https://www.youtube.com/watch?v=x", 61.5), "https://www.youtube.com/watch?v=x&t=61s")
        self.assertEqual(config.timestamp_link("https://www.twitch.tv/xqc", 61), "https://www.twitch.tv/xqc")


class LinuxPortTests(unittest.TestCase):
    def test_linux_setup_plans_apt_and_whisper_build(self):
        from unittest import mock
        from clipper import setup
        def plan(asr):
            with mock.patch.object(setup, "IS_MAC", False), mock.patch.object(setup.shutil, "which", return_value=None), \
                    mock.patch.object(setup.sys, "prefix", "/venv"), mock.patch.object(setup, "uses_whisper",
                                                                                    return_value=asr == "whisper"):
                return [" ".join(c) for c in setup.linux_plan(list(setup.APT), ["onnx_asr"], True)[0]]
        flat = plan("parakeet")
        self.assertTrue(any(c.startswith("sudo apt-get install -y") and "ffmpeg" in c for c in flat))
        self.assertTrue(any("whl/cpu" in c for c in flat))  # CPU torch without an NVIDIA card
        self.assertTrue(any("onnx-asr" in c for c in flat))
        self.assertFalse(any("whisper.cpp" in c for c in flat))
        self.assertTrue(any("whisper.cpp" in c for c in plan("whisper")))

    def test_systemd_timer_written_on_linux(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from clipper import schedule
        with tempfile.TemporaryDirectory() as d, mock.patch.object(schedule, "IS_MAC", False), \
                mock.patch.object(schedule, "UNIT_DIR", Path(d)), mock.patch.object(schedule.subprocess, "run"), \
                mock.patch.object(schedule.shutil, "which", return_value="/usr/bin/claude"):
            schedule.install("09:30")
            timer = (Path(d) / "clipper-gta6-daily.timer").read_text()
            service = (Path(d) / "clipper-gta6-daily.service").read_text()
        self.assertIn("OnCalendar=*-*-* 09:30:00", timer)
        self.assertIn("/usr/bin/claude -p /clip-daily", service)
        self.assertIn("--model sonnet", service)  # unattended runs never default to the priciest model

    def test_unattended_run_may_write_its_report(self):
        import json
        from pathlib import Path
        from clipper import schedule
        # /clip-daily appends its report to exports/<profile>/<date>/index.md; dontAsk mode refuses unlisted tools
        project = json.loads(Path(".claude/settings.json").read_text())["permissions"]["allow"]
        for allowed in (schedule.ALLOWED, project):
            self.assertIn("Write(exports/**)", allowed)
            self.assertIn("Edit(exports/**)", allowed)
        for prompt in (".claude/commands/clip-daily.md", ".codex/prompts/clip-daily.md"):
            self.assertIn("no `cd`", Path(prompt).read_text())

    def test_parakeet_runs_on_cpu_not_coreml(self):
        import sys
        from unittest import mock
        from clipper import transcribe
        fake = mock.MagicMock()
        with mock.patch.dict(sys.modules, {"onnx_asr": fake}), mock.patch.dict(transcribe._PARAKEET, clear=True):
            transcribe.parakeet_model("nemo-parakeet-tdt-0.6b-v3", "int8")
        self.assertEqual(fake.load_model.call_args.kwargs["providers"], ["CPUExecutionProvider"])
        self.assertEqual(fake.load_vad.call_args.kwargs["providers"], ["CPUExecutionProvider"])

    def test_live_schedule_keeps_recorders_and_gates_claude(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from clipper import schedule
        with tempfile.TemporaryDirectory() as d, mock.patch.object(schedule, "IS_MAC", False), \
                mock.patch.object(schedule, "UNIT_DIR", Path(d)), mock.patch.object(schedule.subprocess, "run"), \
                mock.patch.object(schedule.shutil, "which", return_value="/usr/bin/claude"):
            out = schedule.install_live(every_hours=2)
            watch = (Path(d) / "clipper-gta6-live-watch.service").read_text()
            clip = (Path(d) / "clipper-gta6-live-clip.service").read_text()
            clip_timer = (Path(d) / "clipper-gta6-live-clip.timer").read_text()
            watch_timer = (Path(d) / "clipper-gta6-live-watch.timer").read_text()
            self.assertEqual(sorted(schedule.remove_live()), ["clipper-gta6-live-clip", "clipper-gta6-live-watch"])
            self.assertEqual(list(Path(d).iterdir()), [])
        self.assertIn("KillMode=process", watch)  # recorders must outlive the watcher
        self.assertNotIn("KillMode", clip)
        self.assertIn("OnUnitActiveSec=300s", watch_timer)
        self.assertIn("OnUnitActiveSec=7200s", clip_timer)
        self.assertIn("live pending; then", clip)  # Claude only starts when chunks are waiting
        self.assertIn("'/clip-daily live'", clip)
        self.assertIn("every 2 h", out)

    def test_live_chunks_in_the_same_minute_get_their_own_jobs(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from clipper import live
        with tempfile.TemporaryDirectory() as d, mock.patch.object(live, "JOBS", Path(d)), \
                mock.patch.object(live.subprocess, "run", return_value=mock.Mock(stdout="6")):
            ids = {live.make_job(Path(d) / "seg.ts", "xqc", "u", "t", 1794321600 + s) for s in (0, 20)}
        self.assertEqual(len(ids), 2)

    def test_live_job_credits_the_streamer_not_the_recorder(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest import mock
        from clipper import live
        with tempfile.TemporaryDirectory() as d, mock.patch.object(live, "JOBS", Path(d)), \
                mock.patch.object(live.subprocess, "run", return_value=mock.Mock(stdout="6")):
            jid = live.make_job(Path(d) / "seg.ts", "kaicenat-twitch", "u", "t", 1794321600, "KaiCenat")
            self.assertEqual(json.loads((Path(d) / jid / "job.json").read_text())["channel"], "KaiCenat")

    def test_description_hashtags_are_not_repeated(self):
        from clipper import render
        out = render.post_description("Kai promises A1. #gta6 #KaiCenat", {"channel": "KaiCenat"}, "L",
                                      ["#gta6", "#kaicenat", "#shorts"])
        self.assertEqual(out, "Kai promises A1. #gta6 #KaiCenat\n\nClip from KaiCenat: L\n\n#shorts")
        self.assertTrue(render.post_description("d", {"channel": "c"}, "L", ["#gta6"]).endswith("L\n\n#gta6"))

    def test_clips_are_capped_at_60s(self):
        from clipper import hooks
        base = {"hooks": ["Why did Kai scream?"], "start": 10, "end": 70}
        self.assertNotIn("length", hooks.check_picks([base]).get("video 1", {}))
        long = {**base, "end": 72}
        self.assertIn("60s maximum", hooks.check_picks([long])["video 1"]["length"])
        self.assertTrue(hooks.has_fails(hooks.check_picks([long])))
        import json
        import tempfile
        from unittest import mock
        from clipper import __main__ as cli
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump([long], f)
        with mock.patch.object(cli.render_mod, "render") as rj, mock.patch.object(cli.config, "job_dir"), \
                self.assertRaises(SystemExit) as e:
            cli.main(["render", "anyjob", "--picks", f.name])
        self.assertIn("60s maximum", str(e.exception))
        rj.assert_not_called()

    def test_live_clip_cmd_replaces_claude(self):
        from clipper import schedule
        jobs = schedule.live_jobs(None, clip_cmd="/venv/bin/python /ops/autopilot.py live")
        self.assertEqual(jobs["live-clip"][0][2].split("; then ")[1], "/venv/bin/python /ops/autopilot.py live; fi")
        self.assertIn("live pending", jobs["live-clip"][0][2])
        self.assertNotIn("live-clip", schedule.live_jobs(None))  # no claude and no command: watcher only

    def test_interpreter_folder_joins_path(self):
        import os
        import sys
        from pathlib import Path
        from unittest import mock
        from clipper import __main__ as cli
        with mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}):
            cli.tools_on_path()
            cli.tools_on_path()  # idempotent
            self.assertEqual(os.environ["PATH"], f"{Path(sys.executable).parent}:/usr/bin:/bin")

    def test_live_pending_exit_code(self):
        from unittest import mock
        from clipper import __main__ as cli
        for ready, code in (([], 1), (["live-xqc-20261110-0900"], 0)):
            with mock.patch.object(cli.live_mod, "ready_jobs", return_value=ready), \
                    self.assertRaises(SystemExit) as e, mock.patch("builtins.print"):
                cli.main(["live", "pending"])
            self.assertEqual(e.exception.code, code)

    def test_demucs_device_auto(self):
        from unittest import mock
        from clipper import config
        with mock.patch.object(config, "IS_MAC", False), mock.patch.object(config.shutil, "which", return_value=None):
            self.assertEqual(config.demucs_device({"demucs_device": "auto"}), "cpu")
        self.assertEqual(config.demucs_device({"demucs_device": "cpu"}), "cpu")

    def test_live_workers_split_cpus(self):
        from unittest import mock
        from clipper import live
        with mock.patch.object(live.os, "cpu_count", return_value=8):
            self.assertEqual(live.workers({"live_workers": "auto"}), (2, 4))
            self.assertEqual(live.workers({"live_workers": 1}), (1, 8))


class ParakeetTests(unittest.TestCase):
    def test_tokens_group_into_words_with_offsets(self):
        from clipper import transcribe
        toks = [" I", " know", " how", " we", " can", " fi", "x", " this", "."]
        ts = [0.0, 0.08, 0.24, 0.32, 0.4, 0.48, 0.56, 0.64, 0.72]
        words = transcribe.tokens_to_words(toks, ts, 10.0, 1.0)
        self.assertEqual([w["w"] for w in words], ["I", "know", "how", "we", "can", "fix", "this."])
        self.assertEqual(words[5]["s"], 10.48)
        self.assertEqual(words[5]["e"], 10.64)   # ends where "this." starts
        self.assertEqual(words[-1]["e"], 11.0)   # last word ends with its segment


class ProfileTests(unittest.TestCase):
    def tearDown(self):
        from clipper import config
        config.load()

    def test_default_profile_reproduces_gta6_config(self):
        from clipper import config
        cfg = config.load()
        self.assertEqual(cfg["profile"], "gta6")
        self.assertEqual(config.load(profile="gta6"), cfg)
        self.assertEqual(cfg["hashtags"], ["#gta6", "#gtavi", "#shorts"])
        self.assertIn("\\bgta ?(6|vi)\\b", cfg["topic_patterns"])
        self.assertIn("nopixel", cfg["exclude_title_patterns"])
        self.assertEqual(cfg["search"], ["GTA 6 reaction", "GTA 6 gameplay funny"])
        self.assertIn("xQc", [c["name"] for c in cfg["channels"]])
        self.assertEqual(cfg["weights"]["loudness"], 0.30)

    def test_env_picks_profile_and_unknown_profile_fails(self):
        import os
        from unittest import mock
        from clipper import config
        with mock.patch.dict(os.environ, {"CLIPPER_PROFILE": "no-such-profile"}):
            with self.assertRaises(SystemExit):
                config.load()

    def test_profile_files_fall_back_to_root_only_for_default(self):
        from clipper import config
        self.assertEqual(config.profile_file("creators.yaml", "gta6"), config.PROFILES / "gta6" / "creators.yaml")
        self.assertEqual(config.profile_file("creators.yaml", "other"), config.PROFILES / "other" / "creators.yaml")
        self.assertEqual(config.prefs_file("other"), config.ROOT / "prefs.yaml")

    def test_live_jobs_belong_to_their_profile(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest import mock
        from clipper import config, live
        with tempfile.TemporaryDirectory() as d:
            for jid, prof in (("live-a", None), ("live-b", "gta-rp")):
                (Path(d) / jid).mkdir()
                (Path(d) / jid / "live_ready").write_text("x")
                (Path(d) / jid / "job.json").write_text(json.dumps({"profile": prof} if prof else {}))
            with mock.patch.object(live, "JOBS", Path(d)):
                self.assertEqual(live.ready_jobs(), ["live-a"])
                with mock.patch.object(config, "PROFILE", "gta-rp"):
                    self.assertEqual(live.ready_jobs(), ["live-b"])

    def test_gta6_keys_still_work_as_aliases(self):
        from clipper import live, sources
        old = {"gta6_patterns": ["\\bgta ?6\\b"], "require_gta6": False}
        self.assertEqual(sources.topic_evidence("GTA 6 trailer", "", [], old), "title")
        self.assertFalse(sources.require_topic(old))
        self.assertTrue(sources.require_topic({}))
        self.assertFalse(live.topic_only({"gta_only": False}))
        self.assertTrue(live.topic_only({}))

    def test_export_path_includes_profile(self):
        from datetime import date
        from clipper import render
        self.assertEqual(render.export_dir({"profile": "gta-rp"}, date(2026, 11, 9)),
                         render.EXPORTS / "gta-rp" / "2026-11-09")

    def test_gta_checks_only_for_gta_research_profiles(self):
        from clipper import hooks, playbook, simulate
        gta, other = {"research": "gta"}, {"hashtags": ["#minecraft"]}
        self.assertTrue(hooks.check_picks([{"hooks": ["Why is Kai shaking?"], "titles": ["Why Is Kai Shaking?"]}], gta))
        self.assertEqual(hooks.check_picks([{"hooks": ["Why is Kai shaking?"], "titles": ["Why Is Kai Shaking?"]}],
                                           other), {})
        self.assertEqual(playbook.for_profile(gta), playbook.PLAYBOOK)
        generic = playbook.for_profile({**other, "playbook": {"comedy": {"caption_style": "boxed"}}})
        self.assertEqual(generic["comedy"]["caption_style"], "boxed")
        for play in generic.values():
            for ex in play["examples"]:
                self.assertNotIn("GTA", ex)
                self.assertEqual(hooks.check_hook(ex, gta=False)[0], [], ex)
        self.assertEqual(simulate.niche_for(gta), "gta")
        self.assertIsNone(simulate.niche_for(other))
        self.assertEqual(simulate.profile_kw(other)["generic_tags"], ("minecraft",))

    def test_gta_rp_keeps_nopixel_titles_gta6_rejects(self):
        from clipper import config, hooks, playbook
        from clipper.sources import topic_evidence
        title = "The Casino Heist | GTA RP Nopixel V"
        self.assertIsNone(topic_evidence(title, "", [], config.load(profile="gta6")))
        rp = config.load(profile="gta-rp")
        self.assertEqual(rp["profile"], "gta-rp")
        self.assertEqual(topic_evidence(title, "", [], rp), "title")
        self.assertEqual(topic_evidence("xQc becomes a cop on NoPixel 4.0", "", [], rp), "title")
        self.assertIsNone(topic_evidence("Kai Cenat Reacts To GTA 6 Trailer", "", [], rp))
        self.assertIsNone(topic_evidence("Fortnite tournament", "", [], rp))
        self.assertEqual(hooks.check_title("xQc Robs the Bank in GTA RP", ["#gtarp"], hooks.title_topic(rp)), ([], []))
        for play in playbook.for_profile(rp).values():
            for ex in play["examples"]:
                self.assertEqual(hooks.check_hook(ex)[0], [], ex)


class LiveScheduleMacTests(unittest.TestCase):
    def test_launchd_watcher_abandons_its_recorders(self):
        import plistlib
        import tempfile
        from pathlib import Path
        from unittest import mock
        from clipper import schedule
        with tempfile.TemporaryDirectory() as d, mock.patch.object(schedule, "IS_MAC", True), \
                mock.patch.object(schedule, "PLIST", Path(d) / "com.clipper.gta6.daily.plist"), \
                mock.patch.object(schedule.subprocess, "run"), \
                mock.patch.object(schedule.shutil, "which", return_value="/opt/homebrew/bin/claude"):
            schedule.install_live(every_hours=2)
            watch = plistlib.loads((Path(d) / "com.clipper.gta6.live-watch.plist").read_bytes())
            clip = plistlib.loads((Path(d) / "com.clipper.gta6.live-clip.plist").read_bytes())
        self.assertTrue(watch["AbandonProcessGroup"])
        self.assertEqual((watch["StartInterval"], clip["StartInterval"]), (300, 7200))
        self.assertEqual(watch["EnvironmentVariables"]["CLIPPER_PROFILE"], "gta6")
        self.assertIn("/clip-daily live", clip["ProgramArguments"][2])


class ShippedProfilesTests(unittest.TestCase):
    def test_every_profile_loads_and_its_example_hooks_pass_check(self):
        from clipper import config, hooks, playbook
        names = sorted(p.name for p in config.PROFILES.iterdir() if (p / "profile.yaml").exists())
        self.assertIn("gta6", names)  # plus any private profiles linked into profiles/
        try:
            for name in names:
                cfg = config.load(profile=name)
                self.assertTrue(cfg.get("hashtags"), name)
                gta = hooks.is_gta(cfg)
                for kind, play in playbook.for_profile(cfg).items():
                    for ex in play["examples"]:
                        self.assertEqual(hooks.check_hook(ex, gta=gta)[0], [], f"{name}/{kind}: {ex}")
        finally:
            config.load()  # back to the default profile for the other tests
