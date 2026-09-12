# Trinetra demo flow

A recording runbook for a short submission video. Pairs with
`demo_video_ssml.xml` — section numbers below match the SSML's section
comments, so you can generate the narration audio first (see "Generating
the audio" below) and then screen-record against it, or record screen
first and time-stretch narration to match.

**Target length: ~3:05–3:15** at a natural narration pace (measured from
the actual SSML word count + break tags — 460 words, 4.4s of `<break>`
time, using the same ~2.5 words/sec speaking rate measured off the
BidWright/ClaimClarity/GlacierWatch scripts, not a guess). This is
deliberately the tightest of the four project videos: Trinetra has nine
agents and this cut only has room for three of them plus the hook and
close. Everything else — Kumbh Rakshak, rumor triage, Sankat Nirnay's
resource reconciliation and red-team check, A2A, Anukaran Netra's synthetic
telemetry, and the SMS/USSD network-resilience design — is real, tested,
and documented in `TRINETRA.md`, but is named for one sentence in section 4
and left for "If you have more time" below rather than cut for space.

**Why the SSML has no `<emphasis>` or `<prosody>` tags.** An earlier draft
used both for rhetorical emphasis, matching the other three projects'
scripts — but Amazon Polly's Neural engine (the one both `--voice-id
Matthew` and `--voice-id Joanna` use here) doesn't support `<emphasis>` at
all, and rejects it outright with "The input text contains invalid SSML
syntax," not a silent ignore. This script only uses tags Neural actually
supports (`<speak>`, `<p>`, `<s>`, `<break>`), and leans on word choice and
`<break>` placement for emphasis instead. If you hit the same error on the
other three projects' scripts, this is almost certainly why.

Unlike the other three projects, Trinetra has no `JUDGING_CRITERIA.md` and
no bundled `screenshots/` folder yet — this flow assumes you're recording
fresh off the running web UI (`webapp/trinetra`) and a terminal, not
reusing pre-made stills.

## What you need running before you hit record

- The web UI as the primary screen for sections 2–3:
  `cd webapp/trinetra && npm install && npm run build && cd ../..` then
  `python3 server_trinetra.py` → `http://localhost:8000`. `OverviewView`
  for the three-eyes framing, `DigitalTwinView` for the quiet occupancy
  chart in section 3.
- A terminal, visible or narrated over, for the two commands that carry
  section 4: `trinetra calibrate` (no API key required — it's pure code)
  and `trinetra flood-risk --discharge 22000 --occupancy ramkund=8000 ...`
  (also pure code). Run them for real before recording so the on-screen
  numbers are the genuine output, not retyped from `TRINETRA.md`.
- **`trinetra monitor --ghat ramkund`** is the one beat in this script that
  needs both a real `ANTHROPIC_API_KEY` and real ThingsBoard credentials
  (`THINGSBOARD_URL`/`_USERNAME`/`_PASSWORD` in `.env`, pointed at a tenant
  provisioned like [KumbhDigiTwin](https://github.com/akashtalole/KumbhDigiTwin)).
  Without them the command still runs and says so honestly ("not
  configured") instead of faking a reading — but the video needs the real
  live pull, so don't record this section until both are set and you've
  confirmed a live run actually returns a Ramkund reading.
- `docs/trinetra/architecture-diagram.png` for the closing flash.

## Section-by-section

**1. Hook + problem (~0:00–0:25)** — Screen: a dark title card, or real news
photography of a crowd/barricade if you have licensed footage; otherwise
stay on the title card. Narration: the 2003 Nashik and 2025 Prayagraj
stampedes, same root failure.

**2. Who it's for (~0:25–0:45)** — Screen: cut to the web UI, `OverviewView`
showing the three eyes. Narration: Trinetra's three pillars and who each
one serves.

**3. The hybrid design (~0:45–1:00)** — Screen: `DigitalTwinView`, a calm
occupancy chart on screen. Narration: deterministic code computes crowd
numbers, the model only interprets them — the design choice that makes
calibration possible.

**4. Live demo walkthrough (~1:00–2:30) — the core of the video**
- Terminal: run `trinetra calibrate` live (or cut to the pre-run output).
  Narration covers both historical incidents flagging CRITICAL, then the
  two routine controls, then the routing-sensitivity pair — the same
  scenario flipping from CRITICAL to ROUTINE when one narrow lane is
  removed from the route. Hold on this table long enough for a viewer to
  actually read the ✅ column.
- Terminal or a short screen-recorded CLI clip: `trinetra monitor --ghat
  ramkund`, live against the real ThingsBoard tenant. Narration covers the
  live Ramkund pull — occupancy reading calm, Fruin LOS grade reading E —
  and that Trinetra reports both instead of resolving the disagreement
  itself.
- Screen: `FloodRiskView`, the worst-first evacuation table. Narration
  covers the Godavari compound-hazard multiplication: same discharge, same
  crowd, opposite verdict depending on mobility mix.
- Screen: quick 2-3 second cuts across `RumorView` and `CommandView` (no
  need to explain either in depth — this is the one sentence naming Kumbh
  Rakshak, rumor triage, and Sankat Nirnay's resource-reconciliation
  without stopping to demo them).

**5. Close (~2:30–2:55)** — Screen: Trinetra title card, then a 2-3 second
architecture diagram flash (`docs/trinetra/architecture-diagram.png`).
Narration: every recommendation is advice, a human always decides; the
sign-off line.

## Generating the audio

`demo_video_ssml.xml` is AWS Polly-ready SSML. A neural voice (e.g.
`Matthew` or `Joanna`) reads naturally with the `<break>`/`<emphasis>`/
`<prosody>` tags already in place:

```bash
aws polly synthesize-speech \
  --engine neural --voice-id Matthew --output-format mp3 \
  --text-type ssml --text file://docs/trinetra/demo_video_ssml.xml \
  docs/trinetra/demo_narration.mp3
```

This file is ~5,700 characters including tags — well past Polly's ~3,000
billed-character cap for the neural engine on some accounts/regions, so
split at the `<!-- SECTION -->` boundaries into 5 requests and concatenate
the MP3s (the `<break>` tags already keep section boundaries natural for a
clean cut). Time each screen action in the runbook above to the
corresponding narration by ear once you have the audio.

## If you have more time (extended cut, +90-120s)

Not in the core ~3-minute cut, but real, tested, and documented in
`TRINETRA.md` if you want a longer video or a separate feature-highlight
clip:

- **Kumbh Rakshak reunification** — lost-person matching is deliberately
  pure code, never an LLM, and never reports a `certain` match, only
  `strong` or `possible` — a human always confirms in person before anyone
  is told their family member has been found.
- **Rumor triage** — a hard guardrail (`trinetra/tools/rumor_guardrail.py`)
  blocks any drafted counter-message that claims absolute certainty a
  rumor is false, or that tells a crowd to run/hurry/push — because the
  drafting agent cannot actually know the rumor is false, and a wrong
  reassurance can move people toward the danger.
- **Sankat Nirnay** — when a dam release, two SOS incidents, and a rumor
  are all live at once, `trinetra/tools/resources.py` and
  `trinetra/tools/conflicts.py` reconcile every desk's demand against one
  finite responder pool in pure code first, and `trinetra/agents/red_team.py`
  then adversarially attacks the resulting plan without seeing the
  commander's reasoning.
- **A2A** — Trinetra both publishes a real Agent2Agent card
  (`/.well-known/agent-card.json`) and calls out to an allowlisted peer for
  facts it doesn't own (e.g. planned dam discharge) — every peer reply is
  scanned for prompt injection and claimed authority before it's ever shown
  as decision support, and is never treated as authoritative.
- **Anukaran Netra** — pushes a bounded, reproducible synthetic crowd/river
  curve onto a real ThingsBoard tenant so there's something changing to
  monitor; the one model call in that path only picks a scenario
  *directive* (a multiplier, which ghats surge), never a number that gets
  written.
- **Network-resilience formatting** — the same underlying judgment gets
  reformatted for SMS (160-char GSM-7), USSD (~180-char menu), offline-queue,
  or the full app — because not every pilgrim has a live data connection at
  every moment of a 30-50 million person event.
