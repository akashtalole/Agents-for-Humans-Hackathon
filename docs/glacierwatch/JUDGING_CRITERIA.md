# GlacierWatch — mapped to the Agents for Humans judging criteria

Per the actual rules at https://agentsforhumans.devpost.com/rules, Stage
Two judging uses five **equally weighted** criteria. This maps each one to
a specific, real screen in GlacierWatch's web UI (`docs/glacierwatch/
screenshots/judging_0{1-5}_*.png` — captured from a live run against the
real Anthropic API, real Open-Meteo weather data, and real USGS seismic
data, not staged) and a short line of narration to say while showing it in
the demo video. Slot these lines into `demo_video_ssml.xml` / `DEMO_FLOW.md`
at the matching beat, or read this file standalone as a judge-facing pitch
sheet.

The Independent Audit tab referenced below (`risk_cross_check.md`) is a
feature the orchestrator already generated but that the web UI never
surfaced until this pass — capturing these screenshots required actually
wiring it up as a proper tab (`webapp/glacierwatch/src/components/
ResultsTabs.tsx`), matching how BidWright and ClaimClarity already exposed
their equivalent cross-check tabs.

---

## 1. Technical Implementation

> "How thoroughly and skillfully does the project use Strands Agents? Does
> the code reflect genuine effort and a working, non-trivial
> implementation?"

**Screenshot:** `judging_01_technical_implementation.png` — the live
activity log, mid-run, showing a real Open-Meteo and/or USGS tool call.

**Script:**
> "Every one of these lines is a real tool call, happening live: loading
> the watchlist, then reaching out to Open-Meteo for today's actual
> rainfall data, and to the U.S. Geological Survey for real recent
> earthquake activity near each site. Nothing here is mocked — if a fetch
> fails, the agent says so instead of quietly making up a number."

**Why this screen:** for a hazard-triage tool specifically, "genuine
effort and a working implementation" has to mean real external data, not
plausible-sounding placeholder numbers — this screenshot is the direct,
checkable proof that the weather and seismic figures behind every priority
judgment are live API responses, fetched at the moment the report ran, not
hardcoded or hallucinated.

---

## 2. Design

> "Does the project deliver a complete, coherent product experience — not
> just a technical proof of concept?"

**Screenshot:** `judging_02_design.png` — captured from a real run: no site
hit `priority` level that day, so GlacierWatch went straight to
`completed` with the disclaimer banner and "No sites at priority level
this week" status badge, rather than the Approve-All panel for Community
Alert Bulletins (that panel only appears when there's a bulletin that
actually needs human sign-off — see the note below on how the app behaves
on a day a site *does* hit priority).

**Script (what's on screen — no site at priority this run):**
> "This week, nothing crossed the priority threshold — and the app says so
> plainly, with the same disclaimer banner and status badge on every run,
> whether or not there's something urgent to report."

**If you record on a day a site does hit priority,** the app instead shows
an Approve-All panel before those bulletins are considered done — worth
narrating instead if it happens to come up on your recording day:
> "When a site is assessed at priority level, GlacierWatch doesn't publish
> the resulting community alert automatically — a human reviews and
> approves every one of them here first, because this is public-facing
> text meant for a village committee, not an internal report."

**Why this screen:** a "coherent product experience" for a disaster-triage
tool specifically means the UI's behavior changes in a principled way
depending on what's actually true this week — a human approval gate
appears only when there's public-facing text that actually needs a human's
eyes, and a calm, honest "nothing to report" state exists and is shown
plainly rather than treated as an edge case to hide.

---

## 3. Potential Impact

> "Does the project make a credible, specific case for solving a real
> problem for a real audience?"

**Screenshot:** `judging_03_potential_impact.png` — the Weekly Watchlist
tab, showing this run's actual priority levels per site.

**Script:**
> "This is the trusted report a state disaster management authority or a
> village-level committee would actually read: this week's real conditions,
> combined with each site's documented, published risk profile, turned
> into one honest priority list — never a guess, and never a forecast of
> when a failure might happen."

**Why this screen:** the credibility case for GlacierWatch rests on a real,
named disaster (the hook in section 1 of the demo video) and a real
institutional gap — India's disaster management authority actively
monitors 56 lakes, and there are over 28,000 catalogued — this screen is
where that case becomes concrete: an actual triage output, for an actual
short watchlist of real, cited sites, that a real authority with limited
field teams could act on this week.

---

## 4. Creativity & Originality

> "Is this a creative, non-obvious use of Strands Agents — and does the
> team demonstrate genuine understanding of the problem space?"

**Screenshot:** `judging_04_creativity_originality.png` — the Independent
Audit tab (the cross-check output).

**Script:**
> "Every site's priority is independently re-checked by a second agent that
> never sees the first assessment's answer. When the two disagree,
> GlacierWatch always adopts whichever rating is more cautious — never the
> more convenient one. Understating risk here is worse than overstating
> it, so that's the only direction ties ever break."

**Why this screen:** the non-obvious insight is domain-specific, not
generic multi-agent boilerplate — most cross-check designs would resolve a
disagreement by picking whichever answer seems more confident, or by
averaging; GlacierWatch's rule is asymmetric on purpose, because in a
hazard-triage tool the cost of a false "routine" is categorically worse
than the cost of a false "elevated." That's a design decision that comes
directly from understanding the problem space, not from a generic
agent-orchestration pattern applied without thought to what it's for.

---

## 5. Presentation

> "Does the video clearly demonstrate the project working end-to-end? Does
> the pitch communicate what problem is solved, who it's for, and why it
> matters?"

**Screenshot:** `judging_05_presentation.png` — the Current Conditions tab,
the real live numbers (precipitation on India's official rainfall scale,
nearest seismic events with distance and magnitude) behind this run's
judgment.

**Script:**
> "And here's the actual live data behind every judgment on this page —
> fetched at the moment this report ran. Because the honest answer to 'can
> you predict the next glacier disaster' is no. But 'can you help someone
> watch the right place this week' — that one, we can actually say yes
> to."

**Why this screen:** placed last, it closes the loop the hook opened —
this is the receipts screen, the literal numbers a village committee or
disaster authority would want to see before trusting a priority list with
real consequences. It's also the natural home for the project's core
honesty framing (decision support, never prediction), which is the single
most important thing the pitch needs to communicate about why this
project's approach matters.
