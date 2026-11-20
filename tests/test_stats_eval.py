import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


class StatsTests(unittest.TestCase):
    def test_lift_uses_neighbours_and_join_prefers_video_id(self):
        from clipper import stats
        rows = [{"id": f"v{i}", "t": f"Clip {i}", "published": f"2026-11-{10 + i:02d}T12:00:00Z", "views": v}
                for i, v in enumerate([1000, 1000, 4000, 1000, 1000])]
        rows = stats.add_lift(rows)
        self.assertEqual(next(r for r in rows if r["id"] == "v2")["lift"], 4.0)
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "gta6" / "2026-11-12" / "video 1" / "upload.json"
            f.parent.mkdir(parents=True)
            f.write_text(json.dumps([{"title": "Retitled later", "youtube_id": "v2", "turn": "a theft", "arm": "hook"},
                                     {"title": "Clip 3!", "clip_type": "reaction"}]))
            man = stats.local_manifests(Path(d))
        now = datetime(2026, 11, 15, 13, tzinfo=timezone.utc)
        rows = stats.join(rows, man, now)
        by = {r["id"]: r for r in rows}
        self.assertEqual((by["v2"]["profile"], by["v2"]["turn"]), ("gta6", "a theft"))  # by id, despite the title
        self.assertEqual(by["v3"]["clip_type"], "reaction")  # by normalized title
        self.assertFalse(by["v4"]["settled"])  # under 48 h old: left out of comparisons and simulate data
        self.assertNotIn("v4", [r["t"][-2:] for r in stats.own_uploads(rows).get("gta6", [])])
        rep = stats.report(rows)
        self.assertEqual(rep["all settled"]["n"], 4)
        self.assertEqual(rep["turn named"]["n"], 1)


    def test_get_retries_a_dropped_connection(self):
        import http.client
        import io
        from unittest import mock
        from clipper import stats
        calls = []

        def flaky(req, timeout):
            calls.append(1)
            if len(calls) == 1:
                raise http.client.RemoteDisconnected("Remote end closed connection without response")
            return io.BytesIO(b'{"rows": []}')
        with mock.patch("urllib.request.urlopen", flaky):
            self.assertEqual(stats.get("https://x", "tok", wait=0), {"rows": []})
        self.assertEqual(len(calls), 2)


class StrangerCheckTests(unittest.TestCase):
    def test_pick_needs_a_turn_and_a_short_cold_premise(self):
        from clipper import hooks
        base = {"hooks": ["Kai Cenat pranked Lil RT"], "titles": ["Kai Cenat Pranked Lil RT! 😭"]}
        self.assertTrue(hooks.has_fails(hooks.check_picks([base])))
        lore = {**base, "turn": "betrayal", "cold_premise": "OG ordered Jean Paul not to go so Mickey's crew left "
                                                            "him at the tow yard"}
        self.assertIn("words", hooks.check_stranger(lore)[0])
        ok = {**base, "turn": "prank", "cold_premise": "Kai pranks his friend with a fake phone call"}
        self.assertEqual(hooks.check_stranger(ok), [])

    def test_narrated_statement_hook_is_a_note_not_a_fail(self):
        from clipper import hooks
        fails, notes = hooks.check_hook("Ron surprised Lacy with a *PS5 Pro*", False)
        self.assertEqual(fails, [])
        self.assertTrue(any("plain statement" in n for n in notes))


class MomentBenchmarkTests(unittest.TestCase):
    def test_benchmark_reproduces_held_out_results(self):
        from clipper import config, moments_eval
        out, table = moments_eval.run(config.load())
        self.assertGreaterEqual(out["loudness spread (LU)"]["held-out"][0], 0.6)  # the one signal that holds up
        self.assertLess(out["hype words per minute"]["held-out"][0], 0.5)  # hype density points at flops
        self.assertIn("held-out (64 pairs)", table)


if __name__ == "__main__":
    unittest.main()
