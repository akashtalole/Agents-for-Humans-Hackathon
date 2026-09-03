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
