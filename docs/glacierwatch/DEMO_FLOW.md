# GlacierWatch demo flow

A recording runbook for the submission video. Pairs with
`demo_video_ssml.xml` — section numbers below match the SSML's section
comments.

See `JUDGING_CRITERIA.md` for the five official judging criteria mapped
one-to-one to a specific screenshot and script line — useful both as a
sanity check that this flow's beats actually earn points on every
criterion, and as a standalone judge-facing pitch sheet.

**Target length: ~5:20–5:40** at a natural narration pace (measured from
the actual SSML word count + break tags below) — **this exceeds the
actual Devpost rules' hard 5-minute video cap** (confirmed at
https://agentsforhumans.devpost.com/rules, not a soft guideline). Trim
before recording: wrap the SSML body in `<prosody rate="115%">` (buys
back ~45s on its own), and cut the Community Alert Bulletin beat from
section 4 to the "more time" list below — the disclaimer banner, live tool
calls, and Weekly Watchlist result are the load-bearing beats worth
keeping full-length; everything else can flex or move to "more time."

## What you need running before you hit record

- The web UI, not the Streamlit demo, as the primary screen — it's also
  GlacierWatch's first AWS deployment path of any kind, worth a line in the
  video: `cd webapp/glacierwatch && npm install && npm run build && cd ../..`
  then `python3 server_glacierwatch.py` → `http://localhost:8000`.
- A real `ANTHROPIC_API_KEY` in `.env` — record a genuine live run against
  real Open-Meteo (weather) and USGS (seismic) data. Note in narration that
  a fetch failure is reported honestly, never silently mocked — if you can,
  it's worth actually letting one real run play out rather than pre-scripting
  the outcome, since the elevated/routine split depends on real conditions
  the day you record.
- The bundled 4-site watchlist (the default) — two active-watch sites
  (Gepang Gath, Samudra Tapu) and two historical case studies.

## Section-by-section

**1. Hook + the problem (~0:00–1:05)** — Screen: black slide, then a map of
the Himalaya. Narration: the named disaster, the casualty numbers, "nobody
predicted it," Chamoli and South Lhonak as prior close relatives. Do not
rush this — it's the strongest, most consequential framing in any of the
three videos and deserves to land at a serious pace, not a hackathon-pitch
pace.

**2. Who it's for (~1:05–1:35)** — Screen: GlacierWatch title card.
Narration: state disaster management authorities and village-level
committees; explicitly not a replacement for glaciologists/geotechnical
engineers.

**3. Why it matters (~1:35–2:20)** — Screen: stays on title card or a
simple triage-vs-prediction graphic. Narration: the deliberate choice not
to predict, framed as an honesty and safety decision, not a limitation.

**4. Live demo walkthrough (~2:20–4:50) — the core of the video**
- Load the web UI: hold 2-3 seconds on the **disclaimer banner** at the
  top before anything else, visible before any run happens — narration
  calls this out explicitly.
- Click **Run**. Screen: the live activity log, holding on a real
  Open-Meteo/USGS tool call line long enough to be read — "nothing here is
  mocked."
- Cut to **Weekly Watchlist**: the elevated/routine split on the day you
  record (narrate whatever the real result actually is — don't pre-script
  a specific site's status since it depends on live conditions).
- Cut briefly to the **Independent Audit** tab (cross-check output) — a
  second independent assessment runs per site, and narration explains the
  "adopt the more cautious rating" rule: if the two assessments disagree,
  the higher-priority one always wins, because understating risk here is
  worse than overstating it.
- Cut to a **Community Alert Bulletin** (only exists if a site actually
  hit `priority` this run — if none did on your recording day, cut this
  beat and use a bundled example bulletin from a prior run instead, clearly
  narrated as "here's what one of these looks like when a site does hit
  priority"). Point at: plain-language for a village committee (not
  officials), named downstream settlements, concrete committee-level
  actions, explicitly never an evacuation order.
- Cut to **Current Conditions**: the real live numbers — precipitation on
  India's official rainfall scale, nearest seismic events with distance and
  magnitude.

**5. Close (~4:50–5:30)** — Screen: GlacierWatch title card. Narration: the
"published data + this week's real conditions = one honest, disclaimed
priority list" summary, then the scale-to-56/28,043 forward-looking beat,
then the closing line.

## Generating the audio

Same Polly workflow as the other two:

```bash
aws polly synthesize-speech \
  --engine neural --voice-id Matthew --output-format mp3 \
  --text-type ssml --text file://docs/glacierwatch/demo_video_ssml.xml \
  docs/glacierwatch/demo_narration.mp3
```

If a single request exceeds Polly's neural-engine character cap, split at
the `<!-- SECTION -->` boundaries into 5 requests and concatenate.

## If you have more time (extended cut, +60-90s)

- **Run History & Trend Early-Warning Tracker** — after 3+ recorded weekly
  runs of the same site, a rising trend in rainfall/seismic activity gets
  flagged even before any single week's snapshot alone would cross the
  `priority` threshold — pure numeric comparison across stored runs, no
  LLM judgment call. Screen: `trend_report.md`, and the one-line early
  warning that lands in `watchlist_report.md` itself when a site is
  trending.
- **Field Inspection Scheduler** — turns the week's triage into a concrete
  suggested field-visit order for a limited team.
- The **"this is GlacierWatch's first AWS deployment path" note** — worth
  a sentence in an extended cut: unlike BidWright/ClaimClarity, which
  already had a Bedrock AgentCore path, this web UI is the first way
  GlacierWatch runs anywhere but a laptop.

## Screenshots available for cutaways / thumbnails

`docs/glacierwatch/screenshots/`: `01_initial_state.png`,
`02_running.png`, `03_weekly_watchlist.png` (Streamlit demo), and
`webui_01_initial.png` through `webui_05_chat.png` (the web UI — use these
as the primary source).
