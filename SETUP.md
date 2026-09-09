# Setup guide

Getting all four projects running, from a clean machine. If you only want to
run the tests, **step 3 is the last step you need** — the whole suite runs
offline with no credentials.

- [Prerequisites](#prerequisites)
- [1. Clone and create a virtualenv](#1-clone-and-create-a-virtualenv)
- [2. Install the package](#2-install-the-package)
- [3. Verify the install](#3-verify-the-install)
- [4. Configure model credentials](#4-configure-model-credentials)
- [5. Run something](#5-run-something)
- [6. Build the web UIs](#6-build-the-web-uis-optional)
- [Troubleshooting](#troubleshooting)

## Prerequisites

| | Version | Needed for |
|---|---|---|
| **Python** | 3.11+ | everything |
| **Node.js** | 20+ | only the React web UIs (step 6) |
| **git** | any | cloning |
| **Model credentials** | — | only for live runs, not for tests |

A model credential means **either** an Anthropic API key **or** AWS
credentials with Amazon Bedrock access. You do not need both, and you need
neither to run the test suite.

## 1. Clone and create a virtualenv

```bash
git clone https://github.com/akashtalole/Agents-for-Humans-Hackathon.git
cd Agents-for-Humans-Hackathon

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
```

Everything below assumes the virtualenv is active. If a command fails with
`command not found`, that is usually the cause.

## 2. Install the package

The install is one editable package covering all four projects, with optional
extras layered on top:

| Extra | Pulls in | You need it for |
|---|---|---|
| *(base)* | Strands Agents SDK, Pydantic, httpx | the CLIs |
| `dev` | pytest | running the tests |
| `ui` | Streamlit | the Streamlit demos |
| `api` | FastAPI, uvicorn | the React web UIs (`server_*.py`) |
| `a2a` | `strands-agents[a2a]`, `a2a-sdk` | Trinetra's A2A agent server and peer client |
| `agentcore` | `bedrock-agentcore` | the optional AgentCore deployment path |

**Recommended for most people** — CLIs, web UIs, and tests:

```bash
pip install -e ".[api,ui,dev]"
```

**Everything, including A2A and AgentCore:**

```bash
pip install -e ".[api,ui,dev,a2a,agentcore]"
```

**Minimum to run the tests only:**

```bash
pip install -e ".[dev]"
```

> Note: a few tests import FastAPI's `TestClient`, so `pytest` on a
> `[dev]`-only install will skip-or-error on the four `test_*_api.py` files.
> If you want a green run, use `".[api,dev]"`. This is the one place the
> extras are not fully independent.

## 3. Verify the install

```bash
pytest
```

Expected: **504 passed, 3 skipped**. The three skips are opt-in live-model
tests (see [TESTING.md](TESTING.md)). No API key, no network, no cost.

Then check each CLI is on your PATH:

```bash
bidwright --help
claimclarity --help
glacierwatch --help
trinetra --help
```

If those four work and the tests pass, the install is good.

## 4. Configure model credentials

Only needed for live runs. Skip this if you are just reading or testing.

```bash
cp .env.example .env
```

Then edit `.env` and pick **one** option.

### Option A — Anthropic API directly

```bash
ANTHROPIC_API_KEY=sk-ant-...
```

Simplest path, and what every live example in this repo's docs was run
against.

### Option B — Amazon Bedrock

Leave `ANTHROPIC_API_KEY` blank and configure AWS credentials the normal way
(environment variables, `~/.aws/credentials`, or an assumed role). Each
project detects Bedrock automatically when no Anthropic key is present. You
need Bedrock **model access granted** for the Claude model in your region —
that is a one-time opt-in in the Bedrock console, and a missing grant is by
far the most common cause of an `AccessDeniedException` here.

### Checking which provider is active

Every project has a `status` command that tells you what it will use, without
making a billable call:

```bash
bidwright status
claimclarity status
glacierwatch status
trinetra status
```

You want to see either `Anthropic API direct (...)` or `Amazon Bedrock (...)`.
`No credentials found` means `.env` was not loaded or is empty.

### A note on the key

`.env` is gitignored and must never be committed. Nothing in this repo prints,
logs, or echoes the key — the AWS deploy scripts redact it even in `--dry-run`
output, and no build path (CodeBuild included) ever receives it; it is injected
only at service-creation time as a runtime environment variable.

Each project selects its provider independently, so you can point one at
Bedrock and another at Anthropic in the same checkout — see the per-project
`*_MODEL_PROVIDER` overrides in `.env.example`.

## 5. Run something

Each project's own doc has the full command reference. The fastest thing that
does real work in each:

```bash
# BidWright — read an RFP, check compliance, draft a proposal
bidwright run --rfp examples/sample_rfp.md --profile examples/company_profile.json

# ClaimClarity — read a denial letter, check it, draft the appeal
claimclarity run \
  --document examples/claimclarity/denial_notice.md \
  --document examples/claimclarity/plan_summary_of_benefits.md \
  --document examples/claimclarity/medical_record_excerpt.md

# GlacierWatch — prioritise Himalayan glacial-hazard monitoring (live weather + seismic)
glacierwatch run

# Trinetra — validate the crowd simulator against two real disasters (no API key needed)
trinetra calibrate
```

`trinetra calibrate` is the one live-ish command that costs nothing and needs
no credentials — the simulator and calibration are pure deterministic code.

For everything else — CLI flags, architecture, data sourcing, honest
limitations — see [BIDWRIGHT.md](BIDWRIGHT.md),
[CLAIMCLARITY.md](CLAIMCLARITY.md), [GLACIERWATCH.md](GLACIERWATCH.md), and
[TRINETRA.md](TRINETRA.md).

## 6. Build the web UIs (optional)

Each project ships a FastAPI backend plus a React + TypeScript frontend,
served from a single process so there is no CORS setup. The frontend must be
built once before the server can serve it:

```bash
pip install -e ".[api]"

cd webapp/bidwright     && npm install && npm run build && cd ../..
cd webapp/claimclarity  && npm install && npm run build && cd ../..
cd webapp/glacierwatch  && npm install && npm run build && cd ../..
cd webapp/trinetra      && npm install && npm run build && cd ../..
```

Then run whichever you want (each serves on `http://localhost:8000`, so run
one at a time):

```bash
python server_bidwright.py
python server_claimclarity.py
python server_glacierwatch.py
python server_trinetra.py
```

Trinetra additionally has a separate **A2A agent server** — a machine-facing
surface other agents can call, rather than a human-facing dashboard:

```bash
pip install -e ".[a2a]"
python server_trinetra_a2a.py          # or: trinetra a2a-serve --port 9100
curl http://localhost:9100/.well-known/agent-card.json
```

## 7. Build the documentation site (optional)

The published site is at
<https://akashtalole.github.io/Agents-for-Humans-Hackathon/>, rebuilt by GitHub
Actions on every push to `main`. To work on it locally:

```bash
pip install -r requirements-docs.txt

python scripts/build_docs.py --serve    # live-reload at http://127.0.0.1:8000
python scripts/build_docs.py --build    # one-off strict build
```

`scripts/build_docs.py` stages the repo's Markdown into `.mkdocs-build/`
(gitignored) **preserving each file's repository-relative path**. That is what
lets the existing relative links keep working in both places at once — MkDocs
rewrites `.md` links to built URLs, so `[SETUP.md](SETUP.md)` resolves on the
site and on GitHub with no rewriting and no plugin. Read that script's
docstring before restructuring the docs.

`--build` uses `--strict`, so a broken internal link fails the build rather
than publishing a broken page. CI runs the same thing on every pull request.

## Troubleshooting

**`pytest` reports far fewer than 504 tests**
You are probably running a stale install. Re-run `pip install -e ".[api,ui,dev]"`
and confirm with `pip show agents-for-humans-hackathon` that the editable install
points at your checkout.

**`ModuleNotFoundError: No module named 'fastapi'`**
Install the `api` extra: `pip install -e ".[api]"`.

**`ModuleNotFoundError: No module named 'a2a'`**
Install the `a2a` extra: `pip install -e ".[a2a]"`. Only Trinetra's A2A server
and peer client need it; the rest of the repo does not.

**`No credentials found` from a `status` command**
`.env` was not created or not loaded. Confirm `.env` exists in the repo root
and contains a non-empty `ANTHROPIC_API_KEY`, or that your AWS credentials
resolve (`aws sts get-caller-identity`).

**`AccessDeniedException` on Bedrock**
Model access has not been granted for that Claude model in that region. Grant
it in the Bedrock console, then retry. Check the region matches too — an
unset `AWS_REGION` defaults somewhere you may not expect.

**A server starts but the page is blank, or the API answers with old data**
The frontend was not built, or a previous server is still holding port 8000.
Build the frontend (step 6), and check for a stale process:

```bash
lsof -i :8000
```

This bit us during development: a "new" server silently failed to bind and an
old process kept answering `/api/status`, which looked exactly like a code
change having no effect.

**Frontend build fails on `npm install`**
Node 20+ is required. Check with `node --version`.

**A live run is slow**
That is expected for the multi-agent flows. Trinetra's incident-command flow
in particular chains six model calls in series and takes roughly four minutes;
the individual project docs note the runtimes that matter.
