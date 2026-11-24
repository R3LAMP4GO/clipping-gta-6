---
description: Build a long-form 16:9 video (funniest-moments compilation, running-bit supercut, "what happens" video or narrated story) from the streams already fetched or recorded
argument-hint: [streamer or bit, e.g. "xQc lying to the cops"]
---

Build one long-form YouTube video: a **running-bit supercut**, one trait of one streamer delivered 25–30 times and getting bigger each time. Run from the clipping-gta-6 project root; pass `--profile <name>` to every `python3 -m clipper` command if `$ARGUMENTS` or `CLIPPER_PROFILE` names one. Read `research/long-form-compilations.md` first: every number below comes from its 87 outliers (5×–97× their channel's normal).

**Pick the kind first** (`"kind"` in the spec). Read `/clip` step 4's "Why outliers work" table, then set `"question"` and `"premise_type"` the same way; both go into `long.json` for `clipper stats`.
- `supercut` (the default; steps 1–10 below): one running bit, 25–30 clips, 8–10 min.
- `mid`: a **"what happens" video**, 30 s–3 min. It holds 1–4 clips of one situation, with no flash-forward and no counter.
  - Title: state the situation or ask it ("What Happens If You Leave Lucia In Prison In GTA 6?", "Speed Asks A Stranger For $1,000 In Tokyo 😳").
  - Payoff: `"payoff": {"clip": n, "t": <source s>}` must land before 60% of the runtime; the rest is the fallout.
  - Reuse: a moment already posted as a Short may go out once as a `mid`, never as two `mid`s.
  - The outlier study found this length no better than 10+ min (0.75x on GTA 6), so it's a test: compare it in `clipper stats`.
- `story`: a **narrated story**, 4–10 min. The streamers' clips (6–90 s each) are linked by an AI narrator (the Fish Audio voice, else the system voice).
  - Spec: `"narration": [{"at": n, "text": "...", "mode": "freeze" | "duck", "question": true}]`.
    - `freeze` plays the line on the first frame of clip `n`, before it.
    - `duck` plays it over the clip's opening, with the clip's sound lowered.
    - `at` = clip count + 1 is a closing line on the last frame.
  - The first line states the question (mark it `"question": true` or end it with "?") by 15 s.
  - The narrator takes at most 35% of the runtime and never talks over a clip's `payoff_at`.
  - Every clip must have someone talking (`long check` reads each job's transcript).
  - YouTube's inauthentic-content rule targets mass-produced voice-over on reused footage, so keep the volume low:
    - Tell a real arc across moments (how Speed got stranded, who helped, how he got home).
    - Never describe what's already on screen.
- `compilation`: **"[Streamer] Funniest Moments (Compilation)"**, 8–12 min, from any streamer footage: IRL, just chatting, gaming or RP. Read `research/long-form-streamers-2026-11.md` first. Compilation wording on IRL / just-chatting footage was the strongest cell (29.1% outliers, 2.2×); gaming 16.2%; GTA RP weakest (7.8%).
  - Clips: at least 10 moments of 6–60 s from any jobs, with no overlaps. Each has the streamer's face: a facecam `face` box, or `"face": "full"` when they fill the frame (IRL). No flash-forward, no counter. Clip 1 opens mid-moment, someone talking within 2 s.
  - Length: 6–15 min passes; aim for 8–12 (3–6 min is the dead zone).
  - Title: compilation wording (moments, best of, funniest, clips, compilation, highlights) and one or two names. 60 characters at most (aim ≤40). No `|`, hashtag, series tag or length promise ("for 10 minutes").
  - Spec adds `"niche": "irl" | "gaming" | "rp"` and `"streamer": "<name as in the title>"`. Reuse is fine: moments already posted as Shorts may go in.
- **Tag moments as you find them** (every kind, especially compilations, which gather moments over days): `python3 -m clipper bank tag <job> <start> <end> --note "<what happens>" --niche irl`, or `bank tag --short "exports/<profile>/<date>/video N"` for a moment already cut as a Short. Sources are deleted after `keep_sources_days` (live chunks after 3 h); a tagged moment survives as a small clip in `jobs/_longbank/` and the spec keeps using the same job and source seconds. `long check` fails a moment whose source is gone and that was never tagged. `python3 -m clipper bank list` shows what's banked.
- For `mid`, `story` and `compilation`, skip steps 1–5. Pick the moments from `candidates.md` and `clipper find`, then write the spec (step 8, plus the fields above), check and render (step 9) and report (step 10).

1. **Pick the bit.** One trait, one streamer, that recurs across the streams in `jobs/` (and live chunks from `python3 -m clipper live jobs`): lying to the cops, a feud with one character, a catchphrase, rage at one thing. It has to be one sentence a stranger understands ("xQc lies to the cops"), like "CaseOh HATING ON Spiderman for almost 9 minutes" (15×) or "CaseOh Perfect Timing Moments" (97×). Find instances with `python3 -m clipper find "<a line>" --hours 168` and by Grepping each job's `transcript.json` and `candidates.md`. With fewer than 25 strong instances, pick another bit or wait for more streams; don't pad.
2. **Cut the clips.** 25–30 clips of 15–30 s (6–45 s allowed), each a complete beat: the setup line, the bit, the reaction. Start on the first meaningful word, end on the reaction. No two clips overlap. Every clip must show the streamer's face: use jobs where the facecam is on in that stretch.
3. **Order by escalation.** Mild first, boldest last, with a bigger moment every 2–3 minutes (where the outliers' "most replayed" curves spike). Save the single best moment for the last clip; the video ends within 10 s of it. No intro, no outro.
4. **Flash-forward (≤ 20 s).** The three hardest-hitting lines, 3–6 s each, taken from inside later clips (usually the last three), back to back. It promises the payoff before anything is explained (Jeffy 64×, Perfect Timing 97×).
5. **Counter.** A short label shown on every clip, numbered: `"counter": "LIE #{n}"`. Set `"count": false` on a clip that shouldn't take a number.
6. **Title.** "[Streamer] [does the bit] For 10 Minutes Straight 💀 | NoPixel GTA RP", or an emotional promise ("xQc Moments That Get Worse & Worse"). Name a second streamer when one is in most clips (26% of outliers vs 5%). No question, no "NOT". Max 100 characters.
7. **Thumbnail.** Pick a frame with `python3 -m clipper frame <job> <s>`. It should show the streamer named in the title reacting, in a real place (not a game frame), with the face small in the scene (3–8% of the frame) and the thing they react to. Add 0–3 words in the streamer's voice ("I'M INNOCENT"), or none.
   - `"style": "ai"` (the default) has Codex's `$imagegen` (gpt-image-2, your ChatGPT login) lightly clean the frame up to a 1280×720 thumbnail. It keeps the place and people and adds no arrows, cut-outs, borders or logos.
   - Add `"refs": [{"job", "t"}]`: one clean front-facing frame of the streamer from another moment, to keep the likeness. Optional: `"exemplar": "<file in viral/longform/>"` for layout only.
   - Apple Vision then checks it: the same number of people as the frame (faces under half the biggest, like posters, don't count), the biggest face 2–10%, exactly the spec's words (text already in the frame, like a shirt print, doesn't count), the bottom-right badge corner clear, and readable at 168×94. On a miss it retries once, then uses the raw frame. `long.json` records `thumbnail_style` and the reason.
   - `"style": "raw"` (or `--no-ai-thumb`) uses the frame as is; `"style": "face"` is the old enlarged-face look.
   - Always look at `thumbnail.jpg` next to `thumbnail_source.jpg` before uploading: it must show something that happens in the video.
8. **Write the spec** to `jobs/long-<slug>.json`:
   ```json
   {"title": "...", "description": "one or two plain sentences on the bit", "hashtags": ["#gtarp", "#nopixel", "#xqc"],
    "counter": "LIE #{n}",
    "face": [x, y, w, h],
    "flash_forward": [{"job": "<id>", "start": s, "end": e}],
    "clips": [{"job": "<id>", "start": s, "end": e}],
    "thumbnail": {"job": "<id>", "t": s, "text": "I'M INNOCENT", "style": "ai", "refs": [{"job": "<id>", "t": s}]}}
   ```
   Times are source seconds. `face` is the facecam box (fractions, from `clipper frame`); leave it out to reuse the box this channel's earlier split clips used, or set `"face"` on a single clip whose cam sits elsewhere.
9. **Check, then render.** `python3 -m clipper long check jobs/long-<slug>.json` and fix every fail. Then `python3 -m clipper long render jobs/long-<slug>.json`. Output: `exports/<profile>/<date>/long N/` with the MP4 (1920×1080), `thumbnail.jpg` (plus `thumbnail_source.jpg` and, for AI, `thumbnail_ai.png`), `long.json` and `titles and description.md`. The bank clips it used are marked used. The autopilot never posts `long N` folders; uploading is manual.
   - **After you upload it:** `python3 -m clipper bank done "exports/<profile>/<date>/long N" --youtube-id <id>`. Then, after `keep_after_post_days` (2), cleanup deletes its bank clips (single use: a later spec can't reuse them) and its thumbnail files. The long MP4 and `long.json` stay. Until `bank done`, nothing it used is deleted, so a rejected render can be redone.
   - `python3 -m clipper cleanup --dry-run` (or `bank purge --dry-run`) lists what would go and its size. Each deletion is logged to `jobs/_longbank/ledger.jsonl`. Unused bank clips go `bank_expire_days` (30) after tagging, listed one run first.
10. **Report.** The bit, clip count, length, title, thumbnail text and style (ai or raw, and why), and the folder. After posting, compare at 48 h and 7 days: thumbnail click-through, the share still watching at 30 s, average % viewed, and where the retention curve dips. Cut or move the clip at each dip next time.
