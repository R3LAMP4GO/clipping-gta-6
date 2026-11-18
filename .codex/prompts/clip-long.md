---
description: Build a long-form (8-10 min, 16:9) running-bit supercut from the streams already fetched or recorded
argument-hint: [streamer or bit, e.g. "xQc lying to the cops"]
---

Build one long-form YouTube video: a **running-bit supercut**, one trait of one streamer delivered 25–30 times and getting bigger each time. Run from the clipping-gta-6 project root; pass `--profile <name>` to every `python3 -m clipper` command if `$ARGUMENTS` or `CLIPPER_PROFILE` names one. Read `research/long-form-compilations.md` first: every number below comes from its 87 outliers (5×–97× their channel's normal).

1. **Pick the bit.** One trait, one streamer, that recurs across the streams in `jobs/` (and live chunks from `python3 -m clipper live jobs`): lying to the cops, a feud with one character, a catchphrase, rage at one thing. It has to be one sentence a stranger understands ("xQc lies to the cops"), like "CaseOh HATING ON Spiderman for almost 9 minutes" (15×) or "CaseOh Perfect Timing Moments" (97×). Find instances with `python3 -m clipper find "<a line>" --hours 168` and by Grepping each job's `transcript.json` and `candidates.md`. With fewer than 25 strong instances, pick another bit or wait for more streams; don't pad.
2. **Cut the clips.** 25–30 clips of 15–30 s (6–45 s allowed), each a complete beat: the setup line, the bit, the reaction. Start on the first meaningful word, end on the reaction. No two clips overlap. Every clip must show the streamer's face: use jobs where the facecam is on in that stretch.
3. **Order by escalation.** Mild first, boldest last, with a bigger moment every 2–3 minutes (where the outliers' "most replayed" curves spike). Save the single best moment for the last clip; the video ends within 10 s of it. No intro, no outro.
4. **Flash-forward (≤ 20 s).** The three hardest-hitting lines, 3–6 s each, taken from inside later clips (usually the last three), back to back. It promises the payoff before anything is explained (Jeffy 64×, Perfect Timing 97×).
5. **Counter.** A short label shown on every clip, numbered: `"counter": "LIE #{n}"`. Set `"count": false` on a clip that shouldn't take a number.
6. **Title.** "[Streamer] [does the bit] For 10 Minutes Straight 💀 | NoPixel GTA RP", or an emotional promise ("xQc Moments That Get Worse & Worse"). Name a second streamer when one is in most clips (26% of outliers vs 5%). No question, no "NOT". Max 100 characters.
7. **Thumbnail.** Pick the second where the face reacts hardest (mouth open, eyes wide) with `python3 -m clipper frame <job> <s>`, and 0–3 words that state the bit in the streamer's voice ("I'M INNOCENT"). The render puts the face huge on the left with a white outline over the darkened scene, the words on the right.
8. **Write the spec** to `jobs/long-<slug>.json`:
   ```json
   {"title": "...", "description": "one or two plain sentences on the bit", "hashtags": ["#gtarp", "#nopixel", "#xqc"],
    "counter": "LIE #{n}",
    "face": [x, y, w, h],
    "flash_forward": [{"job": "<id>", "start": s, "end": e}],
    "clips": [{"job": "<id>", "start": s, "end": e}],
    "thumbnail": {"job": "<id>", "t": s, "text": "I'M INNOCENT"}}
   ```
   Times are source seconds. `face` is the facecam box (fractions, from `clipper frame`); leave it out to reuse the box this channel's earlier split clips used, or set `"face"` on a single clip whose cam sits elsewhere.
9. **Check, then render.** `python3 -m clipper long check jobs/long-<slug>.json` and fix every fail. Then `python3 -m clipper long render jobs/long-<slug>.json`. Output: `exports/<profile>/<date>/long N/` with the MP4 (1920×1080), `thumbnail.jpg`, `long.json` and `titles and description.md`. The autopilot never posts `long N` folders; uploading is manual.
10. **Report.** The bit, clip count, length, title, thumbnail text, and the folder. After posting, compare at 48 h and 7 days: thumbnail click-through, the share still watching at 30 s, average % viewed, and where the retention curve dips. Cut or move the clip at each dip next time.
