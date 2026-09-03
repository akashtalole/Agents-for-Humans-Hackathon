# Screenshot session notes — what actually happened

Everything below is a genuine account of a real attempt to drive the live
Streamlit demo with Playwright against a real Anthropic model. Nothing here
is fabricated or staged, including the failure.

## Setup that worked

- `streamlit run app_claimclarity.py --server.headless true --server.port 8542`
  started cleanly and served the app (confirmed via `curl` returning `200`).
- Playwright (Chromium at `/opt/pw-browsers/chromium`) navigated to the app
  and captured the true initial state: **`01_initial_state.png`**. Sidebar,
  model status ("Anthropic API direct (claude-sonnet-4-5-20250929)"), and
  the example-claim radio button are all visible and correct.

## What failed, and why (a real, reproducible bug)

Clicking **Run ClaimClarity** crashes the app almost immediately with
`streamlit.errors.NoSessionContext`, captured genuinely in
**`02_crash_after_run_click.png`**. This is not a Playwright artifact or a
timing fluke — it reproduced identically on the very first attempt and
would reproduce for any real user clicking the button, every time.

**Root cause:** `app_claimclarity.py`'s `stream_callback` (the function
passed as `callback_handler=stream_callback` to `run_claim_case`, used to
show a live tool-call log) calls Streamlit UI methods directly:

```python
def stream_callback(**kwargs):
    ...
    log_container.code("\n".join(log_lines), language=None)   # app_claimclarity.py:58
```

Strands' synchronous agent invocation, however, always executes the agent
(and therefore always invokes any `callback_handler`) from inside a brand
new thread, unconditionally — see `strands/_async.py`:

```python
def run_async(async_func):
    ...
    with ThreadPoolExecutor() as executor:
        context = contextvars.copy_context()
        future = executor.submit(context.run, execute)
        return future.result()
```

That worker thread never receives Streamlit's `ScriptRunContext` (Streamlit
attaches that context per-thread, and only to threads it creates itself or
that are explicitly registered via `streamlit.runtime.scriptrunner.
add_script_run_ctx`). So the moment the callback tries to touch `st.*`
(here, `log_container.code(...)`) from that worker thread, Streamlit raises
`NoSessionContext` and the exception propagates all the way back through
`run_async` → `run_claim_case` → the Streamlit script, aborting the whole
run. The two screenshots (`02_crash_after_run_click.png` and what would
have been `03_decisions_needed.png`) are byte-identical for this reason —
the crash happens on essentially the very first tool-call callback, before
any spinner or later state is ever reached.

Confirming this is structural rather than incidental: the CLI run (see
below) hit the exact same underlying pattern — Strands' `ThreadPoolExecutor`
+ `asyncio.run()` bridge tears down its event loop after each synchronous
call, and background `httpx` client cleanup logged
`RuntimeError('Event loop is closed')` on exit (harmless there, because the
CLI's callback only prints to stdout — it never touches a UI object tied to
a specific thread/session the way Streamlit's does).

**What would fix it** (not done here — out of scope: this worktree may only
touch `docs/claimclarity/`): either (a) stop touching `st.*` objects inside
`stream_callback` — accumulate `log_lines` in a plain list/queue during the
run and render them with `st.code(...)` from the main script thread only
*after* `run_claim_case()` returns, or (b) explicitly propagate Streamlit's
context into the worker thread Strands spawns, e.g. by capturing
`streamlit.runtime.scriptrunner.get_script_run_ctx()` before the call and
calling `add_script_run_ctx(thread, ctx)` on the thread `ThreadPoolExecutor`
creates (harder, since `run_async` creates that thread internally and
doesn't expose a hook for it). Option (a) is the simpler, safer fix.

## What we did instead, to still ground the rest of the deliverables in a genuine live run

Since the Streamlit UI's results tabs were unreachable through no fault of
the underlying agent pipeline, we ran the **CLI** — a separate code path
unaffected by this UI-only bug — against the same bundled example, for
real, with a real `ANTHROPIC_API_KEY`:

```
claimclarity run \
  --document examples/claimclarity/denial_notice.md \
  --document examples/claimclarity/plan_summary_of_benefits.md \
  --document examples/claimclarity/medical_record_excerpt.md \
  --out output
```

This completed successfully end to end and, as expected from
`CLAIMCLARITY.md`, correctly told the two denied line items apart:

- **97110 (therapeutic exercise), billed with M54.5** → classified
  `billing_error`, worth appealing, corrected code `M54.51`
  ("Vertebrogenic low back pain") — the investigator's tool trace shows it
  really called `lookup_icd10_code` (confirming M54.5 is a non-billable
  category header retired in FY2022) and then `search_icd10_codes` to find
  the correct specific code, before concluding anything.
- **97124 (massage therapy), billed with M54.5** → classified
  `valid_denial`, not worth appealing — a genuine plan exclusion regardless
  of diagnosis code.

All five output files (`claim_summary.md`, `denial_findings.md`,
`decisions_needed.md`, `appeal_package.md`, `appeal_deadline.ics`) were
generated correctly. This is the same real, live-model behavior described
in `CLAIMCLARITY.md`'s "Honest limitations" section — reconfirmed here on a
fresh run — and is what grounds the specifics used in
`DEVPOST_SUBMISSION.md` and `TESTING.md` in this folder.

## Bottom line

- `01_initial_state.png` — genuine, successful.
- `02_crash_after_run_click.png` — genuine, and a real bug worth fixing in
  `app_claimclarity.py` (see root cause above), not a demo artifact.
- No `03_decisions_needed.png` or `04_appeal_package.png` were produced,
  because the UI never reached those states in this environment or in any
  environment, as shipped. We did not fabricate them. The underlying
  pipeline output they would have displayed is genuine and is quoted above
  and used to ground the other submission documents.
