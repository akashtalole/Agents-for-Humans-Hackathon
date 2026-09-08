# ClaimClarity demo flow

A recording runbook for the submission video. Pairs with
`demo_video_ssml.xml` — section numbers below match the SSML's section
comments.

See `JUDGING_CRITERIA.md` for the five official judging criteria mapped
one-to-one to a specific screenshot and script line — useful both as a
sanity check that this flow's beats actually earn points on every
criterion, and as a standalone judge-facing pitch sheet.

**Target length: ~4:15–4:30** at a natural narration pace (measured from
the actual SSML word count + break tags below). If you want it closer to
Devpost's commonly-recommended ~3:30: wrap the SSML body in
`<prosody rate="115%">`, or cut the Independent Audit beat from section 4
(the two-denials-told-apart moment and the ICD-10 tool-call moment are the
load-bearing beats; the cross-check is the easiest one to move to the
"more time" list without losing the core pitch). This flow is already cut
to the pipeline's strongest, most demoable beats — everything left out is
listed under "If you have more time" at the bottom.

## What you need running before you hit record

- The web UI, not the Streamlit demo, as the primary screen:
  `cd webapp/claimclarity && npm install && npm run build && cd ../..` then
  `python3 server_claimclarity.py` → `http://localhost:8000`.
- A real `ANTHROPIC_API_KEY` in `.env` — record a genuine live run.
- The bundled example pre-selected: a denial notice with two line items
  under the same diagnosis code, one a real billing error, one a genuine
  plan exclusion — the "two identically-worded denials, told apart
  correctly" moment is the strongest visual beat in the whole video.

## Section-by-section

**1. Hook + problem (~0:00–0:45)** — Screen: static title card / a dense
Explanation of Benefits, "CLAIM DENIED" visible. Narration: most denied
claims never get appealed, and a lot of denials are pure mechanical
billing errors.

**2. Who it's for (~0:45–1:15)** — Screen: title card or simple icon strip.
Narration: patients, caregivers, small billing offices.

**3. Why it matters (~1:15–1:40)** — Screen: cut to the web UI landing
screen, header status pill visible. Narration: hours of confusion vs. one
decision summary, and it never recommends fighting a denial that's
genuinely valid.

**4. Live demo walkthrough (~1:40–3:55) — the core of the video**
- Click **Run** on the bundled example. Screen: hold on the live activity
  log for a few seconds — specifically let a `lookup_icd10_code` /
  `search_icd10_codes` tool call line be visible and readable; this is the
  single most important visual proof point in the video (a real tool call,
  not the model guessing at coding rules from memory).
- Cut to **Denial Findings**: point at the two line items landing in
  different buckets — `billing_error` (corrected code found) vs.
  `valid_denial` (genuine plan exclusion) — same starting diagnosis code,
  correctly told apart.
- Cut briefly to the **Independent Audit** tab (cross-check output) —
  narration explains this is a pure-code diff (no second LLM call needed
  here, since findings key off a stable procedure code), and any
  disagreement forces that line item to `needs_review` rather than trusting
  either investigation alone.
- Cut to **Appeal Package**: the real, ready-to-send letter for the
  billing-error item, and the honest "not worth appealing, here's why" note
  for the valid denial — no doomed letter drafted just to be agreeable.
- Cut to the **Approval** panel: edited-text textarea, click **Approve**
  (mention this gate exists precisely because whoever's using this is often
  not watching every file get written — sick, stressed, or just busy).
- Cut to **Decisions Needed**, held for a beat — the landing point.

**5. Close (~3:55–4:20)** — Screen: ClaimClarity title card, then a 2-3
second architecture diagram flash. Narration: it drafts, a human always
sends it; then genuinely forward-looking next steps only (a full live
ICD-10-CM source instead of the curated demo subset, more insurers' plan
formats).

## Generating the audio

Same Polly workflow as BidWright:

```bash
aws polly synthesize-speech \
  --engine neural --voice-id Joanna --output-format mp3 \
  --text-type ssml --text file://docs/claimclarity/demo_video_ssml.xml \
  docs/claimclarity/demo_narration.mp3
```

If a single request exceeds Polly's neural-engine character cap, split at
the `<!-- SECTION -->` boundaries into 5 requests and concatenate.

## If you have more time (extended cut, +60-90s)

- **Insurer Accountability Tracker** — after 2+ separate claims from the
  *same insurer* get denied for the *same reason*, ClaimClarity surfaces
  that pattern in `insurer_pattern_report.md` ("this insurer has denied
  physical therapy on this exact basis three times now") — a materially
  stronger fact to hand an appeals reviewer or a state DOI complaint than
  one denial looked at alone. Privacy note worth a line on screen: the
  history file records only insurer name, timestamp, procedure, denial
  reason, and appeal-worthiness — never the patient's name, member ID,
  diagnosis codes, or clinical notes.
- **Physician Letter of Medical Necessity — Evidence Request Builder** —
  for a denial where a physician LMN would help, ClaimClarity drafts the
  specific request to send the doctor's office, naming exactly what
  clinical detail is missing.
- **External Review & Regulatory Escalation** — when an internal appeal
  isn't enough, generates the next-step guidance for state external review
  or a DOI complaint.

## Screenshots available for cutaways / thumbnails

`docs/claimclarity/screenshots/`: `01_initial_state.png` (Streamlit demo;
`02_crash_after_run_click.png` documents a bug that has since been fixed —
don't use it in the video) and `webui_01_initial.png` through
`webui_07_rejected.png` (the web UI — use these as the primary source).
