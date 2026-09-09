# Testing GlacierWatch

These steps assume no prior context beyond a checkout of this repository. GlacierWatch needs no input files from the tester — it always runs against its own bundled reference watchlist.

## 1. Clone and check out

```bash
git clone https://github.com/akashtalole/Agents-for-Humans-Hackathon.git
cd Agents-for-Humans-Hackathon
git checkout claude/devpost-glacierwatch    # or `main`, once this branch is merged
```

## 2. Set up a Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[ui,dev]"
```

This installs GlacierWatch alongside BidWright and ClaimClarity (all three share one `pyproject.toml`), plus the Streamlit UI extras and dev/test dependencies.

## 3. Configure model credentials (only needed for a live run)

GlacierWatch talks to Anthropic's API directly by default, or to Amazon Bedrock if AWS credentials are present instead. You only need this for steps 5 and 6 below — the offline test suite (step 4) needs neither.

```bash
cp .env.example .env
# then edit .env and set ANTHROPIC_API_KEY=sk-ant-...
# — or, to use Bedrock instead, configure standard AWS credentials
#   (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_REGION, or an AWS profile)
#   and leave ANTHROPIC_API_KEY unset.
```

Check which provider will actually be used:

```bash
glacierwatch status
```

## 4. Run the offline test suite (no cost, no network, no API key)

```bash
pytest
```

Expect **30+ tests to pass** (offline GlacierWatch tests plus BidWright/ClaimClarity's own suites in the same run — the full repo suite is 112 passed / 3 skipped as of this writing). All HTTP calls to Open-Meteo and USGS are mocked with fixtures shaped identically to real captured API responses, so this exercises the parsing, IMD rainfall categorization, distance calculation, rendering, and orchestrator tool-wiring logic without touching the network or spending any API credits. This is the fastest way to confirm nothing is broken.

To run only GlacierWatch's own tests:

```bash
pytest tests/ -k glacierwatch
```

## 5. Run the CLI (real API calls, real cost)

```bash
glacierwatch run --out output
```

This is a genuine end-to-end run:
- **Real, free HTTP calls** to Open-Meteo (precipitation) and the USGS earthquake catalog (seismic activity) for each active-watch site.
- **Real, billed calls** to your configured model provider (Anthropic API or Bedrock) — the orchestrator agent and its two sub-agents (`risk_assessor`, `report_drafter`) all make real model calls.
- **Takes a few minutes** — expect roughly 2-5 minutes depending on model and network latency.
- **No input required** — it always runs against the bundled reference watchlist in `glacierwatch/data/watchlist.json`.

You'll see each tool call streamed live in the terminal as it happens (including the live weather/seismic fetches), then the deterministic `watchlist_report.md`-derived report printed as the trusted headline, followed by the orchestrator's own (clearly labeled, informational-only) summary. Files are written to `output/`: `watchlist_report.md` (the trusted output), plus `site_profile_*.md` and `site_conditions_*.md` per site.

A transient failure fetching live conditions for one site (e.g. a brief Open-Meteo timeout) is expected to occasionally happen and is handled honestly — the tool reports the failure rather than fabricating data, and still assesses every other site.

## 6. Run the Streamlit demo (real API calls, real cost)

```bash
streamlit run app_glacierwatch.py
```

Open the URL Streamlit prints (typically `http://localhost:8501`). Click **Run GlacierWatch** in the sidebar — no other input is needed. It runs the same live pipeline as the CLI, shows a live agent activity log while it works, and once complete shows four tabs: **Weekly Watchlist** (the trusted, disclaimed report — treat this as the source of truth), **Site Profiles**, **Current Conditions** (the live-fetched weather/seismic data), and **Agent's Own Summary (unverified)**. A download button lets you save `watchlist_report.md`.

## Notes for judges

- Every run is genuinely live — there is no demo/mock mode. Both the CLI and the UI make real calls to Open-Meteo, USGS, and your configured LLM provider each time.
- If you don't have model credentials handy, step 4 (`pytest`) is a complete, credential-free way to verify the codebase's correctness — the offline coverage described in `GLACIERWATCH.md`'s "Honest limitations" section explains exactly what is and isn't verified that way.
- An opt-in live integration test also exists, combining a real API/model run with automated assertions:
  ```bash
  GLACIERWATCH_RUN_INTEGRATION=1 pytest tests/test_glacierwatch_pipeline_integration.py
  ```

## Also worth running: the React web UI

These instructions predate the FastAPI + React interface, which is the one
most people will actually look at. It is a separate surface from the
Streamlit demo above, served from a single process (no CORS setup), and it
needs the frontend built once first:

```bash
pip install -e ".[api]"
cd webapp/glacierwatch && npm install && npm run build && cd -
python server_glacierwatch.py          # -> http://localhost:8000
```

Requires Node 20+. All four projects' servers use port 8000, so run one at a
time — and if a page looks stale, check for a leftover process with
`lsof -i :8000` before assuming a code change had no effect.

See [`../../SETUP.md`](../../SETUP.md) for the full setup guide and
[`../../TESTING.md`](../../TESTING.md) for the repo-wide testing reference,
including what the offline suite does and does not verify.

