# ClaimClarity — mapped to the Agents for Humans judging criteria

Per the actual rules at https://agentsforhumans.devpost.com/rules, Stage
Two judging uses five **equally weighted** criteria. This maps each one to
a specific, real screen in ClaimClarity's web UI (`docs/claimclarity/
screenshots/judging_0{1-5}_*.png` — captured from a live run against the
real Anthropic API, not staged) and a short line of narration to say while
showing it in the demo video. Slot these lines into `demo_video_ssml.xml` /
`DEMO_FLOW.md` at the matching beat, or read this file standalone as a
judge-facing pitch sheet.

---

## 1. Technical Implementation

> "How thoroughly and skillfully does the project use Strands Agents? Does
> the code reflect genuine effort and a working, non-trivial
> implementation?"

**Screenshot:** `judging_01_technical_implementation.png` — the live
activity log, mid-run, showing a real `lookup_icd10_code` / `search_icd10_
code` tool call.

**Script:**
> "Watch this line specifically: that's a real ICD-10 lookup tool being
> called, live. Instead of reasoning about medical billing codes from a
> language model's memory — a well-documented source of confidently wrong
> billing advice — the Denial Investigator agent actually looks the code up
> before concluding anything about it."

**Why this screen:** the single riskiest thing an LLM-based medical-coding
tool could do is answer from memory instead of a real source of truth —
this screenshot is direct, checkable proof it doesn't. It's also the
clearest evidence of "genuine effort": grounding a domain-specific
judgment in a real external tool call is meaningfully harder to build (and
to get right) than a single prompt-and-answer LLM call.

---

## 2. Design

> "Does the project deliver a complete, coherent product experience — not
> just a technical proof of concept?"

**Screenshot:** `judging_02_design.png` — the approval panel: reviewer
verdict, guardrail findings, and explicit Approve/Reject actions on the
drafted appeal letter.

**Script:**
> "ClaimClarity drafts the appeal — it never sends it. It lands here, in an
> approval panel, because whoever's reading this is often not watching
> every file get written; they're sick, or stressed, or just busy. A human
> has to actually approve it, edits included, before it's marked done."

**Why this screen:** a stack of generated documents is a technical proof of
concept; a review-and-consent workflow built around the reality that the
end user is often not in a position to carefully audit five files is a
product decision — this screen is the clearest evidence ClaimClarity was
designed around its actual audience (a stressed patient or overworked
caregiver), not just around what the pipeline could technically produce.

---

## 3. Potential Impact

> "Does the project make a credible, specific case for solving a real
> problem for a real audience?"

**Screenshot:** `judging_03_potential_impact.png` — the Denial Findings
tab, showing two line items billed under the *same* diagnosis code landing
in two *different* classifications.

**Script:**
> "Same starting diagnosis code, two denied line items — and ClaimClarity
> tells them apart correctly. One's a mechanical billing error: the code
> was retired for billing purposes, and the corrected replacement code is
> right there. The other is a genuine plan exclusion — no coding fix
> changes that, so it's honestly told not worth appealing. That's the whole
> value proposition in one screen: know which fight is actually winnable."

**Why this screen:** "credible and specific" means a judge should be able
to verify the claim by reading the same screen — this one shows an exact,
checkable fact pattern (same code, different real outcomes) rather than an
abstract claim about saving time. It also directly demonstrates the
project's most important honesty property: it doesn't just say "appeal
everything" to seem helpful.

---

## 4. Creativity & Originality

> "Is this a creative, non-obvious use of Strands Agents — and does the
> team demonstrate genuine understanding of the problem space?"

**Screenshot:** `judging_04_creativity_originality.png` — the Independent
Audit tab (the cross-check output).

**Script:**
> "A second, fully independent investigation runs right after the first —
> same claim, same real coding tools, but it never sees the first
> investigator's conclusion. Because every finding carries a stable
> procedure code, comparing the two doesn't even need another model call:
> it's a plain code diff, and any disagreement forces that line item to
> needs-review instead of quietly trusting either investigation alone."

**Why this screen:** the non-obvious design choice here isn't just "run two
agents" — it's recognizing that comparing two independent LLM-produced
findings lists doesn't need a third LLM call when the underlying data has
a stable key (the procedure code), and building the comparison as
deterministic code instead. That's the kind of judgment call that shows
real understanding of when an agent is the right tool and when plain code
is more trustworthy — not "more AI" for its own sake.

---

## 5. Presentation

> "Does the video clearly demonstrate the project working end-to-end? Does
> the pitch communicate what problem is solved, who it's for, and why it
> matters?"

**Screenshot:** `judging_05_presentation.png` — the Decisions Needed tab,
the pipeline's single landing summary.

**Script:**
> "And everything lands here — one place. What's worth appealing, what
> isn't and why, and the deadline. A stressed patient staring down an
> Explanation of Benefits with no billing background doesn't need to
> understand ICD-10 coding; they need to read this one page and know what
> to do next."

**Why this screen:** placed last in the demo on purpose — it's the visual
proof the full pipeline actually converged on one coherent, decision-ready
answer, which is exactly what "working end-to-end" means here. It's also
the tightest possible answer to who this is for and why it matters: a
person with no billing background, handed exactly one page instead of a
stack of confusing paperwork.
