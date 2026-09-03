# Testing ClaimClarity

These steps assume no prior context beyond a clean machine with Python 3.10+
and git.

## 1. Get the code

```bash
git clone https://github.com/akashtalole/Agents-for-Humans-Hackathon.git
cd Agents-for-Humans-Hackathon
git checkout claude/devpost-claimclarity   # or `main` once this branch is merged
```

## 2. Set up the environment

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[ui,dev]"
```

This installs ClaimClarity plus its two sibling projects in the same repo
(BidWright, GlacierWatch share the same `pyproject.toml`), Streamlit for the
demo UI, and pytest for the test suite.

## 3. Configure credentials

ClaimClarity talks to either Anthropic's API directly or Amazon Bedrock — it
picks automatically based on what's set.

**Option A — Anthropic API key (simplest):**

```bash
cp .env.example .env
# edit .env and set:
ANTHROPIC_API_KEY=sk-ant-...
```

**Option B — Amazon Bedrock (no Anthropic key):** configure standard AWS
credentials (`aws configure`, or `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`
env vars, or an `AWS_PROFILE`) with access to Bedrock and the
`claude-sonnet-4-5` model in your region. No `.env` needed.

Verify which provider ClaimClarity will use:

```bash
claimclarity status
```

## 4. Run the offline test suite (no cost, no API key needed)

```bash
pytest
```

Expect **112 passed, 3 skipped** in a few seconds. This covers the Pydantic
schemas, document/calendar/ICD-10 tools, deterministic Markdown rendering,
and orchestrator wiring (every pipeline stage driven through Strands'
`agent.tool.<name>(...)` interface with the sub-agents mocked) — no network
calls, nothing billed. The 3 skips are opt-in live-model integration tests
across the repo's three projects.

## 5. Run the real thing — CLI

This makes real, billed calls to whichever model provider you configured in
step 3 (three sub-agent calls plus the orchestrator's own turns, including
real ICD-10 lookup tool calls). It takes a few minutes end to end.

```bash
claimclarity run \
  --document examples/claimclarity/denial_notice.md \
  --document examples/claimclarity/plan_summary_of_benefits.md \
  --document examples/claimclarity/medical_record_excerpt.md \
  --out output
```

You'll see each tool call streamed live to stderr, then a **"Decisions
needed"** section (rendered deterministically from validated data — the
trusted headline), followed by the orchestrator's own free-text reply
(labeled informational-only). Files land in `output/`:
`claim_summary.md`, `denial_findings.md`, `decisions_needed.md`,
`appeal_package.md`, `appeal_deadline.ics`.

The bundled example is a physical therapy claim (CPT 97110, billed with a
diagnosis code retired for billing purposes in FY2022) bundled with a
massage-therapy line item (CPT 97124) that's a genuine plan exclusion. A
real run should classify the first as `billing_error` (worth appealing, with
a corrected code) and the second as `valid_denial` (not worth appealing) —
telling the two apart rather than recommending "appeal everything."

## 6. Run the real thing — Streamlit demo

```bash
streamlit run app_claimclarity.py
```

Opens at `http://localhost:8501`. The sidebar defaults to the bundled
example documents (or upload your own). Click **Run ClaimClarity**.

**Known issue:** clicking Run currently crashes the UI with
`streamlit.errors.NoSessionContext` — a real, reproducible bug in how the
demo's live activity-log callback touches Streamlit UI objects from a
background thread that Strands' synchronous agent call spins up
internally. It happens on the very first tool-call event, every time, for
every user, on the current code. Full root-cause detail (including a
captured screenshot of the crash and the exact fix) is in
`screenshots/NOTES.md` in this folder. It does not affect the CLI path in
step 5 above, or the underlying agent pipeline, which is unaffected and
fully working — only the demo UI's live log widget is affected.

## Automated tests included in this package

`pytest` (step 4) is the authoritative, repeatable test suite. Everything
under `docs/claimclarity/` in this branch — screenshots, the architecture
diagram, this file — documents one additional, genuine, live, human-run
verification pass on top of that automated suite, including the UI bug
found along the way; it is not a substitute for running `pytest` yourself.
