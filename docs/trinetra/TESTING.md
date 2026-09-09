# Testing Trinetra

A clean-clone walkthrough, in the same shape as the other three projects'
testing docs. Steps 1–4 need **no API key, no network and no cost**. Steps 5
onward make real model calls.

## 1. Clone and check out

```bash
git clone https://github.com/akashtalole/Agents-for-Humans-Hackathon.git
cd Agents-for-Humans-Hackathon
git checkout claude/trinetra-nashik-kumbh-2027
```

## 2. Set up a Python environment

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[api,dev]"
```

Add `a2a` if you want to exercise the Agent2Agent surface in step 8:
`pip install -e ".[api,dev,a2a]"`.

## 3. Configure model credentials (only needed from step 5 onward)

```bash
cp .env.example .env
# then edit .env and set ANTHROPIC_API_KEY=sk-ant-...
# — or, to use Bedrock instead, configure standard AWS credentials
#   (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_REGION, or an AWS
#   profile) and leave ANTHROPIC_API_KEY unset.
```

Confirm which provider will be used, without making a billable call:

```bash
trinetra status
```

## 4. Run the offline test suite (no cost, no network, no API key)

```bash
pytest tests/ -k trinetra
```

Expected: **143 passed**. Or run the whole repo's suite — 504 passed,
3 skipped.

This is the step that actually verifies the load-bearing parts of Trinetra,
because everything a safety decision rests on is deterministic code with no
model in the path:

| What | Where |
|---|---|
| Crowd simulator risk gradient, admission control, `on_tick` streaming | `test_trinetra_simulator.py` |
| Godavari evacuation feasibility, mobility mix, worst-first ordering | `test_trinetra_hydrology.py` |
| Finite-responder allocation invariants under contention | `test_trinetra_resources.py` |
| Cross-desk conflict detection (the 2003 lane, congestion, trapped egress) | `test_trinetra_conflicts.py` |
| Rumour counter-message guardrail, adversarially | `test_trinetra_rumor_guardrail.py` |
| A2A allowlist, peer-reply trust scan, provenance | `test_trinetra_a2a.py` |
| Lost-person matching (never "certain") | `test_trinetra_reunification.py` |
| SMS/USSD channel length caps | `test_trinetra_network_delivery.py` |
| FastAPI backend incl. draining a live SSE stream | `test_trinetra_api.py` |
| Orchestrator wiring with mocked agents | `test_trinetra_orchestrator_wiring.py` |

## 5. Validate the simulator against two real disasters and three controls (still free)

```bash
trinetra calibrate
```

This replays the documented conditions of the **2003 Nashik** (39 dead,
Kalaram Mandir Marg) and **2025 Prayagraj** (30 official / 82 per BBC, Sangam
Nose) crowd crushes and checks the simulator flags both CRITICAL. It needs no
credentials — the engine and the calibration are pure code.

It then runs three **synthetic controls**, and these are the half worth
watching. Two are ordinary and well-managed days the simulator must decline to
flag; the third routes that same crowd down the 1.8m Kalaram Mandir lane and
must flag. Without them the suite is a tautology — both disasters sit far above
every threshold in the model, so `return CRITICAL` would pass it outright.
`load_calibration_cases()` now refuses to run a case set with no controls, and
`test_calibration_suite_actually_fails_a_model_that_always_says_critical`
stubs exactly that model and asserts the suite fails.

A planning tool that cannot reproduce a documented disaster is not safe to plan
with, and one that alarms at everything gives a control room no way to tell a
warning from noise. A failure either way is disqualifying, not cosmetic. Expect
`✅ all cases behaved as expected`, and a non-zero exit if not.

What a pass does **not** establish: every capacity figure these cases run
against is Trinetra's own estimate, and the controls are constructed rather
than drawn from NTKMA's record. It shows the model is internally consistent and
reacts to routing in the right direction — not that the thresholds are right
for the real ghats.

## 6. Run the CLI (real API calls, real cost)

```bash
# Pilgrim assistant, in Hindi
trinetra ask "Ramkund par kitni bheed hai abhi?" --language hindi

# The emergency-detection path — this should escalate to SOS
trinetra ask "I can't move, the crowd is crushing me near Ramkund, help!" --language english

# Godavari compound flood risk. Exits non-zero when a ghat cannot be cleared.
trinetra flood-risk --discharge 22000 \
  --occupancy ramkund=8000 panchavati_godavari=5000 --elderly-share 0.4

# Rumour triage. Exits non-zero when the guardrail blocks the draft.
trinetra rumor "Ramkund pe bhagdad mach gayi hai" \
  --location "Ramkund approach" --spreading-fast

# The whole board at once, reconciled against a finite responder pool.
# Six model calls in series — budget about four minutes.
trinetra command --discharge 22000 \
  --occupancy ramkund=8000 panchavati_godavari=4800 kalaram_marg=1400 \
  --sos "Ramkund::elderly man collapsed, not breathing well" \
  --rumor "Ramkund pe bhagdad mach gayi hai" --rumor-location "Ramkund approach"
```

Each writes a deterministically-rendered Markdown report to `./output/`. Those
files are generated by code, not by a model, so they reflect the validated
structured data exactly.

## 7. Run the dashboard (real API calls, real cost)

```bash
cd webapp/trinetra && npm install && npm run build && cd ../..
python server_trinetra.py     # -> http://localhost:8000
```

Nine views: Overview, Yatri Netra (pilgrim), Prashasan Netra (admin),
Bhavishya Netra (the live-animated digital twin), Godavari Flood, Rumor Desk,
Incident Command, Agent Mesh, and Calibration. The Calibration view makes no
model call at all, so it is a free way to confirm the UI is wired correctly.

## 8. Exercise the A2A surface (optional)

```bash
pip install -e ".[a2a]"

trinetra a2a-peers                       # the allowlist — free, no model call
trinetra a2a-serve --port 9100           # publish Trinetra's own agent card
curl http://localhost:9100/.well-known/agent-card.json | python3 -m json.tool
```

The peers in `trinetra/data/a2a_peers.json` are **illustrative placeholders
pointing at localhost** — no external organisation's agent exists at those
URLs, so `trinetra a2a-ask` will report them unreachable. That path is worth
seeing: a peer being down must never take Trinetra with it.

To watch the trust scan reject a hostile peer, point one registry entry at any
local A2A-shaped endpoint that returns instruction-like text; the reply is
withheld with the exact triggering excerpt preserved for a human.

## Notes for judges

- **Step 4 is a complete, credential-free way to verify correctness.** If you
  do not have model credentials handy, `pytest tests/ -k trinetra` plus
  `trinetra calibrate` exercises every deterministic safety calculation in the
  platform.
- **`TRINETRA.md`'s "Honest limitations" section is the thing to read next.**
  It states plainly which numbers are real and cited (site geography,
  historical incidents, the Gangapur danger threshold) and which are Trinetra's
  own illustrative planning estimates (ghat capacities, flood lead times,
  egress rates, the responder pool). Nothing in that list should be quoted to
  NTKMA as authoritative without their own verification.
- **Trinetra has no live-integration gate** like the other three projects'
  `*_RUN_INTEGRATION=1` tests. Its agent layers are tested with mocked agents
  and its deterministic core offline; the live runs above are the way to
  exercise the real model path.
