# Why the 5 outliers worked: does "one question the viewer can't answer" hold up? (fetched 2026-11-23)

**Short answer: mostly no.** Of the five question types guessed from 5 outliers, only **event** clears the 2x gate, and
only for streamer Shorts. Even there it rests on one timely cluster (Streamer Awards clips). Question-frame titles
("what happens if…", "<who> tries to…") and mission-name titles show no reliable effect either way. The 30s-3 min band
does not beat >10 min long-form. The rules in `clipper/hooks.py` and `clipper/longform.py` follow this, not the
5-video table.

## Data
- 46 channels: 20 GTA 6 channels (the 5 sources plus 15 found by searching "gta 6 what happens if/when", "tries to",
  "npc reaction", "lucia" and similar) and 26 streamer clip channels (`research/viral-channels.txt` plus 6 long-form
  ones found by searching "ishowspeed irl stream highlights", "kai cenat stream highlights" and similar).
- Last 60 Shorts and last 60 videos per channel (yt-dlp `--flat-playlist`), dropping the 3 newest of each (still
  gaining views). Tabs with under 8 items were skipped.
- **Outlier** = 3x or more of that channel's median for the same tab (Shorts vs Shorts, videos vs videos).
- **Niche** per video: `gta6` when the title names GTA 6 / VI / Lucia / Jason / Vice City / Leonida / Mandy, otherwise
  `streamers` for streamer channels. The 852 non-GTA-6 videos from GTA channels (other games) are excluded.
- Coded: 2,910 titles. Shorts: 219 gta6 and 1,206 streamers. Long-form: 870 gta6 and 615 streamers.
- **Coding:** each title was read and given one question type and one title frame, by hand (by child agents working
  from a written brief, not by keyword rules). A first keyword coder labelled 80% "plain" and missed most types, e.g.
  "Kai Cenat Was Left Speechless By Snoop Dogg" (recognition), so it was discarded.
  - Types: choice, tries, collision, recognition, event, mission name, plain.
  - Frames: question/conditional, "tries to", narrated.
- **Gate (from the plan):** a pattern becomes a rule only if all of these hold:
  - its outlier rate is at least 2x "plain" in that niche and format
  - n is at least 10
  - outliers come from at least 3 channels

  The p value is a one-sided permutation test (4,000 shuffles of labels within channel and tab).

## Caveats
- One coder per title, with no second coder to check agreement. The type boundaries are fuzzy, especially
  collision vs tries and recognition vs event.
- No upload dates (flat listings), so age isn't controlled. The 60 newest uploads span days for some channels and
  months for others.
- GTA 6 launched ~5 days before the fetch, so the GTA 6 data is launch week. Mission and cutscene uploads dominate it
  (42% of GTA 6 long-form titles).
- 4 of the 5 source videos are in the data (as 112x, 6.8x, 31.9x and 6.7x outliers). The Lucia sports-car Short
  isn't among its channel's last 60 coded Shorts.

## Results: Shorts

| niche | type | n | outliers | rate | vs plain | channels | p | gate |
|---|---|---|---|---|---|---|---|---|
| streamers | plain | 582 | 101 | 17% | 1.00x | 21 | | |
| streamers | **event** | 53 | 19 | 36% | **2.07x** | 12 | 0.001 | **PASS** |
| streamers | recognition | 141 | 34 | 24% | 1.39x | 16 | 0.026 | no |
| streamers | choice | 54 | 12 | 22% | 1.28x | 7 | 0.135 | no |
| streamers | collision | 219 | 44 | 20% | 1.16x | 16 | 0.301 | no |
| streamers | tries | 154 | 30 | 19% | 1.12x | 12 | 0.262 | no |
| gta6 | plain | 126 | 26 | 21% | 1.00x | 11 | | |
| gta6 | collision | 19 | 6 | 32% | 1.53x | 3 | 0.163 | no |
| gta6 | choice | 21 | 3 | 14% | 0.69x | 3 | 0.452 | no |
| gta6 | recognition | 28 | 3 | 11% | 0.52x | 2 | 0.725 | no |
| gta6 | mission name | 12 | 0 | 0% | 0.00x | 0 | | no |
| gta6 | tries / event | 9 / 4 | 0 / 0 | 0% | | | | n<10 |

- **The event result is fragile.** 20 of the 53 event Shorts are Streamer Awards clips (nominated, wins, the speech),
  posted in the weeks after the show. Without them, event drops to 27% vs 17% (1.57x, 7 channels): below the gate.
  The rest that worked were also dated happenings: a marathon's 24-hour mark, a mafiathon, a mom taking over the
  stream, a fan giveaway.
  - Read it as "a live event the audience is following right now", not "any place or world".
  - It is still the only type that beat plain by 2x anywhere, so `event` joins `PREMISE_TYPES` as an allowed type.
    It is not a requirement.
- **Recognition** (famous person where they shouldn't be) is the next best in streamer Shorts: 1.39x, p=0.026,
  16 channels. That's a real but modest edge, below the gate. It is already the `recognition` premise type.
- **GTA 6 Shorts are too few** (219 coded) to rank types. Plain description has the most outliers.

| niche | frame | n | outliers | rate | vs narrated | p |
|---|---|---|---|---|---|---|
| streamers | narrated | 1,132 | 227 | 20% | 1.00x | |
| streamers | question/conditional | 39 | 9 | 23% | 1.15x | 0.437 |
| streamers | "tries to" | 35 | 5 | 14% | 0.71x | 0.810 |
| gta6 | narrated | 208 | 37 | 18% | 1.00x | |
| gta6 | question/conditional | 9 | 1 | 11% | 0.62x | 0.851 |

- **Question-frame Shorts titles: no support.** 94-95% of Shorts titles narrate, and the few question titles don't do
  better. The existing note in `check_title` stays: 500K+ clip Shorts narrate what happened.

## Results: long-form (16:9)

| niche | type | n | rate | vs plain | channels | p |
|---|---|---|---|---|---|---|
| gta6 | plain | 185 | 30% | 1.00x | 21 | |
| gta6 | event | 68 | 43% | 1.43x | 12 | 0.625 |
| gta6 | recognition | 83 | 33% | 1.09x | 8 | 0.739 |
| gta6 | choice | 72 | 29% | 0.98x | 13 | 0.853 |
| gta6 | mission name | 362 | 27% | 0.90x | 16 | 0.787 |
| gta6 | collision | 63 | 21% | 0.69x | 8 | 0.918 |
| gta6 | tries | 37 | 19% | 0.64x | 4 | 0.958 |
| streamers | plain | 398 | 22% | 1.00x | 13 | |
| streamers | collision | 57 | 19% | 0.86x | 4 | 0.641 |
| streamers | event | 85 | 13% | 0.58x | 6 | 0.777 |

- No type passes in long-form, in either niche.
- **Mission-name titles are not penalised.** They run 0.90x in GTA 6 long-form, which is noise, and cover 362 of 870
  titles. The "prison scene with a mission name got 19k vs 304k" pair is one comparison, not a pattern, so the
  planned mission-name note is dropped.
- **GTA 6 "what happens if" long-form is a lottery, not a rule.**
  - 33 titles: 39% outliers vs 28% narrated (1.40x, p=0.085).
  - It has the biggest hits in the set: "What Happens if Jason Leaves Lucia in PRISON?" (448x), "This Happens If You
    Kill Arnold" (121x), "What Happens if You Don't Pick Lucia up From Prison" (40x), "What Happens If You Get 6
    Stars" (40x).
  - But its median is below the channel's (most land at 0.2-1x).
  - It can be used, but nothing requires it.

| niche | length band | n | rate | vs >10 min | p |
|---|---|---|---|---|---|
| gta6 | >10 min | 343 | 31% | 1.00x | |
| gta6 | 3-10 min ("story") | 313 | 29% | 0.93x | 0.621 |
| gta6 | 61s-3 min ("mid") | 182 | 23% | 0.75x | 0.882 |
| streamers | >10 min | 500 | 20% | 1.00x | |
| streamers | 3-10 min | 86 | 24% | 1.23x | 0.905 |
| streamers | 61s-3 min | 22 | 18% | 0.92x | 0.671 |

- **No length band is an outlier driver.**
  - The 30s-3 min "what happens" band runs a little below >10 min for GTA 6 (0.75x, not significant).
  - 3-10 min is level.
  - The `mid` and `story` formats are built as planned, as formats to test on our channel (`kind` is in
    `upload.json` and `long.json` for `stats`), not because the data says they win.

## What changes in the clipper
| Hypothesis | Verdict | Change |
|---|---|---|
| "Does it react if I do X?" (choice) | no (0.69x-1.28x) | none; `consequence` already covers it |
| "How badly will this go?" (tries) | no (0.64x-1.12x) | none; "tries to" titles not promoted |
| "Who snaps first?" (collision) | no (0.69x-1.53x) | none; `interaction` covers it |
| "Is that real?" (recognition) | no, best near-miss (1.39x streamer Shorts, p=0.026) | none; `recognition` exists |
| "What is this world?" (event) | **pass in streamer Shorts (2.07x), fragile** | `event` premise type, described as a live event the audience follows now |
| Question-frame titles | no | `check_title` unchanged: narrate-only notes stay |
| Mission-name titles hurt | no (0.90x) | the planned note is dropped |
| 30s-3 min beats long | no (0.75x-0.92x) | `mid` and `story` built as tests; results are grouped by `kind` in `stats` |

Every pick also records `question` (the one question the clip answers), so our own channel can test the 5 types
where this study couldn't.
