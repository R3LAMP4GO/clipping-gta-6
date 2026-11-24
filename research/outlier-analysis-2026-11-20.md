# What separates 100K+ Shorts from average ones (YouTube Shorts stand-in for Reels)

**Data caveat.** The repo holds no Instagram Reels. This uses the 5,203 YouTube Shorts in `viral/` (30 clip channels, fetched 2026-11-19; raw data is purged after 30 days). Conclusions are about YouTube Shorts and may not carry to Reels.
**Not done:** a frame-by-frame review of every 100K+ video. Step 1 relied on stored coding: premise, trigger and 4 title labels for all 5,203; opening OCR/ASR for 440; transcripts for 297; structured visual coding for 72 (36 matched pairs).

## Design
- 100K+ = 2,911 videos. 1K-2K = 81, of which 38 are our own channel and 35 more come from three small channels (NoPixel 14, Insomnia 13, Variety Roleplay 8). The 100K+ videos come from other channels.
- Channel alone explains 45.7% of the variance in log10 views and separates 100K+ from 1K-2K at AUC 0.977. A pooled comparison measures who posted, not what they made.
- **Primary test:** within-channel Spearman (30 channels, size-weighted), 2,000-4,000 within-channel permutations, Benjamini-Hochberg q across each family. Multipliers are within-channel with bootstrap 95% CIs.
- Views accumulate: within channel, older videos have more (rho +0.21). Only 2,443 videos have a publish date, so age adjustment is a sensitivity check, not the main test.

## Results
| # | Finding | Effect | Evidence | Verdict |
|---|---|---|---|---|
| 1 | Who/which channel | 46% of variance; top 8 videos are all Kai Cenat-crew moments | eta^2 | Dominant, not a creative choice |
| 2 | Profanity in transcript (rate/100 words) | rho -0.19 to -0.22; any profanity x0.58 [0.40-0.89] | n=297, q=0.007; sign holds dropping any channel (rho -0.24 to -0.16); excluding own: rho -0.175, p=0.013 but multiplier CI 0.40-1.21 | Best lead. Not replicated in 83 hit/flop pairs (13/30, p=0.59, underpowered) |
| 3 | "GTA" in title/premise | x0.77 [0.63-0.93]; titles with GTA 3% of 100K+ vs 13% of rest | n=5,203, q=0.035-0.052 | Real within-channel dip, but topic (off-niche for these channels), not wording |
| 4 | Face size in first frames | rho +0.13, q=0.09 | n=440 | Own-channel artifact: own rho +0.47, rest ~0; excluding own rho 0.066, p=0.24 |
| 5 | Duration | >=45s x1.85 [1.14-3.08] in one sample; length_s rho -0.18 (q=0.03) in the other | 5/9 channels positive | Falsified as stable: sign flips across samples |
| 6 | Hook text, hook words, hook states setup, hook question, title question, cold-readable, turn, setup-withheld, all 9 trigger types, emoji, hashtag, publish hour/weekday | all within-channel |rho| <= 0.05 (age-adjusted subset too) | n=2,443-5,203 | Falsified for effects above ~0.04 (title) / ~0.13-0.16 (media features) |
| 7 | Clip ends mid-sentence (AB coding: 2/36 vs 12/36, Fisher p=0.006, Bonferroni 0.15) | - | transcript tail gap n=147: rho -0.04, p=0.66; pairs p=0.14 | Not replicated |
| 8 | Blind Gemini A/B (premise, hook, pacing) | picked the higher-view video 21/36 = 58%, p=0.41 | - | Cannot tell outliers from averages |

Multivariate: 116 title/label/token features, ridge, 5-fold out-of-fold R^2 = -0.005 to +0.003; leave-one-channel-out within-channel Spearman = +0.000 (shuffled null SD 0.021).

## Correlation traps found
Pooled 100K+ vs 1K-2K "signals" shrink to nothing within channel: ALL-CAPS word (AUC 0.16 -> rho -0.04), GTA in title (0.22 -> -0.05), hook words (4.1 vs 9.8 -> rho +0.05 n.s.), ">100K videos have bigger faces" (0.06 vs 0.03 -> own-channel only). Shared traits at 100K+ are base rates: emoji 92% vs 90% for the rest, hook text 94%, cold-readable 44% vs 49%, trigger mix identical.

## Experiments (to test cause, not correlation)
1. **Profanity (priority).** Same moment, two versions (bleeped/muted vs raw), randomised order and posting slot within one channel. Within-channel SD is 0.66 log10 (x4.6), so detecting x0.70 needs about 280 videos per arm unpaired. Pre-register the primary metric (views at 7 days). Cheaper: ~60 same-moment pairs and a paired test.
2. **GTA framing.** On GTA-reaction clips, randomise title wording (with/without "GTA") across alternating uploads. Tests wording separately from topic.
3. **Length.** Trim one moment to ~20s and ~50s; the sample flip says the answer depends on content, so stratify by clip type.
4. **Opening crop (own channel only).** Alternate tight-face vs wide opening on matched clips; 40+ pairs.
5. **Same-moment cross-channel pairs.** The repo's pairs tooling can hold the moment fixed and compare packaging; this is the closest to a natural experiment.

## Limits
Titles/labels have enough power to rule out effects above about |rho| 0.04; media features (n 240-440) only above 0.13-0.18, and 83 pairs only above a ~62% win rate. Premise/trigger labels are model-written. Selection of downloaded videos was balanced on outlier status, which keeps within-channel tests valid but means prevalence there is not a base rate. Many results here are exploratory (209+ features); only q < 0.1 are treated as leads.
