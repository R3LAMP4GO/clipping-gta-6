import tempfile
import unittest
from pathlib import Path

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
            self.assertIn("Edit(exports/**)", allowed)  # Claude Code applies Edit path rules to Write as well
            # Write(path) rules are ignored, with a warning on every run (seen in the end-to-end test)
            self.assertFalse([a for a in allowed if a.startswith("Write(")])
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

    def test_recorder_reconnects_without_reprobing(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from clipper import live
        ff = mock.Mock(**{"poll.return_value": 0})
        hls = [mock.Mock(returncode=0, stdout="https://hls/1\n"), mock.Mock(returncode=0, stdout="https://hls/2\n"),
               mock.Mock(returncode=1, stdout="")]
        probes = [{"live": True, "title": "t"}] + [{"live": False}] * 3
        with tempfile.TemporaryDirectory() as d, mock.patch.object(live, "WORK", Path(d)), \
                mock.patch.object(live, "probe", side_effect=probes) as pr, \
                mock.patch.object(live.subprocess, "run", side_effect=hls), \
                mock.patch.object(live.subprocess, "Popen", return_value=ff) as po, \
                mock.patch.object(live.time, "sleep"), mock.patch.object(live.signal, "signal"):
            live.record("kai", "u")
        self.assertEqual(po.call_count, 2)  # the second session started straight after the first ended
        self.assertEqual(pr.call_count, 4)  # probed once to start, then only after a reconnect failed

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
        out = render.post_description("Kai promises A1. #gta6 #KaiCenat", [("KaiCenat", "L")],
                                      ["#gta6", "#kaicenat", "#shorts"])
        self.assertEqual(out, "Kai promises A1. #gta6 #KaiCenat\n\nClip from KaiCenat: L\n\n#shorts")
        self.assertTrue(render.post_description("d", [("c", "L")], ["#gta6"]).endswith("L\n\n#gta6"))

    def test_scenario_windows_open_on_a_curiosity_cue_and_end_on_a_pause(self):
        from clipper import candidates as c
        sents = [{"s": 0, "e": 3, "text": "Okay chat."}, {"s": 20, "e": 23, "text": "Yo I just invented a new move."},
                 {"s": 24, "e": 30, "text": "Watch, you go left then jump."}, {"s": 31, "e": 38, "text": "No way!"},
                 {"s": 50, "e": 52, "text": "Anyway."}]
        out = c.scenario_windows(sents, 120)
        self.assertEqual([(w["start"], w["end"], w["cue"]) for w in out], [(20, 38, "I just invented")])
        self.assertEqual(c.scenario_windows(sents, 120, taken=[(19, 40)]), [])  # already a loudness pick

    def test_twitch_ad_slate_is_detected_and_short_blips_ignored(self):
        import numpy as np
        from clipper import signals
        slate = np.zeros((18, 32, 3))
        slate[..., 0], slate[..., 1] = 70, 76
        slate[..., 2] = np.linspace(150, 180, 32)  # smooth blue-purple gradient
        game = np.random.default_rng(1).integers(0, 255, (18, 32, 3)).astype(float)
        frames = np.stack([game] * 3 + [slate] * 6 + [game] * 3 + [slate] * 2 + [game])
        self.assertEqual(signals.ad_mask(frames, len(frames)).nonzero()[0].tolist(), [3, 4, 5, 6, 7, 8])
        flicker = np.stack([slate] * 3 + [game] + [slate] * 3 + [game] * 2)
        self.assertEqual(signals.ad_mask(flicker, len(flicker)).nonzero()[0].tolist(), list(range(7)))
        from clipper import analyze
        ads = np.array([True] * 30 + [False] * 40 + [True] * 10 + [False] * 20)
        self.assertEqual(analyze.trim_ads({"start": 28.0, "end": 52.0}, ads, 9), {"start": 30.0, "end": 52.0})
        self.assertIsNone(analyze.trim_ads({"start": 60.0, "end": 90.0}, ads, 9))  # an ad inside the clip

    def test_action_labels_fill_quiet_stretches_on_their_own(self):
        from clipper import captions, hooks, render
        pick = {"start": 100, "end": 112, "labels": [{"s": 101, "e": 103, "text": "*enters*"},
                                                      {"s": 104, "e": 105, "text": "*talks over*"},
                                                      {"s": 108, "e": 110, "text": "*gets closer*"}]}
        speech = [{"w": "yo", "s": 4.0, "e": 4.5, "spk": 0}, {"w": "bro", "s": 4.5, "e": 5.0, "spk": 0}]
        words = render.action_labels(pick, speech)
        self.assertEqual([w["w"] for w in words], ["*ENTERS*", "yo", "bro", "*GETS CLOSER*"])  # speech wins
        self.assertEqual(captions.chunk_words(words)[0], [words[0]])  # a label is never merged with speech
        self.assertEqual(hooks.check_labels(pick), [])
        bad = {**pick, "labels": [{"s": 99, "e": 101, "text": "*he walks in slowly*"}]}
        self.assertEqual(len(hooks.check_labels(bad)), 2)
        self.assertTrue(hooks.has_fails(hooks.check_picks([bad])))

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


class SegmentPickTests(unittest.TestCase):
    def _job(self, root, name, channel, url, words, **extra):
        import json
        job = root / name
        job.mkdir()
        (job / "job.json").write_text(json.dumps({"channel": channel, "url": url, "title": "t", **extra}))
        (job / "transcript.json").write_text(json.dumps({"words": words}))
        return job

    def test_segments_join_into_one_vertical_source_with_shifted_words(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from clipper import render
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            kai = self._job(root, "kai", "Kai", "https://www.youtube.com/watch?v=x",
                            [W("Moment", 100.5, 101), W("of", 101, 101.2), W("missed", 300.2, 300.6)])
            xqc = self._job(root, "xqc", "xQc", "https://www.twitch.tv/xqc", [W("no", 50.1, 50.4)])
            pick = {"segments": [{"start": 100, "end": 104}, {"start": 300, "end": 302, "layout": {"type": "split",
                    "face": [0, 0, 0.3, 0.3]}}, {"start": 50, "end": 53, "job": "xqc"}]}
            with mock.patch.object(render.subprocess, "run") as run, \
                    mock.patch.object(render, "source_size", return_value=(1920, 1080)), \
                    mock.patch.object(render.config, "job_dir", side_effect=lambda j: root / j):
                flat, words = render.build_segment_job(pick, kai, {}, root / "seg")
                creds = render.credits(pick, kai, render.load_meta(kai))
            self.assertEqual((flat["start"], flat["end"]), (0.0, 9.0))
            self.assertEqual(flat["layout"], {"type": "vertical", "as": "split"})  # the hook never covers a face
            self.assertEqual([(w["w"], w["s"]) for w in words], [("Moment", 0.5), ("of", 1.0), ("missed", 4.2),
                                                                 ("no", 6.1)])
            self.assertEqual(run.call_count, 4)  # three cuts + the join
            self.assertIn(str(xqc / "source.mp4"), run.call_args_list[2][0][0])
            self.assertIn("crop=", " ".join(run.call_args_list[1][0][0]))  # its own split layout
            self.assertEqual(creds, [("Kai", "https://www.youtube.com/watch?v=x&t=100s"),
                                     ("Kai", "https://www.youtube.com/watch?v=x&t=300s"),
                                     ("xQc", "https://www.twitch.tv/xqc")])
            desc = render.post_description("d", creds, [])
            self.assertIn("Clips from:\nKai: https://www.youtube.com/watch?v=x&t=100s\n", desc)
            self.assertTrue(desc.endswith("xQc: https://www.twitch.tv/xqc"))
            same_stream = [("KaiCenat", "https://www.twitch.tv/kaicenat"), ("kai", "https://www.twitch.tv/kaicenat")]
            self.assertEqual(render.post_description("d", same_stream, []),
                             "d\n\nClip from KaiCenat: https://www.twitch.tv/kaicenat")

    def test_vertical_layout_passes_through_and_keeps_caption_positions(self):
        from clipper import render
        self.assertEqual(render.video_filter({"type": "vertical", "as": "split"}, (1080, 1920)),
                         "[0:v]scale=1080:1920,setsar=1[v1]")
        self.assertEqual(render.caption_layout({"type": "vertical", "as": "split"}), "split")
        self.assertEqual(render.caption_layout({"type": "split"}), "split")
        self.assertEqual(render.caption_layout({}), "fit")

    def test_segment_length_and_labels_use_the_finished_clip(self):
        from clipper import hooks
        pick = {"hooks": ["Why did Kai's game crash?"], "segments": [{"start": 0, "end": 40}, {"start": 100, "end": 125}],
                "labels": [{"s": 41, "e": 43, "text": "*BLACKOUT*"}]}
        self.assertIn("65s is over", hooks.check_length(pick))
        ok = {**pick, "segments": [{"start": 0, "end": 30}, {"start": 100, "end": 125}]}
        self.assertIsNone(hooks.check_length(ok))
        self.assertEqual(hooks.check_labels(ok), [])  # 41-43 s lies inside the 55 s clip
        self.assertIn("segment 1", hooks.check_length({"segments": [{"start": 5}]}))


class FootageTests(unittest.TestCase):
    def test_live_footage_uses_the_wall_clock_and_overlaps_across_chunks(self):
        from clipper import render
        live = {"live": True, "url": "https://www.twitch.tv/KaiCenat", "recorded_at": 1000, "channel": "Kai", "id": "a"}
        later = dict(live, recorded_at=1600, id="b")  # the next chunk of the same stream
        a = render.footage({"start": 610, "end": 640}, None, live)
        b = render.footage({"start": 15, "end": 30}, None, later)
        self.assertEqual(a, [{"source": "twitch:kaicenat", "from": 1610.0, "to": 1640.0}])
        self.assertEqual(render.footage_overlap(a, b), 15.0)
        vod = {"id": "x1", "url": "https://www.youtube.com/watch?v=x1", "offset": 3600}
        self.assertEqual(render.footage({"start": 10, "end": 20}, None, vod),
                         [{"source": "x1", "from": 3610.0, "to": 3620.0}])
        self.assertEqual(render.moment_at({"start": 610, "end": 640}, None, live), 1610)
        vod_chunk = dict(live, url="https://www.twitch.tv/videos/2924282282")  # a VOD recorded like a live chunk
        self.assertEqual(render.footage({"start": 10, "end": 20}, None, vod_chunk),
                         [{"source": "twitch-vod:2924282282", "from": 10.0, "to": 20.0}])

    def test_check_fails_picks_reusing_exported_footage(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest import mock
        from clipper import __main__ as cli
        from clipper import render
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            job = root / "jobs" / "x1"
            job.mkdir(parents=True)
            (job / "job.json").write_text(json.dumps({"id": "x1", "url": "u", "channel": "Kai"}))
            done = root / "exports" / "gta6" / "2026-11-10" / "video 7"
            done.mkdir(parents=True)
            (done / "upload.json").write_text(json.dumps([{"footage": [{"source": "x1", "from": 100, "to": 130}]}]))
            other = root / "exports" / "gta6-es" / "2026-11-10" / "video 1"  # a dub on another channel is fine
            other.mkdir(parents=True)
            (other / "upload.json").write_text(json.dumps([{"footage": [{"source": "x1", "from": 0, "to": 999}],
                                                            "lang": "es"}]))
            picks = [{"start": 128, "end": 150}, {"start": 120, "end": 140}]
            with mock.patch.object(render, "EXPORTS", root / "exports"), \
                    mock.patch.object(cli.config, "job_dir", return_value=job):
                out = cli.reused_footage(picks, "x1", {"profile": "gta6"})
            self.assertEqual(list(out), [2])  # 2 s of overlap is within the tolerance, 10 s is a repost
            self.assertIn("gta6/2026-11-10/video 7 already uses 10s", out[2][0])
            from clipper import hooks
            self.assertTrue(hooks.has_fails({"video 2": {"footage": out[2]}}))

    def test_manifest_carries_footage_prediction_and_moment(self):
        from unittest import mock
        from clipper import render
        meta = {"id": "x1", "url": "https://www.youtube.com/watch?v=x1", "channel": "Kai"}
        pick = {"start": 5, "end": 25, "hooks": ["Why did Kai's game crash?", "Kai never saw the crash coming"]}
        variants = [{"file": "a.mp4", "hook": h, "check": {"duration": 20}} for h in pick["hooks"]]
        with mock.patch.object(render, "predicted", return_value={"Why did Kai's game crash?": 1.4}), \
                mock.patch.object(render.time, "time", return_value=5000):
            out = render.upload_manifest(pick, meta, {}, variants, ["T"])
        self.assertEqual(out[0]["footage"], [{"source": "x1", "from": 5.0, "to": 25.0}])
        self.assertEqual((out[0]["predicted"], out[1]["predicted"], out[0]["moment_at"]), (1.4, None, 5000))
        self.assertEqual(out[0]["source"], "https://www.youtube.com/watch?v=x1&t=5s")


class FindTests(unittest.TestCase):
    def test_find_matches_one_line_across_recent_streams_and_skips_old_jobs(self):
        import json
        import tempfile
        import time
        from pathlib import Path
        from clipper import live
        with tempfile.TemporaryDirectory() as d:
            now = time.time()
            for name, ch, rec, start in (("live-kai-1", "Kai", now - 1800, 100), ("live-xqc-1", "xQc", now - 1700, 3),
                                          ("live-old-1", "Old", now - 86400, 100)):
                job = Path(d) / name
                job.mkdir()
                (job / "job.json").write_text(json.dumps({"channel": ch, "live": True, "recorded_at": rec,
                                                          "duration": 1800}))
                (job / "transcript.json").write_text(json.dumps({"words": [
                    W("Moment", start, start + 0.4), W("of", start + 0.4, start + 0.5), W("truth.", start + 0.5, start + 1),
                    W("unrelated", start + 5, start + 6)]}))
            (Path(d) / "live-kai-1" / "source.mp4").write_bytes(b"x")
            hits = live.find(r"moment of truth", 6, d)
        self.assertEqual([(h["job"], h["start"], h["footage"]) for h in hits],
                         [("live-kai-1", 100, True), ("live-xqc-1", 3, False)])
        self.assertEqual(hits[0]["text"], "Moment of truth.")

    def test_find_orders_matches_across_midnight(self):
        import json
        import tempfile
        from datetime import datetime
        from pathlib import Path
        from unittest import mock
        from clipper import live
        midnight = datetime(2026, 11, 11).timestamp()
        with tempfile.TemporaryDirectory() as d, mock.patch.object(live.time, "time", return_value=midnight + 600):
            for name, rec in (("live-a-1", midnight - 30), ("live-b-1", midnight - 20)):
                job = Path(d) / name
                job.mkdir()
                (job / "job.json").write_text(json.dumps({"channel": name, "live": True, "recorded_at": rec,
                                                          "duration": 600}))
                start = 25 if name == "live-a-1" else 25  # a at 23:59:55, b at 00:00:05
                (job / "transcript.json").write_text(json.dumps({"words": [W("Moment", start, start + 0.4),
                                                                           W("of", start + 0.4, start + 0.5),
                                                                           W("truth.", start + 0.5, start + 1)]}))
            hits = live.find("moment of truth", 6, d)
        self.assertEqual([(h["job"], h["at"]) for h in hits], [("live-a-1", "23:59:55"), ("live-b-1", "00:00:05")])

    def test_live_done_keeps_the_source_for_other_streams_edits(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from clipper import live
        with tempfile.TemporaryDirectory() as d, mock.patch.object(live, "JOBS", Path(d)):
            job = Path(d) / "live-kai-1"
            job.mkdir()
            for f in ("source.mp4", "audio.wav"):
                (job / f).write_bytes(b"x")
            live.mark_done("live-kai-1")
            self.assertEqual(sorted(p.name for p in job.iterdir()), ["live_done", "source.mp4"])


class ScaleTests(unittest.TestCase):
    def test_watch_starts_recorders_by_priority_up_to_the_cap(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from clipper import live
        streams = [{"name": n, "url": f"https://www.twitch.tv/{n}", "live": True, "on_topic": True, "recording": False,
                    **({"priority": p} if p is not None else {})} for n, p in (("b", None), ("a", 1), ("c", 50))]
        with tempfile.TemporaryDirectory() as d, mock.patch.object(live, "WORK", Path(d)), \
                mock.patch.object(live, "status", return_value=streams), \
                mock.patch.object(live, "alive_recorders", return_value=1), \
                mock.patch.object(live.subprocess, "Popen", return_value=mock.Mock(pid=1)):
            self.assertEqual(live.watch({"max_recorders": 3}), ["a", "c"])
            self.assertEqual(live.watch({}), ["a", "c", "b"])

    def test_hot_windows_cover_the_peaks_within_the_budget(self):
        import numpy as np
        from clipper import analyze
        score = np.zeros(1800)
        score[300:305], score[1200:1205], score[320:322] = 1.0, 0.8, 0.9
        wins = analyze.hot_windows(score, 1800.0)
        self.assertTrue(any(a <= 302 < b for a, b in wins) and any(a <= 1202 < b for a, b in wins))
        self.assertLessEqual(sum(b - a for a, b in wins), 0.35 * 1800)
        self.assertEqual(wins, sorted(wins))
        self.assertTrue(all(b1 <= a2 for (_, b1), (a2, _) in zip(wins, wins[1:])))

    def test_hot_transcription_shifts_words_onto_the_chunk_and_auto_needs_load(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from clipper import analyze
        with tempfile.TemporaryDirectory() as d, mock.patch.object(analyze.subprocess, "run"), \
                mock.patch.object(analyze.transcribe, "transcribe",
                                  return_value=([{"w": "no", "s": 1.0, "e": 1.5}], [], "m")):
            words, _, model = analyze.transcribe_windows(Path(d) / "a.wav", Path(d), {}, False, [(100, 190), (600, 690)])
        self.assertEqual([w["s"] for w in words], [101.0, 601.0])
        with mock.patch("clipper.live.alive_recorders", return_value=5):
            self.assertEqual(analyze.transcribe_mode({"transcribe_mode": "auto"}), "hot")
            self.assertEqual(analyze.transcribe_mode({"transcribe_mode": "auto", "hot_when_recorders": 5}), "full")
            self.assertEqual(analyze.transcribe_mode({"transcribe_mode": "full"}), "full")


class WholeStreamTests(unittest.TestCase):
    def test_chunks_whose_analysis_died_are_analyzed_again(self):
        import os
        import tempfile
        from pathlib import Path
        from unittest import mock
        from clipper import config, live
        with tempfile.TemporaryDirectory() as d, mock.patch.object(live, "JOBS", Path(d)), \
                mock.patch.object(live, "WORK", Path(d) / "_live"), mock.patch.object(config, "PROFILE", "gta-rp"):
            def chunk(name, *files, analyzing=None):
                job = Path(d) / name
                job.mkdir()
                (job / "job.json").write_text('{"profile": "gta-rp"}')
                for f in ("live_ready", "source.mp4") + files:
                    (job / f).write_text("x")
                if analyzing:
                    (job / "analyzing").write_text(str(analyzing))
            chunk("live-a-1")                                 # its recorder was killed mid-analysis
            chunk("live-a-2", analyzing=os.getpid())          # being analyzed right now
            chunk("live-a-3", "candidates.json")              # scored
            chunk("live-a-4", "live_done")                    # clipped
            chunk("live-a-5", analyzing=99999999)             # analyzer died
            self.assertEqual(live.stranded_jobs(), ["live-a-1", "live-a-5"])
            with mock.patch.object(live.subprocess, "Popen", return_value=mock.Mock(pid=os.getpid())) as po:
                self.assertEqual(live.reanalyze_stranded(), ["live-a-1", "live-a-5"])
                self.assertEqual(live.stranded_jobs(), [])    # now running
            self.assertIn(["live", "analyze", "live-a-1"], [c[0][0][3:6] for c in po.call_args_list])
            (Path(d) / "live-a-1" / "analyze_tries").write_text("3")
            (Path(d) / "live-a-1" / "analyzing").unlink()
            self.assertEqual(live.stranded_jobs(), [])        # gives up after 3 tries

    def test_restart_hands_over_to_the_new_recorder(self):
        import os
        import tempfile
        from pathlib import Path
        from unittest import mock
        from clipper import live
        with tempfile.TemporaryDirectory() as d, mock.patch.object(live, "WORK", Path(d)), \
                mock.patch.object(live, "load_streams", return_value=[{"name": "kaicenat-twitch",
                                                                       "url": "https://www.twitch.tv/kaicenat"}]), \
                mock.patch.object(live.subprocess, "Popen", return_value=mock.Mock(pid=4242)) as po:
            (Path(d) / "kaicenat-twitch").mkdir()
            (Path(d) / "kaicenat-twitch" / "pid").write_text(str(os.getpid()))
            out = live.restart("kaicenat-twitch", 10)
        self.assertEqual((out["replacing"], out["new_pid"]), (os.getpid(), 4242))
        cmd = po.call_args[0][0]
        self.assertEqual(cmd[-2:], ["--replace", str(os.getpid())])
        self.assertIn("record", cmd)


class TopHookTests(unittest.TestCase):
    def test_only_the_best_passing_hook_and_its_title_are_rendered(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest import mock
        from clipper import render
        pick = {"start": 0, "end": 10, "hooks": ["Kai never saw the crash coming", "Why did Kai's game crash?", "the stream"],
                "titles": ["T lost", "T crash", "T stream"]}
        scores = {"Kai never saw the crash coming": 1.2, "Why did Kai's game crash?": 1.5, "the stream": 9.0}  # fails check
        with mock.patch.object(render, "predicted", return_value=scores):
            top = render.top_hooks(pick, {}, 1)
            self.assertEqual((top["hooks"], top["titles"]), (["Why did Kai's game crash?"], ["T crash"]))
            self.assertEqual(render.top_hooks(pick, {}, 2)["hooks"], ["Why did Kai's game crash?", "Kai never saw the crash coming"])
        with tempfile.TemporaryDirectory() as d:
            job, out = Path(d) / "job", Path(d) / "out"
            job.mkdir()
            (job / "job.json").write_text(json.dumps({"channel": "Kai", "url": "u", "title": "t"}))
            (job / "transcript.json").write_text(json.dumps({"words": []}))
            with mock.patch.object(render, "predicted", return_value=scores), \
                    mock.patch.object(render, "prepare_clip", return_value={"vo": None, "speakers": 1, "transcript": ""}), \
                    mock.patch.object(render, "encode_variant") as enc, mock.patch.object(render, "probe", return_value={}), \
                    mock.patch.object(render, "clip_markdown", return_value=""):
                res = render.render(job, [pick], {}, out_dir=out, top=1)
            self.assertEqual(enc.call_count, 1)
            manifest = json.loads((out / "video 1" / "upload.json").read_text())
            self.assertEqual([(m["hook"], m["title"], m["rank"]) for m in manifest],
                             [("Why did Kai's game crash?", "T crash", 0)])
            self.assertEqual(res[0]["titles"], ["T crash"])


class RecorderPidTests(unittest.TestCase):
    def test_a_stream_never_gets_a_second_recorder(self):
        import os
        import subprocess
        import sys
        import tempfile
        from pathlib import Path
        from unittest import mock
        from clipper import live
        other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            with tempfile.TemporaryDirectory() as root:
                d = Path(root) / "kaicenat-twitch"  # record() finds it by slug(name)
                d.mkdir()
                (d / "pid").write_text(str(other.pid))           # a live recorder owns the stream
                self.assertFalse(live.claim(d))
                self.assertEqual((d / "pid").read_text(), str(other.pid))
                with mock.patch.object(live, "WORK", d.parent), mock.patch.object(live, "probe") as pr, \
                        mock.patch.object(live.subprocess, "run") as run:
                    live.record("kaicenat-twitch", "u", cfg=None)    # refuses before touching the stream
                run.assert_not_called()
                pr.assert_not_called()
                self.assertEqual((d / "pid").read_text(), str(other.pid))
                self.assertTrue(live.claim(d, replace_pid=other.pid))  # `live restart` may take over
                self.assertEqual((d / "pid").read_text(), str(os.getpid()))
                (d / "pid").write_text("99999999")                  # a dead recorder's leftover file
                self.assertTrue(live.claim(d))
                (d / "pid").write_text(str(other.pid))              # the replacement owns it now
                live.release(d)
                self.assertTrue((d / "pid").exists())               # never delete another recorder's file
                (d / "pid").write_text(str(os.getpid()))
                live.release(d)
                self.assertFalse((d / "pid").exists())
        finally:
            other.kill()
            other.wait()


class LearningSafeguardTests(unittest.TestCase):
    def test_manifest_records_how_strong_the_moment_was(self):
        import json
        import tempfile
        from pathlib import Path
        from clipper import render
        with tempfile.TemporaryDirectory() as d:
            job = Path(d)
            (job / "candidates.json").write_text(json.dumps({"candidates": [
                {"start": 0, "end": 20, "score": 40, "tier": "maybe", "signals": {"peak_lufs": -12, "typical_lufs": -24,
                                                                                   "jump_lu": 6, "hype_hits": ["bro"]}},
                {"start": 25, "end": 60, "score": 70, "tier": "strong", "signals": {"peak_lufs": -6, "typical_lufs": -24,
                                                                                     "jump_lu": 15, "hype_hits": []}}]}))
            m = render.moment_signals({"start": 18, "end": 40}, job, {})
        self.assertEqual(m, {"score": 70, "tier": "strong", "jump_lu": 15, "loud_lu": 18.0, "hype": 0})
        self.assertIsNone(render.moment_signals({"start": 18, "end": 40}, None, {}))

    def test_learned_weights_are_bounded_and_can_be_switched_off(self):
        import os
        import tempfile
        from pathlib import Path
        from unittest import mock
        from clipper import config
        with tempfile.TemporaryDirectory() as d:
            prof = Path(d) / "gta-rp"
            prof.mkdir()
            (prof / "learned-weights.yaml").write_text("weights: {jump: 0.25, loudness: 5.0, speech_rate: 0.0, bogus: 1}\n")
            with mock.patch.object(config, "PROFILES", Path(d)), mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("CLIPPER_NO_LEARNED", None)
                w = config.load(None, "gta-rp")["weights"]
                self.assertEqual((w["jump"], w["loudness"], w["speech_rate"]), (0.25, 0.45, 0.05))  # 1.5x / 0.5x caps
                self.assertNotIn("bogus", w)
                os.environ["CLIPPER_NO_LEARNED"] = "1"
                self.assertEqual(config.load(None, "gta-rp")["weights"]["jump"], 0.2)
                os.environ.pop("CLIPPER_NO_LEARNED")


class CleanupTests(unittest.TestCase):
    def make_job(self, root, name, age_h, live_done_h=None, files=("source.mp4", "audio.wav", "transcript.json")):
        import os
        import time
        job = root / name
        job.mkdir()
        t = time.time() - age_h * 3600
        for n in files:
            (job / n).write_text("x" * 10)
            os.utime(job / n, (t, t))
        if live_done_h is not None:
            (job / "live_done").write_text("done")
            t = time.time() - live_done_h * 3600
            os.utime(job / "live_done", (t, t))
        return job

    def test_only_expired_sources_go_and_everything_else_stays(self):
        import os
        from clipper import cleanup
        cfg = {"keep_live_sources_hours": 3, "keep_sources_days": 2}
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            old_live = self.make_job(root, "live-a-1", 5, live_done_h=4)
            new_live = self.make_job(root, "live-a-2", 2, live_done_h=1)
            unclipped = self.make_job(root, "live-a-3", 5)  # recorded, not clipped yet: kept until the day rule
            old_vod = self.make_job(root, "vod-old", 72)
            new_vod = self.make_job(root, "vod-new", 12)
            busy = self.make_job(root, "vod-busy", 72)
            (busy / "analyzing").write_text(str(os.getpid()))  # an analysis is reading it right now
            (root / "_live").mkdir()
            (root / "_live" / "source.mp4").write_text("x")

            dry = cleanup.run(cfg, dry_run=True, jobs_dir=root)
            self.assertEqual(dry["jobs"], ["live-a-1", "vod-old"])
            self.assertTrue((old_live / "source.mp4").exists())  # dry run deletes nothing

            out = cleanup.run(cfg, jobs_dir=root)
            self.assertEqual((out["files"], out["jobs"]), (4, ["live-a-1", "vod-old"]))
            for job in (old_live, old_vod):
                self.assertFalse((job / "source.mp4").exists())
                self.assertFalse((job / "audio.wav").exists())
                self.assertTrue((job / "transcript.json").exists())
            for job in (new_live, unclipped, new_vod, busy):
                self.assertTrue((job / "source.mp4").exists(), job.name)
            self.assertTrue((root / "_live" / "source.mp4").exists())

    def test_null_keeps_sources_forever(self):
        from clipper import cleanup
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.make_job(root, "live-a-1", 500, live_done_h=400)
            self.make_job(root, "vod-old", 500)
            cfg = {"keep_live_sources_hours": None, "keep_sources_days": None}
            self.assertEqual(cleanup.run(cfg, jobs_dir=root)["files"], 0)


class LiveHealthTests(unittest.TestCase):
    def test_reports_missed_stalled_failed_and_low_disk(self):
        import os
        import time
        from collections import namedtuple
        from unittest import mock
        from clipper import live
        with tempfile.TemporaryDirectory() as d:
            jobs = Path(d)
            stalled = jobs / "_live" / "b"
            stalled.mkdir(parents=True)
            (stalled / "pid").write_text(str(os.getpid()))
            seg = stalled / "1-0001.ts"
            seg.write_text("x")
            old = time.time() - 30 * 60
            os.utime(seg, (old, old))
            job = jobs / "live-c-1"
            job.mkdir()
            for n, text in (("live_ready", "1"), ("source.mp4", "x"), ("analyze_tries", "3"), ("job.json", "{}")):
                (job / n).write_text(text)
            streams = [{"name": "a", "live": True, "on_topic": True, "recording": False},
                       {"name": "b", "live": True, "on_topic": True, "recording": True},
                       {"name": "c", "live": False, "on_topic": False, "recording": False}]
            Usage = namedtuple("Usage", "total used free")
            with mock.patch.object(live, "JOBS", jobs), mock.patch.object(live, "WORK", jobs / "_live"), \
                    mock.patch.object(live, "status", return_value=streams), \
                    mock.patch.object(live.shutil, "disk_usage", return_value=Usage(0, 0, 5e9)):
                issues = live.health({"max_recorders": 12, "min_free_gb": 30})
                self.assertEqual(sorted(issues), ["analysis_failed", "disk", "not_recording", "stalled"])
                self.assertIn("a", issues["not_recording"])
                self.assertIn("b (30 min)", issues["stalled"])
                self.assertIn("live-c-1", issues["analysis_failed"])
                # at the recorder cap a missed stream is expected, and a fresh segment means it's recording fine
                os.utime(seg)
                issues = live.health({"max_recorders": 1, "min_free_gb": 1})
                self.assertEqual(sorted(issues), ["analysis_failed"])


class CaptionFontTests(unittest.TestCase):
    def test_non_latin_captions_switch_to_a_font_that_draws_them(self):
        from clipper import captions
        bebas = captions.font("bebas", 116)
        self.assertTrue(captions.covers(bebas, "Y'ALL MISSED THAT ¿AÑO?"))
        self.assertFalse(captions.covers(bebas, "НЕЕЕТ"))  # Bebas has no Cyrillic: it drew empty boxes
        self.assertIs(captions.font_for("bebas", 116, "NOOOO"), bebas)  # Latin keeps the style's font
        self.assertTrue(captions.covers(captions.font_for("bebas", 116, "ВЫ ПРОПУСТИЛИ ВСЁ"), "ВЫ ПРОПУСТИЛИ ВСЁ"))


class DailySkipsFailedDownloads(unittest.TestCase):
    def test_age_restricted_download_is_skipped_not_fatal(self):
        import subprocess
        from unittest import mock
        from clipper import __main__ as cli
        vids = [{"id": "bad", "processed": False, "source": "c", "duration": 60, "title": "a", "channel": "x"},
                {"id": "good", "processed": False, "source": "c", "duration": 60, "title": "b", "channel": "x"}]

        def fetch(vid, section=None):
            if vid == "bad":
                raise subprocess.CalledProcessError(1, ["yt-dlp"])
            return Path("/tmp/good"), {}
        with mock.patch.object(cli.library, "load_prefs", return_value={}), \
                mock.patch.object(cli.cleanup_mod, "run", return_value={"files": 0, "gb": 0}), \
                mock.patch.object(cli.sources, "watch", return_value=(vids, [], 0)), \
                mock.patch.object(cli.sources, "fetch", side_effect=fetch), \
                mock.patch.object(cli.analyze_mod, "analyze", return_value={"candidates": [], "recommended": 1}):
            out = cli.daily({}, limit=2)
        self.assertEqual([j["job"] for j in out["analyzed"]], ["good"])
        self.assertIn("bad", out["errors"][0]["source"])


class TranscriptFileTests(unittest.TestCase):
    def test_one_word_per_line_and_still_json(self):
        import json
        data = {"model": "m", "events": [{"t": 1.0}], "words": [W("Hello", 843.1, 843.4), W("ÿou", 843.5, 843.9)]}
        text = transcribe.dumps_transcript(data)
        self.assertEqual(json.loads(text), data)
        lines = text.splitlines()
        self.assertTrue(any(line.startswith('{"w": "Hello", "s": 843.1') for line in lines))  # Grep finds a second
        self.assertEqual(len(lines), 4)
        self.assertEqual(json.loads(transcribe.dumps_transcript({"words": []})), {"words": []})


class ReportTests(unittest.TestCase):
    def test_reports_append_and_never_drop_the_video_list(self):
        from unittest import mock
        from clipper import render
        with tempfile.TemporaryDirectory() as d, mock.patch.object(render, "EXPORTS", Path(d)):
            cfg = {"profile": "gta-rp"}
            index = render.export_dir(cfg) / "index.md"
            index.parent.mkdir(parents=True)
            index.write_text("- **video 1**: POV: xQc Breaks Into The Wrong House · xQc · 5 hooks\n")
            render.append_report(cfg, "## Run 1\n5 videos from xQc.")
            render.append_report(cfg, "## Run 2\nNo clips: all candidates weak.")
            text = index.read_text()
            self.assertTrue(text.startswith("- **video 1**"))
            self.assertLess(text.index("## Run 1"), text.index("## Run 2"))
        for prompt in (".claude/commands/clip-daily.md", ".codex/prompts/clip-daily.md"):
            body = Path(prompt).read_text()
            self.assertIn("python3 -m clipper report", body)
            self.assertIn("never Write or Edit `index.md`", body)
