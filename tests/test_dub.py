import unittest

from clipper import dub

PICK = {"hooks": ["Me opening the *GTA 6* trailer", "Kai was NOT ready for *this*"],
        "titles": ["When you finally open the GTA 6 trailer"], "description": "Kai Cenat opens the GTA 6 trailer."}
UPLOAD = [{"hook": "Why does Kai's *YouTube* look ugly?", "title": "Why Does Kai Cenat's YouTube Look Like This?",
           "description": "Upload-only english desc\n\nClip from Kai Cenat Live: https://x\n\n#gta6"}]


def good():
    return {"lang": "es", "lines": ["Tráiler oficial.", "Dios mío."],
            "hooks": ["Yo abriendo el tráiler de *GTA 6*", "Kai NO estaba listo para *esto*", "¿Por qué YouTube se ve feo?"],
            "titles": ["Cuando por fin abres el tráiler de GTA 6"], "description": "Kai Cenat abre el tráiler de GTA 6."}


class MsgpackTests(unittest.TestCase):
    def test_bytes_match_the_spec(self):
        m = dub.msgpack
        self.assertEqual(m(None), b"\xc0")
        self.assertEqual((m(True), m(False)), (b"\xc3", b"\xc2"))
        self.assertEqual((m(5), m(-1), m(200), m(-100), m(70000)), (b"\x05", b"\xff", b"\xcc\xc8", b"\xd0\x9c",
                                                                   b"\xce\x00\x01\x11\x70"))
        self.assertEqual(m(1.5), b"\xcb\x3f\xf8\x00\x00\x00\x00\x00\x00")
        self.assertEqual(m("a"), b"\xa1a")
        self.assertEqual(m("x" * 40), b"\xd9\x28" + b"x" * 40)
        self.assertEqual(m("ñ"), b"\xa2\xc3\xb1")
        self.assertEqual(m(b"\x01\x02"), b"\xc4\x02\x01\x02")
        self.assertEqual(m(b"\x00" * 300)[:3], b"\xc5\x01\x2c")
        self.assertEqual(m([1, "a"]), b"\x92\x01\xa1a")
        self.assertEqual(m({"a": 1}), b"\x81\xa1a\x01")
        self.assertEqual(m(list(range(16)))[:3], b"\xdc\x00\x10")


class TimingTests(unittest.TestCase):
    def test_fit_speeds_up_within_the_clamp(self):
        self.assertEqual(dub.fit(1.0, 2.0, 3.0), (1.0, 1.0))  # short lines are never slowed down
        speed, length = dub.fit(2.4, 2.0, 3.0)
        self.assertAlmostEqual(speed, 1.2)
        self.assertAlmostEqual(length, 2.0)

    def test_fit_spills_into_the_gap_but_never_over_the_next_line(self):
        speed, length = dub.fit(3.0, 2.0, 3.0)
        self.assertEqual(speed, dub.MAX_SPEED)
        self.assertAlmostEqual(length, 3.0 / dub.MAX_SPEED)  # 2.22 s: past its window, inside the gap
        speed, length = dub.fit(6.0, 2.0, 2.5)
        self.assertEqual((speed, length), (dub.MAX_SPEED, 2.5))

    def test_caption_words_cover_each_line(self):
        words = dub.caption_words(["Dios mío.", "¿Puede alguien explicarme?"], [(1.0, 1.2), (3.0, 2.0)])
        self.assertEqual([w["w"] for w in words], ["Dios", "mío.", "¿Puede", "alguien", "explicarme?"])
        self.assertEqual((words[0]["s"], words[1]["e"]), (1.0, 2.2))
        self.assertEqual((words[2]["s"], words[-1]["e"]), (3.0, 5.0))
        for a, b in zip(words, words[1:]):
            self.assertLessEqual(a["e"], b["s"] + 1e-9)
        self.assertGreater(words[4]["e"] - words[4]["s"], words[3]["e"] - words[3]["s"])  # longer word, longer


class ValidateTests(unittest.TestCase):
    def check(self, tr, lang="es", n=2):
        return dub.validate_translation(tr, lang, PICK, UPLOAD, n)

    def test_valid_file_passes(self):
        self.assertEqual(self.check(good()), [])

    def test_lang_missing_or_mismatched(self):
        self.assertIn("--lang is required", self.check(good(), lang=None)[0])
        self.assertTrue(any("--lang is 'hi'" in e for e in self.check(good(), lang="hi")))
        tr = good()
        del tr["lang"]
        self.assertTrue(any("translation lang" in e for e in self.check(tr)))

    def test_needs_three_hooks_titles_and_description(self):
        tr = dict(good(), hooks=good()["hooks"][:2])
        self.assertTrue(any("at least 3 hooks" in e for e in self.check(tr)))
        tr = dict(good(), hooks=good()["hooks"][:2] + ["  "])
        self.assertTrue(any("at least 3 hooks" in e for e in self.check(tr)))
        tr = good()
        del tr["titles"]
        self.assertTrue(any("titles" in e for e in self.check(tr)))
        self.assertTrue(any("description" in e for e in self.check(dict(good(), description=" "))))

    def test_line_count_must_match_segments(self):
        self.assertTrue(any("need 3 lines" in e for e in self.check(good(), n=3)))

    def test_rejects_text_copied_from_the_english_pick(self):
        tr = dict(good(), hooks=good()["hooks"][:2] + ["kai was not ready for THIS"])
        self.assertTrue(any("hook is still the English" in e for e in self.check(tr)))
        tr = dict(good(), titles=["When you finally open the GTA 6 trailer"])
        self.assertTrue(any("title is still the English" in e for e in self.check(tr)))
        tr = dict(good(), description="Kai Cenat opens the  GTA 6 trailer.")
        self.assertTrue(any("description is still the English" in e for e in self.check(tr)))

    def test_rejects_text_copied_from_upload_json(self):
        tr = dict(good(), hooks=good()["hooks"][:2] + ["Why does Kai's YouTube look ugly?"])
        self.assertTrue(any("hook is still the English" in e for e in self.check(tr)))
        tr = dict(good(), titles=["Why Does Kai Cenat's YouTube Look Like This?"])
        self.assertTrue(any("title is still the English" in e for e in self.check(tr)))
        tr = dict(good(), description="Upload-only English desc")
        self.assertTrue(any("description is still the English" in e for e in self.check(tr)))

    def test_lang_lands_in_every_manifest_entry(self):
        entries = [{"hook": "a", "description": "D\n\nClip from Kai Cenat Live: https://x\n\n#gta6"},
                   {"hook": "b", "description": "D\n\nClip from Kai Cenat Live: https://x\n\n#gta6"}]
        out, old, new = dub.finish_manifest(entries, "es", "Kai Cenat Live", "Clip de", dub.DISCLOSURE["es"])
        self.assertEqual([e["lang"] for e in out], ["es", "es"])
        self.assertTrue(all(e["description"].endswith(dub.DISCLOSURE["es"]) for e in out))
        self.assertIn("Clip de Kai Cenat Live:", new)
        self.assertEqual(old, entries[0]["description"])



def group(words):  # one line per sentence end, like transcribe.group_sentences
    out, cur = [], []
    for w in words:
        cur.append(w)
        if w["w"].endswith((".", "?", "!")):
            out.append({"s": cur[0]["s"], "e": cur[-1]["e"], "text": " ".join(x["w"] for x in cur)})
            cur = []
    if cur:
        out.append({"s": cur[0]["s"], "e": cur[-1]["e"], "text": " ".join(x["w"] for x in cur)})
    return out


def w(text, s, e):
    return {"w": text, "s": s, "e": e}


class SpeakerTests(unittest.TestCase):
    def test_lines_split_where_the_diarized_speaker_changes(self):
        words = [w("We", 0, .5), w("rob", .5, 1), w("Oh", 1.1, 1.4), w("God.", 1.4, 1.8), w("Now", 2, 2.4), w("sing.", 2.4, 3)]
        dwords = [{"s": 0, "e": 1, "spk": 0}, {"s": 1.1, "e": 1.8, "spk": 1}, {"s": 2, "e": 3, "spk": 0}]
        segs = dub.label_lines(words, dwords, lambda a, b: None, group)
        self.assertEqual([(g["text"], g["spk"]) for g in segs], [("We rob", 0), ("Oh God.", 1), ("Now sing.", 0)])

    def test_a_high_voice_never_stays_with_a_low_speaker(self):
        words = [w("Fix.", 0, 2), w("How?", 2.1, 2.6), w("Sing.", 3, 6), w("Good.", 7, 9)]
        dwords = [{"s": 0, "e": 6, "spk": 0}, {"s": 7, "e": 9, "spk": 1}]
        hz = {0: 120, 2.1: 267, 3: 110, 7: 210}
        segs = dub.label_lines(words, dwords, lambda a, b: hz[a], group)
        self.assertEqual([g["spk"] for g in segs], [0, 1, 0, 1])  # "How?" joins the high-voiced speaker

    def test_without_diarization_pitch_alone_splits_voices(self):
        words = [w("Fix.", 0, 2), w("How?", 2.1, 2.6), w("Sing.", 3, 6)]
        segs = dub.label_lines(words, [], lambda a, b: {0: 120, 2.1: 260, 3: 165}[a], group)
        self.assertEqual([g["spk"] for g in segs], [0, 1, 0])  # 165 Hz is unclear: it keeps its speaker

    def test_one_word_flips_are_smoothed_and_cut_sentences_rejoined(self):
        words = [w("Oh,", 0, .3), w("the", .3, .5), w("guy", .5, .8), w("on", .8, .9), w("left.", .9, 1.3),
                 w("We", 2, 2.2), w("need", 2.2, 2.5), w("two", 2.5, 2.8), w("more.", 2.8, 3.2)]
        dwords = [{"s": 0, "e": .8, "spk": 0}, {"s": .8, "e": .9, "spk": 1}, {"s": .9, "e": 1.3, "spk": 0},
                  {"s": 2, "e": 2.8, "spk": 1}, {"s": 2.8, "e": 3.2, "spk": 0}]
        hz = {0: 120, 2: 210, 2.8: 205}
        segs = dub.label_lines(words, dwords, lambda a, b: hz.get(a, 210), group)
        self.assertEqual([(g["text"], g["spk"]) for g in segs], [("Oh, the guy on left.", 0), ("We need two more.", 1)])

    def test_reference_uses_only_that_speakers_whole_lines(self):
        segs = [{"s": 0, "e": 10, "spk": 0, "text": "a"}, {"s": 10, "e": 12, "spk": 1, "text": "b"},
                {"s": 12, "e": 34, "spk": 0, "text": "c"}, {"s": 34, "e": 40, "spk": 0, "text": "d"}]
        spans, text, total = dub.speaker_spans(segs, 0)
        self.assertEqual((spans, text, total), ([(0, 10), (34, 40)], "a d", 16))  # "c" would pass 30 s
        self.assertEqual(dub.speaker_spans(segs, 1)[:2], ([(10, 12)], "b"))

    def test_speakers_override_must_match_the_lines(self):
        errs = dub.validate_translation(dict(good(), speakers=[0]), "es", PICK, UPLOAD, 2)
        self.assertTrue(any("speakers must list" in e for e in errs))
        self.assertEqual(dub.validate_translation(dict(good(), speakers=[0, 1]), "es", PICK, UPLOAD, 2), [])

    def test_caption_words_keep_the_speaker(self):
        words = dub.caption_words(["Uno.", "Dos tres."], [(0, 1), (1, 1)], [0, 1])
        self.assertEqual([x["spk"] for x in words], [0, 1, 1])

if __name__ == "__main__":
    unittest.main()


class EmotionTests(unittest.TestCase):
    def test_cues_are_voiced_but_never_captioned(self):
        words = dub.caption_words(["[screaming][hysterical] НЕЕЕТ! Вы ВСЁ пропустили?"], [(1.0, 2.0)])
        self.assertEqual([w["w"] for w in words], ["НЕЕЕТ!", "Вы", "ВСЁ", "пропустили?"])
        self.assertEqual((words[0]["s"], words[-1]["e"]), (1.0, 3.0))
        self.assertEqual(dub.spoken("[shocked]  Что? [break] Нет"), "Что? Нет")

    def test_a_line_of_only_cues_is_rejected(self):
        tr = {"lang": "ru", "lines": ["[screaming]"], "hooks": ["а", "б", "в"], "titles": ["т"], "description": "д"}
        self.assertTrue(any("spoken text" in e for e in dub.validate_translation(tr, "ru", {}, [], 1)))

    def test_loudness_marks_the_shouted_line(self):
        import numpy as np
        sr = 16000
        t = np.arange(sr) / sr
        audio = np.concatenate([0.05 * np.sin(2 * np.pi * 200 * t), 0.5 * np.sin(2 * np.pi * 200 * t)]).astype(np.float32)
        calm, shout = dub.loudness_db(audio, sr, 0, 1), dub.loudness_db(audio, sr, 1, 2)
        self.assertAlmostEqual(shout - calm, 20, delta=0.5)
        self.assertEqual((dub.energy(shout, calm), dub.energy(calm, shout), dub.energy(calm, calm + 2)),
                         ("loud", "quiet", None))


class GainTests(unittest.TestCase):
    def test_dub_lines_take_the_original_loudness_within_bounds(self):
        self.assertEqual(dub.match_gain(-14.0, -9.0), 5.0)      # a scream comes back up
        self.assertEqual(dub.match_gain(-14.0, -29.0), -15.0)   # a whisper goes back down
        self.assertEqual(dub.match_gain(-14.0, -50.0), -15.0)   # clamped: never buried
        self.assertEqual(dub.match_gain(-30.0, -5.0), 10.0)     # clamped: never blown out
        self.assertEqual(dub.match_gain(-14.0, None), 0.0)      # an old cache without loudness: unchanged
