# What makes GTA Shorts go viral

Based on 28 GTA creator Shorts with 500k–51M views (raw data: `viral-gta-shorts-data.md`), studied frame by frame on 2026-11-09. Use this when picking clips and writing hooks and titles.

## The four formats that win

| Format | Example (views) | Length | What it looks like |
|---|---|---|---|
| **Streamer reaction** | Kai Cenat "Actually Thinks That A GTA VI Character Is Indecisive 🥀" (6.8M) | 9–25s | Split screen: streamer's face on top, game/trailer below. No hook banner; 1-word captions on the seam. The face *is* the hook. |
| **News / "did you know" listicle** | MrBossFTW "Kids WON'T Be Able To Play GTA 6!" (51M), "4 NEW Features…" (10M) | 50–60s | Full-frame gameplay, huge ALL-CAPS hook pinned at the top for the whole video, then numbered beats ("1. SUNTAN", "2. WATER EFFECTS"). The first spoken line repeats the title word for word. |
| **Creator facecam over gameplay** | DarkViperAU "We Are THAT Close - GTA 6 News" (1.3M) | 9–18s | Small series label pinned at the top with one coloured keyword ("I Can Play **GTA 6 NOW**"), boxed facecam, 1–3-word captions. A one-joke punchline. |
| **Skit / relatable** | RDCworld1 "There has to be a reason for this game taking this long 😂" (5M) | 45–90s | Meme-style white box at the top ("How Playing GTA 6 Is Gonna Be 😂"). Relatable situation, payoff at the end. |

## Hook rules
1. **2–6 words.** Every on-screen hook in the sample was under 7 words (relatable situations can run to 9): "KIDS CAN'T PLAY GTA 6", "GTA 6 GRAPHICS", "HE'S 72 YEARS OLD", "I Can't Believe It's Real...".
2. **Pin it for the whole clip**; it doubles as the title card for people who join late.
3. **Say it in the first second.** The first spoken words match the hook. No intros, no "hey guys".
4. **One coloured keyword** (usually "GTA 6" or the twist word) pulls the eye: `I Can Play *GTA 6 NOW*`.
5. **Reactions skip the banner.** A big face reacting plus loud single-word captions beats any text.
6. **Withhold the payoff.** An ellipsis or a question ("He Is The ONLY One…", "What Happens If You Shoot The Moon?") makes people watch to the end.

## How the viral hooks are built (counted)
Every on-screen hook in the 500k+ sample uses one of seven structures. `clipper check` recognises all of them, and all 13 sample hooks and all 20 GTA 6 titles pass it.

| Structure | Sample hooks (views) | Why it opens a loop |
|---|---|---|
| **Withheld / negation** | "KIDS CAN'T PLAY GTA 6" (51M), "He Is the ONLY One" (1.3M) | can't / won't / only / never: the viewer asks "why?" or "who?" |
| **Number promise** | "4 NEW FEATURES COMING IN GTA 6" (10M) | promises a list, so viewers stay for all of it |
| **Relatable situation** | "How Playing GTA 6 Is Gonna Be 😂" (5M), "Me watching *GTA 6* with my mom in the room" | the viewer pictures the scene and wants to see it play out |
| **First-person claim** | "I'M GONNA PLAY GTA 6!" (2M), "I Can Play GTA 6 NOW" (1.3M) | a bold "I" statement: how? really? |
| **Tease** | "I Can't Believe It's Real..." (1.3M) | ellipsis, "this", "wait", "watch": points at something without showing it |
| **Shock fact** | "HE'S 72 YEARS OLD" (1M) | a number that doesn't fit: who? since when? |
| **Question** | "What Happens If You Shoot The Moon In GTA 6?" (1.7M title) | asks the exact thing the clip answers |
| **Premise + twist** | source title "xQc FORCES Weazel News Ron Otterman to Rob a Bank", "Bank robbers force the hostages to SING" | who does what, with one shouted word: clear in a second, absurd enough to stay for. Add the streamer's name when fans will recognise it |

**Bare labels lose:** "GTA 6 GRAPHICS" (1.2M) and "GTA 5 Pacifist%" did well, but across 1,081 GTA Shorts, titles with no structure averaged 0.88x their channel's norm. `clipper check` now fails bare labels; give them a structure ("Are these *GTA 6* graphics real?").

**Titles:** MrBossFTW, the biggest channel in the sample, often uses **two** CAPS words ("GTA 6 Is HUGE (2x BIGGER Map)" 9.7M, "Cost HOW MUCH!?" 1.2M), so 1–2 are fine and 3+ fails. Joke titles can leave out "GTA 6" if #gta6 is in the hashtags ("There has to be a reason for this game taking this long 😂", 5M).

## How the viral clips open (spoken first line)
Of 28, none opened on filler ("hey guys", "um so", "welcome back"):
- **In-scene cold open: 7.** Dropped mid-conversation: "Sir, lock her up in the door a bit.", "Ooh, all the trophies look cool.", "I'm gonna go right at this mountain."
- **Claim / news: 5.** "It doesn't look like kids are going to be able to play GTA 6…" (51M)
- **Action cold open: 4.** "Go right! Right!" (Kai Cenat, 6.8M)
- **Question: 4.** "Have you ever wondered who is the voice of Lucia?" (2.9M), "Will I play GTA 6?"
- **Number promise: 3.** "4 things coming in GTA 6 that you didn't know about."
- **Setup tease: 2.** "If you look at the GTA 5 map at night…" (9.7M)

`candidates.md` labels each candidate's opening line the same way. If it says *filler*, move the start later.

## The hook variants
Give each variant a **different** structure so the A/B test actually tests something (`clipper check` flags hooks that share structures). Order them by measured effect (see "Measured" below) and run `python3 -m clipper simulate jobs/<id>/picks.json` to rank them. Reaction default: "Why couldn't Kai watch this?", "Kai was NOT ready for *this*", "Me watching *GTA 6* with my mom in the room", "Wait for Kai's face at the end…". The clip must pay the hook off, so start right before the moment it teases.

## Title rules (YouTube Shorts, max 100 characters; 35–70 is the sweet spot)
- **Name + "Actually" + surprise + emoji** for streamer clips: "Kai Cenat Actually Thinks…🥀", "xQc Actually Robbed A Bank For This 💀"
- **Negation shock:** "Kids WON'T Be Able To Play GTA 6!"
- **Number listicle:** "4 NEW Features Coming To GTA 6!"
- **CAPS question:** "GTA 6 Is Going To Cost HOW MUCH!?"
- **Curiosity / did-you-know:** "What Happens If You Shoot The Moon In GTA 6?"
- **Withheld ending:** "He Is The ONLY Character In The GTA Series Where This Happens..."
- At least half of the title options must open a loop too (question, "this", ellipsis, withheld detail).
- **Relatable "When…":** "When GTA 6 is TOO detailed..."
- 1–2 CAPS words per title (3+ reads as shouting). Emoji at the end for comedy or reactions (😂 💀 🥀 😭 ✌️); none for news.
- Put "GTA 6" (or "GTA VI") in the title; series tags help ("- GTA 6 News").
- Descriptions are short: one sentence plus 2–4 hashtags (#gta6 #gtavi #shorts plus the creator).

## Clip selection
- **Short reactions win per second:** the reaction clips were 9–25s. Information clips run to ~58s. Avoid 60–90s unless it's a skit with a payoff.
- Start **on** the reaction or claim, not the setup.
- Captions are huge (about 8–10% of frame height), 1–3 words at a time, bold white with a black outline, and the active or key word in yellow or red. Emphasis words get their own colour ("WHAT?" in red).
- Overlapping voices: show each speaker in a different colour so viewers can follow the back-and-forth.

## Originality: story cuts and multi-streamer edits
YouTube's reused-content rules reward clips that add editing over raw re-uploads, and the same footage posted twice gets no reach the second time. So every video is one of three kinds, and no footage is ever used twice (`clipper check --job` enforces it, 3 s tolerance):
- **Single clip:** one moment that carries itself (the formats above).
- **Story cut:** several beats of one stream joined into one Short (setup → turn → payoff), dead air cut out. Example: Kai's crash: "Moment of truth" → the blackout → "y'all missed that entire thing?".
- **Multi-streamer edit:** the same moment seen from several streams, back to back (the same cutscene, heist or reveal). Cutscene dialogue is identical in every stream, so `clipper find "<line>"` locates each stream's copy. Each streamer is credited.
All three keep the 60 s cap across their segments, and the hook/title rules above apply unchanged.

## Fonts
Identified from full-resolution frames of the top performers (bundled in `assets/fonts`, all OFL/Apache):

| Creator (views) | Where | Font | Look | clipper preset |
|---|---|---|---|---|
| MrBossFTW (51M, 10M) | hook pinned at the top | **Montserrat Black**, all caps | white, soft drop shadow, no box | `hook_style: bold` |
| Kai Cenat Live (6.8M) | 1-word captions | **Bebas Neue** | white on a black box | `caption_style: boxed` |
| RDCworld1 (5M) | meme hook | **TikTok Sans Bold** (TikTok's built-in text font) | black on a white rounded box | `hook_style: box` |
| DarkViperAU (1.3M) | series label + captions | **TikTok Sans SemiBold** | white, thin outline, keyword in purple | `hook_style: label` |
| Typical Gamer (1.3M) | word captions | comic font (Komika Axis style; we ship **Luckiest Guy**) | thick black outline | `caption_style: comic` |

Rule of thumb: geometric heavy sans (Montserrat Black) for news and info hooks, condensed Bebas on black for streamer reactions, TikTok Sans for meme and skit boxes, comic outline for playful gameplay.

## When to add an AI voiceover (`voice: auto`)
- **Add one** when the clip needs context in the first 2s and nobody says it: silent or music-only gameplay, trailer footage, news/info clips, or a moment that starts mid-conversation. Keep it to one punchy line (≤10 words) in the hook angle: "He waited twelve years for this."
- **Skip it** when the creator's own voice or reaction *is* the hook: streamer reactions, screaming, punchlines. A narrator talking over Kai Cenat kills the moment, and none of the top reaction Shorts in the sample used one.
- Never narrate over the payoff. The voiceover ends before the peak moment.

## Playbook: which hook fits which clip
Pick the clip type first, then use its hook structures in order. The first two matter most, and `clipper check` flags a clip whose hooks skip both. The type is a property of the *moment*, not the channel: a Kai Cenat reaction stream can contain a comedy bit, and an xQc RP stream is mostly comedy.

| Type | What it is | Hook structures (best first) | Examples | Hook / caption style | Voiceover | Length | Evidence |
|---|---|---|---|---|---|---|---|
| **reaction** | a streamer reacting to GTA 6 footage (trailer, gameplay, news); their face and voice are the payoff | relatable situation → withheld / negation → question → tease | "Me watching *GTA 6* with my mom in the room" · "Kai was NOT ready for *this*" | bold / boxed | False | 9–25s | Kai Cenat Live 6.8M / 1.2M: face + 1-word Bebas captions, no narrator |
| **comedy** | an absurd or funny scene with several people (RP, skits, group chaos); the situation is the joke | relatable situation → withheld / negation → question → tease | "POV: you're the hostage in *GTA 6*" · "Nobody expected the hostages to *SING*" | box / comic | False | 15–40s (let the bit land) | RDCworld1 5M: meme box 'How Playing GTA 6 Is Gonna Be 😂'; Jaden Williams 2M skit |
| **news** | information: features, leaks, prices, dates, facts about GTA 6, usually narrated | number promise → shock fact → withheld / negation → question | "4 NEW features coming in *GTA 6*" · "The *GTA 6* map is 2x BIGGER" | bold / bold | if nobody narrates | 30–58s | MrBossFTW 51M / 10M / 9.7M: Montserrat Black caps pinned all video |
| **gameplay** | a gameplay moment: a stunt, fail, glitch, speedrun or chaos where something surprising happens | shock fact → superlative → question → tease | "He beat it in 3 minutes" · "The craziest *GTA 6* escape ever" | label / comic | False | 9–25s | shock fact 1.68x, question 1.24x on GTA Shorts; Typical Gamer 1.3M comic captions |
| **showcase** | trailer, screenshots or graphics with no one talking; needs context added | shock fact → number promise → question → tease | "Rockstar spent 10 years on *this*" · "3 details you missed in *GTA 6*" | bold / bold | True | 20–45s | MrBossFTW 'GTA 6 GRAPHICS' 1.2M, Rockstar cover art 16M |
| **scenario** | a curiosity gap: the streamer makes, finds, tries or shows something NEW and the hook names that it exists but withholds what it is or how it turns out; beats escalate to a reveal or a face; often quiet | question → withheld / negation → tease → relatable situation | "What new *combo* did Kai just invent?" · "Nobody's seen Kai's new *getaway car*" | bold / boxed | False | 15–55s (60s max) | Mitro 'Kai Just Invented A New Sauce' 1.5M on 39.6k subs; Kai Cenat Live 'Visits The AMP House In GTA RP' 3.7M |

Worked example: **xQc's hostages forced to sing harmonies** is *comedy*, not a reaction. Several voices plus an absurd setup with a payoff (the harmony). It gets meme-box hooks that name the streamer ("Nobody expected xQc's hostages to *SING*", "POV: xQc is robbing your bank"; "Wait for the harmony…" is too vague and now fails), comic captions with a colour per speaker, and no voiceover. A news hook like "xQc robs a bank" gives away the setup and misses the joke.


### Scenario case study (2 Shorts, 2026-11-10; hypotheses until our own uploads measure them)
- **"Kai Just Invented A New Sauce 🤣😂"** (Mitro, 18s, 1.5M views on 39.6k subscribers, ~38x). A near-silent mukbang: ranch, then cheese, then he mixes them ("GRANCH?!") and his face is the payoff. Captions name the action, not speech (`RANCH`, `CHEESE`, `*AMAZED*`, `*EATING*`, `*TWEAKING*`); a red flash on the payoff; `#asmr` reaches a second audience. Title: name + "Just Invented" + withholds what the sauce is.
- **"Kai Cenat Visits The AMP House In GTA RP"** (Kai Cenat Live, 55s, 3.7M). "Let me show you around", then a chain of reveals (setup, whiteboard, bathroom, a Travis Scott poster, an organized closet). Fans recognise a real-life place recreated in the game; each reveal holds them for the next. Split facecam, word captions with key words coloured. Title: name + real place + "In GTA RP".
- **Why our finder missed them:** neither has a scream or a volume jump. `candidates.md` now lists *scenario candidates* found from transcript cues ("let me show you", "try this", "first time", "welcome to", "this is my"…) next to the loudness picks.
- **The principle (not the food):** both open a *curiosity gap*. "Kai just invented a new sauce" tells you something new exists and withholds what it is, so the viewer thinks "wait, what sauce?" and stays for the reveal. The tour does the same once per room ("what's in the next one?"). It's the information-gap effect: naming a gap without filling it makes people need to close it. Food was just the setting.
- **What to look for, in any game or stream:** the streamer *makes, finds, tries or shows* something new: a combo or trick nobody uses, a secret spot, a custom car or room, a build, a first try at something, a real-life thing recreated in the game, a strange rule they invent. It qualifies when (1) a viewer gets the premise in one second, (2) the outcome is unknown until the end, (3) beats escalate, and (4) it pays off with a reveal or a face. Fan knowledge (a real place, person or running joke) makes it stronger. Cut on the payoff; length follows the beats (one arc ~15–20s, a tour of reveals up to 55s).
- **Hooks inspired by "Kai Just Invented A New Sauce":** name the new thing, withhold the specifics, using types we can measure: question ("What new *combo* did Kai just invent?"), withheld ("Nobody's seen Kai's new *getaway car*"), tease ("Wait till you see the room Kai *built*..."). Never say what it is or how it ends in the hook. Titles can use the real phrasing: "Kai Just Invented A New <thing> 🤣", "Kai Created The Ultimate <thing>" ("Kai Cenat Created The Ultimate Wolverine Room 🔥", 2.6M, 4x channel norm). Only 6 of the 3,481 titles use invent/found/created + new/secret, too few to measure, so treat these as hypotheses that our own uploads will test.

## Outlier study: why people clicked (14 streamer Shorts, 2026-11-10)
The 12 biggest streamer-clip outliers in the dataset (12–117x their channel's norm), plus the two scenario case studies. Each was watched (frames + transcript). The question: what made a stranger stop scrolling, read the title and stay?

| Short (views, x channel norm) | What happens | Why people clicked and stayed |
|---|---|---|
| "CaseOh got every fast food burger right 🤣" (4.7M, 117x) | Nick watches CaseOh ace a "whose burger is this?" quiz; opens "Watch how many he gets right, it's ridiculous" | **Play-along + streak:** viewers guess too and stay to see if the streak breaks. Fits his persona (he's known for eating), so it's funny, not trivia. Title tells you the outcome but not how |
| "Is He Cheating?!" (7.8M, 29x) | Ninja spectates the player who killed him; the aim looks suspicious | **Viewer as judge:** the question hands the verdict to the viewer, who rewatches to decide (14s, so it loops) and argues in the comments |
| "CHAT WAS ABSOLUTELY LOCKED 🤯" (2.8M, 27x) | Tim's chat names songs from 0.1s clips, 5 for 5 | **Collective feat + streak:** impossible-sounding skill, a count that climbs ("four-for-four"), the viewer tries along |
| "I've never been more caught off guard 😳" (1.3M, 25x) | Mid small talk, a guy casually says he used to smoke crack | **Shock confession + the streamer's face:** the title withholds what caught him off guard; the deadpan reveal breaks a taboo |
| "Kai Cenat Explains Why He Never Signs With Blue Markers 🤯" (10.7M, 24x) | Kai refuses a blue marker, then: blue signatures are easier to forge | **Weird rule → why?:** a strange rule creates the question, answered in 15s with a fact viewers repeat to friends (social currency) |
| "Ed Sheeran's Aura Has Kai Cenat Shocked 😭" (9.7M, 23x) | Ed Sheeran walks in; `*AURA*` captions; Kai's crew stares | **Status + meme word:** a celebrity in an unexpected place, framed in the audience's slang ("aura") |
| "Smartest Jynxzi Moment 💀" (44M, 21x) | Jynxzi screams through Roblox red light/green light and runs at the wrong time | **Irony:** "smartest" for a dumb moment; fans get the joke, others click to see. The face does the rest (10s) |
| "Kai Cenat Wanted To Prank IShowSpeed 😂" (23.7M, 21x) | Kai creeps up on Speed: `*ENTERS*`, `*GETS CLOSER*`, `*NOTICES*` | **Suspense / dramatic irony:** we know what Speed doesn't; the title names the setup, never the outcome (9s) |
| "This Kid NEEDS to Touch Grass..." (7.9M, 19x) | A lobby kid does an absurdly sweaty pickaxe routine; Ninja's face | **Judgment + relatable mockery:** everyone has met this kid; the title invites you to judge him |
| "My Wife Caught Me in 4K" (4.7M, 16x) | Ninja celebrates a win; his wife walks in, "HONEY!", a hug | **Implied scandal, wholesome payoff:** "caught in 4K" promises something embarrassing; the gap between implied and real is the joke |
| "Kai Cenat Eats The Viral Kool Aid Pineapple 💀" (10.8M, 14x) | `*SMELLS*`, `*TRIES*`, `*LIKES IT*`, a meme cut | **Trend + sensory curiosity:** "what does that taste like?", answered by his face (8s) |
| "Bro has generational beef 😂" (13.5M, 12x) | "You got stream sniped by a guy, then his son stream sniped you 10 years later" | **Absurd premise in one line:** the setup is the hook; the escalation is the payoff |
| "Kai Just Invented A New Sauce 🤣😂" (1.5M, 38x) | Ranch + cheese → "GRANCH?!" | **Curiosity gap:** "a new what?" (see the scenario case study) |
| "Kai Cenat Visits The AMP House In GTA RP" (3.7M) | A tour of a real place rebuilt in the game | **Recognition + chained reveals:** "what's in the next room?" |

**What they share**
1. **The premise lands in one second,** on screen or in the first line ("Watch how many he gets right", "This blue marker?"). Nobody has to know the stream.
2. **The title states the situation and withholds the outcome:** who + what's happening, never how it ends ("Wanted To Prank", "Caught Me", "Explains Why", "Is He…?!").
3. **One psychological trigger per clip:** a curiosity gap, the viewer as judge, play-along/streak, suspense (we know more than the target), irony against the persona, a shock confession, status/celebrity, an absurd one-line premise.
4. **The face is the payoff.** Most end on the streamer's reaction, so the loop restarts on the setup.
5. **Short and loopable when the trigger is simple:** 8–15s for the top Kai and Jynxzi clips; longer only while a streak or story keeps escalating (CaseOh 59s, Tim's quiz).
6. **Captions narrate actions when nobody talks:** `*ENTERS*`, `*GETS CLOSER*`, `*AURA*`, `*TRIES*`. Many of the biggest clips are nearly silent, so loudness alone would never find them.
7. **The emoji tells you how to feel** (😭 💀 🤣 😳 🤯), and it matches the clip.
8. **No lie:** "Caught in 4K" and "Smartest" work because the clip delivers the twist. A promise the clip doesn't keep is malicious clickbait under YouTube's spam policy.

**How to use it on live clips:** for every candidate, name its trigger. If you can't name one, it isn't a clip. Write the hook and title around that trigger: a question for judge clips ("Is xQc's aim legit?!"), a withheld setup for suspense ("Speed had NO idea Kai was *behind* him"), irony for persona fails ("Smartest xQc *heist* ever 💀"), the stakes for streaks ("Can xQc's chat name *5 songs* straight?"). Cut so the premise lands in the first second and the clip ends on the face.

## Measured: what moves views on 3,481 gaming Shorts (2026-11-09)
The 28-video sample above only has hits, so it can't show what flops. To fix that, we pulled every recent Short (up to 200 each) from 19 GTA, Call of Duty/Warzone, CoD Zombies, Fortnite and streamer channels: MrBossFTW, DarkViperAU, Typical Gamer, RDCworld1, GTA Series Videos, Kai Cenat Live, xQc (GTA); Swagg, TimTheTatman, NICKMERCS, iFerg, BobbyPoff, WhosImmortal, Westie (CoD/Warzone); MrRoflWaffles, MrDalekJD (Zombies); Ninja, SypherPK, Jynxzi (other games). Each Short's views are compared with the 30 its own channel posted around it, so channel size and growth cancel out. A feature's effect is how many times its channel norm a Short with that feature got, vs the same channels' Shorts without it, with a 90% bootstrap range. We use the GTA estimate where GTA alone is conclusive, otherwise the all-gaming estimate. Data: `gaming-shorts-titles.json` (titles and view counts only; no media kept). `clipper simulate` resamples these Shorts to rank a clip's hooks.

| Feature | Effect | 90% range | Shorts | Scope | Verdict |
|---|---|---|---|---|---|
| number promise | 2.46x | 1.49–4.12 | 27 | gta | **keep** |
| shock fact | 1.68x | 1.08–2.78 | 22 | gta | **keep** |
| relatable situation | 1.48x | 1.21–1.82 | 88 | gta | **keep** |
| withheld / negation | 1.41x | 1.09–1.86 | 73 | gta | **keep** |
| question | 1.24x | 1.06–1.52 | 129 | gta | **keep** |
| names a streamer | 1.21x | 1.03–1.40 | 153 | all gaming | **keep** |
| tease | 1.17x | 1.02–1.34 | 185 | gta | **keep** |
| superlative | 1.14x | 1.06–1.25 | 285 | all gaming | **keep** |
| premise + twist | 0.97x | 0.92–1.02 | 1395 | all gaming | no effect: allowed, not recommended |
| first-person claim | 0.94x | 0.84–1.05 | 248 | all gaming | no effect: allowed, not recommended |
| all caps | 0.90x | 0.84–0.96 | 601 | all gaming | **drop** |
| announcement wording | 0.85x | 0.77–0.94 | 200 | all gaming | **drop** |
| vague | 0.67x | 0.48–0.92 | 40 | gta | **drop** |

**First 1.2 seconds of each channel's 2 best and 2 worst Shorts (75 frames, deleted after review):**
- Winners show a face mid-reaction about 80% of the time, versus about 60% for losers, plus one complete, specific line on screen: "you see your chat right?", "KIDS CAN'T PLAY GTA 6", "200 IQ CLUTCH VS CASEOH & SKETCH", "WHEN YOUR HOMETOWN SOUND SOFT 😂", "that much?".
- Losers open on a dark or empty establishing shot or a single mid-sentence caption word ("REASON", "VERY", "ACCESS TO"). Their titles are vague inside jokes ("My Hair Gel", "DBZ FANS WILL UNDERSTAND...", "This Character Might Be Crazy..."), announcements ("XP Tokens WILL Carry Forwards", "NEW STAR System Explained") or ads (0.63x).
- Famous guests are the biggest outliers: "TYLER1 Discovers Call of Duty Zombies" (119x its channel norm), "Ed Sheeran's Aura Has Kai Cenat Shocked" (23x), "CaseOh got every fast food burger right" (118x).

**What changed in the presets:** vague hooks and bare labels now fail `clipper check`. First-person claims are out of every playbook. Superlatives are in. Each type's structures are ordered by measured effect, and every playbook example scores above 1x in the simulator. Hook and caption *styles* (fonts, boxes) can't be measured from titles, so they stay as observed on the 28 hits.

Caveats: these are title effects, applied to on-screen hooks as the closest measurable proxy. Effects describe what happened on these channels, not guaranteed views. Once our own uploads have 48 hours of data, compare the variants' stayed-to-watch rate and feed it back.


## Title formulas per hook type (real titles from the 3,481-Short dataset)
Each hook gets a title of the **same type**, posted with that hook's MP4. Multipliers are views vs the channel's own norm.

| Hook type | Fits clip types | Title formula | Real titles (views, x channel norm) |
|---|---|---|---|
| **Number promise** | news, showcase | `<N> <NEW/things/ways> <coming in / you didn't know about> GTA 6` | "4 NEW Features Coming To GTA 6!" (10M, 149x) · "5 Ways The Police Have Been Improved In GTA 6" (15M, 95x). Worked on 1 channel only; other channels' list titles got 0.4–1x. Use only when the clip really is a list. |
| **Shock fact** | news, showcase, gameplay | `<thing> Is <2x / N years / $N> <BIGGER / later>` | "GTA 6 Is HUGE (2x BIGGER Map)" (9.7M, 109x) · "This Player Spent 200 Days on the Battle Bus" (12M, 13x) · "Bro Has The Exact Reaction 2 Years Later..." (1.4M, 8x) |
| **Relatable situation** | comedy, reaction | `When you… 😂` · `POV: …` · `How <X> be <doing Y> 😂` | "When you know the city you from sound soft 😂" (20M, 10x) · "How Popeyes be choosing the worst locations…" (39M, 10x) · "My Wife Caught Me in 4K" (4.7M, 16x) |
| **Withheld / negation** | all | `<Who> WON'T / NEVER / DID NOT <do X>` | "Kids WON'T Be Able To Play GTA 6!" (51M, 739x) · "Rockstar Games DID NOT Find This Funny" (7M, 44x) · "Kai Cenat Explains Why He Never Signs With Blue Markers 🤯" (10M, 24x) |
| **Question** | all | `Is He <X>?!` · `What Happens If <X>?` · `<X> Costs HOW MUCH!?` | "Is He Cheating?!" (7.8M, 29x) · "What Happens If You Shoot The Moon In GTA 6?" (1.7M, 25x) · "How Did I Predict This at the World Cup?" (4.7M, 33x) |
| **Tease** (must name the thing) | all | `<Specific thing> Is FINALLY Doing This...` · `<X> Of The Year...` | "This Train Mission Nearly Broke Me" (2.9M, 32x) · "Clutch Of The Year..." (22M, 14x) · "Battlefield 6 Is FINALLY Doing This..." (432k, 21x) |
| **Superlative** | all | `World's <Best/Fastest> <X>` · `The Most <X> <Y>` · `Smartest <streamer> Moment` | "World's Best Sniper in Black Ops 7" (1.8M, 26x) · "Smartest Jynxzi Moment 💀" (44M, 22x) · "The Smartest Move I Have Ever Seen" (xQc, 987k, 8x) |
| **+ streamer name** (adds to any type) | all | lead with the name: `<Streamer> <verb>s <X> 😂` | "TYLER1 Discovers Call of Duty Zombies With MrROFLWaffles!" (4.3M, 119x) · "CaseOh got every fast food burger right 🤣" (4.7M, 118x) · "Kai Cenat Pranks IShowSpeed 😭" (8.9M, 10x) |

## How many hooks per clip (simulated)
Should every clip get a variant for every hook type, or should Claude pick the best few? `clipper simulate --strategies` compares strategies at the **same number of uploads** (8 per source). Inputs:
- Each type's effect measured inside each channel, pulled toward zero when few channels back it.
- How much that effect varies from channel to channel, i.e. with the content.
- A clip's views spread, taken from the dataset.
- A hook that doesn't fit the clip scores like a vague one.

Two numbers can't be measured from public data: how much weaker a source's 8th-best moment is than its best, and how many viewers a second variant of the same clip loses to the first. So we ran 27 scenarios covering both, plus how well Claude judges fit.

| Strategy | Average shortfall vs each scenario's winner | Worst case |
|---|---|---|
| **Claude's best 3 types that fit** | 6% | 22% |
| Every type that fits | 6% | 33% |
| Claude's best 4 | 9% | 30% |
| Claude's best 2 | 9% | 35% |
| Every type, including ones that don't fit | 17% | 50% |
| One hook per clip | 23% | 60% |

**Default: Claude drafts a hook for every type that honestly fits the clip, simulates them, and posts the best 3, each a different type.** Forcing every type onto every clip (a "4 things…" hook on a skit) is the second-worst choice. Its misfit variants promise what the clip doesn't deliver.
