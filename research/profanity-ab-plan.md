# Experiment plan: does spoken profanity cost views? (own channel)

Source: `research/outlier-analysis-2026-11-20.md`, finding 2. Observed on YouTube Shorts: any profanity in the transcript was associated with x0.58 views (95% CI 0.40-0.89), and x0.47 (0.29-0.76) on our own channel. This is correlational; clips with swearing also differ in topic and energy.

## Question and arms
Does bleeping spoken profanity raise 7-day views, holding the clip fixed?
- **A (control):** current output. Audio raw, on-screen swears already masked (`captions.censor`, `censor_captions: true`).
- **B (treatment):** same clip, each profane word covered by a beep (or muted) using word timestamps from the existing transcript. Nothing else changes: same cut, captions, title, thumbnail frame, length.
A clip is posted once, in one arm only. Never post the same moment twice (duplicate-content risk, and it contaminates the comparison).

## Eligibility
- Clip audio contains at least 1 word matching `captions.SWEARS`, and no slur (the slur filter drops those words anyway; exclude such clips from both arms).
- Normal quality gates still apply. Do not pick clips by expected performance.

## Randomization
- Before rendering, assign arm by seeded coin flip, blocked in pairs within streamer (and within length band <20s / 20-40s / >40s). Save `{clip_id, arm, seed, assigned_at}` to a log before the render step; never reassign.
- Post in the usual slots; do not change the posting schedule. Alternate arms across slots so time of day is balanced.
- Do not let the assigner see views or the quality score.

## Outcome
- **Primary:** log10 views at 7 days (fetch at 7d +/- 2h; same API call for all clips).
- **Secondary:** average view duration / % viewed (`own_view_duration`), likes per view. Report, do not use to declare a win.
- **Guardrail:** subscribers gained per clip; stop early only on this, see below.

## Sample size
Own-channel SD of log10 views = 0.57. Two-sided alpha 0.05, 80% power, unpaired:
| smallest effect worth detecting | log10 gap | clips per arm | total | at ~8 uploads/day, 67% eligible |
|---|---|---|---|---|
| x0.50 (what we observed) | 0.30 | 56 | 112 | ~21 days |
| x0.65 (plan for this; observed effects are usually inflated) | 0.19 | 146 | 292 | ~55 days |
| x0.75 | 0.125 | 330 | 660 | ~123 days |
Fix **N = 150 per arm (300 clips)**. Blocking and covariates (streamer, length, publish hour) should cut the needed N somewhat; do not rely on that.

## Analysis (write this down before launch)
1. Primary test: permutation test on the arm label, re-randomized within blocks, difference in mean log10 views; report the multiplier 10^diff with a 95% bootstrap CI.
2. Check with OLS: log10 views ~ arm + streamer + length band + hour. Report only if the direction agrees.
3. Pre-registered interpretations: CI entirely above 1.0 -> bleeping helps; entirely inside 0.9-1.1 -> no meaningful effect, stop worrying; otherwise inconclusive, extend to N = 250 per arm once, never more.
4. Exclude, and count: clips removed by YouTube, clips with <48 h data.

## Stopping rule
- One interim look at 150 clips total, **futility/harm only**: stop if the B arm's multiplier CI is entirely below 0.7 (bleeping hurts clearly) or the guardrail drops by more than half in B. No early "win" stops; it inflates false positives.
- Otherwise run to N = 150 per arm.

## Threats and how this plan handles them
- **Beep itself is the treatment:** an irritating beep may cost views independent of profanity. If B loses, run a mute-or-cut arm (C) before concluding profanity itself costs reach. If B wins, the result stands for bleeping as a packaging choice.
- **Topic confound:** randomization removes it; the observational result could not.
- **Channel too small / views too noisy:** at 1.2K median views, 7-day counts are noisy; this is why N is large. Do not shorten.
- **Algorithm drift / one viral clip:** use log views; report results with and without the single largest clip.
- **Winner's curse on the 0.47 estimate:** planned for x0.65, not x0.47.

## Implementation notes (not built yet)
- Word times: `viral/media/<id>.words.json` style data from `clipper/transcribe.py`; match with `captions.SWEARS`.
- Beep render: one ffmpeg audio filter per clip, e.g. `volume=enable='between(t,a,b)':volume=0` on each profane span, mixed with a 1 kHz sine for the same span. Add behind a config flag next to `censor_captions` so arm A is the unchanged default.
- Assignment log goes in `exports/` or `jobs/` (both git-ignored).
