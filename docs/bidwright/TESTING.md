# Testing BidWright

These steps assume no prior context beyond a clean machine with Python 3.10+
and git.

## 1. Get the code

```bash
git clone https://github.com/akashtalole/Agents-for-Humans-Hackathon.git
cd Agents-for-Humans-Hackathon
git checkout claude/devpost-bidwright   # or `main` once this branch is merged
```

## 2. Set up the environment

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[ui,dev]"
```

This installs BidWright plus its two other sibling projects in the same repo
(ClaimClarity, GlacierWatch share the same `pyproject.toml`), Streamlit for
the demo UI, and pytest for the test suite.

## 3. Configure credentials

BidWright talks to either Anthropic's API directly or Amazon Bedrock — it
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

Verify which provider BidWright will use:

```bash
bidwright status
```

## 4. Run the offline test suite (no cost, no API key needed)

```bash
pytest
```

Expect **112 passed, 3 skipped** in a couple of seconds. This covers the
Pydantic schemas, document/calendar tools, deterministic Markdown rendering,
and orchestrator wiring (every pipeline stage driven through Strands'
`agent.tool.<name>(...)` interface with the sub-agents mocked) — no network
calls, nothing billed. The 3 skips are the opt-in live-model integration
tests described below.

## 5. Run the real thing — CLI

This makes real, billed calls to whichever model provider you configured in
step 3 (three sub-agent calls plus the orchestrator's own turns). It takes a
few minutes end to end.

```bash
bidwright run --rfp examples/sample_rfp.md --profile examples/company_profile.json --out output
```

You'll see each tool call streamed live to stderr, then a **"Decisions
needed"** section (rendered deterministically from validated data — the
trusted headline), followed by the orchestrator's own free-text reply
(labeled informational-only). Files land in `output/`:
`requirements.md`, `compliance_report.md`, `decisions_needed.md`,
`proposal_draft.md`, `submission_deadline.ics`.

The bundled example is a municipal landscaping RFP paired with a
deliberately underinsured example company, so you should see multiple real
blocking gaps (insurance below the required minimums, a missing signed
cover letter, a missing pricing schedule, among others) plus one
non-blocking gap (no ISA-certified arborist on staff, which the RFP lists as
preferred, not required).

## 6. Run the real thing — Streamlit demo

```bash
streamlit run app_streamlit.py
```

Opens at `http://localhost:8501`. The sidebar defaults to the bundled
example RFP and company profile (or upload your own). Click **Run
BidWright** and watch the live agent activity log; when it finishes, the
**Decisions Needed** tab is selected by default, with **Requirements**,
**Compliance Report**, **Proposal Draft**, and **Agent's Own Summary
(unverified)** tabs alongside it. Same cost/timing caveats as the CLI run
above — this is a real model run, not a canned demo.

## 7. (Optional) Live integration test

```bash
BIDWRIGHT_RUN_INTEGRATION=1 pytest tests/test_pipeline_integration.py
```

Runs the full pipeline against a real model and asserts on the actual
output. Requires working credentials from step 3; also billed and takes a
few minutes.

## 8. (Optional) AWS Bedrock AgentCore deployment

Not required for judging the core submission. See
[`deploy/cloudshell/README.md`](../../deploy/cloudshell/README.md) for the
one-shot CloudShell scripts (`setup.sh` / `invoke_samples.sh` /
`teardown.sh`) that deploy BidWright to Amazon Bedrock AgentCore Runtime.
This creates real, billable AWS resources and has not been run end-to-end
against a live AWS account — treat it as documented-but-unverified.

## Also worth running: the React web UI

These instructions predate the FastAPI + React interface, which is the one
most people will actually look at. It is a separate surface from the
Streamlit demo above, served from a single process (no CORS setup), and it
needs the frontend built once first:

```bash
pip install -e ".[api]"
cd webapp/bidwright && npm install && npm run build && cd -
python server_bidwright.py          # -> http://localhost:8000
```

Requires Node 20+. All four projects' servers use port 8000, so run one at a
time — and if a page looks stale, check for a leftover process with
`lsof -i :8000` before assuming a code change had no effect.

See [`../../SETUP.md`](../../SETUP.md) for the full setup guide and
[`../../TESTING.md`](../../TESTING.md) for the repo-wide testing reference,
including what the offline suite does and does not verify.

