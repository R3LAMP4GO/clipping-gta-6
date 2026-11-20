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
- **Exception, narrated explainers (2026-11-18):** a story that needs context can be narrated through its setup (`"narrate": true`), then hands over to the streamer's own payoff line. This is the "did you know" format the story-game outliers use (3–18M views). First test: xQc's marlin traffic stop, which flopped un-narrated (26 views).

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

**Strong reactions, not fake controversy (2026-11-14):** a keyword pass on the 3,481 titles (vs the rest of the same set): verdict questions (cheat, legit, fair, wrong, who's right) ~1.28x (36 titles, thin), outrage words (caught, exposed, toxic) ~1.1x (53), emotional words/emoji (😭, wholesome, heartbreak) ~1.07x (126), rage-bait opinions (overrated, worst, trash, ruined, hate) ~0.84x (97). So provoke by handing the viewer a real verdict and by pushing the clip's one true emotion; insults and invented disputes lose.

## Hits vs flops: the idea (2026-11-19)
**Cold hooks.** The cold-premise gate checks the moment; the hook on screen has to pass it too. Of our 73 uploads, the 4 hooks naming a roleplay character (Mickey twice, Marty, Avery) got 164-840 views (median 505) vs a 1.2k median for our other NoPixel clips; crew lore ("xQc's crew", "the betrayal") got 8, 604 and 891. Hooks naming famous game characters did fine (Trevor 7.3k, Jason 1.1k, Michael 1.2k). Small sample: `clipper check` makes it a note, not a fail.

**Method.** 4,792 Shorts from 27 streamer-clip channels (Kai Cenat, IShowSpeed, CaseOh, Jynxzi, Marlon, Lacy, xQc...), each compared with the 30 its channel posted around it: 155 outliers (100K+ views, 3x+ the norm) vs 162 flops (0.4x or less). The idea behind all 155 + 162 titles and our 73 uploads was labelled blind; 83 same-channel hit/flop pairs were transcribed and measured (`research/moment-pairs.json`: 19 read while writing rules, 64 held out). Our channel (Noclipd, 74 uploads) was read with the YouTube Analytics API.
- **What separates a hit from a flop on the same channel is a turn between people,** not the category: both groups were 69% IRL and ~25% social. Hits: OhnePixel's awkward gift turns into 100 gifted subs (4M), Ron surprises Lacy with a PS5 Pro (3.3M), Jamal deletes Speed and Kai's Minecraft world (14M), Ray charms a girl in her language (9.7M). Flops: an activity or commentary with no turn (GeoGuessr, testing shoes, reading comments, reacting to an AI video or **the GTA 6 trailer**, the flop on two channels).
- **Our clips are fished from the smallest pond.** 77% of our uploads were NoPixel storylines; the RP clip channels have 6.9k-24k median views vs 150k-950k for the big streamer-clip channels. On our channel Kai clips median 1,788 views vs xQc 1,000; our top 4 were cold-readable events (xQc steals a Corvette with cops searching, 15k; Kai finds out a player is 13, 9k) and our bottom ones needed lore ("OG ordered", Mickey's crew, Lee's USB).
- **The turn can't be found from keywords.** Turn phrases ("got you a", "prank", "how old are you", "cops") picked the hit in 58% of the seen pairs but 41% of the held-out ones, where 25% of flops and only 8% of hits had any cue, so the agent judges it (`turn` and `cold_premise` in every pick; `clipper check` fails a pick without them) instead of the score.
- **Moment signals (`clipper bench --moments`, held-out 64 pairs):** loudness spread picked the hit 69% (59-78%), volume jump 64% (55-73%), hype words per minute 40% (31-49%). Keywords now weigh 0.10 instead of 0.20; loudness 0.40.
- **Hook rules and ranker:** `check_hook` failed 82% of the outlier titles, mostly as "plain statement" (now a note); the hook simulator separated hits from flops at chance (AUC 0.53) and correlates weakly with our views (Spearman 0.22), so it's a tie-breaker. Outlier titles use questions 2% and negations 5% of the time; ours 25% and 46%.

## Open loops: reframing any clip (2026-11-19)
**Method.** Titles from two sets, each Short compared with the 30 its own channel posted around it (`open-loop-titles.json`, titles and views only): 4,804 Shorts from 30 story-game channels found by searching "what happens if" (RDR2, GTA, Skyrim, Minecraft, Cyberpunk), and the 4,792 streamer-clip Shorts above. Frames are detected by `hooks.loop_frame`.

| Frame | Story-game channels | Streamer-clip channels |
|---|---|---|
| Hypothetical ("What Happens If…", "If you…") | **1.12x** (1.02-1.23), 385 | 2 titles |
| Setup told, ending withheld ("Wanted To", "Tried To", "Only Asked For") | 0.96x (0.78-1.21), 84 | **1.13x** (0.97-1.33), 260 |
| Question | 0.99x, 1,088 | 0.87x (0.73-1.04), 190 |
| Tease ("…", "wait for") | 0.86x (0.79-0.95), 311 | 0.97x, 92 |
| "Did you know" / hidden detail | **0.71x** (0.61-0.83), 145 | 5 titles |

- **The frame adds ~10%; the premise inside it makes the outlier.** Same frame, opposite results: "What Happens If Arthur Drinks 99 Hair Tonics?" (9.9M, 450x), "What Happens If You Kill the Father or Son in RDR2?" (15M, 213x), "If You NEVER EAT in GTA Games" (32x) vs "What Happens If You Blow Up the Train Before Saving Swanson?" (0.24x), "What Happens When You Donate in Saint Denis?" (0.16x), "What if GTA VI cost 100$?" (0.14x). Winners are extreme or forbidden (99, every, never, kill), picturable at once, often about a loved character, with an outcome you can't guess. Losers need mission knowledge or have a small, guessable result.
- **The recipe (now step "Reframe every pick" in /clip):** find the most extreme picturable fact in the clip; open the loop on it and withhold the outcome; open on the line or image that states it, never on lore; end on the outcome. A pick names its `loop` and `payoff_at`, and `clipper check` fails it without them.
- **Worked on our own clips (transcripts):** "When The Ransom Is Two Bags Of Chips" (292 views) → "He Took A Hostage And Only Asked For Two Bags Of Chips 😭", opening on "I want two bags of chips from that vending machine", ending on the handover. "xQc Can't Work Here For Life" (374) → "Why is xQc's *photo* on this wall?", opening on the photo. "Nobody Believed xQc's Booby Traps" (25) → "xQc Booby-Trapped His Apartment… Then The Cops Raided It 💀", only if the raid is in the footage. "When Your Homie Gets Grounded Mid-Robbery" (101) had the right premise but opened on "he got OG ordered": start on "his OG told him not to go" with a `*HIS MOM*` label.
- Caveat: title effects only, and the hypothetical numbers come from story-game channels; `clipper stats` reports our own uploads by title frame as they settle.

## Text over the game (2026-11-19)
In split layout the hook hung from the seam into the game and the captions sat mid-game: hook plus a 3-word caption inked 22-28% of the gameplay area and spanned 28-49% of its height. The hook now stands on the seam over the facecam's lower third, captions are 1-2 words on the game's top edge, sizes are ~30% smaller (big hook 112 → 72 px, boxed captions 116 → 80 px) and the game zoom is 1.1x instead of 1.3x (1.3 cropped out signs): 3-4% ink, and only the caption touches the game (its top 10%). `"captions": false` turns speech captions off for a source with its own burnt-in subtitles.

## Why our Shorts stall near 1-2k views (2026-11-16)
Our channel (50 public Shorts, 11 subs): median 1,191 views, none past 10k (best 8,960). Nearly every upload stops at 1,100-1,800: YouTube's first test audience, then no push. Compared against clip channels on the same streamers and server, measured the same way (frames every 3 s, Apple Vision for faces and text):

| | Median views | Passes 10k | Layout | Hook banner | Cuts per 10 s |
|---|---|---|---|---|---|
| Spaceboy Shorts / Cheeto Head (1M+ sample) | 1-3M | 100% | full-screen gameplay, no facecam | big bold premise at the top | 3.5 |
| Variety Roleplay (3.6k subs, xQc NoPixel clips) | 22,500 | 74% | big face top half, tight gameplay crop | none, word-by-word captions only | 0.85 |
| Us | 1,191 | 0% | face top, wide gameplay | small white box mid-screen | 0.23 |

- **The swipe decides it.** Of our analytics metrics, the share of viewers who stay past the first moment (engaged views / views, ~53%) tracks views best (Spearman +0.47, n=23); average % viewed +0.22; 3-second hold +0.04. In the Shorts feed the first frame and sound are judged before the title is read.
- **Titles barely matter after posting.** Retitling 9 weak Shorts on Nov 15 added +0 to +7 views a day to the older ones; only uploads still in their first test moved.
- **Zero shares** on every one of our Shorts with analytics: nothing in them is worth sending to a friend.
- **Same streamer, same server, 20x the views:** Variety Roleplay clips the same xQc NoPixel stream we do, so the topic isn't the bottleneck. They show a bigger face, crop the gameplay tight on the characters, and post no hook banner at all.
- **Weak moments get posted.** Our bottom Shorts open on a car driving, a dark room or a black screen; the 1M+ ones open on something visibly absurd happening.

## Story-game Shorts outliers: Red Dead 2, GTA and similar (2026-11-18)
**Method.** 15 YouTube API searches (Red Dead Redemption 2, RDR2 Arthur Morgan, GTA 5 / San Andreas, Skyrim, Elden Ring, Cyberpunk 2077, The Last of Us, God of War, Ghost of Tsushima, Spider-Man, Fallout, Minecraft, Hogwarts Legacy), Shorts posted since Nov 2025, kept at **100K+ views and 20K+ likes** (503 Shorts, 250 channels). Each was compared with the median of the 30 Shorts its channel posted around it: **306 beat their channel by 5× or more** (195 channels; some multipliers are huge because the channel's normal is tiny). 20 representative outliers, weighted to Red Dead and GTA, were downloaded and measured: on-screen text (Apple Vision at 0.3 s, 1.5 s, every 2 s), faces, and a full transcript (Parakeet) to tell narration from game audio. Data: `gaming-shorts-outliers.json`.

**Formats (by title, 306 outliers vs 196 below 5×):**
| Format | Outliers | Below 5× |
|---|---|---|
| Story / character moment ("Jack Took Books Too Seriously", "The Moment Joel Found Out") | 19% | 6% |
| Then vs now / comparison ("RDR1 vs RDR2", "PS3 vs PS4 vs PS5") | 14% | 11% |
| Meme / relatable joke ("Men are so hard to gift… Me: GTA fans") | 10% | 9% |
| Hidden detail / easter egg ("The Devs Knew We'd Notice This") | 9% | 2% |
| List / top N ("3 largest animals you can hunt") | 3% | 0% |
| Median length | 30 s | 59 s |

**Three mechanisms, measured on the 20:**
1. **Narrated "did you know" (Fish Audio territory).** A voice talks over 95–100% of the runtime, with word-by-word captions on full-screen footage. These run *long* and still explode: "Seven years later… a new mystery in RDR2" (148 s, 18.1M views, 13,000× its channel), "Did you know GTA San Andreas girlfriends give you cool benefits?" (108 s, 12M, 569K likes), "Here are the three largest animals you can hunt in RDR2" (41 s, 8M), "RDR1 vs RDR2 hidden details" (44 s, 3M), the Fallout 4 voice-acting fact (17 s, 4.7M). **The first spoken line is the whole promise:** a time + discovery ("Seven years later, they've just uncovered…"), "Did you know [surprising benefit]", "Here are the N [biggest/best]…", "If you [do X], [unexpected result]". Each item is a payoff, and the best is saved for last. Viewers get social currency: a fact to repeat or a secret to try themselves.
2. **Wordless character moment.** 6–24 s, one beloved character doing one human thing, no narration, almost no text: "Arthur Morgan Loves Jellybeans" (8 s, 13.5M), "Jack Took Books Too Seriously" (20 s, 26M), "Javier Wants Jack To Go Play" (24 s, 6.6M), "Arthur take his last breath" (7 s), "The Moment Joel Found Out" (23 s, 9.2M), "Five Finger Fillet" (39 s, 80M). The character's face is the face; attachment from a 60-hour story does the work, and the clip loops before you notice.
3. **Text-only surprise over music.** A caps statement at the top, no speech: "THE DEVELOPERS ACTUALLY PUT THIS IN THE GAME" (18 s, 7.2M, 294K likes), "WHAT IN THE ELDEN RING?!" (30 s, 4.8M), "When your hotbar is set up wrong…" (34 s, 102M). A statement of surprise, never a negation.

**Compared with ours:**
| | Story-game outliers | Ours (streamer clips) |
|---|---|---|
| Who is the "face" | A game character in close-up (Arthur, Sadie, Joel), full vertical frame | The streamer's facecam on top |
| Narration | Half of the 20 have a voice explaining (5 of them 95%+ of runtime) | None |
| Opening line | The promise itself ("Did you know…", "Here are the 3…", "Seven years later…") | Whatever the streamer says first |
| Length | 30 s median; narrated lists 40–148 s; character moments 6–24 s | 25–35 s |
| Payoff | Knowledge to repeat, or an emotion about a character people love | A funny reaction |
| Comments per 1K views | 0.19 (they're watched and liked, not argued about) | ~0 shares, few comments |

**Our concepts:**
1. **NoPixel lore explainers (Fish Audio narrator):** "Did you know xQc's Jean Paul is banned from the tow yard for life? Here's why." Our stream footage under a narrator who tells the story in 35–60 s, word-by-word captions, the best beat last. The facecam still shows when xQc reacts.
2. **"Did you know" GTA 6 / GTA 5 facts (gta6 profile):** "Here are the 3 things GTA 6 copied from Red Dead 2" over trailer footage plus a streamer's reaction face, narrated.
3. **Then vs now:** "xQc in NoPixel 3.0 vs NoPixel 4.0 vs 5.0", the same situation across years, labelled with the year like the "480p / 2001" outliers.

**Execution (concept 1):**
- 0.0–1.5 s: the narrator's first line *is* the hook, in the "Did you know / If you / N years later" form, over the most striking frame (the facecam reacting, or the crash).
- Body: 3 beats, each a payoff (what happened → why → the twist), word-by-word captions, footage changes with every sentence.
- End: the best fact last, then a one-line loop back to the opening ("…and that's why he can never work there again").
- Voice: Fish Audio (the clipper's `voiceover` field and `voice: auto` already wire it in; the key comes from `clipper voice-setup`); game audio ducked under it.
- Length: 35–60 s (narrated outliers hold attention longer than reaction clips).

**Test:** post 3 narrated explainers next to normal clips of the same stream. Compare the share who stay past the first moment, average % viewed and shares at 48 h. If narrated clips keep more viewers past the first moment, make every clip whose moment needs context a narrated one; if not, keep narration only for lore stories.

## 500K+ gaming clip Shorts vs ours (2026-11-17)
45 streamer-gaming Shorts with 500K+ views (0.5M-29M), posted since May 2026 by third-party clip channels like ours (Zylok, Stream Vortex, Snickerly, iboclips, OnShortz, DaPlug...), at most 3 per channel; art, animation, ranking compilations and non-English Shorts left out. Found through the YouTube API (16 searches by view count), each one downloaded and measured with Apple Vision (on-screen text at 0.3 s, 1.5 s and every 2 s; face size at 0.3 s), then the banners checked by eye on a contact sheet. Ours: all 47 uploads, measured the same way. Data: `clip-hooks-500k.json` (no media kept).

| | 500K+ clip Shorts | Our top 5 (2k+ views) | Our other 42 |
|---|---|---|---|
| Face on screen at 0.3 s | 40 of 45 (89%) | 3 of 5 | 26 of 42 (62%) |
| Face size at 0.3 s (share of frame) | 0.041 | 0.015 | 0.021 |
| Hook banner on screen | 10 of 45 (22%) | 5 of 5 | 42 of 42 |
| Asterisk context captions | ~11 of 45, mostly in quiet stretches | 0 | 0 |
| Length (median; 30 s or less) | 23 s; 32 of 45 | 23 s; 3 of 5 | 32 s; 20 of 42 |
| "NOT / NEVER / can't / nobody" in the title | 1 of 45 | 3 of 5 | 21 of 45 |
| Question title | 0 of 45 | 0 of 5 | 12 of 42 |
| Emoji in the title | 43 of 45 | 3 of 5 | 27 of 42 |
| Streamer named first | 44 of 45 (Kai 11, CaseOh 6, Speed 6) | 4 of 5 (all Kai) | most (xQc) |
| Two or more streamers named | 17 of 45 | 0 | few |

- **The hook is the face, not a banner.** Nearly every 500K+ clip opens on the streamer's face mid-reaction, about 2-3x bigger in frame than ours. Only 1 in 5 has a banner; the rest rely on word-by-word captions. When a banner is there it states the setup plainly ("CHAT TOLD CASEOH TO SPAM THE KITTY...", "HE ASKED THEM TO SPELL OBESITY", "SPEED IS IN GTA 6?!").
- **Titles narrate what happened.** "[Streamer] [past-tense verb] [what happened]! 😭": "Kai Cenat Finds ICE SPICE In GTA 5 😂", "Jamal Tried To Kill Kai Cenat When IShowSpeed Went AFK! 😂✌️", "Speed Realizes How Bad Kai Cenat Is In Roblox 😭🤣". Almost none use our negation or question formulas (1 of 45 vs 24 of 50 of ours), so those rules, measured on creators' own channels, don't carry over to clip channels.
- **Who is in it.** Kai Cenat, IShowSpeed and CaseOh lead, and clips pairing two big streamers (Kai + Speed) reach tens of millions. That matches ours: 4 of our 5 best Shorts are Kai.
- **Where we already match:** our top 5 have the same 23 s median as the 500K+ clips. Our other uploads run longer (32 s).
- **Asterisk captions are a minority tool in gaming:** about 1 in 4 of the 500K+ clips (`*CONFUSED*`, `*FOLLOWS*`, `*LAST MISSION*`), mostly over silent stretches. The two references that use them throughout are non-gaming (NFL, sneaker convention).

## Hits vs flops inside the same channel (2026-11-14)
From the 3,481-Short dataset, the 3 highest-lift and 3 lowest-lift Shorts from each of 19 channels (104 downloaded and measured; data in `hits-vs-flops.json`, no media kept). Same channel = same face, audience and editor, so only the video differs. Frames were measured automatically: cuts and flashes from frame differences, on-screen text and faces with Apple Vision every 3 s. Titles were labelled blind (the hit/flop group hidden) for emotion, arousal, concrete stake and verdict question. "Channels" counts how many channels' hits had more of the feature than their flops. With 17 channels, none of these is statistically conclusive alone; read them as directions.

| Feature | Hits (median) | Flops (median) | Channels where hits > flops | Reading |
|---|---|---|---|---|
| Length | 48s | 53s | 5 of 17 (hits shorter in 12) | ≤30s: 15 hits vs 6 flops. Shorter wins |
| Cuts per 10 s | 3.0 | 4.3 | 5 of 17 (hits cut less in 12) | Fast cutting doesn't help; let the moment play |
| Flashes per 10 s | 0 | 0.16 | 7 of 8 | No effect. Lime flashes in 3 hits vs 5 flops |
| Face on screen | 86% of frames | 68% | 11 of 4 | Keep the face visible |
| Text on screen (after 3 s) | 77% of frames | 70% | 11 of 6 | Captions all the way through |
| Hook text in the first second | 1 | 1 | 7 of 3 | Nearly all (88 of 104) have it |
| High-arousal title | 21 of 57 | 18 of 57 | | Barely different |
| Concrete stake in title | 18 of 57 | 17 of 57 | | Barely different |
| Curiosity/suspense title | 10 of 57 | 5 of 57 | | Leans hit |
| Ad or plain-info title | 12 of 57 | 22 of 57 | | Leans flop |

**What it means for our clips:** what the video shows decided more than how the title sounds. The hits show the person's face throughout, run shorter, cut less and caption throughout. A title's emotion or stake barely separated hits from flops *within* a channel, but a curiosity gap did, and so did avoiding ad or info wording. Flashes made no difference, so they stay as accents for a payoff, not a driver. This doesn't contradict Berger & Milkman (2012: high-arousal emotions such as awe, anger and anxiety get shared more; sadness gets shared less): the arousal has to be in the moment itself, which the title points at and the face delivers.

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

## Zylok teardown (5 Shorts, 2026-11-12; hypotheses until our own uploads measure them)
Zylok (703k subscribers) posts 17–29s streamer clips; the median of their last 60 Shorts is ~560k views. Each clip was watched frame by frame with its audio.

| Short (views, x channel median) | Length | What happens | The moves |
|---|---|---|---|
| "Agent00 Is Shocked By The New Tesla Roadster's Acceleration! 🤯" (4.07M, 7.3x) | 17s | A launch, his face, the car keeps going | Cold open on the launch; ends on the result (the speed) and his face; meme music under the speech-free stretch |
| "Kai Cenat Finds Out What NPCs Do After Completing A Mission! 😭" (2.63M, 4.7x) | 25s | Big Smoke walks off after a mission, Kai follows him | Action labels in lime (`*FOLLOWS*`, `*RUNS*`, `*TURNS*`) carry the silent chase; a meme track (the Skyrim theme) under 7–12s and 13–18s; captions censored (`SH*T`, `F*CK`); ends on the reveal |
| "Ray Betrayed Him! 😳" (1.51M, 2.7x) | 29s | A betrayal plays out | Music under the whole clip; ends on the betrayal itself, the title withholds who and how |
| "Agent Thinks GTA 6 Story Mode Will Only Last A Week! 🤔" (335k, 0.6x) | 28s | A take, no visible result | A claim with no payoff on screen; no reveal to end on |
| "Kai Cenat Decides Who To Kill in GTA 5! 😭" (81k, 0.14x) | 26s | Kai talks through the Trevor/Michael/Deathwish choice and picks | Ends on the decision (the phone's "Kill Trevor"), never the death; the lime flash and censored captions (`@SSHOLE`, `F*CK`) couldn't save it |

**The moves, in order of how much they seem to matter**
1. **End on the result, not the decision.** The two winners end on what happened (the speed, the NPC's walk); the two weakest end on a choice or a take. If the stream shows the outcome later (the death, the crash, the reveal), cut it on as the last segment with a result label (`*MICHAEL DEAD*`). The hook and title must not say the outcome.
2. **Cold open on the first meaningful word:** no "so", "um", "great, the…". The premise lands in the first second.
3. **No on-screen hook banner.** All 5 rely on the title and the first line. We test this: 1 in 3 of our clips post with no hook (`no_hook_share`), recorded as `hook_type: "none"`.
4. **Captions: one big word at a time, swears censored by masking a vowel** (`F*CK`, `SH*T`, `@SSHOLE`), audio untouched, names spelled right (Trevor, Michael). Action labels in lime fill silent stretches.
5. **Edit effects on beats:** a lime flash on the payoff, punch-in zooms on shouted lines. Cheap and frequent, never long.
6. **Music under the quiet stretches, a sound hit on the reveal.** Meme tracks (game themes) are Content ID claimable: a track is only used once the user approves it (`assets/music/library.yaml`, `approved: true`), and claimable ones stay off until `music.allow_claimable: true`.
7. **No dead air:** any 2s+ gap with no word or label gets cut with segments.

**Music found in the reference clips** (candidates awaiting approval; nothing is downloaded until the user approves each one): see "Reference music" below.

### Reference music (2026-11-12; candidates, none approved or downloaded)
Each clip's audio was split with demucs (`htdemucs --two-stems vocals`, the `no_vocals` stem) and read from spectrograms plus an onset-tempo estimate. No open fingerprinter (`songrec`) is installed, and the macOS `shazam` tool only builds signatures (no lookup), so only one track is named, from the user's own identification. Every one is a game theme or a meme track, so it's `claimable: true`.

| Clip | Where | What the stem shows | Track | claimable |
|---|---|---|---|---|
| NPCs after a mission (4.7x) | 6.7–18s, under the silent chase | Dense orchestral bed starting on a hard cut at 6.7s, ~99 BPM pulse | The Elder Scrolls V: Skyrim main theme ("Dragonborn"), named by the user | true |
| Tesla Roadster (7.3x) | kicks from 0s, full track 6.9–17s | Regular kicks (~81 BPM half-time), then a broadband swell on the launch | Unidentified beat (phonk/trap style) | true |
| Ray Betrayed Him (2.7x) | whole clip | Repeating ~1.9s harmonic pattern, ~89 BPM, under the speech | Unidentified suspense loop | true |
| Agent: story mode (0.6x) | whole clip | A melodic lead with vibrato at 1–2 kHz | Unidentified (may be the stream's own background music) | true |
| Kai decides who to kill (0.14x) | whole clip | Steady sustained harmony at 0.5–1.1 kHz, ~78 BPM | Unidentified (likely the GTA V menu/score from the stream) | true |

To use one: the user approves it, its file goes into `assets/music/local/`, and it's added to `library.yaml` with its mood (Skyrim theme: `epic`; the Tesla beat: `epic`; the Ray loop: `suspense`), `claimable: true` and `approved: true`. It still only plays once the profile sets `music: {allow_claimable: true}`.

## Zylok channel survey (25 Shorts, 2026-11-12; measured by script, then checked on contact sheets and spectrograms)
The channel has 2,866 Shorts with a median of 159k views. We took the 15 most viewed (22M–66M, 138–415x the median) and the 10 most recent (days old, 0.5–4.9x, so their views haven't settled yet). Each was downloaded at 480p. The audio was split with demucs (htdemucs, the vocals stem vs the rest). Video cuts came from ffmpeg `scene>0.35`. Flashes are brief (≤0.4s) jumps in luma (white) or in one colour channel (tint). Shake was measured by phase correlation at 216x384, ignoring the caption band; a freeze is ≥0.35s of almost no frame change. Sound effects are onsets in the no-vocals stem that **don't** fall within 0.12s of a video cut (most raw onsets were just the stream audio jumping at a cut). A boom is a 30–90 Hz rise ≥10 dB that is still ≥4 dB up 0.6s later; a hiss/whoosh is a 3–9 kHz rise ≥10 dB with no sub-bass rise. Music means a periodic beat (onset autocorrelation ≥0.3 over two 4s windows). That test misses non-percussive beds such as the Ray suspense loop above, so the music share is a floor.

| Move | Clips with it (25) | Top 15 | Recent 10 | Built? |
|---|---|---|---|---|
| One word at a time captions + `*ACTION*` labels (`*GRABS*`, `*SHOCKED*`, `*LAUGHING*`, `*CONFUSED*`) | 25/25 (contact sheets) | 15/15 | 10/10 | yes |
| Colour tint flash (red/orange 12, lime 6, purple 4 of 23; 1–3 frames, on a reaction or a cut) | 14 | 8 | 6 | partly: `flash` is lime only |
| White flash (on a cut or the payoff) | 12 | 8 | 4 | no (lime only) |
| Either flash | 19 (76%) | | | |
| Sub-bass boom off a cut (vine-boom / bass-drop shape) | 14 (56%) | 9 | 5 | yes: `boom`, `hit` |
| Short sub thump, no tail | 5 (20%) | 2 | 3 | yes: `hit` |
| Hiss / whoosh off a cut | 5 (20%) | 3 | 2 | yes: `whoosh` |
| Music with a beat | 5 (20%; ~4 added by the editor, km0e's beat is the stream's own challenge) | 3 | 2 | yes: music beds, approval gated |
| Punch-in zoom on a face (visible on 6 of 7 sheets we read; the scale-match detector found 2) | most | | | yes: `zoom` |
| Camera shake (editor jitter) | 0 (the 2 detections were handheld IRL footage) | 0 | 0 | no |
| Freeze frame | 0 (the 1 detection was a white transition frame) | 0 | 0 | no |
| Split screen (two speakers stacked) | 1 (wWP8) | 1 | 0 | no |

**What the numbers say**
- **The booms are the channel's sound.** There's 0.52 boom per 10s of clip, so about 1 per 19s, never more than 3 per clip. They're spread across the clip (7 in the first third, 9 in the middle, 9 at the end) and land on a punchline or a reaction. 7 of 25 coincide with a flash. So most clips get 1–3 booms, not one on every line.
- **Flashes are cheap and frequent, but the colour varies:** white on hard cuts and the payoff (12 clips), and a coloured wash on a reaction or a cut. Of the 23 tint flashes, 12 are red/orange, 6 lime, 4 purple and 1 neutral. Lime (what `flash` draws today) is in the mix but isn't the main colour; white and red/orange together cover most flashes.
- **Music is the exception, not the rule:** about 1 clip in 5, and then it's matched to the moment. m_Voeg ("Really Needed This", 220x) has a soft emotional bed and a desaturated look. HkyeWQ ("Peekaboo", 189x) has a playful loop under a clip that's 59% speech-free. gZ7p ("New Ram 3500" reveal) has a hype beat. The other 20 run on the stream's own audio plus booms. Talk-heavy clips (voice ≥90% of the time) almost never get music.
- **No shake, no freezes.** Neither cleared the 20% bar, so neither was added to the renderer.
- Top-15 clips cut a little faster than recent ones (0.40 vs 0.31 cuts/s) and carry a few more booms and white flashes. That's 15 vs 10 clips, so it's a hint, not a measurement.

**Music candidates from the survey** (none named, none approved or downloaded). No description credits a track, there's no `track`/`artist` metadata, and no open fingerprinter is installed. We didn't send audio to an online recogniser without the user's go-ahead. What the stems show:

| Clip (x median) | Where | What the stem shows | Mood | claimable |
|---|---|---|---|---|
| m_Voeg4izes "Rakai Really Needed This" (220x) | 0–15s, fades out | Steady ~107 BPM pulse, soft, under the speech | sad | true (unidentified) |
| HkyeWQIhaUQ "Tota Playing Peekaboo" (189x) | 1.5–9s | ~67 BPM playful loop in the speech-free gaps | funny | true (unidentified) |
| gZ7pHhbO2-I "Fanum Reveals His New Ram" (0.6x, days old) | 0–18s | ~80 BPM hip-hop beat with sub kicks under the reveal | epic | true (unidentified) |
| kFP4nOHiSeQ "Reggie Hates Tylil" (4.9x, days old) | ~12–15s, the end | ~133 BPM beat comes in on the payoff | funny | true (unidentified) |

Since none is named, there's nothing specific to approve. To use these moods, the user picks royalty-free or CC0 tracks per mood (or names one), and each goes through `library.yaml` approval as before.

**Rule of thumb for our clips** (in `.claude/commands/clip.md`): a boom or hit on the payoff and on the 1–2 biggest reactions (≤1 per 4s); a flash on the payoff; zooms on shouted lines; music only on a 2s+ speech-free stretch or an emotional or tense build, in the mood of the moment; nothing on a clip that's already loud or wall-to-wall talk.

### CC0 mood tracks (2026-11-12; candidates awaiting the user's approval, nothing downloaded)
FreePD (the usual public-domain source) has shut down. These are from OpenGameArt, and the licence on each track page was checked as CC0 (Quirky Jazz is dual CC0 / OGA-BY; we'd take CC0). They'd go into `assets/music/` with `claimable: false` once approved. CC0 means no Content ID registration by the author, but a third party can still wrongly claim a CC0 track, so watch the first uploads.

| Mood | Track (author) | Page | Fits the survey's |
|---|---|---|---|
| sad | Emotional piano loop (extenz) | https://opengameart.org/content/emotional-piano-loop | m_Voeg soft emotional bed |
| funny | Quirky Jazz (Spring Spring) | https://opengameart.org/content/quirky-jazz | Peekaboo playful loop |
| funny (alt) | Catch me if you can! (poinl) | https://opengameart.org/content/catch-me-if-you-can | goofy chase |
| epic | Determined Pursuit, epic orchestra loop (Emma_MA) | https://opengameart.org/content/determined-pursuit-epic-orchestra-loop | big launch / reveal |
| epic (alt, hype beat) | Trance / trap / electronic (Dizzy Crow) | https://opengameart.org/content/trance-trap-electronic-237 | Ram 3500 reveal beat |
| suspense | Night of the Streets (nene) | https://opengameart.org/content/night-of-the-streets-horrorsuspense | build before a reveal |
| sneaky | Acid Detective (obscure music) | https://opengameart.org/content/acid-detective | silent follow / chase |
