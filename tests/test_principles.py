import unittest

from clipper import profile100k as p
from clipper import viral


def split_fixture():
    """Two channels; past-tense titles are high 3 of 4 times in each, question titles 1 time in 7."""
    vids = []
    for ch in ("A", "B"):
        vids += [{"id": f"{ch}h{i}", "ch": ch, "group": "high", "t": "Kai Cenat Pranked His Mom 😭", "views": 2e5,
                  "lift": 6, "dur": 20 + i} for i in range(30)]
        vids += [{"id": f"{ch}l{i}", "ch": ch, "group": "low", "t": "Kai Cenat Pranked His Mom 😭", "views": 2e4,
                  "lift": 0.5, "dur": 30 + i} for i in range(10)]
        vids += [{"id": f"{ch}q{i}", "ch": ch, "group": "low", "t": "Is Kai Cenat Wrong For This?", "views": 2e4,
                  "lift": 0.5, "dur": 30 + i} for i in range(30)]
        vids += [{"id": f"{ch}k{i}", "ch": ch, "group": "high", "t": "Is Kai Cenat Wrong For This?", "views": 2e5,
                  "lift": 6, "dur": 25} for i in range(5)]
    return {"rule": {}, "videos": vids}


class ProfileBuildTests(unittest.TestCase):
    def test_build_is_reproducible_and_finds_the_planted_trait(self):
        a = p.build(split_fixture(), reps=200)
        b = p.build(split_fixture(), reps=200)
        a.pop("built"), b.pop("built")
        self.assertEqual(a, b)
        past = a["traits"]["past_tense"]
        self.assertEqual(past["verdict"], p.CLEAR)
        self.assertGreater(past["lift"], 1)
        self.assertEqual(a["traits"]["duration_s"]["n_high"], 70)
        self.assertLess(a["traits"]["duration_s"]["lift"], 1)

    def test_measured_and_label_fields_become_traits(self):
        s = split_fixture()
        measures = {v["id"]: {"layout": "split" if v["group"] == "high" else "game", "cuts_per_min": 10}
                    for v in s["videos"]}
        prof = p.build(s, measures=measures, reps=100)
        self.assertIn("m_layout=split", prof["traits"])
        self.assertEqual(prof["traits"]["m_layout=split"]["source"], "video")
        self.assertEqual(prof["traits"]["m_cuts_per_min"]["verdict"], p.NONE)

    def test_verdicts(self):
        self.assertEqual(p.verdict(1.3, [1.1, 1.5], 40), p.CLEAR)
        self.assertEqual(p.verdict(1.3, [1.1, 1.5], 10), p.LEAN)
        self.assertEqual(p.verdict(1.3, [0.9, 1.6], 40), p.LEAN)
        self.assertEqual(p.verdict(1.05, [0.9, 1.2], 400), p.NONE)


class SampleTests(unittest.TestCase):
    def test_sample_is_channel_matched_and_prefers_cached(self):
        rows = [{"id": f"{c}{g}{i}", "ch": c, "group": g} for c in "XYZ" for g in ("high", "low") for i in range(5)]
        rows.append({"id": "long", "ch": "X", "group": "high", "dur": 600})
        out = viral.sample_pairs(rows, per_side=4, cached=lambda vid: vid == "Xhigh3")
        self.assertEqual(sum(r["group"] == "high" for r in out), 4)
        self.assertEqual(sum(r["group"] == "low" for r in out), 4)
        self.assertEqual(out[0]["id"], "Xhigh3")
        self.assertNotIn("long", [r["id"] for r in out])
        by = {}
        for r in out:
            by.setdefault(r["ch"], []).append(r["group"])
        self.assertTrue(all(g.count("high") == g.count("low") for g in by.values()))

    def test_flash_dead_space_and_text_kind(self):
        self.assertEqual(viral.flash_count([50, 50, 120, 50, 50, 50, 130, 135, 140, 140]), 1)
        words = [{"w": "a", "s": 1.0, "e": 1.5}, {"w": "b", "s": 3.0, "e": 3.5}]
        self.assertEqual(viral.dead_space(words, 6.0), 1.0 + 1.5 + 2.5)
        self.assertEqual(viral.text_kind("Is Kai cheating here?"), "question")
        self.assertEqual(viral.text_kind("THE EASIEST MISSION"), "label")
        self.assertEqual(viral.text_kind(""), "none")

    def test_layout(self):
        face = lambda a, y: {"faces": [{"area": a, "y": y}], "text": []}  # noqa: E731
        self.assertEqual(viral.layout_of([face(0.04, 0.2)] * 4), "split")
        self.assertEqual(viral.layout_of([face(0.3, 0.5)] * 4), "full")
        self.assertEqual(viral.layout_of([{"faces": [], "text": []}] * 4), "game")


if __name__ == "__main__":
    unittest.main()


class DemandTests(unittest.TestCase):
    def test_demand_build_rates_streamers_inside_channels(self):
        from clipper import demand
        vids = []
        for ch in ("A", "B"):
            vids += [{"ch": ch, "group": "high", "t": "CaseOh Ate 40 Burgers 😭"} for _ in range(20)]
            vids += [{"ch": ch, "group": "low", "t": "CaseOh Ate A Burger"} for _ in range(5)]
            vids += [{"ch": ch, "group": "low", "t": "Lacy Lost His Car 😭"} for _ in range(20)]
            vids += [{"ch": ch, "group": "high", "t": "Lacy Won A Race"} for _ in range(5)]
        d = demand.build({"videos": vids}, reps=100)
        self.assertGreater(d["streamers"]["CaseOh"]["lift"], 1)
        self.assertLess(d["streamers"]["Lacy"]["lift"], 1)
        self.assertEqual(d["streamers"]["CaseOh"]["titles"], 50)
        self.assertEqual(list(d["streamers"])[0], "CaseOh")
        self.assertIn("CaseOh 80% 100K+", demand.line_for("CaseOh in GTA 6", d))
        self.assertEqual(demand.score_for("caseoh live", d), d["streamers"]["CaseOh"]["lift"])
        self.assertIsNone(demand.line_for("nobody here", d))


def fixture_profile():
    return {"traits": {
        "label_payoff_at_s": {"trait": "label_payoff_at_s", "kind": "number", "verdict": "clear", "lift": 0.7,
                             "high": {"p25": 6, "median": 10, "p75": 14}, "low": {"p25": 10, "median": 16, "p75": 22}},
        "m_length_s": {"trait": "m_length_s", "kind": "number", "verdict": "lean", "lift": 0.85,
                       "high": {"p25": 14, "median": 20, "p75": 28}, "low": {"p25": 20, "median": 30, "p75": 40}},
        "m_captions": {"trait": "m_captions", "kind": "binary", "verdict": "clear", "lift": 1.4, "high_share": 0.9,
                       "low_share": 0.7},
        "past_tense": {"trait": "past_tense", "kind": "binary", "verdict": "clear", "lift": 1.1, "high_share": 0.45,
                       "low_share": 0.4},
    }}


class ProfileCheckTests(unittest.TestCase):
    pick = {"start": 100, "end": 140, "payoff_at": 130, "hooks": ["THE EASIEST MISSION"]}

    def test_clear_trait_fails_and_lean_trait_notes(self):
        got = p.check_pick(self.pick, fixture_profile(), "on")
        self.assertEqual(len(got["fails"]), 1)
        self.assertIn("time to payoff", got["fails"][0])
        self.assertEqual(len(got["notes"]), 1)
        self.assertIn("length", got["notes"][0])
        self.assertEqual(got["match"], [1, 2])  # captions met, payoff missed; title traits aren't checked here
        self.assertEqual(p.profile_match(got), 0.5)

    def test_shadow_turns_fails_into_notes_and_off_skips(self):
        got = p.check_pick(self.pick, fixture_profile(), "shadow")
        self.assertEqual(got["fails"], [])
        self.assertEqual(len(got["notes"]), 2)
        self.assertIsNone(p.check_pick(self.pick, fixture_profile(), "off"))

    def test_length_only_notes_even_when_clear(self):
        prof = fixture_profile()
        prof["traits"]["m_length_s"] = {"trait": "m_length_s", "kind": "number", "verdict": "clear", "lift": 1.09,
                                        "high": {"p25": 18.3, "median": 23.5, "p75": 41.4},
                                        "low": {"p25": 15, "median": 22.7, "p75": 35}}
        short = {"start": 100, "end": 114, "payoff_at": 108, "hooks": ["THE EASIEST MISSION"]}  # 14 s, payoff fits
        got = p.check_pick(short, prof, "on")
        self.assertEqual(got["fails"], [])
        self.assertEqual(len(got["notes"]), 1)
        self.assertIn("length", got["notes"][0])
        self.assertEqual(got["match"], [2, 2])  # length isn't counted toward the match

    def test_fitting_pick_passes(self):
        ok = dict(self.pick, end=120, payoff_at=110)
        got = p.check_pick(ok, fixture_profile(), "on")
        self.assertEqual(got["fails"] + got["notes"], [])
        self.assertEqual(got["match"], [2, 2])

    def test_check_picks_reports_profile_and_has_fails(self):
        from unittest import mock
        from clipper import hooks
        with mock.patch.object(p, "load_profile", return_value=fixture_profile()):
            on = hooks.check_picks([self.pick], {"principles": "on", "research": "other"})
            shadow = hooks.check_picks([self.pick], {"principles": "shadow", "research": "other"})
            off = hooks.check_picks([self.pick], {"research": "other"})
        self.assertTrue(on["video 1"]["profile"]["fails"])
        self.assertTrue(hooks.has_fails({"video 1": {"profile": on["video 1"]["profile"]}}))
        self.assertNotIn("fails", shadow["video 1"]["profile"])
        self.assertNotIn("profile", off.get("video 1", {}))


GOOD_REVIEW = {"moment": {c: 8 for c in ("standalone", "surprise", "payoff", "stakes", "emotion", "demand")},
               "packaging": {c: 7 for c in ("hook", "opening", "pacing", "ending", "title", "visual")}}


def new_pick(**kw):
    base = {"start": 10, "end": 30, "payoff_at": 25, "loop": "will he pay?", "turn": "a fan hands him a watch",
            "cold_premise": "a fan gives Kai a watch", "category": "reward", "cause": "a fan hands Kai a $5,000 watch",
            "why_care": "a stranger gives away a $5,000 watch on stream",
            "hooks": ["A FAN'S $5,000 GIFT", "WHO GIVES A STRANGER THIS?", "THE GOLD ROLEX IS REAL"],
            "hook_angles": ["detail", "question", "label"],
            "hook_questions": ["what is the gift?", "why would a fan do this?", "is it real?"],
            "titles": ["Kai Cenat Got A $5,000 Watch From A Fan In GTA 6 😳"], "review": GOOD_REVIEW}
    return {**base, **kw}


class MomentRuleTests(unittest.TestCase):
    def test_cause_rejects_reaction_only_premise_with_hype(self):
        from clipper import hooks
        fails = hooks.check_cause(new_pick(cause="Kai has the craziest reaction and loses it"))
        self.assertTrue(any("hype" in f for f in fails))
        self.assertTrue(any("reaction" in f for f in fails))
        self.assertEqual(hooks.check_cause(new_pick()), [])
        self.assertTrue(any("category" in f for f in hooks.check_cause(new_pick(category="vibes"))))
        self.assertTrue(any("why_care" in f for f in hooks.check_cause(new_pick(why_care=""))))

    def test_generic_hooks_and_angles(self):
        from clipper import hooks
        self.assertTrue(hooks.generic_hook("WAIT FOR IT"))
        self.assertTrue(hooks.generic_hook("THIS IS CRAZY"))
        self.assertFalse(hooks.generic_hook("A FAN'S $5,000 GIFT"))
        self.assertEqual(hooks.check_hook_angles(new_pick())[0], [])
        same = new_pick(hook_angles=["detail", "detail", "label"])
        self.assertTrue(any("distinct" in f for f in hooks.check_hook_angles(same)[0]))
        self.assertTrue(any("hook_questions" in f for f in hooks.check_hook_angles(new_pick(hook_questions=None))[0]))

    def test_review_decision_moment_first(self):
        from clipper import hooks
        th = hooks.REVIEW_DEFAULT_THRESHOLDS
        self.assertEqual(hooks.review_decision({"moment": 75, "packaging": 65}, th), "pass")
        self.assertEqual(hooks.review_decision({"moment": 65, "packaging": 95}, th), "test")
        self.assertEqual(hooks.review_decision({"moment": 50, "packaging": 100}, th), "reject")
        self.assertEqual(hooks.review_decision({"moment": 90, "packaging": 40}, th), "reject")
        w = hooks.review_weights({"review_weights": {"moment": {"surprise": 3}}})
        self.assertEqual(w["moment"]["surprise"], 3.0)
        self.assertEqual(hooks.review_scores(GOOD_REVIEW, hooks.review_weights(None)), {"moment": 80.0, "packaging": 70.0})

    def test_threshold_fails_only_when_on(self):
        from clipper import hooks
        weak = new_pick(review={**GOOD_REVIEW, "moment": {k: 4 for k in GOOD_REVIEW["moment"]}})
        on = hooks.principle_checks(weak, {"principles": "on"}, "on")
        shadow = hooks.principle_checks(weak, {"principles": "shadow"}, "shadow")
        self.assertTrue(on["review"]["fails"])
        self.assertNotIn("fails", shadow["review"])
        self.assertEqual(shadow["review"]["summary"]["decision"], "reject")

    def test_verdict_on_judges_as_if_on_whatever_the_mode(self):
        from clipper import hooks
        cfg = {"principles": "shadow", "research": "gta"}
        self.assertEqual(hooks.verdict_on(new_pick(), cfg, {"traits": {}})["verdict"], "pass")
        weak = new_pick(review={**GOOD_REVIEW, "moment": {k: 4 for k in GOOD_REVIEW["moment"]}})
        got = hooks.verdict_on(weak, cfg, {"traits": {}})
        self.assertEqual(got["verdict"], "reject")
        self.assertTrue(any("review" in w for w in got["why"]))
        prof = fixture_profile()  # payoff at 15 s of 20 is past the clear 100K+ range: a profile fail under on
        got = hooks.verdict_on(new_pick(), cfg, prof)
        self.assertEqual(got["verdict"], "reject")
        self.assertTrue(any("time to payoff" in w for w in got["why"]))
        self.assertIsNone(hooks.verdict_on(new_pick(campaign="brand"), cfg, prof))
        self.assertIsNone(hooks.verdict_on(new_pick(), {"principles": "shadow", "research": "other"}, prof))

    def test_legacy_and_campaign_picks_keep_old_rules(self):
        from clipper import hooks
        legacy = {"start": 0, "end": 20, "premise_type": "consequence",
                  "selection": {k: True for k in hooks.SELECTION}, "hooks": ["X"], "titles": []}
        self.assertEqual(hooks.principle_checks(legacy, {"principles": "on"}, "on"), {})
        old_bad = dict(legacy, selection={})
        self.assertIn("selection", hooks.principle_checks(old_bad, {"principles": "on"}, "on"))
        bare = {"start": 0, "end": 20, "hooks": ["X"]}
        self.assertTrue(hooks.principle_checks(bare, {"principles": "on"}, "on")["moment"]["fails"])
        self.assertNotIn("fails", hooks.principle_checks(bare, {"principles": "shadow"}, "shadow")["moment"])
        report = hooks.check_picks([dict(bare, campaign="brand")], {"principles": "on", "research": "gta"})
        self.assertFalse(any(k in report.get("video 1", {}) for k in ("moment", "review", "hook_angles")))


class LeadUpTests(unittest.TestCase):
    def test_lead_up_block_marks_reactions_and_drops_suggested_hook(self):
        from clipper import analyze
        sents = [{"s": 10.0, "e": 12, "text": "too early to count"},
                 {"s": 60.0, "e": 63, "text": "this fan just sent me five thousand dollars"},
                 {"s": 80.0, "e": 81, "text": "NO WAY BRO!"},
                 {"s": 81.5, "e": 83, "text": "oh my god what the"}]
        lu = analyze.lead_up(sents, 81)
        self.assertEqual([x[0] for x in lu], [60.0, 80.0, 81.5])
        self.assertEqual([x[2] for x in lu], [False, True, True])
        cand = {"id": 1, "tier": "strong", "timestamp": "1:00-1:30", "score": 0.9, "peak": 81, "contact_sheet": "x.jpg",
                "first_line": "", "opens_with": "statement", "transcript": "t", "duration": 30, "link": "l",
                "signals": {"jump_lu": 1, "peak_lufs": -10, "typical_lufs": -20, "hype_hits": []},
                "lead_up": [{"s": a, "text": t, "reaction": r} for a, t, r in lu], "loudest_line": "NO WAY BRO!"}
        r = {"video": {"title": "T", "channel": "C", "url": "u"}, "has_heatmap": False, "recommended": 1,
             "profile": "reaction", "loudness_spread_lu": 5, "clip_length": {"min": 9, "max": 35, "target": 22},
             "candidates": [cand], "demand": "Demand (base 33% 100K+ on 25 clip channels): CaseOh 36%"}
        md = analyze.to_markdown(r)
        self.assertIn("**Lead-up", md)
        self.assertIn("- 1:20 [reaction] NO WAY BRO!", md)
        self.assertIn("- 1:00 this fan just sent me five thousand dollars", md)
        self.assertNotIn("Suggested hook", md)
        self.assertIn("Demand (base 33%", md)


class ExperimentTests(unittest.TestCase):
    def test_two_active_experiments_are_refused(self):
        from clipper import config
        with self.assertRaises(SystemExit):
            config.check_experiments({"experiments": {"active": ["hook_angle", "opening"]}})
        with self.assertRaises(SystemExit):
            config.check_experiments({"experiments": {"active": "colour_grade"}})
        config.check_experiments({"experiments": {"active": "hook_angle", "queue": ["opening", "payoff_edit"]}})
        self.assertEqual(config.active_experiment({"experiments": {"active": ["opening"]}}), "opening")
        self.assertIsNone(config.active_experiment({}))

    def test_arms_only_change_with_principles_on(self):
        from unittest import mock
        from clipper import render
        pick = {"start": 50, "end": 70, "setup_start": 40}
        fp = [{"source": "s", "from": 50.0}]
        with mock.patch.object(render, "footage", return_value=fp):
            shadow = render.apply_experiment(pick, None, {}, {"principles": "shadow",
                                                                "experiments": {"active": "opening"}})
            on = render.apply_experiment(pick, None, {}, {"principles": "on", "experiments": {"active": "opening"}})
            angle = render.apply_experiment(pick, None, {}, {"principles": "on",
                                                               "experiments": {"active": "hook_angle"}})
        self.assertEqual(shadow, (pick, None, None))
        self.assertEqual(on[1], "opening")
        self.assertIn(on[2], render.OPENING_ARMS)
        self.assertEqual(on[0]["start"], 40 if on[2] == "setup_start" else 50)
        self.assertEqual(angle, (pick, "hook_angle", None))


class StatsGroupTests(unittest.TestCase):
    def test_new_and_legacy_manifests_group(self):
        from clipper import stats
        rows = [{"settled": True, "views": 100 * i, "lift": 1, "engaged": None, "ret50": None, "profile": "gta6",
                 "category": "reward", "moment_score": 55 + 10 * i, "profile_match": 0.5, "decision": "pass",
                 "experiment": "hook_angle", "experiment_arm": "label"} for i in range(3)]
        rows.append({"settled": True, "views": 50, "lift": 1, "profile": "gta6", "premise_type": "event"})
        rep = stats.report(rows)
        self.assertEqual(rep["category: reward"]["n"], 3)
        self.assertEqual(rep["premise type: event"]["n"], 1)
        self.assertEqual(rep["experiment hook_angle: label"]["n"], 3)
        self.assertEqual(rep["moment score <60"]["n"], 1)
        self.assertEqual(rep["moment score 60-70"]["n"], 1)


class CalibrateTests(unittest.TestCase):
    def test_calibrate_suggests_but_writes_nothing(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from clipper import stats
        rows = []
        for i in range(70):
            rv = {"moment": {c: (i % 10) for c in ("standalone", "surprise", "payoff", "stakes", "emotion", "demand")},
                  "packaging": {c: 5 for c in ("hook", "opening", "pacing", "ending", "title", "visual")}}
            rows.append({"settled": True, "views": 100 + i * 10 + (i % 10) * 50, "review": rv,
                         "moment_score": (i % 10) * 10, "packaging_score": 50, "profile_match": 0.5})
        c = stats.calibrate(rows)
        self.assertEqual(c["n"], 70)
        self.assertGreater(c["criteria"]["moment.surprise"], 0.15)
        self.assertGreater(c["suggested"]["moment"]["surprise"], 1)
        text = stats.format_calibration(c)
        self.assertIn("packaging.hook: rho None", text)
        self.assertIn("nothing was written", text)
        few = stats.format_calibration(stats.calibrate(rows[:10]))
        self.assertIn("too few scored posts", few)
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "own-stats.json"
            f.write_text('{"uploads": []}')
            before = sorted(Path(d).iterdir())
            with mock.patch.object(stats, "STATS", f):
                stats.run_calibrate()
            self.assertEqual(sorted(Path(d).iterdir()), before)
            self.assertEqual(f.read_text(), '{"uploads": []}')

    def test_flat_scores_are_flagged_not_tracking(self):
        from clipper import stats
        self.assertIn("not tracking views", stats.format_calibration(
            {"n": 80, "min_n": 60, "criteria": {"moment.surprise": 0.05}, "totals": {}, "suggested": {}}))


class PromptMirrorTests(unittest.TestCase):
    def test_claude_and_codex_prompts_are_identical(self):
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        claude = sorted((root / ".claude" / "commands").glob("*.md"))
        self.assertTrue(claude)
        for f in claude:
            twin = root / ".codex" / "prompts" / f.name
            self.assertTrue(twin.exists(), f"missing .codex/prompts/{f.name}")
            self.assertEqual(f.read_bytes(), twin.read_bytes(), f"{f.name} differs between .claude and .codex")


class LabelMergeTests(unittest.TestCase):
    def test_merge_labels_validates_and_examples_group(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "a.jsonl"
            f.write_text(json.dumps({"id": "x", "category": "reward", "opening": "weird", "payoff_at_s": 99,
                                     "premise_at_s": 1.23, "streamers": ["Kai Cenat"]}) + "\n")
            got = p.merge_labels([f], {"x": 20})
        self.assertEqual(got["x"]["category"], "reward")
        self.assertIsNone(got["x"]["opening"])
        self.assertIsNone(got["x"]["payoff_at_s"])
        self.assertEqual(got["x"]["premise_at_s"], 1.2)
        split = {"videos": [{"id": "x", "ch": "A", "group": "high", "views": 3e6, "lift": 9, "t": "Kai Cenat Got Gifted"},
                            {"id": "y", "ch": "A", "group": "low", "views": 3e4, "lift": 0.5, "t": "Kai Cenat Lost"}]}
        ex = p.build_examples(split, {"x": {"ocr_0_3": "A GIFT", "length_s": 20}, "y": {}}, got)
        self.assertEqual([r["id"] for r in ex["by_category"]["reward"]], ["x"])
        self.assertEqual(ex["by_streamer"], {})


class RenderDefaultTests(unittest.TestCase):
    def test_no_hook_arm_off_only_when_on_and_profile_says_text_helps(self):
        prof = {"traits": {"label_text_role=none": {"verdict": "clear", "lift": 0.7, "kind": "binary"}}}
        self.assertEqual(p.no_hook_share({"principles": "on", "no_hook_share": 0.5}, prof), 0.0)
        self.assertEqual(p.no_hook_share({"principles": "shadow", "no_hook_share": 0.5}, prof), 0.5)
        self.assertEqual(p.no_hook_share({"principles": "on", "no_hook_share": 0.5}, {"traits": {}}), 0.5)

    def test_layout_not_judged_without_a_cam_and_any_label_hook_counts(self):
        hidden = p.pick_values({"start": 0, "end": 20, "layout": {"type": "fit", "facecam": "hidden"}})
        self.assertNotIn("m_layout=split", hidden)
        fit = p.pick_values({"start": 0, "end": 20, "layout": {"type": "fit"}, "hooks": ["IS HE CHEATING?",
                                                                                         "THE EASIEST MISSION"]})
        self.assertNotIn("m_layout=split", fit)  # a plain fit pick (no cam info) isn't judged either
        split = p.pick_values({"start": 0, "end": 20, "layout": {"type": "split", "face": [0, 0, 1, 1]},
                               "hooks": ["IS HE CHEATING?", "THE EASIEST MISSION"]})
        self.assertTrue(split["m_layout=split"])
        self.assertTrue(split["m_text_0_3_kind=label"])


class ManifestTests(unittest.TestCase):
    def test_declared_angle_follows_the_hook_text_not_its_position(self):
        from unittest import mock
        from clipper import render
        pick = {"start": 0, "end": 20, "hooks": ["B HOOK", "A HOOK"], "hook_angles": ["question", "label"],
                "titles": ["t1", "t2"]}
        variants = [{"file": "x.mp4", "hook": "A HOOK", "check": {"duration": 20}}]
        with mock.patch.object(render, "footage", return_value=[{"source": "s", "from": 0.0}]), \
                mock.patch.object(render, "moment_at", return_value=None), \
                mock.patch.object(render, "predicted", return_value={}), \
                mock.patch.object(render, "moment_signals", return_value={}), \
                mock.patch.object(render, "credits", return_value=[("ch", "link")]):
            m = render.upload_manifest(pick, {}, {"principles": "off"}, variants, ["t2"], angle_of={"A HOOK": "label"})
        self.assertEqual(m[0]["hook_angle_declared"], "label")
        self.assertEqual(m[0]["principles"], "off")
        self.assertIsNone(m[0]["decision"])
        self.assertNotIn("verdict_on", m[0])  # off: no shadow verdict
