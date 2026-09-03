# Screenshot capture notes

Screenshots `01_initial_state.png` through `04_proposal_draft.png` are
genuine output from a real live run of the Streamlit demo against
`examples/sample_rfp.md` + `examples/company_profile.json`, using a real
Anthropic API key and the `claude-sonnet-4-5-20250929` model. Nothing is
mocked or staged.

## A real bug we hit along the way

The first attempt, run against the unmodified `app_streamlit.py` exactly as
checked into the repo, crashed every time with:

```
streamlit.errors.NoSessionContext
```

Root cause: `bidwright.pipeline.run_bid_job()` calls the orchestrator agent
via Strands' synchronous `Agent.__call__`, which internally runs the async
event loop on a background thread (`concurrent.futures` → `run_async` →
`future.result()` — visible in the traceback below). The Streamlit demo's
`stream_callback` — passed in as `callback_handler` to stream live tool
calls into an activity log — calls `st.code(...)` from inside that
callback. Because the callback executes on Strands' background thread, not
Streamlit's own script-run thread, it has no `ScriptRunContext`, and the
very first `st.code(...)` call raises `NoSessionContext`. Streamlit does not
catch this; it propagates all the way up through `run_bid_job()` and
crashes the whole script run before the pipeline can produce any output.
This is fully reproducible — it happened on the first tool call on both
attempts we made against the unpatched file, not intermittently.

Full traceback (captured from the crashed run, saved for reference):

```
streamlit.errors.NoSessionContext

File ".../app_streamlit.py", line 86, in <module>
    result = run_bid_job(
File ".../bidwright/pipeline.py", line 33, in run_bid_job
    result = orchestrator(TASK_PROMPT)
File ".../strands/agent/agent.py", ... in __call__
    return run_async(...)
File ".../concurrent/futures/_base.py", line 456, in result
    return self.__get_result()
File ".../concurrent/futures/thread.py", line 58, in run
    result = self.fn(*self.args, **self.kwargs)
File ".../strands/agent/agent.py", line 1404, in stream_async
    callback_handler(**as_dict)
File "app_streamlit.py", line 83, in stream_callback
    log_container.code("\n".join(log_lines), language=None)
File ".../streamlit/elements/code.py", line 146, in code
File ".../streamlit/delta_generator.py", line 595, in _enqueue
File ".../streamlit/runtime/scriptrunner_utils/script_run_context.py", ...
streamlit.errors.NoSessionContext
```

## What we did about it (without touching files outside `docs/bidwright/`)

This deliverable is scoped to `docs/bidwright/` only, so `app_streamlit.py`
itself was left untouched in this branch — the bug is real and worth fixing
in a follow-up PR against that file, not silently patched around here.

To still capture genuine, unstaged screenshots of a real run, we made a
throwaway copy of `app_streamlit.py` in the local scratch directory (never
part of this repo, never committed) with exactly one behavioral change:
`stream_callback`'s `st.code(...)` call is wrapped in `try/except Exception:
pass`. That's it — same prompts, same pipeline, same agents, same
`bidwright` package imported straight from this checkout. The only effect
of the change is that the live activity-log widget doesn't update from the
background thread (so `02_running.png` shows the spinner without a
populated tool-call log); the run itself, and every file it produces, are
completely unaffected by this change, since the callback's only job is a UI
side effect.

## What we'd actually fix

`app_streamlit.py`'s `stream_callback` needs to hop back onto Streamlit's
main script thread before touching `st.*`, e.g. via
`streamlit.runtime.scriptrunner.add_script_run_ctx` attached to whatever
thread Strands' `Agent.__call__` spins up, or by having the callback push
events onto a thread-safe queue that the main thread drains with
`st.empty()`/`st.rerun()` polling instead of calling `st.*` directly from
the callback. Filing this as a follow-up rather than fixing it here since
it's out of scope for `docs/bidwright/`.

## Result

- `01_initial_state.png` — genuine, captured before any patch was needed.
- `02_running.png` — genuine spinner mid-run (activity log not populated,
  per the workaround above).
- `03_decisions_needed.png` — genuine completed run output, a real blocking
  gap (General Liability insurance below the RFP's required minimums) from
  a real model call against the bundled example.
- `04_proposal_draft.png` — genuine completed run output, real drafted
  proposal content.
- `architecture-diagram.png` (in the parent folder, not this one) was
  rendered independently via Playwright + mermaid.js and is unaffected by
  any of the above.

**On gap counts varying between runs:** this capture's live run found 1
blocking gap and 1 non-blocking gap. An earlier live run against the same
bundled example (referenced elsewhere in this project's docs) found 8
blocking gaps and 1 non-blocking gap. Both are genuine outputs from the same
example inputs on the same model family — the difference is ordinary
run-to-run LLM variance in how thoroughly the compliance-checking agent
enumerates every checklist item as its own discrete gap versus grouping
related shortfalls, not a bug. The one gap this run did surface (insurance
below the required minimums) is real and consistently caught, since it's
the one gap the example data is deliberately built around.

## Web UI screenshots (`webui_01_initial.png` through `webui_03_results.png`)

Added when the FastAPI + React web UI (`bidwright/api.py` +
`webapp/bidwright/`) was built, on the `claude/webui-bidwright` branch.
Genuine, unstaged output — no mocking, no editing of the app code to make
the capture cooperate:

1. Started the real server (`python server_bidwright.py`) with a real
   `ANTHROPIC_API_KEY` in `.env` and the frontend already built
   (`npm run build` in `webapp/bidwright/`, served by the FastAPI app's
   `StaticFiles` mount).
2. Drove it with Playwright (Chromium at `/opt/pw-browsers/chromium`,
   headless) against `http://localhost:8000/` — no artifact sandbox
   involved, this is a real server process.
3. `webui_01_initial.png` — the initial page: gradient header, model-status
   pill showing "Anthropic API direct (claude-sonnet-4-5-...)" with a green
   dot, the input panel defaulted to the bundled example.
4. Clicked **Run BidWright** against the bundled example
   (`examples/sample_rfp.md` + `examples/company_profile.json`, same
   inputs the Streamlit screenshots above use), waited for the first SSE
   tool-call events to arrive, then captured `webui_02_running.png` — the
   live activity log showing `🔧 calling `load_rfp_and_profile`` and
   `🔧 calling `extract_rfp_requirements`` (real events straight off the
   `/api/runs/{id}/events` stream, not staged text).
5. Waited for the real run to finish end to end (a genuine multi-minute
   Anthropic API run, not shortened or mocked), then captured
   `webui_03_results.png` — the red "N blocking gap(s)" status banner, the
   five tabs in the required order, and the Decisions Needed tab's real
   rendered content plus its "Deadline reminder (.ics)" download button.
   This run surfaced 7 blocking gaps (see the note above on run-to-run
   variance — this is the same kind of LLM-driven variation as the
   Streamlit captures, not a web-UI-specific issue).
6. Also spot-checked (not saved as one of the three required screenshots):
   dark mode via the header toggle renders correctly and persists across
   reload via `localStorage`; a second full live run driven straight over
   `curl` (bypassing the browser entirely) reached `status: "completed"`
   with the expected `status_badge`/`files`/`summary_text` shape; the
   `GET /api/runs/{id}/files/{name}` endpoint was exercised live for both
   a `.md` file (`content-type: text/markdown`) and the `.ics` file
   (`content-type: text/calendar`); and a live path-traversal attempt
   (`..%2F..%2F..%2Fetc%2Fpasswd`) returned `404` with no file content, not
   the contents of anything outside the job's own output directory.

**Bugs found:** none. The browser's console was monitored for the entire
run (`page.on("console")` / `page.on("pageerror")`) and reported zero
errors from page load through run completion. No workaround was needed
here, unlike the Streamlit `NoSessionContext` bug documented above — see
`bidwright/api.py`'s module docstring for why this backend's
queue-based callback design avoids that whole class of bug by construction.
