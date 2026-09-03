# GlacierWatch

## Elevator Pitch
GlacierWatch combines published, cited Himalayan glacial-hazard assessments with live weather and seismic data to tell disaster management authorities which documented hazard sites deserve attention this week — it is a triage tool for prioritizing scarce monitoring resources, and it never predicts if, when, or where an avalanche or glacial lake outburst flood (GLOF) will occur.

## Inspiration
On August 26, 2026, a glacier collapse and debris flow on the Nepal-Tibet border killed over 600 people, with thousands still missing — an event so violent it registered on seismographs as a magnitude-4.4 equivalent. Nobody predicted it, including institutions with dedicated instrumentation nearby. It wasn't the first: India has already had two close analogues, Chamoli, Uttarakhand (2021) and South Lhonak Lake, Sikkim (2023), the latter killing 42 people and leaving 70+ missing despite the lake having been formally flagged as dangerous since 2019.

That history makes one thing clear: a tool that claims to *predict* the next glacial disaster would be dishonest, and worse, could give someone false confidence not to evacuate. What's real and useful is narrower. India's National Disaster Management Authority tracks only 56 glacial lakes nationally for active monitoring, out of 28,043+ glacial lakes ≥0.25 hectares catalogued across the Indian Himalayan Region — nobody can instrument all of them, so risk has to be triaged, every week, by someone. GlacierWatch is that triage step, automated: combine what's already published and documented about a site with this week's real, observed conditions, and flag which sites deserve a look right now. Honest scope, not overpromised capability, is the whole idea.

## What it does
1. **Loads** a small, cited reference watchlist of documented Himalayan glacial hazard sites.
2. **Fetches live conditions** for every active site from real, public APIs: daily precipitation from Open-Meteo, categorized on India Meteorological Department's official rainfall scale, and recent nearby seismic activity from the USGS earthquake catalog.
3. **Assesses each site**: combines the site's documented, cited risk profile with this week's real conditions into a `priority` / `elevated` / `routine` classification, grounded only in the specific facts provided — never invented detail, and never predicting an event.
4. **Drafts a weekly watchlist report**, prominently disclaimed as decision support, listing which sites need attention this week and the specific, concrete action recommended for each.

The bundled watchlist has four sites: two currently-monitored lakes (Gepang Gath and Samudra Tapu, both in Himachal Pradesh's Lahaul-Spiti, both formally assessed by India's National Remote Sensing Centre) and two historical case studies (South Lhonak, Sikkim 2023, and Chorabari, Uttarakhand 2013) used honestly, as calibration reference points for the tool's rainfall-trigger threshold — never implied to be building toward "another" failure.

## How we built it
GlacierWatch is built on the Strands Agents SDK using the same **"agents as tools"** pattern as the other two projects in this hackathon entry: an orchestrator agent (`glacierwatch/orchestrator.py`) drives two sub-agents — `risk_assessor` and `report_drafter` — by calling them as tools, alongside plain-code tools for loading the watchlist and fetching live data.

The tool layer (`glacierwatch/tools/weather.py`, `glacierwatch/tools/seismic.py`) makes real, live HTTP calls at run time — no mocking in production. `fetch_precipitation` calls Open-Meteo and buckets the result against IMD's official rainfall categories; `fetch_seismic_events` queries the USGS earthquake catalog for nearby recent activity. Both go through a shared retry helper (`glacierwatch/tools/_http.py`) for transient network failures, and both return an honest error rather than a fabricated number when a fetch genuinely fails.

The schema (`glacierwatch/models.py`) keeps two kinds of data visibly separate: `WatchSite` is static, published, cited fact that never changes at run time; `CurrentConditions` is live data pulled fresh from the APIs. `SiteRiskBrief` is the only place they combine, and only to prioritize attention, never to make a claim about causation or forecast. All of it is validated Pydantic structured output at every step — the `risk_assessor` sub-agent receives the complete `WatchSite` and `CurrentConditions` JSON in its own prompt, not a terse summary, so it has no gap to fill with invented specifics.

The trusted output — `watchlist_report.md` — is rendered deterministically from validated `SiteRiskBrief` objects by plain code (`glacierwatch/rendering.py`), never by the model, always priority-ordered, always carrying the full non-prediction disclaimer. Both the CLI and the Streamlit demo (`app_glacierwatch.py`) show this file as the headline, with the orchestrator's own free-text reply demoted to a clearly labeled, informational-only view underneath it. `glacierwatch/config.py` picks Anthropic direct or Amazon Bedrock automatically depending on available credentials.

## Challenges we ran into
- **Sourcing real, citable data instead of inventing plausible-sounding numbers.** It would have been easy to make up lake names, growth rates, and breach scenarios that read as realistic. Instead every entry in `glacierwatch/data/watchlist.json` is sourced to specific published reporting — NRSC GLOF risk assessments, peer-reviewed glacier growth measurements, and established news coverage of the 2013 Chorabari and 2023 South Lhonak failures — which took real research time and constrained the watchlist to four sites instead of dozens.
- **Real-world API flakiness.** During a live run captured for this submission, Open-Meteo returned a transient failure for one of the two active sites mid-run. The orchestrator handled it exactly as designed: it logged the failure honestly, did not fabricate a replacement value, and proceeded to assess the remaining sites correctly rather than stalling or guessing. That behavior — plus the retry helper in `glacierwatch/tools/_http.py` — exists directly because of failures like this seen during development.
- **Applying hallucination-prevention lessons from day one.** BidWright and ClaimClarity (the other two projects in this hackathon entry) each discovered the hard way that a sub-agent given only a terse tool-result summary will occasionally fabricate plausible-sounding specifics it was never actually given. GlacierWatch's `risk_assessor` was built from the start to receive full structured `WatchSite` + `CurrentConditions` JSON rather than a summary, avoiding that failure mode instead of patching it in after seeing it happen again.

## Accomplishments that we're proud of
- Every fact in the bundled watchlist is sourced to specific, checkable published reporting — nothing is estimated or invented, and the `sources` field on each entry says exactly where it came from.
- A full live run against the real Open-Meteo and USGS APIs, with a real model, worked correctly on the first try: it fetched genuine current rainfall and seismic data, correctly classified both active sites as "elevated" (high documented baseline risk, no acute trigger that week), correctly kept both historical sites at "routine," and produced an honest, non-alarmist orchestrator summary with no fabrication.
- The two historical sites (South Lhonak and Chorabari) are used strictly as calibration and reference material — the tool never implies a drained, already-failed lake is "building toward" another event, which was a deliberate, easy-to-get-wrong framing choice.
- 30+ offline tests pass with no API key or network access (HTTP calls mocked with fixtures shaped identically to real captured responses), plus an opt-in live integration test against the real APIs and a real model.

## What we learned
- Separating static/cited facts from live data at the schema level (`WatchSite` vs. `CurrentConditions`), rather than just in prose or convention, made it structurally harder for either the code or the model to blur the two — a discipline worth carrying into future agent projects.
- Scoping a tool honestly — triage, not prediction — turned out to be more defensible and arguably more useful than a more ambitious-sounding pitch would have been, especially for a domain where overclaiming has real safety consequences.
- Giving a judgment-making sub-agent the full structured data it needs, instead of a compressed summary, is a small design decision with an outsized effect on whether it invents details.
- Real external APIs fail in real, mundane ways (a single transient timeout, not a dramatic outage), and an agent pipeline needs an honest, visible way to say "this one fetch failed" rather than silently omitting or guessing.

## What's next for GlacierWatch
- Expanding the watchlist toward India's full 56-lake NDMA monitoring list, or the complete 28,043-lake NRSC inventory, if and when that underlying data becomes available in a machine-readable form — `glacierwatch/tools/watchlist.py`'s docstring already documents how to swap in a fuller source.
- Adding satellite-based glacier deformation / lake-area change monitoring as an additional live signal alongside precipitation and seismicity.
- An AgentCore deployment path, matching the one already built for BidWright and ClaimClarity in this repo (`deploy/cloudshell/`), so state disaster management authorities could run this on managed infrastructure rather than locally.
- Validating the rainfall-trigger threshold against more historical GLOF/avalanche events as documented data becomes available, rather than relying on the single Chorabari data point.

## Built With
Strands Agents SDK, Python, Anthropic Claude, Claude Sonnet 4.5, Amazon Bedrock, Pydantic, Streamlit, httpx, Open-Meteo API, USGS Earthquake API, pytest, Playwright

## Track
Good Neighbor Agents

## Architecture Diagram
See `architecture-diagram.png` in this folder. It shows the orchestrator agent calling four tools in sequence — `load_watchlist`, `fetch_current_conditions` (with real HTTP calls to Open-Meteo and USGS), `assess_site_risk` (the risk_assessor sub-agent), and `draft_watchlist_report` (the report_drafter sub-agent) — writing into a shared `WatchRun` state that produces the per-site profile files and the final `watchlist_report.md` handed back to the disaster management official.

## Testing Instructions
Full step-by-step instructions are in `TESTING.md` in this folder. Fastest path: create a Python venv, `pip install -e ".[ui,dev]"`, then run `pytest` for a no-cost, no-network offline sanity check (30+ tests), or set `ANTHROPIC_API_KEY` and run `glacierwatch run --out output` for a real end-to-end run against the live Open-Meteo/USGS APIs and a real model (a few minutes, no input files needed).

## Optional Bonus Blog Post (builder.aws)
Not required, but if pursued: must be publicly posted to builder.aws with "Agents for Humans" in the title (per the actual Devpost rules at https://agentsforhumans.devpost.com/rules).

Suggested working title: **"Agents for Humans: Why I Built a Glacier Hazard Tool That Refuses to Predict Anything"**

Outline:
- Open with the August 26, 2026 Nepal-Tibet disaster and the temptation to build a "prediction" demo — and why that would have been the wrong, and dangerous, thing to ship.
- Walk through the `WatchSite` vs. `CurrentConditions` schema split as the concrete design decision that enforces the tool's honesty at the code level, not just in the README.
- Describe the real live run: genuine Open-Meteo/USGS data, one real transient API failure handled honestly, both active sites correctly landing on "elevated" with no fabricated specifics.
- Close on the lesson carried over from this repo's other two agents (BidWright, ClaimClarity): give judgment-making sub-agents full structured data, not summaries, and scope a tool to what it can honestly support.
