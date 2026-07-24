# carshorts — system roadmap

Goal: a self-correcting, continuously-learning Shorts factory where the human
does taste (script approval, final watch, footage) and the system does the rest.

## Done
- Fact machine: sourced specs + news, skeptic, number-guard, structural check
- Script studio: variants → judge → editor; personas; formats; learnings injected
- Render: phrase-synced cuts (TTS word marks), speech-timed overlays, motion
  variety, loop-close, mood-matched music, ducked/limited/-14 LUFS audio,
  unified grade, keyword + callout cards
- QA gate (12 checks) + auto-fix loop + failure journal + auto-lessons
- Publish: kit (title-promise check), API upload, thumbnail, recipe linkage
- Learning: recipe cards, analytics join (analyze.py), learnings injection

## In progress
1. **Visual QA** — the system sees its own frames: per-cut frame vs phrase via
   vision model; flags plates, watermarks, wrong vehicles, mismatches.
2. **Orchestrator** — pipeline.py: one command per car through draft + QA, then
   an approval queue (Gate 1 human), `--approve` runs final + upload.

## Done (cont.)
3. Retention-curve → beat mapping ✅
4. Inbox auto-ingest ✅
8. .env secrets + provider fallback chains ✅

## Next (agreed 2026-07-21, execute in order, auto-advance)
A. **Hardening sprint ✅** — golden-manifest integration tests (mock TTS +
   --plan-only), GitHub Actions CI. produce.py refactor: incremental, behind
   the held tests, as modules get touched (not big-bang).
B. **Experiment scheduler ✅** — data/calendar.json of pre-assigned A/Bs
   (persona / hook-type / format / length / music rotations);
   `pipeline --next` pulls the top entry. Makes learnings causal.
C. Comment mining ✅ (comments.py — topics to data/topic_ideas.json, draft replies; re-run as audience grows)
D. **Brain v1 (in progress)** — brain.py: embedded judgment (failure triage
   beyond the fix-table, asset-vet second opinion, news curation, weekly
   strategy note) with decisions journal (data/brain_log.jsonl). Groq for
   bounded verdicts; headless Claude for hard calls. Daily heartbeat via cron.
E. **Review portal v1 (in progress)** — portal.py (localhost, stdlib): daily
   draft variants side by side, BEAT-LEVEL feedback framework (tag hook/visual/
   pacing/joke per section), pick → rework → approve → auto-upload → analytics
   tab. Feedback JSON feeds learnings. v2: variants differ by one calendar
   variable; unlisted-upload mobile review.
F. Semantic asset index + cross-video freshness (as footage grows)
G. Hinglish/Hindi re-issues of winners
H. Cadence: daily heartbeat — brain drafts, you approve


## North star (owner directive, 2026-07-22): a system with its own brain

Architecture: **deterministic hands, agentic minds.** The tested pipeline
(produce/QA/VQA/portal/publish) stays the hands. Five Claude-powered minds
(headless `claude -p`, role charters in agents/, budget-capped, journaled)
supply the judgment. The interactive supervisor (Claude) audits, corrects,
and grows the free brain's menu from every escalation.

- [x] **P1 Foundation** — agent harness (src/carshorts/agent.py: budget
      12 runs/day, 40-turn cap, journal data/agent_log.jsonl), mechanic +
      supervisor charters, rework dead-ends escalate to the mechanic,
      menu-growth inbox (data/brain_inbox.jsonl). Smoke-tested live.
- [x] **P2 Scriptwright** (live-validated on Creta 2026-07-22) — agents/scriptwright.md: crawl fresh news +
      price/spec data from outlets (free/official), write the script with
      humor that lands + curated pops; output = specs_extras + script JSON
      through the existing number-guard/fact-check gates.
- [x] **P3 Analyst** — agents/analyst.md: weekly competitor tactic research
      (what top car channels do for attention/retention) + own analytics
      (retention curve → beats) → learnings + experiment calendar entries.
- [x] **P4 Composer** — agents/composer.md: car personality profile →
      music mood/beat/SFX choices (extends music_tags.json + generate_beat).
- [x] **P5 Curator** — agents/curator.md: crawl assets (Wikimedia, official
      press kits, Pexels) with license checks, build per-car pools, propose
      stitching variety (shot plans) for the renderer.
- [ ] **P6 Supervisor cadence** — scheduled daily supervisor run (audit
      agent logs, fold brain_inbox into the free menu, heal stuck cards,
      report to owner). Needs owner OK for the schedule mechanism.


## Upgrade ladder (owner-approved 2026-07-22, execute in order)

### Tier 1 — Agent quality (this week) — IN PROGRESS
- [x] Taste constitution (agents/TASTE.md): the supervisor's context made
      portable — owner taste, incidents, house style; every agent reads it
      first; supervisor + scheduled audits keep it current.
- [x] Mandatory self-verification: any agent whose work changes rendered
      output must extract frames and READ them before reporting done.
- [x] Right-sized orders: one concern per agent run (supervisor practice +
      charter rule).
- [x] Standing self-improvement mandate: every 8h supervisor shift ships
      one small improvement unprompted (owner directive).

### Tier 2 — Data engine (~2 weeks)
- [ ] Activate analytics: analyze.py on the Thar after 24-48h; retention
      curve -> per-beat lessons; wire outcomes back onto recipe cards.
- [ ] Experiment discipline: every published video carries exactly one
      tagged experiment from the calendar; wins/losses recorded.
- [ ] Portal analytics tab: owner sees views/retention/CTR per video, with
      the beat map, inside the review station.

### Tier 3 — Asset ceiling (weeks 2-4)
- [ ] Owner footage pipeline: SHOT_CHECKLIST shoots -> assets/inbox ->
      ingest; own footage outranks all stock in pool ordering.
- [ ] Shot-coverage index per car (front/rear/interior/motion gaps drive
      curator hunts automatically).
- [ ] Semantic asset index (roadmap item F) once footage volume justifies.

### Tier 4 — Autonomy (month 2)
- [ ] Nightly autopilot: heartbeat produces the next calendar video
      end-to-end overnight; owner wakes to a draft in the portal.
- [ ] Machine-independent scheduling (true cloud or Mac launchd — owner's
      option (a) upgrade).
- [ ] Hinglish/Hindi re-issues of proven winners (roadmap item G).


## BRAIN GAP ANALYSIS (owner directive 2026-07-23): the three missing organs

Diagnosis after a full-codebase audit + first real analytics pull. The factory
(hands) is strong. What is missing is the brain's ability to PERCEIVE the market,
EXPERIMENT causally, and RUN ITSELF. The system currently learns only from its
own output, from 5 videos, of which YouTube had processed 4% of views.

### Evidence base (measured 2026-07-23, channel carsInShorts)
- 5 uploads, 767 real-time views, but only **33 views analytics-processed**.
  Every retention % quoted before this date was computed on <=26 views = noise.
- Engagement (real-time, trustworthy): **~0.65% like rate, ~0.13% comment rate,
  +1 subscriber**. This is the loudest reliable signal and nothing targets it.
- Traffic is dominated by the SHORTS feed -> distribution surface is correct;
  this is NOT a technical/classification failure.
- Channel is a cold start: created 2012 but dormant, 1 subscriber.
- impressions / impressionsClickThroughRate return HTTP 400 on the Analytics
  API — **CTR is Studio-only**. Permanent blind spot for automation.
- Cadence stopped after 2026-07-22 despite a daily goal.

### Organ 1 — EYES (perception). Biggest gap.
- [ ] **Competitor intel engine.** agents/analyst.md exists as a CHARTER and ran
      once (the `[medium][analyst]` entries in learnings.json came from it), but
      there is **no module** and no continuous observation. Need: rival channel
      tracking, format/hook/length/pacing extraction, cadence benchmarks.
- [ ] **News/press crawler.** crawl.py is Wikipedia-only and spec-scoped. Prices
      and news come from **hand-curated specs_extras/** — a human bottleneck that
      structurally blocks the daily goal.
- [ ] **Demand signal for topic choice.** calendar_plan.py CARS is a hardcoded
      list. Topic is likely the largest reach lever and is currently arbitrary.
- [ ] **CTR ingestion** — manual Studio read (API cannot supply it).

### Organ 2 — LAB (causal inference)
- [ ] **Experiment ledger**: hypothesis -> prediction -> result -> verdict, one
      tagged variable per published video. calendar_plan.py assigns A/Bs but
      nothing ENFORCES holding variables constant.
- [ ] **Significance gate before any lesson may change the writer prompt.**
      learnings.json is a flat LLM-appended list with no confidence, evidence
      link, expiry, or contradiction check. A single weak signal can steer every
      future script — this is how the system teaches itself superstitions.
      (2026-07-23: the LLM learning pass was deliberately NOT run for this reason.)
- [ ] **Belief revision**: retire lessons that later evidence disproves.

### Organ 3 — HEARTBEAT (autonomous operation)
- [x] Retention auto-recheck (retention_watch.py + daily Windows task) — polls
      for curves, maps drops to beats the moment data lands. Shipped 2026-07-23.
- [ ] **Daily orchestrator**: nothing actually runs the day. pipeline --next and
      the calendar exist but no driver. No volume -> no data -> no learning.
      Cadence is the DATA-GENERATION ENGINE, not a growth tactic.

### Also missing
- [ ] **Algorithm levers are unoptimised**: Shorts live/die on the first 1-2s
      (in Shorts the FIRST FRAME is the thumbnail), retention shape, and
      engagement rate. Nothing engineers or tests the opening frame; nothing
      drives comments/likes despite that being the weakest measured number.
- [ ] **Self-diagnostics**: on 2026-07-23 a cp1252 bug was mangling every `₹`,
      font paths were macOS-only, fetched images had no plate-guard, and 3 of 5
      videos were unattributable — and the system had no idea. A brain needs
      checks that fire without a human noticing.
- [ ] **Iteration speed**: moviepy ~12 min/render caps how fast we can learn.
      ffmpeg-native assembly (filter_complex + zoompan) is the fix.

### Build order (agreed 2026-07-23)
1. [x] **Heartbeat** — daily orchestrator. SHIPPED 2026-07-23: heartbeat.py
       (guards: in-flight / back-pressure / idempotent / empty-calendar, plus
       PRE-FLIGHT dependency check), 13 tests, daily Windows task 08:00.
       NEVER publishes — both gates stay the owner's.
2. [x] **Eyes** — competitor intel. SHIPPED 2026-07-23: competitors.py.
       Curated watchlist (data/competitors.json, 8 real channels) instead of
       search.list — 3-5 quota units per channel vs 100 per search. Benchmarks
       SHAPE (length / cadence / title construction), never view counts, and
       states plainly that rival retention + CTR are private and invisible.
       FIRST EXTERNAL BASELINE (2026-07-23, 8 channels x 30 videos):
         - median short-form length: OURS 58s vs RIVALS 33s (6 of 8 shorter
           than us; carwow the biggest at 27s, CarWale 15s)
         - titles with emoji:  OURS 80% vs RIVALS 8.5%   <- starkest outlier
         - titles as question: OURS 80% vs RIVALS 27%
         - MATCHING already: uploads/week 12.2 vs 12.4, title length 39 vs 40
           chars, numbers in title 40% vs 33.5% — these are NOT problems.
       Also observed: median views do NOT track subscriber count (CarWale,
       310k subs, out-medians Autocar India at 2.54M). Per-video reach on
       Shorts is not gated by channel size — encouraging for a cold start.
       These are HYPOTHESES for the experiment ledger, not instructions.
3. [x] **News/press crawler** — SHIPPED 2026-07-23: newscrawl.py. RSS/Atom only
       (published for syndication), robots.txt honored, sources are DATA
       (data/news_sources.json). **Never writes price** (CLAUDE.md rule) — it
       reports the gap instead. Verified live: found 2 sourced Brezza stories
       and unblocked the heartbeat end-to-end.
       Fixed en route: produce._apply_extras returned "" when price was missing,
       silently discarding EVERY news item on exactly the new cars the crawler
       exists to unblock (tests/test_extras_news.py).
4. [x] **Lab** — experiment ledger + significance gate. SHIPPED 2026-07-23:
       experiments.py. Hypothesis -> arms -> verdict, ONE variable per
       experiment. A lesson may reach learnings.json only if BOTH arms have
       >= min_samples videos, every video clears a VIEWS FLOOR (default 500 —
       below that the metric is noise), the effect exceeds min_effect, and a
       Welch t-test clears alpha. Everything else returns INSUFFICIENT.
       Statistics are real: t-distribution p-value via regularized incomplete
       beta (Lentz continued fraction), no scipy dependency, verified in tests
       against textbook critical values t(4)=2.776, t(10)=2.228, t(30)=2.042.
       exp-001 registered from the competitor finding (58s vs 35s). On first
       evaluation the gate correctly REFUSED: all three seeded control videos
       were excluded by the views floor (144 / 79 / 57 views).

       ** BINDING CONSTRAINT DISCOVERED **: no experiment can conclude until
       videos clear ~500 views. Current reach is 26-467. So REACH, not retention
       craft, is what currently blocks learning — the lab cannot run without
       traffic. Lowering the floor would only manufacture false confidence
       (our "42.2% retention" came from 7 processed views).

       Not registered as experiments: title emoji % and question % (the two
       other competitor divergences). Their honest metric is CTR, and CTR is
       YouTube-Studio-only (Analytics API returns HTTP 400). They can only be
       tested with manual CTR entry — do not fake them with view counts.
5. [~] **Engagement + first-frame engineering** — engagement half SHIPPED
       2026-07-23 (engagement.py); first-frame half still open.
       Likes/comments are DIRECT COUNTS — no sampling, no 24-48h lag, no view
       threshold — so unlike retention they are measurable and experimentable
       TODAY. Rates are now written onto recipe cards as like_rate/comment_rate
       so the ledger can test CTA variants at low view counts.
       Comments-disabled videos record commentCount as None (unknown), never 0,
       so a disabled comment section cannot masquerade as an audience that
       chose not to reply.

       ** CORRECTION to the 2026-07-23 brain-gap analysis **: that document
       says "~0.65% like rate" and implies a crisis. That number was
       total_likes/total_views (5/767), an aggregate dominated by one
       high-view/zero-like video. The correct PER-VIDEO MEDIAN, measured
       against 8 rivals:
         - like rate:    OURS 1.389%  vs RIVALS 2.382%  (0.58x — below par,
           but inside the rival range, which spans CarWale 0.862% to
           MotorBeam 3.365%)
         - comment rate: OURS 0.0%    vs RIVALS 0.069%
       Comments are rare for EVERYONE (0.029%-0.137%, i.e. ~1 per 1,000-3,000
       views). At our 808 lifetime views the expected comment count is ~0.6.
       We have 1. So our comment volume is roughly what our view count
       predicts — engagement is NOT dramatically broken.
       => Reinforces the ledger's finding: REACH is the binding constraint,
          not engagement craft. Do not over-engineer the CTA to fix a number
          that is mostly a denominator problem.
       Genuine outlier worth investigating: Swift has our best reach (467
       views) and ZERO likes — high reach with no reaction at all.

       FIRST-FRAME half SHIPPED 2026-07-23 (firstframe.py). On Shorts frame 1
       IS the thumbnail; QA checked only that it OPENS ON THE SUBJECT CAR, never
       whether the frame is arresting. Measures deterministic, citable stats
       (brightness, RMS contrast, Hasler-Susstrunk colourfulness, saturation,
       edge density) and benchmarks them against 127 REAL rival Shorts
       thumbnails pulled from the API.

       METHOD BUG CAUGHT BEFORE IT MISLED US: YouTube returns a Short's
       thumbnail as 1280x720 with the 9:16 frame centred and the sides filled
       with a DARKENED, BLURRED COPY of it. Two thirds of every measured image
       was synthetic fill. The first baseline was therefore wrong — brightness
       58.5 (actual 117.4), colourfulness 26.1 (actual 43.6), edge density
       7.6 (actual 18.2).
       Acting on it would have told us to DARKEN our frames, the exact opposite
       of the truth. Fixed by cropping the letterbox (crop_vertical_content).

       FINDING (both our renders, two independent methods agreeing):
         Creta frame 0: brightness 0.70x, contrast 0.71x, colourfulness 0.59x,
                        edge density 0.25x of the rival median
         Thar  frame 0: brightness 0.77x, contrast 0.69x, colourfulness 0.38x,
                        edge density 0.22x
         Vision read agreed independently: stops_scroll=false, problems =
         low_contrast, dull_colour, awkward_crop, nothing_happening.
       Our opening frames are FLAT, DULL AND EMPTY versus the feed norm — worst
       on edge density (~1/4 the rival detail, i.e. visually barren).

       LIKELY CODE CAUSE (renderer._prepare_background):
         `img = Image.blend(img, overlay, 0.35)` darkens EVERY still by 35% so
         white captions stay readable. But frame 0 carries NO caption — pops are
         voice-synced and start later — so the opener is darkened for no benefit
         and loses its swipe-stop. Rivals also put BOLD TEXT on frame 1; ours is
         bare (vision: readable_text=false).

       NOT registered as an experiment: first-frame impact surfaces in CTR /
       swipe-stop, and CTR is YouTube-Studio-only. Testing it needs manual CTR
       entry — same limitation as the title-shape hypotheses.

       FIX SHIPPED 2026-07-23: renderer now exempts the OPENING cut (and the
       loop-close tail that flashes it) from the 35% darkening —
       OPENING_DARKEN=0.0 vs DEFAULT_DARKEN=0.35, threaded through
       _timed_scene/_pooled_scene/_sub_visual via opening=(idx==0). Every other
       cut keeps the darkening, so mid-video overlay legibility is unchanged
       (regression-tested). Verified on the real Creta opening asset:
         brightness   82.1 -> 127.1  (0.70x -> 1.08x of rival median)
         contrast     45.5 ->  69.9  (0.71x -> 1.10x)
         colourfulness 25.5 ->  39.3  (0.59x -> 0.90x)
         edge density  4.7 ->   7.0  (0.25x -> 0.39x)  <- STILL SHORT
       Three of four gaps closed. Edge density cannot be fixed by not darkening:
       it measures CONTENT, and our opener is a clean car photo with no text
       while rivals put bold text on frame 1.

       OPEN TENSION (needs an owner call): the rival tactic conflicts with
       TASTE ("Text appears ONLY while its words are spoken... no anchor in the
       voice timeline -> the text does not exist. Ever."). A COMPLIANT route
       exists: anchor the hook's strongest pop to the FIRST spoken words so text
       is legitimately on screen from t=0. Today the Creta hook's first pop
       fires at 1.396s, leaving frame 0 bare.

       CONFIRMED IN ARTIFACT 2026-07-23 (out/creta_openfix.mp4, 655s render).
       Rendered frame 0 matches the undarkened path exactly (brightness 100.6 vs
       100.3 predicted; would have been 64.7 darkened). Pop legibility over the
       brighter frame checked BY EYE, not assumed: "AGAIN." / "PRICE HIKE" read
       crisply — the ~9% stroke + blurred shadow carry it.
       NOTE the first A/B attempt was CONFOUNDED: the two renders opened on
       DIFFERENT photos, so the comparison measured pictures, not the fix.

### Three defects the confirmation render exposed (2026-07-23)
1. **The opening asset is NON-DETERMINISTIC.** The GROQ phrase-matcher picks a
   different hook image on every render (run 1: Hyundai_Creta_Electric_SU2_EV_PE
   .jpg, run 2: 2024_Hyundai_Creta_Alpha.jpg). On a Short frame 1 IS the
   thumbnail — the single highest-leverage frame is currently chosen at random.
2. **The chosen opener is bad, and nothing noticed.** Tight crop of a BLACK car
   in a dim showroom, with Thai financing promo text ("0.99% ... 48 ..."), a
   dealer QR code and "Hyundai Anniversary" burned into the windshield — wrong
   market signals for an India channel, and not identifiable as a Creta at a
   glance.
3. **QA's "opens on subject car" is a FILENAME SUBSTRING CHECK** (qa.py ~line
   103: `any(f in name for f in families)`). "2024_Hyundai_Creta_Alpha.jpg"
   contains "creta", so it passed. The gate for the most important frame in the
   video never looks at the pixels.
   Related: assetvet only runs on the AUTO-FETCH path, so owner-curated pools
   (like Creta's 198 images) bypass visual vetting entirely.

   The firstframe audit DID flag this frame numerically (colourfulness 0.52x,
   edge density 0.39x of rival median) — the tooling worked; it simply is not
   wired into the render gate yet. Candidate fix: make QA consult firstframe
   stats + assetvet on the opening cut, and vet curated pools too.

### FIXED 2026-07-23 — deterministic opener + visual QA gate
- **firstframe.choose_opening_still()**: ranks subject stills by measured
  stop-power against the rival baseline (score_still). brightness/contrast/
  colourfulness scored ONE-SIDED (reaching the feed median is the target; a
  median is not an optimum so exceeding earns no extra credit); edge_density
  scored SYMMETRICALLY because barren and cluttered both fail to stop a scroll.
  Ties break on path -> same pool + same baseline always yields the same opener.
  produce.py now overrides the LLM's pick for the FIRST cut only.
  Verified on Creta: chose 2022_..._IVT_orange_and_black_front_view (0.964) over
  the LLM's random 2024_Hyundai_Creta_Alpha.jpg. Checked BY EYE — vivid red
  Creta, full 3/4 front, identifiable, no readable plate, no watermark.
  Cost: 29.5s to score 137 stills (~215ms each) on an ~11min render.
- **qa.py "opening frame vs feed norm"**: extracts frame 0 and measures the
  actual PIXELS against the baseline. Fails only on the exposure axes we
  control (brightness/contrast/colourfulness < 0.5x rival). edge_density is
  REPORTED BUT NEVER FAILS — closing it means text on frame 0, which collides
  with the TASTE rule that text appears only while its words are spoken. That
  is the owner's call, not QA's.

### STILL OPEN
- **The scorer is blind to content defects.** It measures exposure/structure
  only — it cannot see a plate, watermark, dealer promo text or bad crop. The
  Thai-promo Alpha image would still score acceptably. Mitigation: assetvet
  quarantines defects into _quarantine/, which selection then never globs — so
  CURATED POOLS NEED VETTING (Creta's 137 stills have never been vetted; only
  the auto-fetch path is).

### Curated-pool vet — report-only pass 2026-07-23/24
Confirmed the curated pools were NEVER visually vetted. Every flag spot-checked
by eye was a TRUE positive:
  - Thar:  roxx_dirt_full.jpg + roxx_dirt_detail.jpg — readable plate MH01ER6709
  - Swift: Maruti_Suzuki_Swift_LXi.jpg — plate TN-01-Z-7375 AND a third-party
           watermark "jljl.wordpress.com" (a LICENSING violation, not just
           quality — CLAUDE.md: never third-party watermarked content); plus two
           1990s/US-market Swifts (wrong car).
  - Nexon: 2 readable plates (2020 EV, Blue Dual Tone).
  - Creta: BLOCKED — only 6/198 vetted (all clean); see quota note.

### assetvet robustness fixes (2026-07-23/24)
1. A single failed batch used to abort the whole folder and DISCARD all partial
   results (this is why the first Creta run produced nothing). Now a failed
   batch marks its images UNVETTED (never quarantined on no evidence) and the
   run continues; a report is always written.
2. On a DAILY-QUOTA 429 ("exceeded your current quota") the run now stops
   calling instead of firing every remaining doomed batch (Creta fired 32).
   A transient per-minute 429 (message says "rate limit") does NOT stop — the
   2s inter-batch pacing is the remedy for that.

### HARD CONSTRAINT: Gemini free-tier daily quota
Vision vetting ~350 curated images in one day exceeds the free-tier daily quota
(gemini-2.5-flash), especially alongside VQA and the first-frame reads. The vet
degrades safely (marks unvetted, moves nothing) but cannot COMPLETE Creta today.
Also: google.generativeai is END-OF-LIFE upstream (migrate to google.genai).

RESOLVED 2026-07-24 (owner chose: quarantine the 7 + vet-on-use):
  - Quarantined the 7 confirmed bad images from the SAVED reports (zero quota,
    no re-vetting) via assetvet.quarantine_from_report / --apply-report:
    Thar 2 plates, Swift 2 wrong-car + 1 plate+watermark, Nexon 2 plates.
    Reversible (moved to _quarantine/). Active pools now: Thar 4, Swift 2,
    Nexon 4.
  - VET-ON-USE shipped: persistent cache data/vet_cache.json keyed by
    parent/name:size; seeded from every existing vet_report.json (25 verdicts
    preserved, nothing re-paid). produce.py ranks opener candidates once
    (firstframe.rank_opening_stills), vets the top 12 cache-first and capped at
    3 calls/render, drops blocking-failed ones from the opener AND the pool, and
    walks down to the next clean pick. Cached verdicts and quota-death are both
    safe (unvetted != blocked).
  - Validated on the real Creta pool: blocked 3 of the top-12 stop-power stills,
    all TRUE positives verified by eye — Creta_Electric_SU2_EV_PE.jpg carried
    "EVolvers" media branding on the front plate (it was the opener of the FIRST
    Creta render, caught only now); Legacy_SR2 was an Indonesian BUS mis-filed
    in the Creta pool; Creta_1.5_Value_2023 had a readable plate. The opener
    then landed on the eye-verified-clean top scorer
    (2022_..._IVT_orange_and_black_front_view, 0.964).
  Remaining 198 Creta stills are unvetted BY DESIGN — vetted lazily the first
  time a render considers them, cached forever after. Daily quota reset
  2026-07-24. Still TODO: migrate google.generativeai -> google.genai (EOL).
6. [~] **Fast renderer** — HYBRID shipped behind CARSHORTS_FFBASE=1 (2026-07-24).
       ffmpeg assembles the base scene (cuts + Ken Burns via zoompan on a 2x
       canvas + concat), then the IDENTICAL moviepy overlay/audio/music code runs
       on top — so the tuned overlays are byte-for-byte unchanged (verified by
       eye: ₹12.06 LAKH card renders exactly as before over the ffmpeg base).
       adapters/ffrenderer.py; pure filter-graph builder (build_scene_filter) is
       fully unit-tested (9 tests). Opt-in; only when every section is
       phrase-synced; any failure falls back to moviepy. Opener no longer
       darkened, deterministic + vetted.

       HONEST SPEEDUP — MODEST, NOT the 20x the base-scene spike suggested:
         base scene alone:  ffmpeg 29s vs moviepy (the bulk of the render)
         END-TO-END Creta:  moviepy 655s -> hybrid 408s  (~1.6x)
       Why: moviepy's FINAL overlay-composite + re-encode still processes all
       ~1488 frames in Python (decode base, composite ~19 overlay windows,
       re-encode). That pass (~370s) is now the bottleneck; the base was only
       part of the total. The hybrid removed the base cost, not the composite.

       INCREMENT 2 SHIPPED 2026-07-24 (adapters/ffoverlay.py): the overlay
       composite is now ffmpeg too, so moviepy never touches the full timeline.
       Each pop is baked to full-frame RGBA PNGs (position + settle/slam easing
       + count-up/wipe sequences) using the renderer's EXACT PIL generators, then
       ffmpeg overlays them with per-layer enable windows in one pass. Voice is
       concatenated by ffmpeg from the section audio files (moviepy's audio
       writer threw broken-pipe on Windows). build_overlay_command is a pure,
       unit-tested builder (9 tests).
       Three-tier fallback, identical overlays at every tier, fastest first:
         full ffmpeg (fffull) -> hybrid (ffmpeg base + moviepy overlays)
         -> pure moviepy. ON BY DEFAULT (2026-07-24); CARSHORTS_FFBASE=0 forces
         pure moviepy; CARSHORTS_FFOVERLAY=0 forces the hybrid tier. Requires
         ffmpeg on PATH (as QA/audiopolish already do); falls back otherwise.
       END-TO-END Creta (--no-polish): moviepy 655s -> hybrid 408s -> FULL 209s
         (~3.1x faster than moviepy, 2x faster than hybrid).
       VERIFIED IDENTICAL BY EYE against the hybrid ground truth: the ₹ count-up
       card, a number pop WITH its cyan wipe bar, and the LSS icon strip all
       render pixel-for-pixel the same, composited by ffmpeg.
       Remaining headroom (not chased): the 46-overlay ffmpeg chain + PIL baking
       + QA loudnorm make up most of the 209s; a single pre-composed overlay
       track could cut further, but 3x with identical overlays met the goal.
       156 tests pass.

### Next blocker discovered (2026-07-23)
The heartbeat can now SCRIPT a new car but cannot safely VISUALISE one:
- New cars have empty asset pools (Brezza = 0 files); the curator agent that
  fills them needs the `claude` CLI, which is **not installed on Windows**
  (nor is Node/npm) — the whole agentic layer is dead on this machine.
- The Wikimedia auto-fetch fallback has **no plate/watermark/generation guard**
  (unlike ingest.py). Fetched Thar stills had readable plates and one was
  wrong-gen + watermarked. So the fallback cannot be trusted to publish.
=> RESOLVED 2026-07-23 (assets half): assetvet.py + wired into produce.py.
   Still open: the agent layer is dead on Windows (no Node/npm/claude CLI).

### Asset vet — SHIPPED 2026-07-23 (assetvet.py)
CLAUDE.md always said "new stock/CC fetches get a visual vet grid before
entering the pool" — nothing implemented it. vqa.py could already SEE these
defects but only AFTER a 12-minute render. This moves the eyes to fetch time and
produce.py now vets every auto-fetched image before it can enter the pool.
- Blocking: readable_plate, watermark, wrong_vehicle, too_dark_or_blurry.
  Advisory (never blocks): wrong_generation — old gens are often deliberate.
- Failures are QUARANTINED to <dir>/_quarantine/, never deleted: vision is
  advisory and the owner must be able to overrule it.
- Validated against ground truth (images verified by eye): correctly caught
  readable plates; correctly passed the official press shots.
- CAUGHT ITS OWN FALSE POSITIVE: with a generation-specific subject the model
  labelled old-gen Thars `wrong_vehicle` (blocking) instead of
  `wrong_generation` (advisory) — it would have quarantined 4 of 6 legitimate
  owner assets. Fixed by separating NAMEPLATE from TARGET GENERATION in the
  prompt (--subject / --generation). Re-vet then matched human judgement.
- Finding for the owner: 2 of 6 curated Thar stills (roxx_dirt_full.jpg,
  roxx_dirt_detail.jpg) have READABLE PLATES (MH01ER6709, confirmed by eye).

### Tech debt found 2026-07-23
- `google.generativeai` is END-OF-LIFE upstream ("all support has ended;
  switch to google.genai"). Used by vqa.py, assetvet.py, firstframe.py,
  analyze.py. Migrate — functional change, needs a Gemini call to verify.

### Code quality pass 2026-07-24 (industry standards)
- ruff added (curated config in pyproject.toml): correctness + modernization +
  simplification rules; opinionated rules that fight deliberate patterns are
  ignored with rationale (naive local-time journals, best-effort try/except on
  optional network work, manual subprocess return-code checks). `ruff check .`
  is clean and now a CI step (.github/workflows/ci.yml), so it stays clean.
  Fixed a real loop-variable-closure smell in newscrawl.parse_feed and removed
  two dead locals in produce.py along the way. 156 tests green.
- STILL OPEN (durable, not yet done): pass encoding="utf-8" to every read_text/
  write_text/open. Windows defaults to cp1252 (the ₹ mojibake bug); currently
  mitigated by PYTHONUTF8=1 (env, set on this machine) and CI being Linux
  (utf-8 default). The proper fix touches ~50 call sites and must change reads
  AND writes together or writes crash on ₹. Enable ruff PLW1514 when done.

Framing: nobody reverse-engineers the YouTube algorithm. You beat it by
OUT-ITERATING it — publish consistently, measure honestly, change one variable
at a time.
