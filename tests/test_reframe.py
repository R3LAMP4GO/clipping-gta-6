import json
import math
import statistics as st
import unittest

from clipper import hooks
from clipper.config import ROOT


class LoopFrameTests(unittest.TestCase):
    def test_frames(self):
        f = hooks.loop_frame
        self.assertEqual(f("What Happens If Arthur Drinks 99 Hair Tonics? 🤯 #rdr2"), "hypothetical")
        self.assertEqual(f("He Took A Hostage And Only Asked For Two Bags Of Chips 😭"), "setup, ending withheld")
        self.assertEqual(f("Kai Cenat Wanted To Prank IShowSpeed 😂"), "setup, ending withheld")
        self.assertEqual(f("Did you know GTA 6 has this?"), "did you know")
        self.assertEqual(f("Why is xQc's *photo* on this wall?"), "question")
        self.assertEqual(f("xQc Steals A Corvette In GTA 6"), "closed")

    def test_did_you_know_gets_a_note(self):
        self.assertTrue(any("0.71x" in n for n in hooks.check_hook("Did you know Kai found *this*?", True)[1]))
        self.assertTrue(any("0.71x" in n for n in hooks.check_title("Did You Know This About GTA 6?", ["#gta6"])[1]))


class CheckLoopTests(unittest.TestCase):
    def test_loop_and_payoff_are_required_and_must_close_on_screen(self):
        pick = {"start": 100.0, "end": 130.0, "turn": "ransom", "cold_premise": "A robber's only ransom demand is chips",
                "hooks": ["His only ransom demand: *two bags of chips*"], "titles": ["He Asked For Two Bags Of Chips 😭"]}
        self.assertTrue(hooks.has_fails(hooks.check_picks([pick])))
        self.assertEqual(len(hooks.check_loop(pick)[0]), 2)
        outside = {**pick, "loop": "will they pay it?", "payoff_at": 140}
        self.assertIn("outside the clip", hooks.check_loop(outside)[0][0])
        early = {**outside, "payoff_at": 106}
        self.assertEqual(hooks.check_loop(early)[0], [])
        self.assertIn("closes 6s into a 30s clip", hooks.check_loop(early)[1][0])
        self.assertFalse(hooks.has_fails({"video 1": {"loop": {"fails": [], "notes": ["x"]}}}))
        good = {**outside, "end": 113, "payoff_at": 110}
        self.assertEqual(hooks.check_loop(good), ([], []))

    def test_late_payoff_and_long_tail_get_notes(self):
        base = {"start": 100.0, "loop": "will they pay it?"}
        late = hooks.check_loop({**base, "end": 130.0, "payoff_at": 126})
        self.assertEqual(late[0], [])
        self.assertIn("payoff lands 26s in", late[1][0])
        tail = hooks.check_loop({**base, "end": 120.0, "payoff_at": 111})
        self.assertEqual(len(tail[1]), 1)
        self.assertIn("9s past the payoff", tail[1][0])

    def test_segment_pick_payoff_uses_clip_seconds(self):
        pick = {"segments": [{"start": 10, "end": 20}, {"start": 50, "end": 60}], "loop": "x", "payoff_at": 18}
        self.assertEqual(hooks.check_loop(pick), ([], []))
        self.assertTrue(hooks.check_loop({**pick, "payoff_at": 55})[0])  # source seconds are outside a 20 s clip


class OpenLoopDataTests(unittest.TestCase):
    def test_stored_titles_reproduce_the_frame_effects(self):
        rows = json.loads((ROOT / "research" / "open-loop-titles.json").read_text(encoding="utf-8"))

        def effect(group, frame):
            vals = [(hooks.loop_frame(r["t"]), math.log10(r["lift"])) for r in rows if r["set"] == group and r["lift"] > 0]
            base = st.mean(v for _, v in vals)
            on = [v for f, v in vals if f == frame]
            return 10 ** (st.mean(on) - base), len(on)
        hyp, n = effect("story-game", "hypothetical")
        self.assertGreater(n, 300)
        self.assertGreater(hyp, 1.05)
        self.assertLess(effect("story-game", "did you know")[0], 0.85)
        self.assertGreater(effect("streamer-clips", "setup, ending withheld")[0], 1.0)


if __name__ == "__main__":
    unittest.main()


class TitleLoopNoteTests(unittest.TestCase):
    def test_closed_and_mood_titles_get_a_note_open_loops_dont(self):
        note = lambda t: hooks.check_title(t, ["#gta6"])[1]
        self.assertTrue(any("hides the streamer" in n for n in note("Me At My First GTA 6 Sneaker Drop 😂")))
        self.assertTrue(any("hides the streamer" in n for n in note("POV: GTA 6 Gives You Chores 😂")))
        self.assertTrue(any("no open loop" in n for n in note("Kai Cenat Was NOT Having This GTA 6 Take 😭")))
        for t in ("Kai Cenat Tried To Steal A Car Off A Moving Truck In GTA 6 😱",
                  "What Happens If You Rob The First Guy You See In GTA 6?"):
            self.assertFalse([n for n in note(t) if "open loop" in n or "hides the streamer" in n], t)
        self.assertEqual(hooks.check_title("Me At My First Sneaker Drop 😂", topic=None, narrate=False)[1], [])


class HookLoopNoteTests(unittest.TestCase):
    def test_plain_hook_without_a_loop_gets_a_note_structured_hooks_dont(self):
        loop = lambda h, gta=True: [n for n in hooks.check_hook(h, gta)[1] if "no open loop" in n]
        self.assertTrue(loop("Kai Cenat steals a *Corvette* in traffic"))
        self.assertEqual(hooks.check_hook("Kai Cenat steals a *Corvette* in traffic")[0], [])  # a note, not a fail
        for h in ("Ron tried to surprise Lacy with a *PS5 Pro*", "Nobody expected xQc's hostages to *SING*",
                  "Kai pays $500K for a *painting*", "Why are the hostages *singing*?"):
            self.assertFalse(loop(h), h)
        self.assertFalse(loop("Kai Cenat steals a *Corvette* in traffic", gta=False))


class ColdHookTests(unittest.TestCase):
    def test_roleplay_names_and_crew_lore_get_a_note(self):
        base = {"start": 0, "end": 20, "turn": "betrayal", "cold_premise": "A streamer leaves the gang he ran with"}
        cold = lambda **k: hooks.check_cold({**base, **k})
        self.assertIn("Mickey", cold(hooks=["Why did xQc really leave *Mickey's* crew?"])[0])
        self.assertTrue(any("lore" in n for n in cold(hooks=["How did xQc's crew take the *betrayal*?"])))
        self.assertTrue(cold(hooks=["Why won't xQc hear *Marty* out?"], titles=["Why Won't xQc Hear Marty Out?!"]))
        for h in ("Kai Cenat was NOT ready for *Trevor*", "How did Jason end up in a *tree*?",
                  "xQc did NOT care about his 2 *stars*", "Kai did NOT expect him to be *13*",
                  "Nobody Told xQc How J-Turns Work In GTA 6 😭"):
            self.assertEqual(cold(hooks=[h]), [], h)
        self.assertEqual(hooks.check_cold({**base, "hooks": ["Hear *Marty* out?"], "campaign": "x"}), [])

    def test_unknown_name_in_premise_flags_the_title_that_repeats_it(self):
        pick = {"cold_premise": "xQc's feud ends when Mickey makes one call", "hooks": ["One call ended the *feud*"],
                "titles": ["How Did Mickey End xQc's Feud In One Call?! | GTA RP"]}
        self.assertIn("Mickey", hooks.check_cold(pick)[0])
        self.assertIn("cold", hooks.check_picks([pick])["video 1"])
        self.assertEqual(hooks.check_cold({"hooks": ["Quit the PD for *1.6K* an hour?"],
                                           "titles": ["Would You Quit The PD For 1.6K An Hour?!"]}), [])
        self.assertEqual(hooks.check_cold({"hooks": ["What's on xQc's *USB*?"]}), [])
        for h in ("Kai DIDN'T expect the *NPCs* to talk back", "Me after totaling the car: *I'm alive!*",
                  "When you walk past a gator in *Florida*", "How do you date a Latina with NO *Spanish*?"):
            self.assertEqual(hooks.check_cold({"hooks": [h]}), [], h)
        self.assertIn("Mangrove", hooks.check_cold({"hooks": ["Nobody warned xQc about *Mr. Mangrove*"]})[0])


class MoodTitleFailTests(unittest.TestCase):
    def test_me_title_fails_on_a_streamer_clip_only(self):
        pick = {"hooks": ["Me when they call my statue *fake*"],
                "titles": ["Me When They Call My Rich Uncle's Statue Fake In GTA 6 😂"],
                "description": "Kai Cenat playing GTA 6 live: a dealer calls the statue fake.", "hashtags": ["#gta6"]}
        t = hooks.check_picks([pick])["video 1"]["titles"][pick["titles"][0]]
        self.assertIn(hooks.MOOD_NOTE, t["fails"])
        self.assertNotIn(hooks.MOOD_NOTE, t.get("notes", []))
        skit = {**pick, "description": "A GTA 6 skit about a fake statue."}
        t = hooks.check_picks([skit])["video 1"]["titles"][pick["titles"][0]]
        self.assertEqual(t["fails"], [])
        self.assertIn(hooks.MOOD_NOTE, t["notes"])
        self.assertTrue(hooks.streamer_clip({"source": "https://www.twitch.tv/kaicenat"}))
