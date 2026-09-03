# Screenshot capture notes

## Summary

`01_initial_state.png` and `02_running.png` are genuine screenshots from a real, live run of `app_glacierwatch.py` (real Anthropic API + real Open-Meteo/USGS calls in flight). `03_weekly_watchlist.png` and `04_current_conditions.png` could not be captured: the live run in the Streamlit UI crashes with an uncaught `streamlit.errors.NoSessionContext` before it reaches the results tabs. This is a genuine, reproducible bug in `app_glacierwatch.py`'s activity-log callback — not a Playwright issue, not a headless-mode artifact, and not something specific to this sandbox. It would happen for any user clicking **Run GlacierWatch** in the current code. Per the task instructions, no results-tab screenshots were fabricated; this file explains exactly what happened instead.

Separately, the underlying pipeline (`glacierwatch/pipeline.py` → `glacierwatch/orchestrator.py`) was verified working correctly end to end via the CLI (`glacierwatch run --out output`), with real live API and model calls, during this same session — see "What was actually verified" below. The bug is isolated to the Streamlit demo's activity-log callback, not the agent pipeline itself.

## What happened, step by step

1. Started `streamlit run app_glacierwatch.py --server.headless true --server.port 8543`; the app loaded correctly (`01_initial_state.png`: disclaimer banner and sidebar visible, matches source).
2. Clicked **Run GlacierWatch**. The spinner appeared correctly (`02_running.png`).
3. `run_watchlist()` (`app_glacierwatch.py` line 61) invoked the Strands orchestrator agent with `callback_handler=stream_callback`, where `stream_callback` (lines 52-58) calls `log_container.code(...)` — a Streamlit rendering call — on every tool-call event.
4. On the very first tool-call event, this raised:
   ```
   streamlit.errors.NoSessionContext
   ```
   uncaught, halting the script. Streamlit rendered this as a red error box in place of the results (visible in the `03_weekly_watchlist.png` capture attempt — the tab bar never appeared because the script terminated before reaching that code).

## Root cause (verified by reading both libraries' source in this environment)

- Strands' `Agent.__call__` (the synchronous entry point `app_glacierwatch.py` uses) runs the actual async agent loop via `strands/_async.py`'s `run_async()`:
  ```python
  def run_async(async_func):
      ...
      with ThreadPoolExecutor() as executor:
          context = contextvars.copy_context()
          future = executor.submit(context.run, execute)
          return future.result()
  ```
  This **always** executes the agent (and therefore every `callback_handler` invocation, including every tool-call event) on a fresh `ThreadPoolExecutor` worker thread, regardless of whether a Streamlit script thread is calling it. This is unconditional, not something that only triggers under specific conditions.

- Streamlit's `get_script_run_ctx()` (`streamlit/runtime/scriptrunner_utils/script_run_context.py`) looks up the current session's context as a **plain attribute set directly on the `threading.Thread` object** (`getattr(thread, SCRIPT_RUN_CONTEXT_ATTR_NAME, None)`), not as a `contextvars.ContextVar`. Streamlit threads only get this attribute via an explicit call to `streamlit.runtime.scriptrunner.add_script_run_ctx(thread)` made *before* the thread starts.

- `ThreadPoolExecutor`'s `context.run(...)` propagates Python `contextvars` correctly into the worker thread, but Streamlit's session context is **not** a contextvar — it's a thread attribute. Strands' executor threads never have `add_script_run_ctx()` called on them, so `get_script_run_ctx()` returns `None` on that thread, and any Streamlit call made from inside `stream_callback` (which runs on that thread) hits `enqueue_message()`'s `if ctx is None: raise NoSessionContext()`.

This is a deterministic mismatch between two libraries' threading models, not a flaky or environment-specific failure. It will reproduce on any machine, headless or not, every time `Run GlacierWatch` is clicked, as long as `callback_handler` in `app_glacierwatch.py` calls a Streamlit function directly.

## What would fix it

Without touching Streamlit or Strands internals, the fix belongs in `app_glacierwatch.py`'s `stream_callback` (out of scope for this docs-only branch, noted here for whoever picks it up):

- Simplest: don't call `st.*` from inside the callback at all. Append each log line to a plain Python list (e.g. `st.session_state.log_lines`) from the callback, and render the accumulated log with `st.code(...)` from the main script thread only — either after `run_watchlist()` returns, or via a placeholder that's updated by polling `st.session_state` on a rerun.
- Alternative: explicitly propagate the session context into Strands' executor thread before it runs, e.g. by wrapping `callback_handler` so its first invocation calls `streamlit.runtime.scriptrunner.add_script_run_ctx(threading.current_thread())` before any `st.*` call on that thread. This works because `add_script_run_ctx()` has a documented "self-attach" fallback for exactly this case (attaching from inside the thread being attached to), seeding `ThreadState` directly.
- Either fix should be paired with a regression test that calls `run_watchlist(..., callback_handler=<one that touches st.*>)` inside a Streamlit `AppTest` harness, since this bug produces no failure at all when `callback_handler` is `None` or prints to stdout (as the CLI's callback does) — which is exactly why it wasn't caught by the existing test suite or by CLI-only manual testing.

## What was actually verified (genuine, live, this session)

To ground the rest of the documentation package in real output despite the UI bug, the full pipeline was run live via the CLI in this same session:

```
glacierwatch run --out <dir>
```

This made real calls to Open-Meteo and the USGS earthquake catalog, and real calls to the Anthropic API (`claude-sonnet-4-5-20250929`), and completed successfully:
- All four sites were loaded and assessed.
- One site (Samudra Tapu) hit a transient live-weather fetch failure mid-run; the orchestrator reported it honestly in its own summary ("The weather service is temporarily unavailable for one site") rather than fabricating data, and correctly proceeded to assess all four sites anyway using each site's documented profile.
- Both active-watch sites (Gepang Gath, Samudra Tapu) were correctly classified **ELEVATED** — high documented baseline risk, no acute trigger that week (max daily precipitation 4.2mm at Gepang Gath, categorized "light"; one distant M4.0 seismic event, not judged notable).
- Both historical sites (Chorabari, South Lhonak) were correctly kept **ROUTINE**, used only as calibration reference, never implied to be at risk of recurrence.
- `watchlist_report.md` was rendered deterministically and correctly, disclaimer intact.

This confirms the orchestrator, sub-agents, tool layer, and rendering — i.e. everything except the Streamlit demo's activity-log callback — work exactly as described in `GLACIERWATCH.md`.

## Environment note

Unrelated to the above: the Playwright/Chromium launch in this sandbox could not reach `cdnjs.cloudflare.com` directly (intermittent `ERR_CONNECTION_RESET` through the environment's egress proxy, confirmed via `curl -sS http://127.0.0.1:35459/__agentproxy/status` showing repeated `ws_closed_mid_exchange` relay failures across multiple unrelated hosts at the same time — a shared-proxy congestion issue, not specific to this request). This did not affect the screenshots above (the Streamlit app itself is served from `localhost`, which bypasses the proxy). It did affect the separate architecture-diagram render, which was worked around by downloading `mermaid.min.js` once via `curl` (which succeeded) and loading it from a local file instead of the CDN inside the Playwright page — `docs/glacierwatch/architecture-diagram.png` is a clean, genuine render of the real diagram from `GLACIERWATCH.md`, produced this way.
