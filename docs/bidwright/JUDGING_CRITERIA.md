# BidWright — mapped to the Agents for Humans judging criteria

Per the actual rules at https://agentsforhumans.devpost.com/rules, Stage
Two judging uses five **equally weighted** criteria. This maps each one to
a specific, real screen in BidWright's web UI (`docs/bidwright/screenshots/
judging_0{1-5}_*.png` — captured from a live run against the real Anthropic
API, not staged) and a short line of narration to say while showing it in
the demo video. Slot these lines into `demo_video_ssml.xml` / `DEMO_FLOW.md`
at the matching beat, or read this file standalone as a judge-facing pitch
sheet.

---

## 1. Technical Implementation

> "How thoroughly and skillfully does the project use Strands Agents? Does
> the code reflect genuine effort and a working, non-trivial
> implementation?"

**Screenshot:** `judging_01_technical_implementation.png` — the live
activity log, mid-run, streaming real tool calls.

**Script:**
> "This isn't a mockup. Every line in this activity log is a real Strands
> tool call, happening live — an orchestrator agent coordinating
> specialized sub-agents, each one calling real tools and returning
> validated, structured Pydantic output, not loose text one agent hands the
> next and hopes is right."

**Why this screen:** it's the most concrete, hardest-to-fake evidence of
"genuine effort and a working, non-trivial implementation" — a static
screenshot of a finished report could be mocked up in an afternoon; a
live-streaming Server-Sent-Events log of real tool calls against a real
model can't be. The orchestrator ("agents as tools" pattern), the
Pydantic-validated hand-offs between sub-agents, and the independent
cross-check agent (a second full agent invocation, not a cheaper
heuristic) are the specific technical depth this criterion is asking
about.

---

## 2. Design

> "Does the project deliver a complete, coherent product experience — not
> just a technical proof of concept?"

**Screenshot:** `judging_02_design.png` — the approval panel: reviewer
verdict, guardrail findings, an editable draft textarea, and explicit
Approve/Reject actions.

**Script:**
> "And nothing here ships without a human. Before a proposal ever reaches
> the business owner, it passes a critic agent and a guardrail scan — and
> even then, it lands in an approval panel, not a mailbox. The owner reads
> the reviewer's verdict, edits the draft if they want to, and has to
> actually click Approve. That's a product decision, not just a technical
> one."

**Why this screen:** a results page showing generated files proves the
pipeline runs; this screen proves BidWright is a *product* with a real
workflow — review, disclosure, edit, explicit consent — not a script that
dumps output and exits. It's also the single screen that best shows the
project isn't "just a technical proof of concept": the human-in-the-loop
gate is a deliberate design choice with UI consequences (the checkbox
acknowledgment when guardrail findings exist), not an afterthought.

---

## 3. Potential Impact

> "Does the project make a credible, specific case for solving a real
> problem for a real audience?"

**Screenshot:** `judging_03_potential_impact.png` — the Compliance Report
tab, showing the real caught gap: general liability insurance at $1M
against the RFP's $2M-per-occurrence requirement.

**Script:**
> "Here's the case, made concrete: this company's actual insurance is a
> genuine one million dollars short of what this RFP requires. That's
> exactly the kind of technicality that gets a qualified small business
> disqualified — not on price, not on quality of work, on a detail nobody
> had time to cross-check by hand. BidWright caught it automatically, with
> a specific number and a specific fix."

**Why this screen:** "credible and specific" is the operative phrase in
this criterion — a generic "saves time" claim isn't credible on its own,
but a real dollar-amount insurance shortfall, caught against a real RFP's
real requirement, is a specific, checkable fact a judge can verify by
reading the same report. This is the single screen that turns the pitch
from an abstract claim into evidence.

---

## 4. Creativity & Originality

> "Is this a creative, non-obvious use of Strands Agents — and does the
> team demonstrate genuine understanding of the problem space?"

**Screenshot:** `judging_04_creativity_originality.png` — the Independent
Audit tab (the cross-check output).

**Script:**
> "Most agent demos stop at one model call per step. BidWright runs a
> second, completely independent compliance auditor — same requirements,
> same company profile, but it never sees the first check's answer. When
> the two disagree, that's not resolved by picking a winner; it's forced
> into 'needs review' so a human decides. Adversarial cross-verification
> between two independent agents, not one agent revising its own work —
> that's a genuinely different multi-agent pattern than a linear pipeline."

**Why this screen:** the obvious way to use an agent SDK for compliance
checking is one model call that reads requirements and produces a verdict
— BidWright does that too, but layers a second, architecturally distinct
verification agent on top specifically because a single LLM call checking
its own homework is a known failure mode. This is also honestly the
feature that caught a real bug during live testing (documented in
BIDWRIGHT.md's "Independent Compliance Cross-Check" section) — genuine
evidence of understanding the problem space, not just building toward a
demo.

---

## 5. Presentation

> "Does the video clearly demonstrate the project working end-to-end? Does
> the pitch communicate what problem is solved, who it's for, and why it
> matters?"

**Screenshot:** `judging_05_presentation.png` — the Decisions Needed tab,
the pipeline's single landing summary.

**Script:**
> "And everything funnels here — one place. Ready to submit, or here's
> exactly what's blocking and what closes it. A busy owner with no
> compliance team doesn't need to read five files to know what to do next;
> they read this one."

**Why this screen:** this is deliberately the *last* screen of the demo,
not a mid-pipeline detail — it's the visual proof that the whole run
actually completed end-to-end and converges on one coherent answer,
which is exactly what this criterion is checking for. It's also the
cleanest single-sentence answer to "what problem is solved, who for, and
why it matters": one summary instead of five documents an owner has no
time to read.
