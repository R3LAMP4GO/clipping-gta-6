import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from clipper import candidates as cand
from clipper import captions, transcribe


def W(text, s, e):
    return {"w": text, "s": s, "e": e}


def streamers_cfg():
    """The `streamers` profile's routing and gate settings (the profile itself is private, so CI builds them)."""
    from clipper import config
    gta = config.load(profile="gta6")
    config.load()
    return {**gta, "profile": "streamers", "research": None, "require_topic": False, "selection_gate": True,
            "exclude_title_patterns": gta["topic_patterns"], "title_topic": None}


# every pick names its turn, a cold premise, its open loop and the payoff (`clipper check` fails it otherwise)
TURN = {"turn": "meeting", "cold_premise": "Kai meets a kid who says he is 13", "loop": "how old is he really?",
        "payoff_at": 9.0, "premise_type": "interaction",
        "selection": {"standalone": True, "unexpected": True, "payoff": True, "six_words": True, "story": False}}


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
        self.assertEqual(tl[1][4], ["no", "way"])  # 1-2 words at a time, like the 500K+ clip captions
        self.assertEqual(tl[2][4], ["bro."])


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
    def test_claim_skips_folder_taken_by_parallel_render(self):
        from clipper.render import claim_video_folder
        with tempfile.TemporaryDirectory() as d:
            Path(d, "video 3").mkdir()
            n, folder = claim_video_folder(Path(d), 3)
            self.assertEqual((n, folder.name), (4, "video 4"))
            self.assertTrue(folder.is_dir())

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
            self.assertTrue(hooks.structures(h), h)
            if not hooks.banned_hook(h):  # reaction/meme openers are banned for our clips since 2026-11-21
                self.assertEqual(hooks.check_hook(h)[0], [], h)

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
        for good in ("Watching *GTA 6* with his mom in the room", "His parents walk in during *GTA 6*",
                     "How playing *GTA 6* is gonna be 😂"):
            self.assertEqual(hooks.check_hook(good)[0], [], good)
        for meme in ("Me watching *GTA 6* with my mom in the room", "When your parents walk in during *GTA 6*"):
            self.assertIn(hooks.BANNED_NOTE, hooks.check_hook(meme)[0], meme)


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
    def test_titles_narrate_instead_of_matching_the_hook(self):
        from clipper import hooks
        rep = hooks.check_picks([{"hooks": ["Why is xQc making the hostages sing?"],
                                  "titles": ["xQc Made The Hostages Sing In GTA RP 😭"]}])
        self.assertNotIn("pairing", rep.get("video 1", {}))
        notes = hooks.check_title("xQc Made The Hostages Sing In GTA RP 😭", topic=None)[1]
        self.assertFalse([n for n in notes if "narrate what happened" in n])  # only the open-loop note may show
        for t in ("xQc Did NOT Plan The Escape 💀 | GTA RP", "Why Is xQc Driving In Scuba Gear?! | GTA RP"):
            self.assertIn("narrate what happened", hooks.check_title(t, topic=None)[1][0])
            self.assertEqual(hooks.check_title(t, topic=None)[0], [])  # a note, not a fail
            self.assertEqual(hooks.check_title(t, topic=None, narrate=False)[1], [])  # non-GTA profiles

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
                                                                                    return_value=asr == "whisper"), \
                    mock.patch.object(setup.subprocess, "run", return_value=mock.Mock(returncode=0)):
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

    def test_action_labels_win_over_speech_on_their_own(self):
        from clipper import captions, hooks, render
        pick = {"start": 100, "end": 112, "labels": [{"s": 101, "e": 103, "text": "*enters*"},
                                                      {"s": 104, "e": 105, "text": "*talks over*"},
                                                      {"s": 108, "e": 110, "text": "*gets closer*"}]}
        speech = [{"w": "yo", "s": 4.0, "e": 4.5, "spk": 0}, {"w": "bro", "s": 4.5, "e": 5.0, "spk": 0}]
        words = render.action_labels(pick, speech)
        self.assertEqual([w["w"] for w in words], ["*ENTERS*", "*TALKS OVER*", "*GETS CLOSER*"])  # labels win
        later = render.action_labels({**pick, "labels": pick["labels"][2:]}, speech)
        self.assertEqual([w["w"] for w in later], ["yo", "bro", "*GETS CLOSER*"])  # speech shows outside labels
        self.assertEqual(captions.chunk_words(later)[-1], [later[-1]])  # a label is never merged with speech
        self.assertEqual(hooks.check_labels(pick), [])
        bad = {**pick, "labels": [{"s": 99, "e": 101, "text": "*he walks in really slowly*"}]}
        self.assertEqual(len(hooks.check_labels(bad)), 2)  # 5 words, outside the clip
        self.assertTrue(hooks.has_fails(hooks.check_picks([bad])))

    def test_clips_are_capped_at_45s(self):
        from clipper import hooks
        base = {"hooks": ["Why did Kai scream?"], "start": 10, "end": 55}
        self.assertNotIn("length", hooks.check_picks([base]).get("video 1", {}))
        self.assertIn("aim for 12-25s", hooks.check_picks([base])["video 1"]["length_note"])  # a note, not a fail
        self.assertIn("length_note", hooks.check_picks([{**base, "end": 38}])["video 1"])  # 28s: over the 25s aim
        self.assertNotIn("length_note", hooks.check_picks([{**base, "end": 35}]).get("video 1", {}))
        long = {**base, "end": 57}
        self.assertIn("45s maximum", hooks.check_picks([long])["video 1"]["length"])
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
        self.assertIn("45s maximum", str(e.exception))
        rj.assert_not_called()

    def test_live_clip_cmd_replaces_claude(self):
        from clipper import schedule
        jobs = schedule.live_jobs(None, clip_cmd="/usr/local/bin/my-clip-job")
        self.assertEqual(jobs["live-clip"][0][2].split("; then ")[1], "/usr/local/bin/my-clip-job; fi")
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
        import os
        from unittest import mock
        from clipper import config
        mock.patch.dict(os.environ, {"CLIPPER_NO_LEARNED": "1"}).start()  # a posting box's learned weights override these
        self.addCleanup(mock.patch.stopall)
        cfg = config.load()
        self.assertEqual(cfg["profile"], "gta6")
        self.assertEqual(config.load(profile="gta6"), cfg)
        self.assertEqual(cfg["hashtags"], ["#gta6", "#gtavi", "#shorts"])
        self.assertIn("\\bgta ?(6|vi)\\b", cfg["topic_patterns"])
        self.assertIn("nopixel", cfg["exclude_title_patterns"])
        self.assertEqual(cfg["search"], ["GTA 6 reaction", "GTA 6 gameplay funny"])
        self.assertIn("xQc", [c["name"] for c in cfg["channels"]])
        self.assertEqual(cfg["weights"]["loudness"], 0.40)

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
        self.assertEqual(hooks.check_picks([{"hooks": ["Why is Kai shaking?"], "titles": ["Why Is Kai Shaking?"],
                                             **TURN}], other), {})
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
        fails, notes = hooks.check_title("xQc Robs the Bank in GTA RP 😭", ["#gtarp"], hooks.title_topic(rp))
        self.assertEqual(fails, [])
        self.assertTrue(all("open loop" in n for n in notes))  # the topic is found; only the open-loop note may show
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


class ScheduleAgentTests(unittest.TestCase):
    """Daily and live runs per profile, with Claude or Codex; nothing is installed (launchctl/systemctl mocked)."""

    def _install(self, profile, agent, mac):
        import plistlib
        import tempfile
        from pathlib import Path
        from unittest import mock
        from clipper import config, schedule
        bins = {"claude": "/opt/bin/claude", "codex": "/opt/bin/codex", "python3": "/usr/bin/python3"}
        with mock.patch.object(config, "PROFILE", profile):
            with tempfile.TemporaryDirectory() as d, mock.patch.object(schedule, "IS_MAC", mac), \
                    mock.patch.object(schedule, "UNIT_DIR", Path(d)), \
                    mock.patch.object(schedule, "PLIST", Path(d) / "com.clipper.gta6.daily.plist"), \
                    mock.patch.object(schedule.subprocess, "run") as run, \
                    mock.patch.object(schedule.shutil, "which", side_effect=bins.get):
                out = schedule.install("08:15", agent)
                files = {f.name: f.read_bytes() for f in Path(d).iterdir()}
                live = schedule.live_jobs(schedule.find_agent(agent), agent=agent)
                schedule.remove() if mac else None
                left = sorted(f.name for f in Path(d).iterdir())
        plists = {k: plistlib.loads(v) for k, v in files.items() if k.endswith(".plist")}
        return out, files, plists, live, left, run

    def test_claude_and_codex_argv_per_profile(self):
        import shlex
        from clipper.config import ROOT
        for profile, sfx in (("gta6", ""), ("streamers", "-streamers")):
            for agent in ("claude", "codex"):
                out, _, plists, live, left, _ = self._install(profile, agent, mac=True)
                label = f"com.clipper.gta6.daily{sfx}"
                self.assertEqual(list(plists), [f"{label}.plist"], (profile, agent))  # gta6 keeps its label
                p = plists[f"{label}.plist"]
                self.assertEqual(p["Label"], label)
                self.assertEqual(p["EnvironmentVariables"]["CLIPPER_PROFILE"], profile)
                self.assertTrue(p["StandardOutPath"].endswith(f"logs/daily{sfx}.log"))
                argv = p["ProgramArguments"]
                clip = live[f"live-clip{sfx}"][0][2]
                args = profile if sfx else ""
                if agent == "claude":
                    self.assertEqual(argv[:3], ["/opt/bin/claude", "-p", f"/clip-daily {args}".strip()])
                    self.assertIn("--model", argv)
                    self.assertIn(shlex.quote(f"/clip-daily {args} live".replace("  ", " ")), clip)
                else:
                    self.assertEqual(argv[:4], ["/opt/bin/codex", "exec", "-C", str(ROOT)])
                    self.assertEqual(argv[4:-1], ["-s", "workspace-write", "-c",
                                                  "sandbox_workspace_write.network_access=true",
                                                  "-c", 'approval_policy="never"'])
                    self.assertIn(".codex/prompts/clip-daily.md", argv[-1])
                    self.assertIn(f"arguments: {args or 'none'}.", argv[-1])
                    self.assertIn(f"arguments: {(args + ' live').strip()}.", clip)
                    self.assertNotIn("$", argv[-1])  # systemd would expand it
                self.assertIn(f"daily {profile} run ({agent})", out)
                self.assertEqual(left, [])  # remove takes this profile's daily job away

    def test_systemd_units_per_profile_with_codex(self):
        _, files, _, _, _, run = self._install("streamers", "codex", mac=False)
        self.assertEqual(sorted(files), ["clipper-gta6-daily-streamers.service", "clipper-gta6-daily-streamers.timer"])
        service = files["clipper-gta6-daily-streamers.service"].decode()
        self.assertIn("Environment=CLIPPER_PROFILE=streamers", service)
        self.assertIn("/opt/bin/codex exec -C", service)
        self.assertIn("sandbox_workspace_write.network_access=true", service)
        self.assertIn("OnCalendar=*-*-* 08:15:00", files["clipper-gta6-daily-streamers.timer"].decode())
        self.assertIn("clipper-gta6-daily-streamers.timer", str(run.call_args_list))

    def test_agent_pref_and_unknown_agent(self):
        from unittest import mock
        from clipper import library, schedule
        with mock.patch.object(library, "load_prefs", return_value={"agent": "codex"}):
            self.assertEqual(schedule.pick_agent(), "codex")
            self.assertEqual(schedule.pick_agent("claude"), "claude")
        with mock.patch.object(library, "load_prefs", return_value={}):
            self.assertEqual(schedule.pick_agent(), "claude")
        with self.assertRaises(SystemExit):
            schedule.pick_agent("gemini")
        self.assertIn("agent", library.PREF_RULES)


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
                "labels": [{"s": 0.5, "e": 2, "text": "*game freezes*"}, {"s": 41, "e": 43, "text": "*BLACKOUT*"}]}
        self.assertIn("65s is over", hooks.check_length(pick))
        ok = {**pick, "segments": [{"start": 0, "end": 20}, {"start": 100, "end": 125}]}
        self.assertIsNone(hooks.check_length(ok))
        self.assertEqual(hooks.check_labels(ok), [])  # 41-43 s lies inside the 45 s clip
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
        pick = {"start": 5, "end": 25, "hooks": ["Why did Kai's game crash?", "Kai's game *crashed* mid-heist"]}
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
        pick = {"start": 0, "end": 10, "hooks": ["Kai's game *crashed* mid-heist", "Why did Kai's game crash?", "the stream"],
                "titles": ["T lost", "T crash", "T stream"]}
        scores = {"Kai's game *crashed* mid-heist": 1.2, "Why did Kai's game crash?": 1.5, "the stream": 9.0}  # fails check
        with mock.patch.object(render, "predicted", return_value=scores):
            top = render.top_hooks(pick, {}, 1)
            self.assertEqual((top["hooks"], top["titles"]), (["Why did Kai's game crash?"], ["T crash"]))
            self.assertEqual(render.top_hooks(pick, {}, 2)["hooks"], ["Why did Kai's game crash?", "Kai's game *crashed* mid-heist"])
        with tempfile.TemporaryDirectory() as d:
            job, out = Path(d) / "job", Path(d) / "out"
            job.mkdir()
            (job / "job.json").write_text(json.dumps({"channel": "Kai", "url": "u", "title": "t"}))
            (job / "transcript.json").write_text(json.dumps({"words": []}))
            with mock.patch.object(render, "predicted", return_value=scores), \
                    mock.patch.object(render, "prepare_clip", return_value={"vo": None, "speakers": 1, "transcript": ""}), \
                    mock.patch.object(render, "encode_variant") as enc, mock.patch.object(render, "probe", return_value={}), \
                    mock.patch.object(render, "clip_markdown", return_value=""):
                res = render.render(job, [pick], {"no_hook_share": 0}, out_dir=out, top=1)
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
                self.assertEqual((w["jump"], w["loudness"], w["speech_rate"]), (0.25, 0.6, 0.05))  # 1.5x / 0.5x caps
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
    def test_audio_extraction_fills_timestamp_gaps(self):
        # a gappy live recording decoded without this ran 98 s short, so captions came 15 s early
        from unittest import mock
        with mock.patch.object(transcribe.subprocess, "run") as run:
            transcribe.extract_audio("source.mp4", "audio.wav")
        cmd = run.call_args[0][0]
        self.assertIn("aresample=async=1:first_pts=0", cmd[cmd.index("-af") + 1])

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


    def test_unreadable_audio_is_skipped_not_fatal(self):
        import subprocess
        from unittest import mock
        from clipper import __main__ as cli
        vids = [{"id": "bad", "processed": False, "source": "c", "duration": 60, "title": "a", "channel": "x"},
                {"id": "good", "processed": False, "source": "c", "duration": 60, "title": "b", "channel": "x"}]

        def analyze(job, cfg):
            if job.name == "bad":
                raise subprocess.CalledProcessError(234, ["ffmpeg"])
            return {"candidates": [], "recommended": 1}
        with mock.patch.object(cli.library, "load_prefs", return_value={}), \
                mock.patch.object(cli.cleanup_mod, "run", return_value={"files": 0, "gb": 0}), \
                mock.patch.object(cli.sources, "watch", return_value=(vids, [], 0)), \
                mock.patch.object(cli.sources, "fetch", side_effect=lambda vid, section=None: (Path("/tmp") / vid, {})), \
                mock.patch.object(cli.analyze_mod, "analyze", side_effect=analyze):
            out = cli.daily({}, limit=2)
        self.assertEqual([j["job"] for j in out["analyzed"]], ["good"])
        self.assertEqual(out["errors"][0]["source"], "bad")
        self.assertIn("analysis failed", out["errors"][0]["error"])


    def test_failed_audio_extraction_leaves_no_partial_wav(self):
        import subprocess
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            wav = Path(d) / "audio.wav"

            def run(cmd, check):
                wav.write_bytes(b"RIFF partial")
                raise subprocess.CalledProcessError(234, cmd)
            with mock.patch.object(transcribe.subprocess, "run", side_effect=run):
                with self.assertRaises(subprocess.CalledProcessError):
                    transcribe.extract_audio(Path(d) / "source.mp4", wav)
            self.assertFalse(wav.exists())


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


class EditCheckTests(unittest.TestCase):
    def test_filler_opening_is_noted_and_a_real_word_is_not(self):
        from clipper import hooks
        pick = {"start": 10.0, "end": 20.0, "hooks": ["Why did Kai *run*?"]}
        filler = [W("so", 10.1, 10.3), W("um", 10.4, 10.6), W("Trevor", 11.0, 11.4)]
        self.assertIn("filler", hooks.check_opening(pick, hooks.clip_words(pick, filler)))
        real = [W("Trevor", 10.1, 10.5), W("so", 10.6, 10.8)]
        self.assertIsNone(hooks.check_opening(pick, hooks.clip_words(pick, real)))

    def test_hook_that_says_the_last_segments_label_is_a_spoiler(self):
        from clipper import hooks
        pick = {"segments": [{"start": 0, "end": 10}, {"start": 50, "end": 54}],
                "labels": [{"s": 11, "e": 13, "text": "*MICHAEL DEAD*"}],
                "hooks": ["Kai kills *Michael*", "Who does Kai *pick*?"]}
        notes = hooks.check_spoiler(pick)
        self.assertEqual(len(notes), 1)
        self.assertIn("michael", notes[0])

    def test_dead_air_gaps_are_noted_and_labels_fill_them(self):
        from clipper import hooks
        pick = {"start": 0.0, "end": 10.0, "hooks": ["Why did Kai *run*?"]}
        words = [W("go", 0.0, 0.5), W("now", 5.0, 5.5), W("run", 8.5, 9.9)]
        gaps = hooks.check_dead_air(pick, hooks.clip_words(pick, words))
        self.assertEqual(len(gaps), 2)
        self.assertIn("0.5-5.0s", gaps[0])
        pick["labels"] = [{"s": 0.6, "e": 4.9, "text": "*RUNS*"}]
        self.assertEqual(len(hooks.check_dead_air(pick, hooks.clip_words(pick, words))), 1)

    def test_check_picks_reports_edit_notes_without_failing(self):
        from clipper import hooks
        pick = {"start": 0.0, "end": 6.0, "hooks": ["Why did Kai *run*?"]}
        rep = hooks.check_picks([pick], {"research": "gta"}, [W("um", 0.1, 0.3), W("go", 4.0, 4.4)])
        self.assertTrue(any("filler" in n for n in rep["video 1"]["edit"]))
        self.assertTrue(any("dead air" in n for n in rep["video 1"]["edit"]))
        self.assertFalse(hooks.has_fails({"video 1": {"edit": rep["video 1"]["edit"]}}))


class CaptionCleanupTests(unittest.TestCase):
    def test_swears_are_masked_whole_words_only_and_slurs_dropped(self):
        self.assertEqual(captions.censor("fuck"), "f*ck")
        self.assertEqual(captions.censor("SHIT!"), "SH*T!")
        self.assertEqual(captions.censor("Asshole,"), "@sshole,")
        self.assertEqual(captions.censor("MOTHERFUCKER"), "MOTHERF*CKER")
        self.assertEqual(captions.censor("dumbass"), "dumb@ss")
        for ok in ("class", "Dickens", "assume", "Michael", "hello"):
            self.assertEqual(captions.censor(ok), ok)
        self.assertIsNone(captions.censor("nigga"))
        words = [W("oh", 0, 0.2), W("nigga", 0.2, 0.4), W("shit", 0.4, 0.6), dict(W("*FUCK*", 0.6, 1), label=True)]
        self.assertEqual([w["w"] for w in captions.censor_words(words)], ["oh", "sh*t", "*FUCK*"])

    def test_caption_fixes_replace_whole_words_any_case(self):
        words = [W("Swerver!", 0, 0.3), W("swerve", 0.3, 0.5), dict(W("SWERVER", 0.5, 1), label=True)]
        fixed = captions.apply_fixes(words, {"swerver": "Trevor"})
        self.assertEqual([w["w"] for w in fixed], ["Trevor!", "swerve", "SWERVER"])

    def test_render_applies_profile_then_pick_fixes_before_captions(self):
        from unittest import mock
        from clipper import render
        seen = {}
        def overlay(words, *a, **k):
            seen["words"] = [w["w"] for w in words]
            seen["censor"] = a[-1]
            return "caps"
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(render.subprocess, "run"), \
                mock.patch.object(render.captions, "write_overlay", side_effect=overlay):
            pick = {"start": 0.0, "end": 5.0, "caption_fixes": {"michel": "Mikey"}}
            words = [W("trever", 0.1, 0.4), W("michel", 0.5, 0.9)]
            render.prepare_clip(Path(d), pick, words, {"separate_voices": False, "censor_captions": False,
                                                      "caption_fixes": {"trever": "Trevor", "michel": "Michael"}},
                                Path(d))
        self.assertEqual(seen["words"], ["Trevor", "Mikey"])
        self.assertFalse(seen["censor"])


class WhisperPromptTests(unittest.TestCase):
    def test_profile_vocabulary_reaches_whisper_cli_as_prompt(self):
        from unittest import mock
        self.assertIsNone(transcribe.whisper_prompt([]))
        with tempfile.TemporaryDirectory() as d:
            prefix = Path(d) / "w"
            prefix.with_suffix(".json").write_text('{"transcription": []}', encoding="utf-8")
            with mock.patch.object(transcribe.subprocess, "run",
                                   return_value=mock.Mock(returncode=0, stderr="")) as run:
                transcribe.run_whisper("a.wav", prefix, "m.bin", "en", transcribe.whisper_prompt(["Trevor", "Lucia"]))
        cmd = run.call_args[0][0]
        self.assertEqual(cmd[cmd.index("--prompt") + 1], "Trevor, Lucia.")


class EditFxTests(unittest.TestCase):
    def test_auto_fx_zooms_shouts_at_most_every_3s_and_flashes_the_payoff(self):
        from clipper import render
        words = [W("no!", 1.0, 1.3), W("way!", 2.0, 2.3), W("RUN!", 4.5, 5.0), dict(W("*DEAD!*", 6, 7), label=True)]
        fx = render.auto_fx(words, 10.0, payoff=8.0)
        self.assertEqual([(f["t"], f["type"]) for f in fx],
                         [(1.0, "zoom"), (4.5, "zoom"), (8.0, "flash"), (8.0, "hit")])
        self.assertEqual(render.auto_fx(words[:1], 10.0), [{"t": 1.0, "type": "zoom"}])

    def test_pick_fx_are_moved_onto_the_clip_and_bad_ones_dropped(self):
        from clipper import render
        pick = {"start": 100.0, "end": 110.0, "fx": [{"t": 104, "type": "flash"}, {"t": 99, "type": "zoom"},
                                                     {"t": 105, "type": "spin"}, {"t": 106, "type": "hit"}]}
        self.assertEqual(render.clip_fx(pick, [], 10.0), [{"t": 4.0, "type": "flash"}, {"t": 6.0, "type": "hit"}])
        self.assertEqual(render.clip_fx({**pick, "fx": []}, [W("go!", 101, 102)], 10.0), [])

    def test_fx_filter_zooms_and_flashes_the_video(self):
        from clipper import render
        self.assertEqual(render.fx_filter([{"t": 3.0, "type": "hit"}], 10.0), "")
        f = render.fx_filter([{"t": 2.0, "type": "zoom"}, {"t": 5.0, "type": "flash"}], 10.0)
        self.assertIn("scale=w='trunc(1080*(1+0.12*min(1,if(between(t,2.000,2.600),1-(t-2.000)/0.6,0)))/2)*2'", f)
        self.assertIn("eval=frame,crop=1080:1920", f)
        self.assertIn("color=0x9EFF00@0.45:t=fill:enable='between(t,5.000,5.120)'", f)
        self.assertIn("color=0x9EFF00@0.2:t=fill:enable='between(t,5.120,5.250)'", f)

    def test_segment_pick_payoff_is_where_the_last_segment_starts(self):
        from unittest import mock
        from clipper import render
        pick = {"segments": [{"start": 10, "end": 16}, {"start": 50, "end": 54}], "layout": {"type": "fit"}}
        with tempfile.TemporaryDirectory() as d:
            job = Path(d)
            (job / "transcript.json").write_text('{"words": []}', encoding="utf-8")
            with mock.patch.object(render.subprocess, "run"), \
                    mock.patch.object(render, "source_size", return_value=(1920, 1080)):
                flat, _ = render.build_segment_job(pick, job, {}, job / "seg")
        self.assertEqual(flat["payoff_at"], 6.0)


class MusicTests(unittest.TestCase):
    def lib(self, d):
        from clipper import music
        folder = Path(d)
        for name in ("ok.wav", "claim.wav", "unapproved.wav", "hit.wav"):
            (folder / name).write_bytes(b"x")
        (folder / "library.yaml").write_text(
            "tracks:\n"
            "  - {id: ok, file: ok.wav, kind: music, mood: sneaky, claimable: false, approved: true}\n"
            "  - {id: claim, file: claim.wav, kind: music, mood: epic, claimable: true, approved: true}\n"
            "  - {id: unapproved, file: unapproved.wav, kind: music, mood: sad, claimable: false, approved: false}\n"
            "  - {id: missing, file: gone.wav, kind: music, mood: funny, claimable: false, approved: true}\n"
            "  - {id: hit, file: hit.wav, kind: hit, mood: any, claimable: false, approved: true}\n", encoding="utf-8")
        return music.load_library(folder)

    def test_unapproved_or_claimable_tracks_never_play(self):
        from clipper import music
        with tempfile.TemporaryDirectory() as d:
            lib = self.lib(d)
            self.assertEqual(music.choose(lib, {}, "music", "sneaky")["id"], "ok")
            self.assertIsNone(music.choose(lib, {}, "music", "epic"))
            self.assertEqual(music.choose(lib, {"music": {"allow_claimable": True}}, "music", "epic")["id"], "claim")
            self.assertIsNone(music.choose(lib, {"music": {"allow_claimable": True}}, "music", "sad"))
            self.assertIsNone(music.choose(lib, {}, "music", "funny"))

    def test_plan_fills_windows_and_hits_and_skips_moods_with_no_track(self):
        from clipper import music
        with tempfile.TemporaryDirectory() as d:
            lib = self.lib(d)
            pick = {"start": 100.0, "end": 120.0, "music": [{"s": 102, "e": 108, "mood": "sneaky"},
                                                           {"s": 110, "e": 115, "mood": "epic"},
                                                           {"s": 116, "e": 116.5, "mood": "sneaky"}]}
            layers = music.plan(pick, [], [{"t": 9.0, "type": "hit"}, {"t": 3.0, "type": "zoom"}], 20.0, {}, lib=lib)
        self.assertEqual([(t["id"], s, round(n, 3), k) for t, s, n, k in layers],
                         [("ok", 2.0, 6.0, "music"), ("hit", 9.0, 2.0, "hit")])

    def test_mix_ducks_music_under_speech_and_records_ids(self):
        from unittest import mock
        from clipper import music
        with tempfile.TemporaryDirectory() as d:
            lib = self.lib(d)
            layers = [(lib[0], 2.0, 6.0, "music"), (lib[4], 9.0, 2.0, "hit")]
            with mock.patch.object(music.subprocess, "run") as run:
                out, used = music.mix("bed.wav", [W("go", 3.0, 3.5)], layers, 20.0, "out.wav")
            self.assertEqual((out, used), ("out.wav", ["ok", "hit"]))
            cmd = run.call_args[0][0]
            graph = cmd[cmd.index("-filter_complex") + 1]
            self.assertIn("adelay=2000:all=1,volume='if(gt(between(t,2.85,3.65),0),0.1259,1)':eval=frame[m1]", graph)
            self.assertIn("afade=t=out:st=5.700:d=0.3", graph)
            self.assertIn("adelay=9000:all=1[m2]", graph)
            self.assertIn("amix=inputs=3:duration=first:normalize=0", graph)
            self.assertEqual(cmd.count("-stream_loop"), 1)
            self.assertEqual(music.mix("bed.wav", [], [], 20.0, "out.wav"), ("bed.wav", []))

    def test_shipped_library_has_only_approved_unclaimable_effects(self):
        from clipper import music
        lib = music.load_library()
        self.assertTrue(lib)
        for t in lib:
            self.assertTrue(t["path"].exists(), t["file"])
            self.assertFalse(t["claimable"])
        self.assertTrue((music.MUSIC / "LICENSE.txt").exists())

    def test_manifest_records_the_music_used(self):
        from unittest import mock
        from clipper import render
        with mock.patch.object(render, "predicted", return_value={}), \
                mock.patch.object(render, "moment_signals", return_value=None):
            m = render.upload_manifest({"start": 0, "end": 10, "hooks": ["h"]},
                                       {"channel": "c", "url": "https://youtube.com/watch?v=x", "id": "x"},
                                       {}, [{"file": "a.mp4", "hook": "h", "check": {}}], ["t"],
                                       music_used=["ok", "hit"])
        self.assertEqual(m[0]["music"], ["ok", "hit"])


class NoHookArmTests(unittest.TestCase):
    def test_arm_is_deterministic_and_about_a_third(self):
        from clipper import render
        meta = {"id": "vid", "url": "https://youtube.com/watch?v=vid", "channel": "c"}
        arms = [render.no_hook_arm({"start": s, "end": s + 20}, None, meta, 0.33) for s in range(0, 3000, 10)]
        self.assertEqual(arms, [render.no_hook_arm({"start": s, "end": s + 20}, None, meta, 0.33)
                                for s in range(0, 3000, 10)])
        self.assertAlmostEqual(sum(arms) / len(arms), 0.33, delta=0.07)
        self.assertFalse(any(render.no_hook_arm({"start": s, "end": s + 20}, None, meta, 0) for s in range(50)))

    def test_no_hook_arm_renders_one_bannerless_mp4_with_the_best_title(self):
        from unittest import mock
        import json
        from clipper import render
        pick = {"start": 0, "end": 10, "hooks": ["Why did Kai *run*?", "Kai never saw it"],
                "titles": ["Why Did Kai Run In GTA 6?", "Kai NEVER Saw It Coming In GTA 6"]}
        with tempfile.TemporaryDirectory() as d:
            job, out = Path(d) / "job", Path(d) / "out"
            job.mkdir()
            (job / "job.json").write_text(json.dumps({"channel": "Kai", "url": "u", "title": "t"}))
            (job / "transcript.json").write_text(json.dumps({"words": []}))
            with mock.patch.object(render, "no_hook_arm", return_value=True), \
                    mock.patch.object(render, "predicted", return_value={}), \
                    mock.patch.object(render, "prepare_clip", return_value={"vo": None, "speakers": 1, "transcript": "",
                                                                          "music": ["hit"]}), \
                    mock.patch.object(render, "encode_variant") as enc, mock.patch.object(render, "probe", return_value={}), \
                    mock.patch.object(render, "clip_markdown", return_value=""):
                render.render(job, [pick], {}, out_dir=out)
            self.assertEqual(enc.call_count, 1)
            self.assertEqual(enc.call_args[0][3], "")
            m = json.loads((out / "video 1" / "upload.json").read_text())
            self.assertEqual([(x["hook"], x["hook_type"], x["arm"], x["title"], x["music"]) for x in m],
                             [("", "none", "no-hook", "Why Did Kai Run In GTA 6?", ["hit"])])
            self.assertTrue((out / "video 1" / "no hook.mp4").name.endswith(".mp4"))


class SoundAndQuietTests(unittest.TestCase):
    def test_hit_sound_id_is_used_when_usable_and_falls_back_otherwise(self):
        from clipper import music
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            for name in ("boom.wav", "whoosh.wav"):
                (folder / name).write_bytes(b"x")
            (folder / "library.yaml").write_text(
                "tracks:\n"
                "  - {id: boom, file: boom.wav, kind: hit, claimable: false, approved: true}\n"
                "  - {id: whoosh, file: whoosh.wav, kind: hit, claimable: false, approved: true}\n"
                "  - {id: scratch, file: gone.wav, kind: hit, claimable: false, approved: true}\n", encoding="utf-8")
            lib = music.load_library(folder)
            for seed in ("a", "b", "c", "d"):
                self.assertEqual(music.choose(lib, {}, "hit", seed=seed, want="whoosh")["id"], "whoosh")
                self.assertIn(music.choose(lib, {}, "hit", seed=seed, want="scratch")["id"], ("boom", "whoosh"))
            layers = music.plan({"start": 0, "end": 10}, [], [{"t": 2.0, "type": "hit", "sound": "boom"}], 10.0,
                                {}, lib=lib)
            self.assertEqual(layers[0][0]["id"], "boom")

    def test_pick_hit_keeps_its_sound_id(self):
        from clipper import render
        pick = {"start": 100.0, "end": 110.0, "fx": [{"t": 102, "type": "hit", "sound": "whoosh"},
                                                     {"t": 103, "type": "flash", "sound": "boom"}]}
        self.assertEqual(render.clip_fx(pick, [], 10.0),
                         [{"t": 2.0, "type": "hit", "sound": "whoosh"}, {"t": 3.0, "type": "flash"}])

    def test_explicit_empty_fx_or_music_turns_auto_effects_off(self):
        from clipper import render
        pick = {"start": 0.0, "end": 10.0, "payoff_at": 6.0}
        words = [W("go!", 1.0, 1.4)]
        self.assertEqual([f["type"] for f in render.clip_fx(pick, words, 10.0)], ["zoom", "flash", "hit"])
        self.assertEqual(render.clip_fx({**pick, "fx": []}, words, 10.0), [])
        self.assertEqual([f["type"] for f in render.clip_fx({**pick, "music": []}, words, 10.0)], ["zoom", "flash"])

    def test_quiet_stretch_without_music_key_gets_an_edit_note(self):
        from clipper import hooks
        pick = {"start": 0.0, "end": 10.0, "hooks": ["Why did Kai *run*?"],
                "labels": [{"s": 1.2, "e": 4.8, "text": "*RUNS*"}], **TURN}
        words = [W("go", 0.0, 1.0), W("now", 5.0, 5.5), W("run", 6.0, 9.9)]
        note = hooks.check_music(pick, hooks.clip_words(pick, words))
        self.assertIn("4.0s with no speech at 1.0-5.0s", note)
        self.assertIsNone(hooks.check_music({**pick, "music": []}, words))
        self.assertIsNone(hooks.check_music(pick, [W("a", 0, 2.5), W("b", 5, 7.5), W("c", 8, 10)]))
        rep = hooks.check_picks([pick], {"research": "gta"}, words)
        self.assertTrue(any("no `music` key" in n for n in rep["video 1"]["edit"]))
        self.assertFalse(hooks.has_fails(rep))


class FlashColourTests(unittest.TestCase):
    def test_each_flash_colour_reaches_the_filter(self):
        from clipper import render
        for color, hexv in (("white", "0xFFFFFF"), ("red", "0xFF1E1E"), ("orange", "0xFF8A00"), ("lime", "0x9EFF00"),
                            ("#12ab3C", "0x12AB3C"), ("0xff0000", "0xFF0000"), ("RED", "0xFF1E1E")):
            f = render.fx_filter([{"t": 5.0, "type": "flash", "color": color}], 10.0)
            self.assertIn(f"color={hexv}@0.45:t=fill:enable='between(t,5.000,5.120)'", f)
            self.assertIn(f"color={hexv}@0.2:t=fill:enable='between(t,5.120,5.250)'", f)

    def test_flash_without_colour_stays_lime_and_the_auto_payoff_flash_is_white(self):
        from clipper import render
        self.assertIn("color=0x9EFF00@0.45", render.fx_filter([{"t": 5.0, "type": "flash"}], 10.0))
        auto = render.clip_fx({"start": 0.0, "end": 10.0, "payoff_at": 6.0}, [], 10.0)
        self.assertEqual(auto, [{"t": 6.0, "type": "flash", "color": "0xFFFFFF"}, {"t": 6.0, "type": "hit"}])
        self.assertIn("color=0xFFFFFF@0.45", render.fx_filter(auto, 10.0))
        pick = {"start": 100.0, "end": 110.0, "fx": [{"t": 104, "type": "flash"}, {"t": 105, "type": "flash",
                                                                                   "color": "red"}]}
        self.assertEqual(render.clip_fx(pick, [], 10.0),
                         [{"t": 4.0, "type": "flash"}, {"t": 5.0, "type": "flash", "color": "0xFF1E1E"}])

    def test_invalid_flash_colour_is_rejected(self):
        from clipper import hooks, render
        for bad in ("purple", "#FFF", "red;drawbox", ""):
            with self.assertRaises(ValueError) as e:
                render.flash_colour(bad)
            self.assertIn("flash color", str(e.exception))
        pick = {"start": 0.0, "end": 10.0, "hooks": ["Why did Kai *run*?"],
                "fx": [{"t": 5.0, "type": "flash", "color": "purple"}]}
        with self.assertRaises(ValueError):
            render.clip_fx(pick, [], 10.0)
        rep = hooks.check_picks([pick], {"research": "gta"})
        self.assertIn("purple", rep["video 1"]["fx"][0])
        self.assertTrue(hooks.has_fails(rep))


class ShippedMusicTests(unittest.TestCase):
    def test_every_mood_gets_a_shipped_cc0_track_and_a_missing_one_skips(self):
        from clipper import music
        lib = music.load_library()
        credits = (music.MUSIC / "CREDITS.md").read_text(encoding="utf-8")
        for mood in music.MOODS:
            t = music.choose(lib, {}, "music", mood, seed="x")
            self.assertIsNotNone(t, mood)
            self.assertEqual(t["mood"], mood)
            self.assertIn(t["file"], credits)
        pick = {"start": 0.0, "end": 20.0, "music": [{"s": 2, "e": 8, "mood": "sad"}, {"s": 10, "e": 15, "mood": "epic"}]}
        only_sad = [t for t in lib if t.get("mood") != "epic"]
        layers = music.plan(pick, [], [], 20.0, {}, lib=only_sad)
        self.assertEqual([(t["mood"], s, k) for t, s, _, k in layers], [("sad", 2.0, "music")])


class DebateRuleTest(unittest.TestCase):
    def test_debate_note_and_rage_bait(self):
        from clipper import hooks
        self.assertTrue(hooks.is_debate("Is xQc's aim *legit*?!"))
        self.assertTrue(hooks.is_debate("Was Kai wrong for this?"))
        self.assertFalse(hooks.is_debate("Why is Kai shaking?"))
        self.assertTrue(hooks.is_debate("Does Jason look like *Arthur Morgan*?"))
        plain = {"hooks": ["Why is Kai shaking?", "THE *EASIEST* MISSION"],
                 "titles": ["Why Is Kai Shaking At GTA 6?", "Kai Was NOT Ready For GTA 6"], **TURN}
        self.assertIn("debate", hooks.check_picks([plain])["video 1"])
        judged = {**plain, "hooks": ["Is xQc's aim *legit*?!", "THE *EASIEST* MISSION"]}
        self.assertNotIn("debate", hooks.check_picks([judged]).get("video 1", {}))
        self.assertFalse(hooks.has_fails(hooks.check_picks([plain])))
        self.assertTrue(hooks.check_hook("GTA 6 maps are *overrated*?")[1])


class YouTubeBotFixTest(unittest.TestCase):
    def test_fetch_asks_for_mweb_client(self):
        from unittest import mock
        from clipper import sources
        from clipper.config import YT_ARGS
        with tempfile.TemporaryDirectory() as d, mock.patch.object(sources, "JOBS", Path(d)), \
                mock.patch.object(sources.subprocess, "run", side_effect=RuntimeError("stop")) as run:
            with self.assertRaises(RuntimeError):
                sources.fetch("5tVN1_XnVDI")
        cmd = run.call_args[0][0]
        self.assertEqual(cmd[1:3], YT_ARGS)
        self.assertIn("mweb", YT_ARGS[1])

    def test_setup_plans_pot_provider_when_missing(self):
        from unittest import mock
        from clipper import setup
        with tempfile.TemporaryDirectory() as d, mock.patch.object(setup, "POT_HOME", Path(d) / "pot"), \
                mock.patch.object(setup, "POT_ZIP", Path(d) / "p.zip"), \
                mock.patch.object(setup, "_has_module", lambda m: m == "yt_dlp"), \
                mock.patch.object(setup.shutil, "which", return_value="/bin/node"):
            checks, plan, _ = setup.youtube_fix()
        self.assertFalse(any(ok for _, ok in checks))
        flat = [" ".join(c) for c in plan]
        self.assertTrue(any(setup.POT_ZIP_URL in c for c in flat))
        self.assertTrue(any("--branch " + setup.POT_VERSION in c for c in flat))
        self.assertTrue(any(setup.EJS in c for c in flat))


class CodeVersionTest(unittest.TestCase):
    def test_code_version_is_commit_and_date(self):
        import re
        from clipper.config import code_version
        self.assertRegex(code_version(), r"^([0-9a-f]{7,} \d{4}-\d{2}-\d{2}( modified)?|unknown)$")

    def test_setup_reports_code_version(self):
        from unittest import mock
        from clipper import setup
        with mock.patch("clipper.config.code_version", return_value="abc1234 2026-11-14"), \
                mock.patch.object(setup, "missing", return_value=([], [], False, False)), \
                mock.patch.object(setup, "youtube_fix", return_value=([], [], [])), \
                mock.patch.object(setup, "install_commands", return_value=[]):
            self.assertIn("clipper code: abc1234 2026-11-14", setup.run())


class StakeRuleTest(unittest.TestCase):
    def test_stakes_from_our_top_and_bottom_shorts(self):
        from clipper import hooks
        for h in ["Kai Cenat was NOT ready for *Trevor*", "Kai did NOT expect him to be *13*",
                  "Wait for Kai's *$500K* painting...", "Did CaseOh catch a GTA 6 *cheater*?!",
                  "Ray won't forgive xQc's *betrayal*"]:
            self.assertTrue(hooks.has_stake(h), h)
        for h in ["What's on xQc's *USB*?", "When someone hands you a *marlin*", "How did xQc's crew take the *betrayal*?",
                  "CaseOh couldn't tell this was *GTA 6*", "When someone hands you a *marlin*", "Why is xQc sniffing it?"]:
            self.assertFalse(hooks.has_stake(h), h)
        notes = hooks.check_hook("What's on xQc's *USB*?")[1]
        self.assertTrue(any("concrete stake" in n for n in notes))
        self.assertEqual(hooks.check_hook("What's on xQc's *USB*?")[0], [])


class SetupSudoTest(unittest.TestCase):
    def test_apt_step_needing_a_password_is_listed_not_run(self):
        from unittest import mock
        from clipper import setup
        with mock.patch.object(setup, "IS_MAC", False), mock.patch.object(setup.sys, "prefix", "/venv"), \
                mock.patch.object(setup.os, "geteuid", return_value=1000), \
                mock.patch.object(setup.subprocess, "run", return_value=mock.Mock(returncode=1)):
            plan, lines = setup.linux_plan(["ffmpeg"], [], False)
        self.assertFalse(any(c[:2] == ["sudo", "apt-get"] for c in plan))
        self.assertTrue(any("sudo apt-get install -y ffmpeg" in l for l in lines))

    def test_parakeet_setup_doesnt_need_build_tools(self):
        from unittest import mock
        from clipper import setup
        with mock.patch.object(setup, "IS_MAC", False), mock.patch.object(setup, "uses_whisper", return_value=False), \
                mock.patch.object(setup.shutil, "which", return_value=None):
            tools = setup.missing()[0]
        self.assertNotIn("cmake", tools)
        self.assertNotIn("c++", tools)
        self.assertIn("ffmpeg", tools)

    def test_parakeet_setup_report_doesnt_list_build_tools(self):
        from unittest import mock
        from clipper import setup
        with mock.patch.object(setup, "IS_MAC", False), mock.patch.object(setup, "uses_whisper", return_value=False), \
                mock.patch.object(setup, "missing", return_value=([], [], False, False)), \
                mock.patch.object(setup, "linux_plan", return_value=([], [])), \
                mock.patch.object(setup, "youtube_fix", return_value=([], [], [])), \
                mock.patch.object(setup, "install_commands", return_value=[]):
            out = setup.run()
        self.assertNotIn("cmake", out)
        self.assertIn("ffmpeg", out)


class BiggerFaceBigHookOpeningTest(unittest.TestCase):
    def test_opening_check_measures_the_split_frame_not_the_dark_desktop(self):
        import subprocess
        from clipper import hooks
        with tempfile.TemporaryDirectory() as d:
            job = Path(d)
            subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i",
                            "color=c=0x101010:s=640x360:d=3", "-f", "lavfi", "-i", "testsrc2=s=180x160:d=3",
                            "-f", "lavfi", "-i", "testsrc2=s=134x108:d=3", "-filter_complex",
                            "[0][1]overlay=230:100[a];[a][2]overlay=0:0", "-pix_fmt", "yuv420p",
                            str(job / "source.mp4")], check=True)
            split = {"type": "split", "face": [0, 0, 0.21, 0.3], "game_zoom": 2.2}
            fit = hooks.check_opening_frames({"start": 0, "end": 2}, job)
            framed = hooks.check_opening_frames({"start": 0, "end": 2, "layout": split}, job)
        self.assertIn("opens dark", fit["fails"][0])
        self.assertNotIn("fails", framed)

    def test_split_gives_face_half_the_frame_and_zooms_gameplay(self):
        from clipper import render
        vf = render.video_filter({"type": "split", "face": [0, 0, 0.2, 0.3]}, (1920, 1080))
        self.assertIn("crop=1080:960[top]", vf)
        self.assertIn("scale=-2:1056,crop=1080:960", vf)  # 960 * 1.1 zoom (1.3 cropped signs out)

    def test_big_hook_fits_two_lines_on_the_seam(self):
        import numpy as np
        from PIL import Image
        from clipper import captions
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "h.png"
            captions.render_hook("Ray won't forgive *xQc*", p, "big", "split")
            short = np.array(Image.open(p))[:, :, 3]
            captions.render_hook("CaseOh won't believe this is *controller*", p, "big", "split")
            long_ = np.array(Image.open(p))[:, :, 3]
        rows = np.where(short.max(axis=1) > 0)[0]
        self.assertLess(rows.max(), captions.SPLIT_TOP)  # never over the gameplay
        self.assertGreater(rows.min(), captions.SPLIT_TOP - 320)  # the facecam's lower third (chest/desk), not the face
        self.assertLess(rows.max() - rows.min(), 2 * 72 * 1.2 + 60)  # a short hook: 2 lines
        self.assertGreater(np.ptp(np.where(long_.max(axis=1) > 0)[0]), 2 * 56 * 1.2)  # a long one keeps its 3rd line

    def test_split_hook_and_captions_leave_the_game_clear(self):
        # regression: the old hook hung into the game and captions sat mid-game, covering 22-28% of it
        import numpy as np
        from PIL import Image
        from clipper import captions
        with tempfile.TemporaryDirectory() as d:
            hp, cp = Path(d) / "h.png", Path(d) / "c.png"
            for style, cstyle in (("big", "boxed"), ("box", "comic"), ("bold", "bold")):
                captions.render_hook("CaseOh won't believe this GTA 6 aim is on *controller*", hp, style, "split")
                captions.render_state(((0, ("WAIT", "WHAT"), 1),), cp, captions.LAYOUTS["split"]["caption_y"], False,
                                      cstyle)
                ink = np.maximum(np.array(Image.open(hp))[:, :, 3], np.array(Image.open(cp))[:, :, 3])
                self.assertLess((ink[captions.SPLIT_TOP:] > 0).mean(), 0.06, style)

    def test_opening_check_fails_dark_and_notes_static(self):
        import subprocess
        from clipper import hooks
        with tempfile.TemporaryDirectory() as d:
            job = Path(d)
            for name, src in (("dark", "color=c=0x101010:s=320x180:d=3"), ("busy", "testsrc2=s=320x180:d=3")):
                (job / name).mkdir()
                subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", src, "-pix_fmt",
                                "yuv420p", str(job / name / "source.mp4")], check=True)
            dark = hooks.check_opening_frames({"start": 0, "end": 2}, job / "dark")
            busy = hooks.check_opening_frames({"start": 0, "end": 2}, job / "busy")
        self.assertIn("opens dark", dark["fails"][0])
        self.assertIn("opens static", dark["notes"][0])
        self.assertEqual(busy, {})
        self.assertTrue(hooks.has_fails({"video 1": {"opening": dark}}))
        self.assertFalse(hooks.has_fails({"video 1": {"opening": {"notes": ["x"]}}}))


class ContextCaptionsAndFacecamTest(unittest.TestCase):
    def test_no_opening_context_caption_is_a_note_not_a_fail(self):
        from clipper import hooks
        pick = {"start": 100, "end": 120, "labels": [{"s": 110, "e": 111, "text": "*in disbelief*"}]}
        self.assertEqual(hooks.check_labels(pick), [])
        self.assertIn("first 3 s", hooks.check_context_note(pick))
        self.assertIn("first 3 s", hooks.check_picks([{"start": 100, "end": 120}])["video 1"]["context_note"])
        self.assertFalse(hooks.has_fails({"video 1": {"context_note": hooks.check_context_note(pick)}}))
        opens = {**pick, "labels": [{"s": 101, "e": 102.5, "text": "*Tyreek Hill mocks them*"}]}  # 4 words is fine
        self.assertEqual(hooks.check_labels(opens), [])
        self.assertIsNone(hooks.check_context_note(opens))
        self.assertIsNone(hooks.check_context_note({"hooks": ["Why is Kai shaking?"]}))  # no clip timing yet

    def test_fit_clip_fails_when_the_channel_has_a_facecam(self):
        import json
        from clipper import hooks
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for job, channel, layout in (("old", "xQc", {"type": "split", "face": [0, 0, 0.3, 0.28]}),
                                         ("new", "xQc", {"type": "fit"}), ("comp", "RP Central", {"type": "fit"})):
                (root / job).mkdir()
                (root / job / "job.json").write_text(json.dumps({"channel": channel}))
                (root / job / "picks.json").write_text(json.dumps([{"start": 0, "end": 20, "layout": layout}]))
            cams = hooks.known_facecams(root)
            self.assertEqual(cams, {"xQc": ("old", [0, 0, 0.3, 0.28])})
            fit = {"start": 0, "end": 20, "layout": {"type": "fit"}}
            fails = hooks.check_facecam(fit, root / "new", cams)
            self.assertIn("xQc's streams have a facecam", fails[0])
            self.assertTrue(hooks.has_fails({"video 1": {"facecam": fails}}))
            hidden = {**fit, "layout": {"type": "fit", "facecam": "hidden"}}
            self.assertEqual(hooks.check_facecam(hidden, root / "new", cams), [])
            split = {**fit, "layout": {"type": "split", "face": [0, 0, 0.3, 0.28]}}
            self.assertEqual(hooks.check_facecam(split, root / "new", cams), [])
            self.assertEqual(hooks.check_facecam(fit, root / "comp", cams), [])  # no cam known for that channel
            seen = hooks.known_facecams(root, [(root / "comp", [split])])  # the picks being checked count too
            self.assertIn("RP Central", seen)


class FavorCreatorsTest(unittest.TestCase):
    def test_daily_clips_favored_creators_first(self):
        from clipper import __main__ as cli
        from clipper import config
        found = [{"id": "a", "channel": "xQc", "source": "creator:xQc"},
                 {"id": "b", "channel": "Some Search Hit", "source": "search:gta rp"},
                 {"id": "c", "channel": "Kai Cenat Live", "source": "creator:Kai Cenat"}]
        cfg = {"favor_creators": ["Kai Cenat"]}
        self.assertEqual([v["id"] for v in cli.favored_first(found, cfg)], ["c", "a", "b"])
        self.assertEqual([v["id"] for v in cli.favored_first(found, {})], ["a", "c", "b"])
        self.assertFalse(cli.is_favored("Kai Cenat Live", {"favor_creators": [""]}))
        self.assertEqual(config.load(profile="gta-rp")["favor_creators"], ["Kai Cenat"])
        self.assertEqual(config.load(profile="gta6")["favor_creators"], ["Kai Cenat", "IShowSpeed", "CaseOh"])


class RequireFacecamTest(unittest.TestCase):
    def test_profile_can_require_the_face_in_every_clip(self):
        from clipper import config, hooks
        hidden = {"start": 0, "end": 20, "layout": {"type": "fit", "facecam": "hidden"}}
        split = {"start": 0, "end": 20, "layout": {"type": "split", "face": [0, 0, 0.3, 0.28]}}
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(hooks.check_facecam(hidden, Path(d), {}), [])  # allowed by default
            self.assertIn("no face on screen", hooks.check_facecam(hidden, Path(d), {}, require=True)[0])
            self.assertEqual(hooks.check_facecam(split, Path(d), {}, require=True), [])
            mixed = {"segments": [{"start": 0, "end": 5, "layout": split["layout"]}, {"start": 9, "end": 14}],
                     "layout": {"type": "fit"}}
            self.assertEqual(len(hooks.check_facecam(mixed, Path(d), {}, require=True)), 1)
        self.assertTrue(config.load(profile="gta-rp").get("require_facecam"))
        self.assertFalse(config.load(profile="gta6").get("require_facecam"))


class NarrationTest(unittest.TestCase):
    def test_captions_follow_the_narrator_then_the_streamer(self):
        from clipper import render
        narr = [{"w": "Did", "s": 0.1, "e": 0.3}, {"w": "you", "s": 0.3, "e": 0.5}, {"w": "know?", "s": 0.5, "e": 0.9}]
        speech = [{"w": "fishy", "s": 0.4, "e": 0.8, "spk": 0}, {"w": "ranger", "s": 5.0, "e": 5.4, "spk": 0}]
        self.assertEqual([w["w"] for w in render.merge_narration(narr, speech, 4.0)], ["Did", "you", "know?", "ranger"])

    def test_narration_must_fit_and_leave_the_payoff(self):
        from clipper import hooks
        base = {"start": 0, "end": 30, "narrate": True}
        self.assertIn("needs a voiceover", hooks.check_narration(base)[0])
        self.assertIn("runs about", hooks.check_narration({**base, "voiceover": "word " * 90})[0])  # ~35 s
        self.assertIn("payoff line", hooks.check_narration({**base, "voiceover": "word " * 72})[0])  # ~28 s
        self.assertEqual(hooks.check_narration({**base, "voiceover": "word " * 60}), [])               # ~23 s
        self.assertEqual(hooks.check_narration({"start": 0, "end": 30, "voiceover": "x " * 90}), [])  # not narrated
        self.assertTrue(hooks.has_fails({"video 1": {"narration": ["x"]}}))


class AlignScriptTest(unittest.TestCase):
    def test_script_words_keep_their_spelling_with_heard_timings(self):
        from clipper import render
        heard = [{"w": "Did", "s": 0.0, "e": 0.2}, {"w": "a", "s": 0.3, "e": 0.4}, {"w": "no", "s": 0.5, "e": 0.7},
                 {"w": "pixel", "s": 0.7, "e": 1.0}, {"w": "cop", "s": 1.1, "e": 1.4}, {"w": "XQC", "s": 1.5, "e": 2.0}]
        out = render.align_script("Did a NoPixel cop xQc", heard)
        self.assertEqual([w["w"] for w in out], ["Did", "a", "NoPixel", "cop", "xQc"])
        self.assertEqual((out[3]["s"], out[3]["e"]), (1.1, 1.4))       # matched word keeps its time
        self.assertTrue(0.4 <= out[2]["s"] < out[2]["e"] <= 1.1)       # unmatched one fits between its neighbours
        self.assertTrue(out[4]["s"] >= out[3]["e"])
        self.assertEqual(render.align_script("", heard), heard)


class TitleTemplateTests(unittest.TestCase):
    def test_series_tag_suffix_and_missing_end_emoji_are_noted(self):
        from clipper import hooks
        notes = hooks.check_title("Kai Cenat Did NOT Expect Him To Be 13 💀 | GTA RP", topic=None)[1]
        self.assertTrue(any("series tag" in n for n in notes))
        self.assertEqual(hooks.check_title("Kai Cenat Did NOT Expect Him To Be 13 💀 | GTA RP", topic=None)[0], [])
        self.assertTrue(any("no emoji at the end" in n for n in hooks.check_title("Kai Cenat Met Ice Spice In GTA 6", topic=None)[1]))
        clean = hooks.check_title("Kai Cenat Met Ice Spice In GTA 6 😭😭", topic=None)[1]
        self.assertFalse([n for n in clean if "series tag" in n or "emoji at the end" in n])
        self.assertFalse([n for n in hooks.check_title("Kai Cenat Met Ice Spice In GTA 6 ❤️", topic=None)[1] if "emoji" in n])
        self.assertEqual(hooks.check_title("Me At My First Sneaker Drop", topic=None, narrate=False)[1], [])


class SelectionAndAngleTests(unittest.TestCase):
    def test_selection_gate_needs_premise_type_and_four_of_five(self):
        from clipper import hooks
        base = {"hooks": ["Kai Cenat fails the *easiest* mission"], **TURN}
        self.assertNotIn("selection", hooks.check_picks([base]).get("video 1", {}))
        weak = {**base, "selection": {"standalone": True, "unexpected": True, "payoff": True}}
        self.assertIn("3/5", hooks.check_picks([weak])["video 1"]["selection"][0])
        self.assertTrue(hooks.has_fails(hooks.check_picks([weak])))
        untyped = {k: v for k, v in base.items() if k != "premise_type"}
        self.assertIn("premise_type", hooks.check_picks([untyped])["video 1"]["selection"][0])
        self.assertNotIn("selection", hooks.check_picks([untyped], {"research": "cod"}).get("video 1", {}))
        self.assertEqual(hooks.check_selection({"campaign": "brand"}), [])

    def test_streamers_profile_opts_into_the_selection_gate(self):
        from clipper import hooks
        cfg = streamers_cfg()
        weak = {"hooks": ["SPEED BUYS A $2,000 JACKET"], "start": 0, "end": 18, "turn": "money spent",
                "cold_premise": "Speed buys a jacket", "loop": "does he buy it?", "payoff_at": 9.0,
                "selection": {"standalone": True, "payoff": True}}
        rep = hooks.check_picks([weak], cfg)["video 1"]
        self.assertIn("premise_type", rep["selection"][0])
        self.assertIn("2/5", rep["selection"][1])
        self.assertTrue(hooks.has_fails({"video 1": rep}))
        self.assertNotIn("angles", rep)  # the GTA hook-angle A/B stays GTA-only
        self.assertNotIn("selection", hooks.check_picks([weak], {**cfg, "selection_gate": False}).get("video 1", {}))
        self.assertIn("Marty", hooks.check_picks([{**weak, "hooks": ["Why won't Speed hear *Marty* out?"]}], cfg)["video 1"]["cold"][0])

    def test_streamer_not_reacting_is_a_note_in_every_profile(self):
        from clipper import hooks
        quiet = {"hooks": ["THE *CUTSCENE*"], "start": 0, "end": 18, "streamer_reacts": False, **TURN}
        for cfg in (None, {"research": "cod"}):
            rep = hooks.check_picks([quiet], cfg)["video 1"]
            self.assertIn("cutscenes", rep["reacts"])
        self.assertFalse(hooks.has_fails({"video 1": {"reacts": rep["reacts"]}}))
        for ok in ({**quiet, "streamer_reacts": True}, {k: v for k, v in quiet.items() if k != "streamer_reacts"},
                   {**quiet, "campaign": "brand"}):
            self.assertNotIn("reacts", hooks.check_picks([ok]).get("video 1", {}))

    def test_situation_label_passes_but_topic_label_still_fails(self):
        from clipper import hooks
        self.assertEqual(hooks.check_hook("THE EASIEST MISSION")[0], [])
        self.assertEqual(hooks.check_hook("DRIVING IN SCUBA GEAR")[0], [])
        self.assertTrue(hooks.check_hook("GTA 6 GRAPHICS")[0])

    def test_reaction_only_titles_get_a_note(self):
        from clipper import hooks
        self.assertTrue(any("announces the reaction" in n
                            for n in hooks.check_title("Kai Cenat Was NOT Ready For This Mission 😭", topic=None)[1]))
        self.assertFalse(any("announces the reaction" in n
                             for n in hooks.check_title("Kai Cenat Was NOT Ready For Trevor In GTA 5 😭", topic=None)[1]))

    def test_hook_angles_and_coverage(self):
        from clipper import hooks
        self.assertEqual(hooks.hook_angle("THE EASIEST MISSION"), "label")
        self.assertEqual(hooks.hook_angle("ONE GUN COSTS $590?!"), "detail")
        self.assertEqual(hooks.hook_angle("Kai did NOT expect this"), "reaction")
        self.assertIsNone(hooks.hook_angle(""))
        three = {"hooks": ["THE EASIEST MISSION", "ONE GUN COSTS $590?!", "HE'S ONLY 13?!"], **TURN}
        self.assertNotIn("angles", hooks.check_picks([three]).get("video 1", {}))
        one_kind = {**three, "hooks": ["ONE GUN COSTS $590?!", "HE'S ONLY 13?!", "Why is he *13*?"]}
        self.assertIn("label", hooks.check_picks([one_kind])["video 1"]["angles"]["fails"][0])
        self.assertTrue(hooks.has_fails(hooks.check_picks([one_kind])))
        self.assertIn("notes", hooks.check_picks([{**one_kind, "hooks": one_kind["hooks"][:2]}])["video 1"]["angles"])

    def test_render_leads_with_the_assigned_angle_and_records_it(self):
        from clipper import render
        full = {"hooks": ["HE'S ONLY 13?!", "ONE GUN COSTS $590?!", "THE EASIEST MISSION"],
                "titles": ["T detail2", "T detail", "T label"]}
        cut = {**full, "hooks": full["hooks"][:2], "titles": full["titles"][:2]}
        led = render.lead_with_angle(full, cut, "label")
        self.assertEqual(led["hooks"], ["THE EASIEST MISSION", "HE'S ONLY 13?!"])
        self.assertEqual(led["titles"], ["T label", "T detail2"])
        self.assertEqual(render.lead_with_angle(full, cut, "nonexistent"), cut)
        meta = {"url": "https://youtu.be/x", "id": "x"}
        arms = {render.angle_arm({"start": float(s), "end": float(s) + 20}, None, meta) for s in range(0, 600, 7)}
        self.assertEqual(arms, {"label", "detail"})
        a = render.angle_arm({"start": 12.0, "end": 30.0}, None, meta)
        self.assertEqual(a, render.angle_arm({"start": 12.0, "end": 30.0}, None, meta))


class SetupFirstPlaybookTests(unittest.TestCase):
    def test_reaction_playbook_leads_with_setup_hooks(self):
        from clipper import hooks, playbook
        play = playbook.PLAYBOOK["reaction"]
        self.assertEqual(play["hooks"][:2], ["superlative", "shock fact"])
        self.assertNotIn("reaction", [hooks.hook_angle(x) for x in play["examples"]])

    def test_no_playbook_example_uses_a_banned_opener(self):
        from clipper import hooks, playbook
        for table in (playbook.PLAYBOOK, playbook.GENERIC):
            for kind, play in table.items():
                for ex in play.get("examples", []):
                    self.assertFalse(hooks.banned_hook(ex), f"{kind}: {ex}")

    def test_any_reaction_hook_fails_the_angle_check(self):
        from clipper import hooks
        pick = {"hooks": ["THE *EASIEST* MISSION", "Nobody warned Kai about this", "ONE GUN COSTS $590?!"], **TURN}
        fails = hooks.check_picks([pick])["video 1"]["angles"]["fails"]
        self.assertIn("Nobody warned Kai about this", fails[0])
        clean = {**pick, "hooks": ["THE *EASIEST* MISSION", "ONE GUN COSTS $590?!"]}
        self.assertNotIn("angles", hooks.check_picks([clean]).get("video 1", {}))


class BannedHookTests(unittest.TestCase):
    BANNED = ["Nobody expected that *one word*", "The clerk was NOT ready for the *AR*",
              "Nobody warned Kai the bag had a *limit*", "Kai did NOT expect *Vale* to flip",
              "Kai didn't expect his *Uber* to leave", "xQc could NOT believe *those genetics*",
              "When you can't pay for the *ride*", "Me when she says *just say it*", "POV: the plug brings his *friend*",
              "xQc wasn't taking the *stairs* down", "Kai never saw this guy *coming*",
              "GTA 6 Ubers are NOT *what xQc expected*", "xQc would NOT leave without *a hat*"]
    OK = ["THE FINAL *BRIDGE* SHOOTOUT", "STEALING HIS OWN *UBER*", "ONE GUN COSTS $590?!", "Kids CAN'T play *GTA 6*",
          "Why couldn't he finish the game?", "HE'S ONLY *13*?!", "NO RUNNING IN THE *HALLWAY*",
          "Why isn't Kai's *perfect run* enough?"]

    def test_old_style_hooks_fail_check_and_setup_labels_pass(self):
        from clipper import hooks
        for h in self.BANNED:
            self.assertTrue(hooks.banned_hook(h), h)
            self.assertIn(hooks.BANNED_NOTE, hooks.check_hook(h)[0], h)
            self.assertEqual(hooks.hook_angle(h), "reaction", h)
        for h in self.OK:
            self.assertFalse(hooks.banned_hook(h), h)
            self.assertNotIn(hooks.BANNED_NOTE, hooks.check_hook(h)[0], h)
        report = hooks.check_picks([{"hooks": ["Nobody expected that *one word*"], **TURN}])
        self.assertTrue(hooks.has_fails(report))

    def test_render_drops_banned_hooks_with_their_titles(self):
        from clipper import render
        hs, ts = render.drop_banned_hooks(["Nobody saw the *chopper* coming", "THE *HELIPAD* ESCAPE"], ["T1", "T2"])
        self.assertEqual((hs, ts), (["THE *HELIPAD* ESCAPE"], ["T2"]))
        self.assertEqual(render.drop_banned_hooks(["POV: you're the *pool boy*"], ["T1", "T2"]), ([""], ["T1"]))
        self.assertEqual(render.drop_banned_hooks(["THE *HELIPAD* ESCAPE"], ["T"]), (["THE *HELIPAD* ESCAPE"], ["T"]))


class HookEmojiTests(unittest.TestCase):
    def test_emoji_in_hook_is_noted_and_dropped_by_the_renderer(self):
        from clipper import hooks
        self.assertTrue(any("emoji" in n for n in hooks.check_hook("THE *EASIEST* MISSION 💀")[1]))
        self.assertEqual(hooks.check_hook("THE *EASIEST* MISSION 💀")[0], [])
        self.assertEqual(hooks.check_hook("THE *EASIEST* MISSION")[0], [])
        self.assertEqual(hooks.check_title("Kai Cenat Fails The Easiest Mission In GTA 6 💀")[0], [])  # titles keep emoji

    def test_render_hook_drops_emoji_instead_of_drawing_boxes(self):
        import tempfile
        from pathlib import Path
        from PIL import Image
        from clipper import captions
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a.png", Path(d) / "b.png"
            captions.render_hook("THE *EASIEST* MISSION 💀", a, "big", "split")
            captions.render_hook("THE *EASIEST* MISSION", b, "big", "split")
            self.assertEqual(Image.open(a).tobytes(), Image.open(b).tobytes())


class RequeueTests(unittest.TestCase):
    """Unposted exports get keep / recut / hold; posted ones are skipped; a dry run writes nothing."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        from clipper import render
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.jobs, self.exports, self.stats = root / "jobs", root / "exports", root / "own-stats.json"
        base = {"turn": "money spent", "cold_premise": "Speed buys a jacket", "loop": "does he buy it?",
                "hooks": ["SPEED BUYS A *$2,000* JACKET"], "titles": ["Speed Paid $2,000 For A Jacket 😭"]}
        self.picks = {
            "keep": {**base, "start": 100, "end": 118, "payoff_at": 114},
            "tail": {**base, "start": 200, "end": 235, "payoff_at": 212,
                     "labels": [{"s": 201, "e": 202, "text": "*AT THE STORE*"}, {"s": 230, "e": 231, "text": "*LATER*"}]},
            "late": {**base, "start": 300, "end": 330, "payoff_at": 326},
            "nopay": {**base, "start": 400, "end": 420},
            "posted": {**base, "start": 500, "end": 515, "payoff_at": 510, "titles": ["Posted One"]},
            "ytid": {**base, "start": 600, "end": 640, "payoff_at": 610},
            "quiet": {**base, "start": 700, "end": 740, "payoff_at": 710, "streamer_reacts": False},
            "story": {**base, "segments": [{"start": 800, "end": 815}, {"start": 900, "end": 920}], "payoff_at": 22},
        }
        words = [{"w": "so", "s": 310.6, "e": 310.9}, {"w": "yo", "s": 214.5, "e": 215.4}]
        self.job = self._job("J1", self.picks, words)
        gone = self._job("J2", {"gone": {**base, "start": 10, "end": 30, "payoff_at": 20}}, [], source=False)
        n = 0
        for name, pick in [*self.picks.items(), ("gone", None)]:
            n += 1
            job, pick = (gone, {**base, "start": 10, "end": 30, "payoff_at": 20}) if name == "gone" else (self.job, pick)
            folder = self.exports / "streamers" / "2026-11-20" / f"video {n}"
            folder.mkdir(parents=True)
            entry = {"title": (pick.get("titles") or ["x"])[0] + (f" {name}" if name != "posted" else ""),
                     "footage": render.footage(pick, job, render.load_meta(job)), "payoff_at": pick.get("payoff_at")}
            if name == "ytid":
                entry["youtube_id"] = "abc"
            (folder / "upload.json").write_text(json.dumps([entry]))
        legacy = self.exports / "streamers" / "2026-11-20" / f"video {n + 1}"
        legacy.mkdir()
        (legacy / "upload.json").write_text(json.dumps([{"title": "Old render"}]))
        self.stats.write_text(json.dumps({"uploads": [{"id": "x", "t": "Posted One"}]}))

    def tearDown(self):
        self.tmp.cleanup()

    def _job(self, jid, picks, words, source=True):
        job = self.jobs / jid
        job.mkdir(parents=True)
        (job / "job.json").write_text(json.dumps({"id": jid, "url": f"https://www.youtube.com/watch?v={jid}",
                                                  "channel": "IShowSpeed"}))
        (job / "picks.json").write_text(json.dumps(list(picks.values())))
        (job / "transcript.json").write_text(json.dumps({"words": words}))
        if source:
            (job / "source.mp4").write_bytes(b"")
        return job

    def _rows(self):
        from clipper import requeue
        rows = requeue.verdicts({"profile": "streamers"}, self.exports, self.jobs, self.stats)
        return {r["folder"].split("/")[-1]: r for r in rows}

    def _files(self):
        return sorted(str(p.relative_to(self.tmp.name)) for p in __import__("pathlib").Path(self.tmp.name).rglob("*"))

    def test_verdicts(self):
        before = self._files()
        rows = self._rows()
        self.assertEqual(self._files(), before)  # a dry run writes nothing
        v = {k: r["verdict"] for k, r in rows.items()}
        self.assertEqual(v, {"video 1": "keep", "video 2": "recut", "video 3": "recut", "video 4": "hold",
                             "video 7": "hold", "video 8": "recut", "video 9": "hold", "video 10": "hold"})
        self.assertIn("payoff", rows["video 4"]["reasons"][0])
        self.assertIn("isn't talking", rows["video 7"]["reasons"][0])
        self.assertIn("source deleted (J2)", rows["video 9"]["reasons"][0])
        self.assertIn("no footage recorded", rows["video 10"]["reasons"][0])
        tail, late, story = rows["video 2"]["pick"], rows["video 3"]["pick"], rows["video 8"]["pick"]
        self.assertEqual((tail["start"], tail["end"]), (200, 215.4))  # payoff + 3 s, out to the end of the word
        self.assertEqual([x["text"] for x in tail["labels"]], ["*AT THE STORE*"])  # labels past the new end go
        self.assertEqual((late["start"], late["end"]), (310.6, 330))  # starts on a word, payoff ~16 s in
        self.assertEqual(story["segments"], [{"start": 806.0, "end": 815.0}, {"start": 900.0, "end": 910.0}])
        self.assertEqual(story["payoff_at"], 16.0)
        self.assertEqual(tail["requeued_from"], "streamers/2026-11-20/video 2")

    def test_apply_renders_into_new_folders_and_keeps_originals(self):
        from clipper import requeue
        rows = requeue.verdicts({"profile": "streamers"}, self.exports, self.jobs, self.stats)
        originals = {p: p.read_bytes() for p in self.exports.rglob("upload.json")}
        calls = []

        def fake_render(job, picks, cfg, top=0):
            calls.append((job.name, picks))
            out = self.exports / "streamers" / "2026-11-23"
            return [{"folder": str(out / f"video {i}")} for i in range(1, len(picks) + 1)]
        done = requeue.apply({"profile": "streamers"}, rows, self.exports, self.jobs, fake_render)
        self.assertEqual([c[0] for c in calls], ["J1"])
        self.assertEqual(len(json.loads((self.jobs / "J1" / "picks-requeue.json").read_text())), 3)
        self.assertEqual(done[0], {"from": "streamers/2026-11-20/video 2", "to": "streamers/2026-11-23/video 1"})
        self.assertEqual({p: p.read_bytes() for p in originals}, originals)  # nothing overwritten
        marker = json.loads((self.exports / "streamers/2026-11-20/video 2/superseded.json").read_text())
        self.assertEqual(marker["recut"], "streamers/2026-11-23/video 1")
        self.assertNotIn("video 2", self._rows())  # a recut original isn't re-checked
        requeue.apply({"profile": "streamers"}, [{**rows[1], "folder": "streamers/2026-11-20/video 1"}],
                      self.exports, self.jobs, fake_render)
        self.assertTrue((self.jobs / "J1" / "picks-requeue-2.json").exists())  # never overwrites picks-requeue.json


class OutlierQuestionTests(unittest.TestCase):
    """research/outlier-questions-2026-11.md: `event` premise type and the recorded `question` type."""

    def test_event_premise_and_question_pass_in_gta6_and_streamers(self):
        from clipper import config, hooks
        gta = config.load(profile="gta6")
        config.load()
        gta_pick = {"hooks": ["Lucia *joins a cult* in GTA 6"], "start": 0, "end": 18, **TURN,
                    "premise_type": "event", "question": "event"}
        irl_pick = {"hooks": ["SPEED WINS *STREAMER OF THE YEAR*"], "start": 0, "end": 18, **TURN,
                    "premise_type": "event", "question": "recognition", "description": "IShowSpeed at the awards"}
        for cfg, pick in ((gta, gta_pick), (streamers_cfg(), irl_pick)):
            rep = hooks.check_picks([pick], cfg).get("video 1", {})
            self.assertNotIn("selection", rep)
            self.assertNotIn("question", rep)

    def test_question_must_be_a_known_type_and_is_noted_when_missing(self):
        from clipper import hooks
        base = {"hooks": ["Kai Cenat fails the *easiest* mission"], "start": 0, "end": 18, **TURN}
        bad = hooks.check_picks([{**base, "question": "what happens"}], streamers_cfg())["video 1"]
        self.assertIn("must be one of", bad["question"]["fails"][0])
        self.assertTrue(hooks.has_fails({"video 1": bad}))
        missing = hooks.check_picks([base], streamers_cfg())["video 1"]["question"]
        self.assertEqual(missing["fails"], [])
        self.assertFalse(hooks.has_fails({"video 1": {"question": missing}}))
        self.assertEqual(hooks.check_question({"campaign": "brand"}), ([], []))

    def test_upload_manifest_records_shape_premise_and_question(self):
        from unittest import mock
        from clipper import render
        meta = {"id": "x1", "url": "https://www.youtube.com/watch?v=x1", "channel": "Speed"}
        pick = {"start": 5, "end": 25, "hooks": ["SPEED WINS *STREAMER OF THE YEAR*"], "premise_type": "event",
                "question": "event"}
        variants = [{"file": "a.mp4", "hook": pick["hooks"][0], "check": {"duration": 20}}]
        with mock.patch.object(render, "predicted", return_value={}):
            out = render.upload_manifest(pick, meta, {}, variants, ["T"])[0]
        self.assertEqual((out["kind"], out["premise_type"], out["question"]), ("short", "event", "event"))
