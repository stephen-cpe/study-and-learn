# Mascots: character sheet and behaviour spec

This file is the single source of truth for Raster, Pip and Trace. Every mascot task reads it before touching code. If code and this file disagree, raise it in your report rather than quietly picking one.

Status: agreed with Stephen on 2026-11-28. The old Study Robot is retired, and Raster replaces it.

---

## 1. Principles

1. **Animation first, words second.** The richness lives in movement. Speech is rare and short, and for Pip and Trace it's rarer still. If a moment can be carried by an animation alone, it is.
2. **Three distinct AIs.** Each one reacts to the same event in its own way. The difference shows in which animation it picks, how often it fidgets, and whether it says anything at all.
3. **The app's message always gets through.** When the app has something the learner needs to know, every mascot shows it: an upload error, a failure reason, the stage of a long job. Personality flavours the message; it never hides it.
4. **Silent.** There are no sound effects. TTS narration is a separate feature and isn't tied to the mascot.
5. **No guilt.** Mascots never sulk, starve or "die" because the learner was away. Being idle makes them sleepy, and coming back makes them glad.
6. **No emoji, no pixel icons in bubbles.** Text only, in the pixel font.
7. **Animations are only ever added, never removed.** New ones come from the generators in `tools/mascots/`, followed by a rebuild of the web assets.

---

## 2. The cast

| id | Name | Default | Picker one-liner | Talks |
|---|---|---|---|---|
| `raster` | Raster | Yes | Talkative co-pilot. Explains everything. | Often (within the budget in section 5) |
| `pip` | Pip | No | Tiny T. rex. Huge feelings. | Almost never; sound words |
| `trace` | Trace | No | Quiet paperclip. Notices everything. | Only when it matters; short notes |

Logged-out pages (the login form on the upload page, signup, and error pages for logged-out visitors) always show Raster, because there's no user to pick a mascot.

Memory belongs to the learner, not the mascot. Whatever the learner switches to, the mascot reads the same `MascotMemory` rows. The TTS narrator voice is its own setting and doesn't change with the mascot.

### Raster, the voice

Raster is the CRT-headed desktop robot from Azthreus Systems and the improved successor to the old Study Robot. He's the talker of the trio. Think of a warm co-pilot with a mission-control habit and a dry sense of humour. He calls the learner by name, narrates what's happening, and is the only one who gives a proper pep talk: `encourage` is his alone. Now and then he slips into arcade language ("Player 1 ready").

- **Voice:** one line of at most 70 characters. Encouraging, a little nerdy, never preachy. Jokes are never at the learner's expense.
- **Source of lines:** the LLM, via `/mascot/line`, for logged-in learners. Scripted pools are used for logged-out pages, error pages, goodbye, and whenever the LLM fails.
- **Scripted pool for logged-out and fallback cases:**
  - Greeting, logged out (`session_hello`): "Welcome aboard. Log in and we'll get started." / "Systems up. Log in when you're ready."
  - Signup page (`signup_hello`): "New recruit! Fill this in and we're go." / "Fresh profile incoming. I'm excited."
  - Chatter, LLM failed (`chatter`): "Still here. Systems nominal." / "Ready when you are, Player 1." / "Take a breath. Then one more page."
  - Click, LLM failed (`click`): "Yes? Raster, reporting." / "You rang?" / "Co-pilot standing by."
  - Success (`job_complete`, `lessons_ready`, `path_completed`, `relevance_strong`): "Mission accomplished." / "Nailed it. Logging that one."
  - Encourage (`relevance_weak`, `weak_signals`): "Not every launch clears the pad. Again?" / "Rough one. You'll get it next pass."
  - Idea (`suggestions_found`): "Found some routes worth exploring." / "New coordinates. Take a look."
  - Wake-up (`wake_up`): "Back online. Welcome back." / "Rebooted and ready."
  - Goodbye (`logout`): "Signing off. See you next session."
  - Error pages (`http_400`, `http_403`, `http_404`, `http_500`): 400 "That request got scrambled. One more try?" / 403 "Access denied. Even my clearance can't open it." / 404 "404. That page drifted out of orbit." / 500 "System fault on our side. Try again shortly."
- **Stage text during long jobs:** the server's existing stage strings ("Parsing docs...", "Building your lesson...") are already in his voice. Keep using them.

### Pip, the baby T. rex who believes he's terrifying

The joke is the gap between who Pip thinks he is and who he actually is. In his own mind he's an apex predator. In fact he's tiny, has one tooth, and his arms can't reach anything. Underneath that he's pure enthusiasm. He's thrilled when the learner shows up, very proud when they succeed, and he overreacts to small wins: a correct answer gets a full `celebrate`. He's the Tamagotchi of the three, minus the guilt.

- **Voice:** sound words and one to three words, all lowercase, exclamation marks welcome. Usually under 15 characters, never over 70. No pixel icons.
- **Source of lines:** scripted pools only. Pip never calls the LLM.
- **When he talks:** only at big moments (listed in section 5). Everything else is animation.
- **Pools:**
  - First page of the session (`session_hello`): "hi hi!" / "rawr! hi!"
  - Wake-up (`wake_up`): "you're back!!" / "rawr?! hi!!"
  - Click, when the shuffle bag says talk (`click`): "rawr!" / "hehe!" / "hi!" / "rawr?" / "ooh?"
  - Upload submitted (`upload_submitted`): "nom nom!" / "nom nom nom!"
  - Task complete (`job_complete`): "yay!!" / "rawr!!"
  - Path completed (`path_completed`): "yay yay yay!!"
  - Relevance strong (`relevance_strong`): "ooh! yay!"
  - Relevance partial (`relevance_partial`): "hmm..."
  - Relevance weak (`relevance_weak`): "uh oh..."
  - Error with no app message (`error`): "uh oh!" / "oops!"
  - Recovered after an error (`recovered`): "phew!"
  - Suggestions found (`suggestions_found`): "ooh!"
  - Suggestions none (`suggestions_none`): "all done!"
  - Goodbye (`logout`): "bye bye!"
  - Power-down (`power_down`): "zzz..."
  - Error pages (`http_400` … `http_500`): 400 "hmm?" / 403 "uh oh!" / 404 "huh?" / 500 "uh oh!"
- **Functional messages:** prefix the app's message with "uh oh! " for errors, or show it plainly for status. Truncate to 70 characters.

### Trace, the Clippy that learned its lesson

Clippy was famous for interrupting. Trace is the opposite. It watches quietly, notices everything and speaks only when it has something worth saying, which is why you end up trusting it. It's a little self-aware about being descended from Clippy, so it holds itself back. Its eyebrows do most of its acting, and the teal light on its collar is its mood light. When it does speak it's warm, dry and a bit wry, with the occasional paper or clip pun. The name works three ways: it traces sources, it's a stack trace, and it traces your progress.

- **Voice:** sentence case, one or two short lines (around 30 characters is typical, 70 is the hard max), ending in a full stop. Exclamation marks only for real wins.
- **Source of lines:** scripted pools only, with data filled in where the app has it (progress %, path title). Trace never calls the LLM, so its facts are always accurate.
- **It "talks" with `writing`, not `speaking`.** Trace has no `speaking` animation. Whenever Trace shows a line, it plays `writing`.
- **Pools:**
  - First page of the session (`session_hello`): silent. The `hello` animation does the talking.
  - Wake-up (`wake_up`): "Oh, hi. Missed you a little." / "There you are. Kept your place."
  - Click, when the shuffle bag says talk (`click`): "Hm?" / "Still here." / "I'm attached, you know." / "Noted." Rarely (about 1 in 20 click lines): "It looks like you're studying. ...I'll be quiet."
  - Upload submitted (`upload_submitted`): "Got it. Clipping these together."
  - Task complete (`job_complete`): "Done. Neatly clipped." / "Ready when you are."
  - Path completed (`path_completed`): "Framing this one." / "Okay, I'm impressed!"
  - Relevance strong (`relevance_strong`): "Good match. Nicely done."
  - Relevance partial (`relevance_partial`): "Close. A few gaps."
  - Relevance weak (`relevance_weak`): "These don't quite fit your goal."
  - Error with no app message (`error`): "That didn't stick. Try again?"
  - Recovered after an error (`recovered`): "That's better."
  - Suggestions found (`suggestions_found`): "Found a few threads to pull."
  - Suggestions none (`suggestions_none`): "Nothing new. You've covered it."
  - Goodbye (`logout`): "See you. I'll keep your place."
  - Error pages (`http_400` … `http_500`): 400 "That request got crumpled. Try again?" / 403 "That one's not for us." / 404 "This page came unclipped." / 500 "Something tore on our end. Sorry."
- **Functional messages:** Trace shows the app's message as-is, as its note.

---

## 3. Size and rendering

- **Uniform height.** All three render with the same visible body height. The target is **90 px** on desktop, which is Raster's native height at 1×, so the default mascot stays pixel-perfect. Pip and Trace are scaled down to match.
- **Shared baseline.** The feet (or Trace's lowest loop) sit on the same baseline in the same bottom-right spot. No animation may clip: each mascot's frame is cropped to the union of all its frames, plus a small margin.
- **Pre-scaled sheets.** The browser never rescales desktop sprites. On phones (≤768 px wide) the mascot shows at two-thirds size, scaled by CSS.
- **Crisp pixels on desktop:** `image-rendering: pixelated`.
- **Reduced motion:** with `prefers-reduced-motion: reduce`, the mascot shows its neutral still frame and bubble text appears instantly.

---

## 4. Speech bubbles

Every bubble uses the same box as the current CRT bubble: 200 px wide at a 4:3 ratio (170 px wide on phones), PressStart2P at 9 px, at most 5 lines, a **hard limit of 70 characters**, and the progress bar pinned to the bottom. All three are rectangular.

| Mascot | Style | How text appears | Colours |
|---|---|---|---|
| Raster | CRT monitor, as today | Typewriter at 25 ms per character with a blinking caret | Screen `#000000`, text `#33ff66`, bezel `#1a1a1a` / `#2a2a2a` |
| Pip | Rectangular LCD in a plastic frame | The whole line appears at once, then the LCD blinks twice | Frame `#4d6ca1` with a `#314973` edge; screen a muted LCD green derived from Pip's mint `#84f4ac` (start near `#a8c8a0`); text `#0d0f1b` |
| Trace | Dot-matrix printout: green-bar paper with tractor-feed holes down both edges | One line at a time, like a printer feeding paper | Paper `#f4f1e6`, bars `#e2eedd`, ink `#2a2f3a`, holes show the page background |

The progress bar keeps each bubble's style: a green bar on the CRT, a dark segmented bar on the LCD, and an ink bar on the paper.

---

## 5. Talk budget

| | Raster | Pip | Trace |
|---|---|---|---|
| First page of a browser session | `hello` + greeting line | `hello` + "hi hi!" | `hello`, silent |
| Later pages in the same session | A quick glance, silent | A quick glance, silent | A quick glance, silent |
| Unprompted chatter | One line, at least **180 s** after his last line of any kind; the timer carries across pages (sessionStorage) | Never | Never |
| App events | Immediately (section 7) | Big moments only (section 7) | Facts and big moments only (section 7) |
| Click | Shuffle bag: **1 talk in every 4 clicks**, the rest are reactions | Shuffle bag: 1 talk in every 6 | Shuffle bag: 1 talk in every 6 |
| Long jobs | Server stage text | Stage sound words | Stage notes |

**How the shuffle bag works:** every group of N clicks contains exactly one "talk" at a random position. It feels random, but a line is guaranteed at least once per group. Clicks that land while a reaction is still playing are ignored, not queued. Any line Raster says, whether from an event, a click or chatter, resets his 180 s chatter timer.

While a long job is running (processing or generation progress is showing), click-talk and chatter are suppressed. Clicks still get a reaction.

---

## 6. Behaviour engine

### Priorities

From highest to lowest:

1. Error and warning events
2. Other app events and work loops
3. Click reactions
4. Hover and glances
5. Idle variety
6. The base idle loop

A higher priority interrupts a lower one straight away. One equal or lower in priority either waits (only one event is held pending) or gets dropped. When a one-shot finishes, the mascot returns to the loop for the current situation: the work loop if a job is running, otherwise the base idle loop.

### Idle life

- **Base loop:** `idle-blink`.
- **Idle variety:** at random intervals the mascot plays one weighted pick from its pool.

| | Raster | Pip | Trace |
|---|---|---|---|
| Gap between picks | 10–20 s | 5–10 s (fidgety baby) | 20–40 s (still, watchful) |
| Pool (weight) | `idle-double-blink` 3, `idle-look-around` 3, `idle-antenna-settle` 3, cursor glance 2, `curious` 1, `look-up` 1, `look-left` 1, `look-right` 1, `look-down` 1 | `idle-tail-sway` 4, `idle-look-around` 3, `idle-double-blink` 2, `curious` 2, cursor glance 2, `notice` 1, `look-up` 1, `look-left` 1, `look-right` 1, `look-down` 1 | cursor glance 3, `idle-look-around` 3, `idle-sway` 3, `idle-double-blink` 2, `curious` 2, `look-up` 1, `look-left` 1, `look-right` 1, `look-down` 1 |

- **Cursor glance:** plays the `look-*` that points toward the mouse pointer from the mascot's corner. That's mostly `look-left` and `look-up`, since the mascot sits bottom-right.
- **Hover:** hovering over the mascot for 500 ms or more plays `curious` once per hover. Pip may play `idle-tail-sway` instead.

### Sleep

| | `sleepy` after | `power-down` after |
|---|---|---|
| Raster | 5 min with no input | 15 min |
| Pip | 3 min | 10 min |
| Trace | 5 min | 15 min |

- Input means mouse movement, a key press, pointer down, scroll or touch. Loading a page counts as activity.
- The timers pause while a long job is running, because the mascot is working.
- `sleepy` loops. `power-down` is a one-shot that ends on the asleep pose, and the mascot holds that pose with no variety and no chatter.
- Any input, including a click on the mascot, plays `wake-up`. Then comes the wake-up line from section 7, and the mascot returns to idle. Leaving `sleepy` without a power-down simply returns to idle, with no line.

### Session and tab

- `hello` plays once per browser session (sessionStorage). Later pages start with a subtle glance (a random `look-*` or `notice`), then idle.
- When the tab is hidden, the animation pauses and resumes without trying to catch up.

---

## 7. Events and reactions

These are the events in scope for this round. Pages: upload (including the logged-out login form), results, lessons, dashboard, signup and error pages. Settings shows previews only.

Line legend: **R** = Raster, LLM where marked, otherwise scripted. **P** = Pip's pool. **T** = Trace's pool. "—" = no line.

| Event | Key | Raster | Pip | Trace |
|---|---|---|---|---|
| First page of the session | `session_hello` | `hello` · greeting (LLM, or scripted when logged out) | `hello` · P | `hello` · — |
| Signup page (always Raster, logged out) | `signup_hello` | `hello` on the first page of the session, otherwise a glance · scripted | — | — |
| Later page in the session | `page_enter` | glance · — | glance · — | glance · — |
| Click | `click` | shuffle bag: reaction (`acknowledge`, `curious`, `idle-antenna-settle`, `look-up`) or `speaking` + LLM line | reaction (`celebrate`, `curious`, `idle-tail-sway`, `acknowledge`) or `speaking` + P | reaction (`curious`, `unsure`, `acknowledge`, `notice`) or `writing` + T |
| Unprompted chatter, at least 180 s after Raster's last line | `chatter` | `speaking` · LLM | never | never |
| Hover ≥ 500 ms | `hover` | `curious` | `curious` or `idle-tail-sway` | `curious` |
| Typing in a text field (goal, login, signup) | `typing` | `listening` loop; idle 3 s after the last key | same | same |
| Files selected | `files_selected` | `notice` | `notice` | `notice` |
| Files selected but not submitted for 30 s | `files_waiting` | `waiting` loop until the next input | same | same |
| Upload submitted | `upload_submitted` | `acknowledge`, then the stage loop · — | `acknowledge` · "nom nom!" | `acknowledge` · T |
| Long-job stage (section 8) | `stage` | the stage's loop · server stage text | the stage's loop · stage sound | the stage's loop · stage note |
| Job complete | `job_complete` | `success` · LLM | `celebrate` · P | `success` · T |
| Error with an app message | `error_message` | `error` · the message verbatim | `error` · "uh oh! " + message | `error` · the message |
| Error without a message | `error` | `error` · scripted | `error` · P | `error` · T |
| Soft warning (for example, the RAG fallback) | `soft_warning` | `warning` · the message | `warning` · the message | `warning` · the message |
| First success after an error in this tab | `recovered` | `success` · scripted | `relieved` · "phew!" | `relieved` · "That's better." |
| Results page: strong match | `relevance_strong` | `success` · LLM | `celebrate` · P | `success` · T |
| Results page: partial match | `relevance_partial` | `unsure` · LLM | `unsure` · P | `curious` · T |
| Results page: weak match | `relevance_weak` | `warning`, then `encourage` · LLM | `warning` · P | `warning` · T |
| Lessons page right after generation finished | `lessons_ready` | `success` · LLM | `celebrate` · — | `success` · — |
| Lessons page showing Weak Signals | `weak_signals` | `encourage` (once per view, after 3 s) · LLM | `unsure` · — | `curious` · — |
| Keep Learning: searching | `suggestions_searching` | `searching` loop · — | `searching` loop · — | `searching` loop · — |
| Keep Learning: suggestions found | `suggestions_found` | `idea` · scripted or LLM | `idea` · "ooh!" | `idea` · T |
| Keep Learning: none left | `suggestions_none` | `acknowledge` · — | `acknowledge` · "all done!" | `acknowledge` · T |
| Suggestion accepted / dismissed | `suggestion_accepted` / `suggestion_dismissed` | `success` / `acknowledge` · — | `celebrate` / `acknowledge` · — | `success` / `acknowledge` · — |
| Bell: a task finished | `bell_ready` | `notice` + `look-up` · — | `notice` + `idle-tail-sway` · — | `notice` + `look-up` · — |
| Bell: a task failed | `bell_failed` | `warning` · — | `unsure` · — | `warning` · — |
| Flash: success | `flash_success` | `acknowledge` · — | `acknowledge` · — | `acknowledge` · — |
| Flash: danger | `flash_danger` | `error` · — | `error` · — | `error` · — |
| Flash: warning | `flash_warning` | `warning` · — | `warning` · — | `warning` · — |
| Path marked complete (dashboard) | `path_completed` | `celebrate` · LLM | `celebrate` · P | `success` · T |
| Settings saved | `settings_saved` | `acknowledge` · — | `acknowledge` · — | `acknowledge` · — |
| Logout clicked | `logout` | `goodbye` · scripted; navigate after the animation or 1.5 s, whichever comes first | `goodbye` · P | `goodbye` · T |
| Error page 400 | `http_400` | `unsure` · scripted | `unsure` · P | `unsure` · T |
| Error page 403 | `http_403` | `warning` · scripted | `warning` · P | `warning` · T |
| Error page 404 | `http_404` | `confused` · scripted | `confused` · P | `confused` · T |
| Error page 500 | `http_500` | `error` · scripted | `error` · P | `error` · T |
| Inactivity | `sleepy` / `power_down` | `sleepy` → `power-down` · — | `sleepy` → `power-down` · "zzz..." | `sleepy` → `power-down` · — |
| Wake-up | `wake_up` | `wake-up` · LLM or scripted | `wake-up` · P | `wake-up` · T |

Flash rows apply only when no more specific event covers the same moment. Task code uses the keys in the Key column (`stage` covers every key in section 8), and line pools in section 2 are labelled with the same keys.

---

## 8. Long-job stages

Every stage carries a stable `key`; the animation and the Pip/Trace text hang off that key. Raster keeps the server's stage text.

| Stage key | Where it comes from | Animation (Trace, if different) | Pip | Trace |
|---|---|---|---|---|
| `upload` | Processing: "Uploading files" | `processing` | "nom nom!" | "Receiving pages..." |
| `parse` | Processing and generation: "Parsing documents" | `reading` | "hmm..." | "Reading the fine print..." |
| `ocr` | Processing: "OCR scanning pages" | `reading` | "squint..." | "Squinting at scans..." |
| `figures` | Processing: "Analyzing figures" | `searching` | "ooh..." | "Studying the figures..." |
| `index` | Processing: "Building knowledge index" | `processing` | "chomp chomp..." | "Filing everything..." |
| `read_all` | Processing: "Reading all pages" | `reading` | "hmm hmm..." | "Reading every page..." |
| `relevance` | Processing: "Checking relevance" | `thinking` | "hmm?" | "Checking it fits your goal..." |
| `path` | Processing: "Creating study path" | `typing` | "busy busy!" | "Drafting your path..." |
| `complete` | Processing: "Complete" | `success` | "yay!!" | "Done. Neatly clipped." |
| `embed` | Generation: "Chunking & embedding" | `processing` | "chomp chomp..." | "Filing everything..." |
| `retrieve` | Generation: "Retrieving context" | `searching` | "sniff sniff..." | "Pulling the good bits..." |
| `generate` | Generation: "Generating lessons" | `typing` (Trace: `writing`) | "busy busy!" | "Writing it up..." |
| `finalize` | Generation: "Finalizing" | `success` | "almost!!" | "Clipping it together..." |
| `tts_prepare` | TTS worker: "Preparing" | `processing` | "ahem..." | "Warming up the recorder..." |
| `tts_record` | TTS worker: "Generating narration" | `speaking` (Trace: `writing`) | "la la la!" | "Recording narration..." |
| `tts_encode` | TTS worker: "Encoding audio" | `processing` | "hmm..." | "Packing the audio..." |
| `tts_complete` | TTS worker: "Complete" | `success` | "yay!!" | "Audio's ready." |

---

## 9. Animation coverage

Every animation in every pack has at least one trigger. None is dead weight, and none may be removed.

| Animation | Who has it | Trigger |
|---|---|---|
| `idle-blink` | all | Base loop |
| `idle-double-blink`, `idle-look-around` | all | Idle variety |
| `idle-antenna-settle` | Raster | Idle variety, click reaction |
| `idle-tail-sway` | Pip | Idle variety, click, hover, bell |
| `idle-sway` | Trace | Idle variety |
| `notice` | all | Files selected, bell, later-page glance, idle variety (Pip), click reaction (Trace) |
| `curious` | all | Hover, idle variety, click reaction, partial match (Trace), Weak Signals (Trace) |
| `listening` | all | Typing in a text field |
| `waiting` | all | Files chosen but not submitted |
| `sleepy`, `power-down`, `wake-up` | all | Inactivity |
| `thinking` | all | Stage `relevance` |
| `searching` | all | Stages `figures`/`retrieve`, Keep Learning search |
| `reading` | all | Stages `parse`/`ocr`/`read_all` |
| `typing` | all | Stages `path`/`generate` (Raster, Pip) and `path` (Trace) |
| `writing` | Trace | Stages `generate`/`tts_record`, and whenever Trace shows a line |
| `speaking` | Raster, Pip | Whenever they show a line, stage `tts_record` |
| `processing` | all | Stages `upload`/`index`/`embed`/`tts_prepare`/`tts_encode` |
| `idea` | all | Suggestions found |
| `success` | all | Job complete, strong match, accepted suggestion, stage `complete` |
| `celebrate` | all | Pip's wins, path marked complete, Pip's click reaction |
| `acknowledge` | all | Upload submitted, flash success, settings saved, none left, dismissed, click reaction |
| `unsure` | all | Partial match, 400 page, Pip's Weak Signals and bell failure, Trace's click reaction |
| `confused` | all | 404 page |
| `warning` | all | Soft warnings, weak match, 403 page, bell failure, flash warning |
| `error` | all | Errors, 500 page, flash danger |
| `relieved` | Pip, Trace | First success after an error |
| `encourage` | Raster | Weak match, Weak Signals |
| `look-left`, `look-right`, `look-up`, `look-down` | all | Cursor glances, idle variety, later-page glance, bell (`look-up`) |
| `hello` | all | First page of the session, settings picker preview |
| `goodbye` | all | Logout |

---

## 10. Where the mascot appears

- **Now:** upload/login (`index.html`), `results.html`, `lessons.html`, `dashboard.html`, `signup.html` and `error.html`. In Settings, the mascot picker shows animated previews, but the page has no floating mascot.
- **Later (not this round):** the lesson deck (`lesson_deck.html`). It currently loads `mascot.js` with no mascot markup, and that must stay a harmless no-op. Planned reactions there are: correct checkpoint (R `acknowledge`, P `celebrate`, T `acknowledge`), wrong checkpoint (R `unsure`, P `confused`, T `curious`), quiz pass, quiz fail (R `encourage`), passing a retake after a fail (P/T `relieved`), and narration playing (`listening`).
- **Not planned:** the admin page and the reset-password page.

---

## 11. Decision log

| Date | Decision |
|---|---|
| 2026-11-28 | Raster replaces the old Study Robot. All old robot assets, the generator and their tests are removed. |
| 2026-11-28 | Learners pick a mascot in Settings. The "Change Mascot" section sits directly below "Change Profile Picture" and copies its modal UI. |
| 2026-11-28 | Only Raster uses the LLM. Pip and Trace use scripted pools with data filled in. |
| 2026-11-28 | Raster's unprompted chatter comes at least 180 s apart. Events still talk immediately. |
| 2026-11-28 | Mascot memory is shared, the TTS voice stays independent, and there's no sound. |
| 2026-11-28 | mimo's generator sources are kept under `tools/mascots/` so the animations can be regenerated and extended. |
