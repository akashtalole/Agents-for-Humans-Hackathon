# GlacierWatch

**Combines published, cited Himalayan glacial-hazard assessments with live weather and seismic data to prioritize monitoring attention — never a prediction of if, when, or where an avalanche or glacial lake outburst flood (GLOF) will occur.**

Built with the [Strands Agents SDK](https://strandsagents.com) for the Agents for Humans Hackathon — **Good Neighbor Agents** track.

## Why this, and why framed this way

On August 26, 2026, a glacier collapse and debris flow on the Nepal-Tibet border killed over 600 people, with thousands still missing — an event so violent it registered on seismographs as a magnitude-4.4 equivalent. It wasn't predicted. India has had the same kind of event twice already: [Chamoli, Uttarakhand (2021)](https://en.wikipedia.org/wiki/2021_Uttarakhand_flood) and [South Lhonak Lake, Sikkim (2023)](https://www.downtoearth.org.in/climate-change/the-2023-sikkim-disaster-exposes-growing-risk-of-glofs-in-a-warming-himalaya), which killed 42 and left 70+ missing despite the lake having been formally flagged as dangerous since 2019.

A tool that claims to predict the next one would be dishonest, and worse, could give someone false confidence not to evacuate. What's real and useful is narrower: India's National Disaster Management Authority tracks 56 glacial lakes nationally for monitoring, out of [28,043 glacial lakes ≥0.25 hectares](https://www.downtoearth.org.in/climate-change/the-2023-sikkim-disaster-exposes-growing-risk-of-glofs-in-a-warming-himalaya) catalogued across the Indian Himalayan Region — nobody can instrument all of them, so risk has to be triaged. GlacierWatch is exactly that triage step, automated: combine what's already published and documented about a site with this week's real, observed conditions, and flag which sites deserve a look right now.

## Who it's for

State disaster management authorities, and village-level disaster committees in Himalayan districts, who need to decide where to point limited field-inspection and monitoring resources this week — not a replacement for the glaciologists and geotechnical engineers who make the actual call.

## What it does, end to end

1. **Loads** a small, cited reference watchlist of documented Himalayan glacial hazard sites (see [Honest limitations](#honest-limitations) on why this list is small).
2. **Fetches live conditions** for every active site from real, public APIs: daily precipitation from [Open-Meteo](https://open-meteo.com), categorized on India Meteorological Department's official rainfall scale, and recent nearby seismic activity from the [USGS earthquake catalog](https://earthquake.usgs.gov).
3. **Assesses each site**: combines the site's documented, cited risk profile with this week's real conditions into a `priority` / `elevated` / `routine` classification, grounded only in the specific facts provided — never invented detail, and never predicting an event.
4. **Drafts a weekly watchlist report**, prominently disclaimed as decision support, listing which sites need attention this week and the specific, concrete action recommended for each.

Run it against the bundled reference sites — two currently-monitored lakes (Gepang Gath and Samudra Tapu, both in Himachal Pradesh's Lahaul-Spiti, both formally assessed by India's National Remote Sensing Centre) and two historical case studies (South Lhonak, Sikkim and Chorabari, Uttarakhand) used to ground the tool's rainfall-trigger threshold in a real, documented failure. See **Quickstart** below.

## Downstream Exposure & Community Alert Bulletins

`watchlist_report.md` is written for officials who already know what a moraine dam or an "extremely heavy rainfall" flag means. It says nothing about who is actually downstream of a flagged site, or how to tell them - which is exactly the gap that turned a formally-identified, monitored hazard into 42 deaths at South Lhonak in 2023: the lake was known, but the early-warning system that was supposed to reach people downstream lost power at the critical moment. Good triage that never reaches a village committee doesn't save anyone. This feature is the pipeline's fifth step, closing that gap:

5. **Drafts a Community Alert Bulletin** for every site assessed at `priority` level this week (only priority sites - `elevated` and `routine` sites don't get one), written in plain language for a village-level committee rather than officials, listing the specific downstream settlements potentially exposed, concrete actions the committee itself can take (never an evacuation order - that's not this tool's authority), and a short public-notice text in English plus, where a confident translation is possible, in the local language (Hindi or Nepali, Devanagari script).

This draws on a new bundled reference file, `glacierwatch/data/downstream_exposure.json`, listing plausible downstream settlements per site with approximate distance and a coarse population-exposure *band* (e.g. "small hamlet <500") - deliberately never a precise headcount. **Be clear-eyed about this file's authority: unlike `watchlist.json`, most of its settlement/population entries are illustrative placeholders for this demo, not verified data**, and its `data_caveat` field says so explicitly. The one exception is Sissu village near Gepang Gath Lake, whose exposure (reachable in ~21 minutes of a breach) is directly sourced to the same NRSC/press modeling cited in `watchlist.json`. A real deployment of this feature must replace the illustrative entries with verified settlement and population data from the relevant state disaster management authority and national census - never hand a village committee a bulletin built on invented population figures.

Every bulletin carries the same non-prediction disclaimer as the rest of this project, and the drafting sub-agent (`glacierwatch/agents/alert_drafter.py`) is instructed, same as `risk_assessor.py`, to use only the data it's given - never inventing a settlement, a distance, or a population figure, and never claiming a flood or avalanche "will" happen. If a site's downstream exposure isn't documented yet, the bulletin says so plainly instead of guessing.

Outputs: `community_alert_<site_id>.md` per priority site, plus `community_alerts_index.md` listing which sites got one this week (or, when zero sites are at priority level, a clear "no alerts drafted" note - the pipeline never writes empty per-site files).

## Architecture

Same proven shape as this repo's other two entries: a Strands **"agents as tools"** orchestrator, validated Pydantic structured outputs at every step, and a deterministic, code-rendered report as the trusted output.

```mermaid
flowchart TD
    U[Disaster management official] -->|run| O["Orchestrator Agent\n(glacierwatch/orchestrator.py)"]

    O -->|tool call| L[load_watchlist]
    O -->|tool call| W["fetch_current_conditions\n(per active site)"]
    O -->|tool call| A["assess_site_risk\n→ Risk Assessor Agent"]
    O -->|tool call| D["draft_watchlist_report\n→ Report Drafter Agent"]
    O -->|tool call| C["draft_community_alerts\n→ Alert Drafter Agent\n(priority sites only)"]

    W -->|real HTTP calls| API1[Open-Meteo weather API]
    W -->|real HTTP calls| API2[USGS earthquake API]
    C -->|bundled, illustrative| API3[downstream_exposure.json]

    L -->|WatchSite x4, cited| J[(Shared WatchRun state)]
    W -->|CurrentConditions, live| J
    A -->|SiteRiskBrief| J
    D -->|WatchlistReport| J
    C -->|CommunityAlertBulletin| J

    J --> F1[site_profile_*.md]
    J --> F2[site_conditions_*.md]
    J --> F3[watchlist_report.md]
    J --> F4["community_alert_*.md\n+ community_alerts_index.md"]

    O -->|plain-English summary| U
    F3 -->|priority-ordered, disclaimed| U
    F4 -->|village-committee facing| V[Downstream community]
```

Design choices worth calling out:

- **Two distinct kinds of data, kept visibly separate in the schema.** `WatchSite` is static, published, cited fact (never changes); `CurrentConditions` is live data pulled from real APIs at run time. `SiteRiskBrief` is the only place they combine, and only to prioritize attention.
- **The judgment agent gets full structured data, not a summary.** `risk_assessor` receives the complete `WatchSite` and `CurrentConditions` JSON in its own prompt - a lesson learned the hard way building this repo's other two agents, where sub-agents given only terse tool-result summaries would occasionally fabricate plausible-sounding specifics they were never actually given. See `BIDWRIGHT.md`'s and `CLAIMCLARITY.md`'s Honest Limitations sections for that story.
- **The trusted output is generated by code, not the model.** `watchlist_report.md` is built deterministically from validated `SiteRiskBrief` objects in `glacierwatch/rendering.py`, always ordered priority-first, always carrying the full non-prediction disclaimer. The orchestrator's own free-text reply is instructed to point at this file rather than reconstruct specifics from memory, and both the CLI and the Streamlit UI show the deterministic report as the headline, with the model's own reply demoted to a clearly labeled, informational-only view.
- **Real APIs, real error handling.** `fetch_precipitation` and `fetch_seismic_events` make live HTTP calls with a short retry for transient network failures, but never substitute fabricated data for a real failure - a failed fetch returns an honest error, visible in the tool result, not a silently-guessed number.
- **Model-provider agnostic**, in the same way as the other two projects — `glacierwatch/config.py` picks Anthropic direct or Amazon Bedrock automatically.

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[ui]"
cp .env.example .env   # then fill in ANTHROPIC_API_KEY (or configure AWS creds for Bedrock)
```

Run the CLI:

```bash
glacierwatch run --out output
```

This streams each tool call as it happens (including the live weather/seismic API calls), then prints the deterministic weekly watchlist report, followed by the orchestrator's own summary, and writes `site_profile_*.md`, `site_conditions_*.md`, `watchlist_report.md`, and (for any priority-level sites) `community_alert_*.md` plus `community_alerts_index.md` to `output/`.

Or run the Streamlit demo:

```bash
streamlit run app_glacierwatch.py
```

Click **Run GlacierWatch** — it shows a live agent activity log, the weekly watchlist, per-site profiles and current conditions, and a download button for the report.

Check which model provider will be used at any time with `glacierwatch status`.

## Project layout

```
glacierwatch/
  models.py                    Pydantic schemas - WatchSite (static/cited) vs
                                CurrentConditions (live) kept explicitly separate
  config.py                    Model provider selection (Anthropic direct / Bedrock)
  rendering.py                  Deterministic Markdown rendering (no LLM calls)
  data/
    watchlist.json               Bundled reference sites - every claim cited
    downstream_exposure.json     Bundled downstream settlements - illustrative, see data_caveat field
  tools/
    documents.py                 @tool save_text_file
    weather.py                   Live precipitation via Open-Meteo + IMD categorization
    seismic.py                   Live seismic activity via USGS earthquake catalog
    watchlist.py                 Loads the bundled reference data
    downstream.py                 Loads the bundled downstream-exposure data
    _http.py                      Shared retry helper for the two live API calls
  agents/
    risk_assessor.py              Sub-agent: WatchSite + CurrentConditions -> SiteRiskBrief
    report_drafter.py             Sub-agent: -> WatchlistReport
    alert_drafter.py              Sub-agent: SiteRiskBrief + settlements -> CommunityAlertBulletin
  orchestrator.py                 Orchestrator Agent (agents-as-tools) + shared WatchRun state
  pipeline.py                     run_watchlist() convenience wrapper used by CLI/UI
  cli.py                          `glacierwatch run` / `glacierwatch status`
app_glacierwatch.py              Demo UI
tests/                           Unit tests (mocked HTTP, no network) + an opt-in live-model integration test
```

## Testing

```bash
pip install -e ".[dev]"
pytest
```

All unit tests run offline - HTTP calls to Open-Meteo and USGS are mocked with fixtures shaped exactly like real captured responses, so parsing/categorization/error-handling logic is verified without network access. Orchestrator wiring tests use Strands' `agent.tool.<name>(...)` direct-call interface with the sub-agents mocked, same discipline as the other two projects. A live end-to-end test against real APIs and a real model is included but skipped by default; opt in with:

```bash
GLACIERWATCH_RUN_INTEGRATION=1 pytest tests/test_glacierwatch_pipeline_integration.py
```

## Honest limitations

- **This is a triage tool, not a forecasting system, full stop.** It cannot and does not claim to predict whether, when, or where an avalanche or GLOF will occur. Every generated report carries this disclaimer prominently; treat any output as a starting point for expert review, never as an operational decision on its own.
- **The bundled watchlist is small and illustrative, not comprehensive.** Four sites, chosen because each has genuinely citable, published data (NRSC risk assessments, peer-reviewed growth measurements, documented historical failures) - not because they're the most dangerous sites in India. Expanding this to the real 56-lake NDMA monitoring list or the full 28,043-lake NRSC inventory requires that data in a machine-readable form, which is not fully public as of this writing. `glacierwatch/tools/watchlist.py`'s docstring says how to swap in a fuller source.
- **The rainfall trigger threshold is a reasonable proxy, not a validated model.** It's set at IMD's official "extremely heavy rainfall" category (>204.4mm/24h), the same order of magnitude as the documented trigger in the 2013 Chorabari Lake failure (>315mm combined with rapid glacier melt) - but real GLOF/avalanche triggering involves glacier dynamics, permafrost, and slope mechanics this tool has no access to. A quiet week of rainfall does not mean a site is safe.
- **What's actually been verified, precisely:** every HTTP-calling tool function, the IMD rainfall categorization, the distance calculation, the rendering, and the orchestrator's tool-call plumbing are covered by offline tests using response fixtures shaped identically to real captured API responses. The full pipeline has also been run against the real Open-Meteo and USGS APIs directly during development (not just mocked). Whether the orchestrator LLM reliably sequences all tool calls unprompted, and the quality of its risk judgments with a real model in the loop, depends on model access this development environment did not always have reliably - run `GLACIERWATCH_RUN_INTEGRATION=1 pytest tests/test_glacierwatch_pipeline_integration.py` yourself before treating a specific model/prompt combination as demo-proven.
- **Every fact in `glacierwatch/data/watchlist.json` is sourced** to specific published reporting (NRSC assessments, peer-reviewed papers, established news coverage) - see the `sources` field on each entry. Nothing there is estimated or invented.
- **`glacierwatch/data/downstream_exposure.json` is explicitly the opposite of that:** demo-grade and mostly illustrative, not verified. Its `data_caveat` field says so, and most individual entries are marked "illustrative, unverified" rather than sourced. The one settlement backed by the same real published modeling as `watchlist.json` is Sissu village near Gepang Gath Lake. Before any real village committee acts on a `community_alert_*.md` bulletin, this file must be replaced with verified settlement and population data from the relevant state disaster management authority and national census - shipping placeholder population figures to a real community would be a serious harm this project takes seriously enough to flag loudly here, not just in the JSON comment.
