# Trinetra (त्रिनेत्र)

**A three-eyed agent platform for the Nashik-Trimbakeshwar Kumbh Mela 2027 — built with the [Strands Agents SDK](https://strandsagents.com).**

*Trinetra* means "the three-eyed one" — the literal meaning of **Trimbakeshwar**, the jyotirlinga this Kumbh Mela centers on. Three eyes, three pillars, one platform:

| Eye | Pillar | Serves |
|---|---|---|
| **Yatri Netra** (यात्री नेत्र) | Pilgrim assistance | Pilgrims — multilingual guidance, crowd advisories, SOS |
| **Prashasan Netra** (प्रशासन नेत्र) | Administration command | NTKMA / NMC control-room operators |
| **Bhavishya Netra** (भविष्य नेत्र) | Foresight simulator | NTKMA planning — a crowd digital-twin to stress-test crowd-control strategies *before* the event, not just monitor during it |

## Read this first: an honest note on prior art

**Trinetra is not the first project to propose "an AI agent for every pilgrim" at Nashik 2027.** [KumbhDoot](https://www.kumbhdoot.org/) already exists as exactly that — a real, Maharashtra Government-backed initiative conceived by Ramesh Raskar (MIT Media Lab) and Project NANDA, inaugurated by CM Devendra Fadnavis, hosted under [Kumbhathon](https://kumbhathon.com/kumbh-doot/). NTKMA has separately approved budget for AI-driven crowd monitoring and a ghat-density app. If you're reading this to pitch to NTKMA or NMC, **say so** — pretending this space is empty would undermine the pitch, not strengthen it.

What Trinetra adds that our research did not find already built:

1. **Bhavishya Netra — a multi-agent crowd digital-twin for pre-event planning.** KumbhDoot's public materials center on the per-pilgrim concierge experience. We found nothing resembling a simulator NTKMA could use to stress-test a crowd-control plan against a modeled surge *before* committing to it operationally. This is Trinetra's flagship differentiator, and it's calibrated against two real, documented disasters (below) — not just internally consistent numbers.
2. **A from-scratch, openly-documented reference implementation** of the pilgrim/administration agent pattern, released under this repo's MIT license, in case that's useful alongside or independent of KumbhDoot's own build.
3. **Explicit network-resilience design** for SMS/USSD/offline-queue delivery, not just an app assuming a live data connection — see below.

Trinetra is offered as **complementary infrastructure and an open reference implementation**, not a replacement pitch for KumbhDoot's own mandate.

## The problem, grounded in what actually happened

- **August 27, 2003, Nashik.** A barricade at a gully near Kalaram Mandir collapsed under crowd pressure as sadhus threw coins toward devotees. 39 dead, ~150 injured, on lanes narrower than 6 feet. ([Al Jazeera](https://www.aljazeera.com/news/2003/8/27/indian-stampede-leaves-39-dead))
- **January 29, 2025, Prayagraj.** Pre-dawn barricades broke under crowd pressure during the Mauni Amavasya Amrit Snan at the Sangam Nose. 30 officially confirmed dead (a BBC investigation found at least 82); 60+ injured. ([CBS News](https://www.cbsnews.com/news/india-crowd-stampede-kumbh-mela-hindu-festival-deaths-2025/))
- **The scale, 2027.** Nashik-Trimbakeshwar Simhastha 2027 runs roughly October 2026 through 2027's core bathing months, expecting tens of millions of pilgrims over the cycle. NTKMA's Technical Advisory Committee has reviewed crowd-management, surveillance, and disaster-risk-reduction plans, with budget approved for AI-driven crowd monitoring at Ramkund and Kushavarta.

Two disasters, 22 years apart, at two different Kumbh sites, with the same root pattern: **a barricade failing under crowd pressure at a physically narrow point, during the single most crowded window of the event.** A planning tool that can't correctly flag both of these as high-risk isn't worth deploying — see Bhavishya Netra's calibration approach below.

## Who it's for

- **Pilgrims** — logistics, ghat crowd status, and safety, in their own language, on whatever device/connection they actually have (Yatri Netra).
- **NTKMA / NMC control-room operators** — live crowd-signal interpretation and proportionate intervention recommendations, always with a human making the final call (Prashasan Netra).
- **NTKMA planning teams** — a simulator to stress-test crowd-control strategies against modeled surge scenarios weeks or months before the actual event (Bhavishya Netra).

**Honestly out of scope for this build**, named rather than silently skipped: vendor/volunteer-facing agents, and a dedicated NMC municipal-services agent (sanitation, waste, water). The architecture (Strands "agents as tools", the same Pydantic-validated hand-off discipline) extends cleanly to both — they weren't built in this pass because the pilgrim/admin/simulator triad is the strongest, most differentiated slice to prove out first.

## What it does, end to end

### Yatri Netra — the pilgrim assistant (Yatri Sahayak)

Answers a pilgrim's question in their own language (Hindi, Marathi, English, Gujarati, Bhojpuri, Tamil, Telugu, Kannada, or Bengali — a short, honest list, not an unverifiable "20+ languages" claim), grounded only in Trinetra's bundled, cited site data. It never invents a ghat, distance, or crowd status it wasn't given, and it actively watches for a described emergency (a crush, a missing child, a medical issue) inside an ordinary-sounding question and escalates it — see the live example below.

```bash
trinetra ask "Ramkund par kitni bheed hai abhi?" --language hindi
trinetra ask "I can't move, the crowd is crushing me near Ramkund, help!" --language english
```

The second query, run live against the real Anthropic API while building this: the agent correctly classified it as an emergency, gave sound crowd-crush safety guidance (stay upright, don't push, signal for help — never "run"), escalated to SOS, and cited the *real* documented fact that the Kalaram Marg approach near Ramkund is only 1.8m wide where the 2003 stampede happened — pulled from the bundled site data, not invented.

### Prashasan Netra — administration command (Prashasan Command)

Reads current crowd signals (occupancy, inflow, outflow) per ghat and recommends a specific, proportionate intervention — `route_diversion`, `gate_closure`, `capacity_throttle`, `deploy_personnel`, or `public_advisory` — with a rationale citing the actual numbers. **Every recommendation goes to a human operator; Trinetra never auto-executes a gate closure or dispatch.** In this build, crowd signals are synthetic (see Honest limitations) — a real deployment wires this to NTKMA's own CCTV/footfall-counter feed without changing anything downstream of the `CrowdSignal` contract.

### Bhavishya Netra — the crowd digital-twin simulator

This is the flagship piece. Two layers, deliberately separated:

1. **A deterministic crowd-dynamics engine** (`trinetra/tools/simulator.py`, pure code, no LLM) — a tick-by-tick occupancy simulation per ghat, using each ghat's real documented `safe_capacity`, `access_points`, and `narrowest_approach_m`, and each route's `capacity_per_minute` as the actual constraints. This is exactly the kind of thing that should be computed, not judged by a model — see the module's own docstring for why.
2. **An LLM advisor** (`trinetra/agents/foresight_advisor.py`) that *interprets* a finished simulation report into specific recommendations and a plain-language narrative for a control-room operator — it never recomputes or restates the numbers themselves.

**Calibrated against the two real disasters above, not just internally consistent.** `trinetra calibrate` replays the documented conditions of both the 2003 Nashik and 2025 Prayagraj incidents and checks whether the simulator correctly comes back CRITICAL for both:

```
$ trinetra calibrate
# Bhavishya Netra Calibration Against Real Historical Incidents
**Result: ✅ all cases correctly flagged**

## ✅ Nashik Kumbh stampede, Kalaram Mandir
- Real-world deaths: 39
- Simulated peak risk: CRITICAL

## ✅ Prayagraj Maha Kumbh stampede, Sangam Nose
- Real-world deaths: 30
- Simulated peak risk: CRITICAL
```

A genuine negative control matters just as much: a routine-demand scenario against the same sites and code correctly comes back ROUTINE, not CRITICAL by default — the simulator discriminates, it doesn't just always alarm. And a real live run (see below) against a hypothetical Mauni-Amavasya-scale scenario on Nashik's own Kalaram Marg/Ramkund/Kushavarta produced a genuinely useful, specific advisory: gate closure at the 1.8m Kalaram Marg lane within 0 minutes, route diversion at Ramkund within 5, personnel deployment at Kushavarta within 3 — each tied to the actual modeled occupancy percentage, not a generic warning.

```bash
trinetra simulate --name "Mauni Amavasya equivalent" --pilgrims 3000000 --duration 300 \
  --peak-multiplier 3.5 --ghats ramkund kalaram_marg kushavarta
```

**How the hybrid design was chosen, honestly:** simulating each of millions of individual pilgrims via a separate LLM call would be both unaffordable and unnecessary — crowd occupancy over time is exactly the kind of thing that should be computed. A pure LLM-narrative simulator with no underlying dynamics model would be unfalsifiable and impossible to calibrate against a real incident. The hybrid — deterministic core, LLM interpretation layer — is what lets `trinetra calibrate` mean anything at all.

### Kumbh Rakshak — safety triage and reunification (shared by both personas)

One SOS-triage agent, not two different opinions depending on which persona is asking. Classifies severity, gives a concrete 60-second action, and routes to a specific responder type. Lost-person matching (`trinetra/tools/reunification.py`) is deliberately **pure code, never an LLM** — a false "match" sends a stressed family to the wrong person, and the module's confidence levels are always `strong` or `possible`, never `certain`; a human always confirms a match in person before anyone is told their family member has been found.

## Network-resilience design

A 30-50 million person event puts enormous strain on cellular networks — the honest assumption for this platform is that **not every pilgrim has a working smartphone data connection at every moment.** `trinetra/models.py`'s `NetworkMode` enum and `trinetra/tools/network_delivery.py` implement this as a first-class design axis, not an afterthought:

- **SMS** — every pilgrim-facing response is hard-capped to 160 characters (single GSM-7 segment), with emergencies prefixed `EMERGENCY:`.
- **USSD** — capped to ~180 characters for a menu-style session.
- **Offline-queued** — a response generated while offline is clearly labeled as possibly stale once the device reconnects.
- **Kiosk / online app** — the full structured response (route, crowd advisory, safety note).

The underlying agent judgment is generated **once**, regardless of channel — a pilgrim on SMS and a pilgrim on the full app get the same underlying answer, just formatted for what their device/connection can actually carry.

**Honest limitation, stated plainly:** this module formats text correctly for each channel's constraints. It does **not** send an SMS or serve a live USSD session — that requires a contracted telecom aggregator (an SMS gateway API key) this project has no access to and cannot fabricate. A real deployment wires the strings this module already produces into that gateway's send API; nothing about the rest of the architecture needs to change.

## Architecture

```
                         ┌─────────────────────────┐
                         │   Trinetra Orchestrator   │
                         │  (agents-as-tools router) │
                         └───────────┬───────────────┘
              ┌────────────────────┼────────────────────────┐
              │                    │                         │
     ┌────────▼────────┐ ┌─────────▼─────────┐  ┌────────────▼────────────┐
     │  Yatri Sahayak   │ │   Kumbh Rakshak    │  │   Prashasan Command      │
     │ (pilgrim agent)  │ │ (safety/SOS agent) │  │   (admin agent)          │
     └────────┬─────────┘ └─────────┬──────────┘  └────────────┬─────────────┘
              │                     │                            │
              │        ┌────────────▼────────────┐               │
              │        │  reunification.py         │              │
              │        │  (pure-code matching)      │              │
              │        └────────────────────────────┘              │
              │                                                     │
     ┌────────▼─────────────────────────────────────────────────────▼────────┐
     │                      Bundled site data (sites.json)                    │
     │            real, cited Ramkund / Kushavarta / Kalaram Marg / ...       │
     └─────────────────────────────────────────────────────────────────────┘

     ┌───────────────────────────────────────────────────────────────────┐
     │                     Bhavishya Netra (separate flow)                  │
     │  simulator.py (deterministic engine)  →  foresight_advisor.py (LLM)  │
     │              validated against calibration_cases.json                │
     └───────────────────────────────────────────────────────────────────┘
```

Same discipline as BidWright/ClaimClarity/GlacierWatch elsewhere in this repo: every agent hand-off is a validated Pydantic model (`trinetra/models.py`), deterministic renderers (`trinetra/rendering.py`) — never an LLM — produce the file a human actually reads, and the model-provider selection (`trinetra/config.py`) supports both direct Anthropic and Amazon Bedrock.

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill in ANTHROPIC_API_KEY, or configure AWS credentials for Bedrock

trinetra status                    # confirm model provider
trinetra calibrate                 # validate the simulator against real disasters (no API key needed for the deterministic core)
trinetra ask "Kushavarta ghat kaise pahunche?" --language hindi
trinetra sos "lost my father near Ramkund" --location Ramkund --incident-type lost_person
trinetra simulate --name "test" --pilgrims 500000 --duration 180 --ghats ramkund kushavarta
```

## Testing

`pytest tests/test_trinetra_*.py` — 24 offline tests, no API key required: the simulator's risk gradient (routine → elevated → critical), the admission-control cap that keeps extreme-demand scenarios from producing nonsensical percentages, both real-disaster calibration cases, lost-person matching (strong/possible/no-match, never "certain"), SMS/USSD channel-length enforcement, and orchestrator wiring with mocked agents. All pass; see the repo root's full suite for the other three projects alongside it.

## Honest limitations

- **Crowd signals are synthetic, not live.** No public NTKMA sensor/CCTV API exists for this project to integrate with. `CrowdSignal` is a stable contract a real feed can be wired into without changing Prashasan Command's logic.
- **SMS/USSD delivery is formatted, not sent.** See the network-resilience section above — no telecom gateway integration exists or is claimed.
- **Simulation demand-distribution is a simplifying assumption.** Total pilgrim demand is split evenly across a scenario's active ghats; a real deployment should weight this by NTKMA's own historical footfall-distribution data.
- **Ghat/route capacity figures are Trinetra's own illustrative planning estimates**, not official NTKMA-surveyed numbers — see `trinetra/data/sites.json`'s own citation note. Site *names, locations, and historical incident facts* are real and cited; the numeric capacities are not, and must never be presented to NTKMA as authoritative without their own verification.
- **Lost-person matching is exact/near-exact, not semantic.** Two genuinely matching descriptions phrased very differently may not surface as a "possible" match — a deliberate, documented trade-off against false reunification matches, not an oversight.
- **The calibration set is two cases.** Both are real and well-documented, but two data points is not a robust validation suite — a real deployment should calibrate against every documented Kumbh/mass-gathering crowd-crush incident available, not just these two.
- **Vendor/volunteer/NMC-municipal personas are not built** in this pass — see "Who it's for" above for why and how the architecture extends to them.

## Deploying to AWS

See `deploy/trinetra/README.md` for the CloudShell/AgentCore deployment path, following the same pattern as BidWright's and ClaimClarity's `deploy/cloudshell/` scripts.
