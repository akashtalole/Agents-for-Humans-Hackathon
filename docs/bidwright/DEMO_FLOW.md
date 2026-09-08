# BidWright demo flow

A recording runbook for the submission video. Pairs with
`demo_video_ssml.xml` — section numbers below match the SSML's section
comments, so you can generate the narration audio first (see "Generating
the audio" below) and then screen-record against it, or record screen
first and time-stretch narration to match.

**Target length: ~4:00–4:15** at a natural narration pace (measured from
the actual SSML word count + break tags below, not a guess). Devpost demo
videos are generally read fastest by judges under ~3.5 minutes, so if you
want it tighter: set Polly's speaking rate up (`<prosody rate="115%">`
wrapped around the body of the SSML, or the `--engine neural` default rate
bumped a step in the console) to land closer to 3:30, or cut the Chat-tab
beat from section 4 (it's the single easiest section to drop without losing
a load-bearing point). This flow is already cut to the pipeline's
strongest, most demoable beats, not every feature — everything left out is
listed under "If you have more time" at the bottom.

## What you need running before you hit record

- The web UI, not the Streamlit demo, as the primary screen — it's the more
  polished surface and is what section 4 below assumes. Build + serve it:
  `cd webapp/bidwright && npm install && npm run build && cd ../..` then
  `python3 server_bidwright.py` → `http://localhost:8000`.
- A real `ANTHROPIC_API_KEY` in `.env` — the run needs to actually happen
  live, not be faked. Budget ~1-2 minutes of real run time; you can either
  record it at real speed (the activity log streaming is genuinely
  watchable) or speed up the run segment in post and keep narration natural
  pace on top.
- The bundled example pre-selected (it's the default) — the municipal
  landscaping RFP against a deliberately underinsured example company, so
  the compliance check has something real to catch on screen.

## Section-by-section

**1. Hook + problem (~0:00–0:45)** — Screen: static title card / a dense
RFP PDF, no app yet. Narration: the small-business-loses-bids-on-a-
technicality hook.

**2. Who it's for (~0:45–1:15)** — Screen: stays on title card or a simple
icon strip. Narration: who BidWright serves.

**3. Why it matters (~1:15–1:40)** — Screen: cut to the web UI's landing
screen, header status pill visible ("Anthropic API direct" or "Bedrock").
Narration: the time-saved-and-mistakes-caught pitch.

**4. Live demo walkthrough (~1:40–3:45) — the core of the video**
- Click **Run** on the bundled example. Screen: the live activity log
  streaming real tool calls (Server-Sent Events) — this is genuinely more
  visually interesting than a spinner, let it play for a few seconds on
  screen before narration continues.
- Cut to the **Compliance Report** tab once ready: point at the real caught
  gap (general liability insurance at $1M vs. the RFP's $2M-per-occurrence
  requirement) plus the missing cover letter / pricing schedule.
- Cut briefly to **Independent Audit** tab (the cross-check output) —
  this is the "second opinion" moment; narration explains a separate agent
  re-derives compliance from scratch with no view of the first check's
  answer, and any disagreement is never silently dropped.
- Cut to the **Approval** panel: reviewer verdict + guardrail findings
  visible, edited-text textarea, the acknowledgment checkbox if guardrail
  findings exist. Click **Approve**.
- Cut to the **Chat** tab: type a real question ("what's the submission
  deadline?") and show the grounded answer landing, sourced only from that
  job's own generated files.
- Cut to **Decisions Needed**, held for a beat as the visual "landing" point
  — the one file a busy owner actually has to read.

**5. Close (~3:45–4:10)** — Screen: BidWright title card, then a 2-3 second
architecture diagram flash (`docs/bidwright/architecture-diagram.png`).
Narration: the human-always-signs-off framing, then the sign-off line.

## Generating the audio

`demo_video_ssml.xml` is AWS Polly-ready SSML. A neural voice (e.g.
`Matthew` or `Joanna`) reads naturally with the `<break>`/`<emphasis>`/
`<prosody>` tags already in place:

```bash
aws polly synthesize-speech \
  --engine neural --voice-id Matthew --output-format mp3 \
  --text-type ssml --text file://docs/bidwright/demo_video_ssml.xml \
  docs/bidwright/demo_narration.mp3
```

Polly caps a single request around 3,000 billed characters for the neural
engine on some accounts/regions — if the call errors on length, split at
the `<!-- SECTION -->` boundaries into 5 requests and concatenate the MP3s
(the `<break>` tags already keep section boundaries natural for a clean
cut). Time each screen action in the runbook above to the corresponding
narration by ear once you have the audio — the SSML's section comments give
you the anchor points.

## If you have more time (extended cut, +60-90s)

Not in the core 3-minute cut, but genuinely differentiating if you want a
longer video or a separate feature-highlight clip:

- **Teaming partner gap-fill advisor** — for a gap that's plausibly
  fillable by bringing in a subcontractor/JV partner rather than fixed
  in-house, BidWright writes concrete search guidance (SAM.gov SubNet, a
  PTAC/APEX Accelerator, a named trade association) plus a ready-to-send
  outreach email draft. Screen: `teaming_plan.md` tab.
- **Amendment / addendum impact analysis** — pass `--amendment` and
  BidWright diffs it against the already-extracted requirements, flags
  whether anything previously marked "met" is now stale, and surfaces a
  blocking amendment as an "AMENDMENT ALERT" banner at the top of
  `decisions_needed.md`.
- **Portfolio Insights** — recurring compliance gaps across a company's
  last 5 bids (e.g. "insufficient bonding capacity" showing up 3 bids in a
  row), detected by plain code over a small local history file, no LLM.

## Screenshots available for cutaways / thumbnails

`docs/bidwright/screenshots/`: `01_initial_state.png`, `02_running.png`,
`03_decisions_needed.png`, `04_proposal_draft.png` (Streamlit demo), and
`webui_01_initial.png` through `webui_06_chat.png` (the web UI — use these
as the primary source since the flow above is built around the web UI).
